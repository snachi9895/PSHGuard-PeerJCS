#!/usr/bin/env python3
"""Frozen adapters for the S10 one-shot exact-V2 final-test protocol.

The module is deliberately import-light.  Torch/transformers/PyG/pandas are
loaded only inside an explicitly authorized worker.  The S10-B preflight can
therefore import and test all calibration, fusion, metric, receipt, and
authorization logic without touching a test artifact or a GPU.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Sequence


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[2]
AUTH_STATUS = "AUTHORIZED_EXACT_V2_ONE_SHOT_TEST"
AUTH_VERSION = "1.0.0"
AUTH_NONCE = re.compile(r"^[a-f0-9]{64}$")
EXPECTED_ROWS = 2128
EXPECTED_MANIFEST_SHA256 = (
    "4481e03bcb932698515466a556e3ff72f30aa94d6a6e6408668c296e0d6abb1b"
)
REQUIRED_AUTH_INPUTS = (
    "graph_manifest",
    "modernbert_sequence_index",
    "modernbert_package_input_index",
    "ea4mp_grouped_inputs",
    "ea4mp_package_input_index",
    "ea4mp_input_summary",
    "ea4mp_metadata_predictions",
    "static_tool_task_index",
)
MAIN_ROWS = (
    "Bandit4Mal",
    "GuardDog",
    "OSSGadget",
    "VirusTotal (>=1 malicious engine)",
    "Cerebro",
    "EA4MP",
    "Practical HGT (ours, graph branch)",
    "ModernBERT (auxiliary sequence branch)",
    "HGT plus ModernBERT (ours)",
)


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_csv(rows: Sequence[dict[str, Any]], path: Path) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write an empty CSV: {path}")
    fields = list(rows[0])
    if any(list(row) != fields for row in rows):
        raise RuntimeError("CSV rows have inconsistent field order")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def stable_sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def apply_single_calibrator(margins: Sequence[float], fit: dict[str, Any]) -> list[float]:
    mean = float(fit["scaler_mean"])
    scale = float(fit["scaler_scale"])
    coefficient = float(fit["coefficient"])
    intercept = float(fit["intercept"])
    if not math.isfinite(scale) or scale <= 0:
        raise RuntimeError("invalid frozen scaler scale")
    return [
        stable_sigmoid(intercept + coefficient * ((float(value) - mean) / scale))
        for value in margins
    ]


def apply_fusion(
    graph_margins: Sequence[float],
    sequence_margins: Sequence[float],
    fit: dict[str, Any],
) -> list[float]:
    if len(graph_margins) != len(sequence_margins):
        raise RuntimeError("fusion input length mismatch")
    means = [float(value) for value in fit["scaler_mean"]]
    scales = [float(value) for value in fit["scaler_scale"]]
    coefficients = [float(value) for value in fit["coefficients"]]
    if len(means) != 2 or len(scales) != 2 or len(coefficients) != 2:
        raise RuntimeError("frozen fusion must have exactly two inputs")
    if any(value <= 0 or not math.isfinite(value) for value in scales):
        raise RuntimeError("invalid frozen fusion scale")
    intercept = float(fit["intercept"])
    return [
        stable_sigmoid(
            intercept
            + coefficients[0] * ((float(graph) - means[0]) / scales[0])
            + coefficients[1] * ((float(sequence) - means[1]) / scales[1])
        )
        for graph, sequence in zip(graph_margins, sequence_margins)
    ]


def _tie_aware_auc(labels: Sequence[int], scores: Sequence[float]) -> float:
    positives = sum(int(value) == 1 for value in labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        raise RuntimeError("AUROC requires both classes")
    ordered = sorted(zip(map(float, scores), map(int, labels)), key=lambda item: item[0])
    positive_rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        positive_rank_sum += average_rank * sum(label == 1 for _, label in ordered[index:end])
        index = end
    return (
        positive_rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def _average_precision(labels: Sequence[int], scores: Sequence[float]) -> float:
    positives = sum(int(value) == 1 for value in labels)
    if positives == 0:
        raise RuntimeError("AP requires at least one positive")
    ordered = sorted(zip(map(float, scores), map(int, labels)), key=lambda item: item[0], reverse=True)
    tp = 0
    fp = 0
    previous_recall = 0.0
    ap = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        group = ordered[index:end]
        tp += sum(label == 1 for _, label in group)
        fp += sum(label == 0 for _, label in group)
        recall = tp / positives
        precision = tp / (tp + fp)
        ap += (recall - previous_recall) * precision
        previous_recall = recall
        index = end
    return ap


def metric_bundle(
    labels: Sequence[int], scores: Sequence[float], threshold: float
) -> tuple[dict[str, Any], list[int]]:
    if not labels or len(labels) != len(scores):
        raise RuntimeError("metric input length mismatch or empty input")
    if any(int(value) not in (0, 1) for value in labels):
        raise RuntimeError("labels must be binary")
    predictions = [int(float(score) >= float(threshold)) for score in scores]
    tp = sum(y == 1 and p == 1 for y, p in zip(labels, predictions))
    tn = sum(y == 0 and p == 0 for y, p in zip(labels, predictions))
    fp = sum(y == 0 and p == 1 for y, p in zip(labels, predictions))
    fn = sum(y == 1 and p == 0 for y, p in zip(labels, predictions))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return (
        {
            "rows": len(labels),
            "average_precision": _average_precision(labels, scores),
            "auroc": _tie_aware_auc(labels, scores),
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "fpr": fpr,
            "accuracy": (tp + tn) / len(labels),
            "threshold": float(threshold),
            "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        },
        predictions,
    )


def metric_bundle_from_predictions(
    labels: Sequence[int], scores: Sequence[float], predictions: Sequence[int]
) -> dict[str, Any]:
    if not labels or not (len(labels) == len(scores) == len(predictions)):
        raise RuntimeError("metric input length mismatch or empty input")
    if any(int(value) not in (0, 1) for value in labels) or any(
        int(value) not in (0, 1) for value in predictions
    ):
        raise RuntimeError("labels and predictions must be binary")
    tp = sum(y == 1 and p == 1 for y, p in zip(labels, predictions))
    tn = sum(y == 0 and p == 0 for y, p in zip(labels, predictions))
    fp = sum(y == 0 and p == 1 for y, p in zip(labels, predictions))
    fn = sum(y == 1 and p == 0 for y, p in zip(labels, predictions))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "rows": len(labels),
        "average_precision": _average_precision(labels, scores),
        "auroc": _tie_aware_auc(labels, scores),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fp / (fp + tn) if fp + tn else 0.0,
        "accuracy": (tp + tn) / len(labels),
        "threshold": None,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def validate_prediction_rows(rows: Sequence[dict[str, Any]], expected_rows: int = EXPECTED_ROWS) -> None:
    if len(rows) != expected_rows:
        raise RuntimeError(f"prediction row drift: expected={expected_rows} actual={len(rows)}")
    identifiers = [str(row["sample_id"]) for row in rows]
    if any(not value for value in identifiers) or len(set(identifiers)) != expected_rows:
        raise RuntimeError("empty or duplicate prediction sample_id")
    labels = [int(row["y_true"]) for row in rows]
    if set(labels) != {0, 1}:
        raise RuntimeError("prediction population does not contain both labels")


def parse_binary_prediction(value: Any) -> int:
    """Parse the frozen native policies without assuming a shared CSV dtype."""
    if isinstance(value, bool):
        return int(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "1.0", "true", "yes", "malicious", "positive"}:
        return 1
    if normalized in {"0", "0.0", "false", "no", "benign", "negative"}:
        return 0
    raise RuntimeError(f"invalid frozen binary prediction: {value!r}")


def hierarchical_component_bootstrap(
    *,
    labels: Sequence[int],
    component_ids: Sequence[str],
    systems: dict[int, dict[str, dict[str, Sequence[Any]]]],
    replicates: int,
    random_state: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Paired seed-and-component bootstrap for the final complementarity claim.

    Each replicate samples the three training seeds with replacement and samples
    source-clone components with replacement.  The same seed draw and component
    weights are shared by fusion and both branches, so the reported differences
    are paired rather than differences between unrelated confidence intervals.
    """
    import numpy as np

    labels_array = np.asarray(labels, dtype=np.int8)
    if len(labels_array) == 0 or len(labels_array) != len(component_ids):
        raise RuntimeError("bootstrap population mismatch")
    if set(map(int, labels_array.tolist())) != {0, 1}:
        raise RuntimeError("bootstrap requires both labels")
    seeds = tuple(sorted(int(seed) for seed in systems))
    if len(seeds) != 3:
        raise RuntimeError("bootstrap requires exactly three frozen seeds")
    families = ("graph", "modernbert", "fusion")
    components = sorted(set(map(str, component_ids)))
    if not components or any(not str(value) for value in component_ids):
        raise RuntimeError("bootstrap component identity is empty")
    component_lookup = {value: index for index, value in enumerate(components)}
    codes = np.asarray([component_lookup[str(value)] for value in component_ids], dtype=np.int32)
    component_count = len(components)

    contributions: dict[int, dict[str, dict[str, np.ndarray]]] = {}
    point_metrics: dict[int, dict[str, dict[str, float]]] = {}
    for seed in seeds:
        if set(systems[seed]) != set(families):
            raise RuntimeError(f"bootstrap family drift for seed {seed}")
        contributions[seed] = {}
        point_metrics[seed] = {}
        for family in families:
            item = systems[seed][family]
            predictions = np.asarray(item["predictions"], dtype=np.int8)
            if len(predictions) != len(labels_array) or not np.isin(predictions, (0, 1)).all():
                raise RuntimeError("bootstrap prediction drift")
            masks = {
                "tp": (labels_array == 1) & (predictions == 1),
                "fp": (labels_array == 0) & (predictions == 1),
                "fn": (labels_array == 1) & (predictions == 0),
            }
            contributions[seed][family] = {
                name: np.bincount(codes, weights=mask.astype(float), minlength=component_count)
                for name, mask in masks.items()
            }
            tp = float(np.sum(masks["tp"]))
            fp = float(np.sum(masks["fp"]))
            fn = float(np.sum(masks["fn"]))
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
            point_metrics[seed][family] = {
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }

    comparisons = ("fusion_minus_graph", "fusion_minus_modernbert")
    metric_names = ("f1", "precision", "recall")
    values = {
        f"{metric}_{comparison}": np.empty(int(replicates), dtype=np.float64)
        for metric in metric_names
        for comparison in comparisons
    }
    rng = np.random.default_rng(int(random_state))
    replicate_rows: list[dict[str, Any]] = []
    uniform = np.full(component_count, 1.0 / component_count)
    for replicate in range(int(replicates)):
        sampled_seeds = rng.choice(np.asarray(seeds), size=len(seeds), replace=True)
        component_weights = rng.multinomial(component_count, uniform).astype(float)
        by_family = {family: {metric: [] for metric in metric_names} for family in families}
        for sampled_seed in sampled_seeds:
            seed = int(sampled_seed)
            for family in families:
                counts = contributions[seed][family]
                tp = float(component_weights @ counts["tp"])
                fp = float(component_weights @ counts["fp"])
                fn = float(component_weights @ counts["fn"])
                precision = tp / (tp + fp) if tp + fp else 0.0
                recall = tp / (tp + fn) if tp + fn else 0.0
                f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
                by_family[family]["precision"].append(precision)
                by_family[family]["recall"].append(recall)
                by_family[family]["f1"].append(f1)
        row: dict[str, Any] = {
            "replicate": replicate + 1,
            "sampled_seeds": ",".join(map(str, map(int, sampled_seeds))),
        }
        for metric in metric_names:
            means = {
                family: float(np.mean(by_family[family][metric])) for family in families
            }
            for comparator in ("graph", "modernbert"):
                key = f"{metric}_fusion_minus_{comparator}"
                delta = means["fusion"] - means[comparator]
                values[key][replicate] = delta
                row[key] = delta
        replicate_rows.append(row)

    def summarize(array: np.ndarray) -> dict[str, float]:
        return {
            "mean": float(np.mean(array)),
            "sample_standard_deviation": float(np.std(array, ddof=1)),
            "ci95_percentile_lower": float(np.quantile(array, 0.025)),
            "median": float(np.median(array)),
            "ci95_percentile_upper": float(np.quantile(array, 0.975)),
            "probability_gt_zero": float(np.mean(array > 0)),
        }

    point_deltas: dict[str, float] = {}
    for metric in metric_names:
        means = {
            family: float(np.mean([point_metrics[seed][family][metric] for seed in seeds]))
            for family in families
        }
        for comparator in ("graph", "modernbert"):
            point_deltas[f"{metric}_fusion_minus_{comparator}"] = (
                means["fusion"] - means[comparator]
            )
    summary = {
        "status": "PASS_PRE_REGISTERED_PAIRED_BOOTSTRAP",
        "replicates": int(replicates),
        "random_state": int(random_state),
        "seeds": list(seeds),
        "source_clone_components": component_count,
        "scheme": (
            "sample three seeds with replacement and source-clone components with "
            "replacement; share every draw across fusion and both branches"
        ),
        "primary_metric": "F1",
        "secondary_metrics": ["Precision", "Recall"],
        "point_deltas": point_deltas,
        "bootstrap": {key: summarize(array) for key, array in values.items()},
    }
    return summary, replicate_rows


def validate_authorization(
    authorization_path: Path,
    *,
    verify_input_hashes: bool,
) -> dict[str, Any]:
    if not authorization_path.is_file():
        raise RuntimeError("authorization file does not exist")
    payload = load_json(authorization_path)
    if payload.get("status") != AUTH_STATUS or payload.get("version") != AUTH_VERSION:
        raise RuntimeError("invalid exact-V2 one-shot authorization status/version")
    if payload.get("explicit_user_authorization") is not True:
        raise RuntimeError("explicit user authorization is absent")
    if not AUTH_NONCE.fullmatch(str(payload.get("nonce", ""))):
        raise RuntimeError("invalid authorization nonce")
    test = payload.get("test_contract", {})
    if (
        int(test.get("expected_rows", -1)) != EXPECTED_ROWS
        or test.get("expected_manifest_sha256") != EXPECTED_MANIFEST_SHA256
        or test.get("one_authorized_evaluation_phase") is not True
    ):
        raise RuntimeError("authorization test contract drift")
    inputs = payload.get("inputs", {})
    if set(inputs) != set(REQUIRED_AUTH_INPUTS):
        raise RuntimeError("authorization input set drift")
    if (
        inputs.get("graph_manifest", {}).get("sha256")
        != EXPECTED_MANIFEST_SHA256
    ):
        raise RuntimeError("authorized graph manifest does not match locked test contract")
    resolved: dict[str, dict[str, str]] = {}
    for name in REQUIRED_AUTH_INPUTS:
        item = inputs[name]
        path = Path(str(item.get("path", "")))
        expected_sha = str(item.get("sha256", ""))
        if not path.is_absolute() or not re.fullmatch(r"[a-f0-9]{64}", expected_sha):
            raise RuntimeError(f"invalid authorized path/hash: {name}")
        if verify_input_hashes:
            if not path.is_file():
                raise RuntimeError(f"authorized input missing: {name}")
            actual = sha256_file(path)
            if actual != expected_sha:
                raise RuntimeError(
                    f"authorized input drift: {name} expected={expected_sha} actual={actual}"
                )
        resolved[name] = {"path": str(path), "sha256": expected_sha}
    payload["resolved_inputs"] = resolved
    return payload


def receipt_payload(
    *, stage: str, input_sha256: dict[str, str], outputs: Iterable[Path]
) -> dict[str, Any]:
    output_map = {str(path): sha256_file(path) for path in outputs}
    return {
        "status": "COMPLETE",
        "stage": stage,
        "input_sha256": dict(sorted(input_sha256.items())),
        "output_sha256": dict(sorted(output_map.items())),
    }


def validate_receipt(
    receipt_path: Path, *, stage: str, input_sha256: dict[str, str]
) -> dict[str, Any] | None:
    if not receipt_path.exists():
        return None
    receipt = load_json(receipt_path)
    if (
        receipt.get("status") != "COMPLETE"
        or receipt.get("stage") != stage
        or receipt.get("input_sha256") != dict(sorted(input_sha256.items()))
    ):
        raise RuntimeError(f"incompatible completed-stage receipt: {receipt_path}")
    outputs = receipt.get("output_sha256", {})
    if not outputs:
        raise RuntimeError(f"completed-stage receipt has no outputs: {receipt_path}")
    for value, expected in outputs.items():
        path = Path(value)
        if not path.is_file() or sha256_file(path) != expected:
            raise RuntimeError(f"completed-stage output drift: {path}")
    return receipt


def _import_from_path(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def worker_hgt(args: argparse.Namespace) -> None:
    import pandas as pd
    import torch
    from torch_geometric.loader import DataLoader

    scripts = PROJECT_ROOT / "scripts/formal_training_v10c_20260612"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import train_p3_rcber_paired_hgt_v2 as p3

    manifest = Path(args.manifest).resolve()
    frame = pd.read_csv(manifest, low_memory=False)
    if len(frame) != EXPECTED_ROWS or frame["sample_id"].nunique() != EXPECTED_ROWS:
        raise RuntimeError("HGT authorized population drift")
    if set(frame["label_int"].astype(int)) != {0, 1}:
        raise RuntimeError("HGT authorized labels invalid")
    p3.install_model("practical")
    base = p3.p2trainer.base
    base.configure_architecture(int(args.seed), manifest)
    mode = "ast_event_param_context"
    schema = base.architecture.base.graph_schema(mode)
    device = torch.device(args.device)
    model = base.architecture.TypeBalancedHGTV9(64, schema, mode).to(device)
    checkpoint = torch.load(Path(args.checkpoint), map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    loader = DataLoader(
        base.FormalDataset(frame.reset_index(drop=True), mode),
        batch_size=int(args.batch_size),
        shuffle=False,
        num_workers=int(args.workers),
        pin_memory=device.type == "cuda",
    )
    output = Path(args.output).resolve()
    metrics = base.evaluate(model, loader, device, save_pred_path=output)
    atomic_json(
        {
            "status": "PASS_FROZEN_TEST_INFERENCE",
            "seed": int(args.seed),
            "checkpoint_sha256": sha256_file(Path(args.checkpoint)),
            "manifest_sha256": sha256_file(manifest),
            "predictions_sha256": sha256_file(output),
            "raw_metrics_diagnostic": metrics,
        },
        output.with_suffix(".summary.json"),
    )


def _resolve_recorded_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve()
    marker = "/pypi_dataset_cutoff20260101/"
    normalized = value.replace("\\", "/")
    if marker not in normalized:
        raise RuntimeError(f"cannot safely rebase recorded path: {value}")
    return (PROJECT_ROOT / normalized.split(marker, 1)[1]).resolve()


def worker_modernbert_cache(args: argparse.Namespace) -> None:
    import numpy as np
    from transformers import AutoTokenizer

    ea4mp_src = PROJECT_ROOT / "baselines/ea4mp/src"
    if str(ea4mp_src) not in sys.path:
        sys.path.insert(0, str(ea4mp_src))
    from ea4mp_repro.behavior_canonicalization import canonicalize_behavior_text

    sequence = read_csv(Path(args.sequence_index))
    package = {row["sample_id"]: row for row in read_csv(Path(args.package_index))}
    graph = read_csv(Path(args.graph_manifest))
    if len(sequence) != EXPECTED_ROWS or len(package) != EXPECTED_ROWS or len(graph) != EXPECTED_ROWS:
        raise RuntimeError("ModernBERT cache population drift")
    graph_by_id = {row["sample_id"]: row for row in graph}
    if len(graph_by_id) != EXPECTED_ROWS or {row["sample_id"] for row in sequence} != set(graph_by_id):
        raise RuntimeError("ModernBERT cache identity drift")
    tokenizer = AutoTokenizer.from_pretrained(Path(args.snapshot), local_files_only=True)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ids_path = output / "input_ids.npy"
    mask_path = output / "attention_mask.npy"
    labels_path = output / "labels.npy"
    ids = np.lib.format.open_memmap(ids_path.with_suffix(".npy.tmp"), mode="w+", dtype=np.int32, shape=(EXPECTED_ROWS, 512))
    mask = np.lib.format.open_memmap(mask_path.with_suffix(".npy.tmp"), mode="w+", dtype=np.uint8, shape=(EXPECTED_ROWS, 512))
    labels = np.lib.format.open_memmap(labels_path.with_suffix(".npy.tmp"), mode="w+", dtype=np.int8, shape=(EXPECTED_ROWS,))
    metadata: list[dict[str, Any]] = []
    for index, source in enumerate(sequence):
        sample_id = source["sample_id"]
        old = package[sample_id]
        graph_row = graph_by_id[sample_id]
        missing = str(old.get("behavior_missing", "False")).lower() in {"true", "1"}
        dfs = _resolve_recorded_path(source["sample_directory"]) / "dfs_output.txt"
        if dfs.is_file():
            raw = dfs.read_text(encoding="utf-8")
        elif missing and old.get("dfs_sha256") == "no_dfs_artifact":
            raw = ""
        else:
            raise RuntimeError(f"unexpected missing behavior artifact: {sample_id}")
        canonical, audit = canonicalize_behavior_text(raw, sample_id=sample_id)
        if audit.residual_sample_id_occurrences or audit.residual_raw_root_occurrences or audit.residual_source_tag_occurrences:
            raise RuntimeError(f"canonical identity residual: {sample_id}")
        encoded = tokenizer(
            "" if missing else canonical,
            add_special_tokens=True,
            truncation=True,
            max_length=512,
            padding="max_length",
            return_attention_mask=True,
            verbose=False,
        )
        ids[index] = np.asarray(encoded["input_ids"], dtype=np.int32)
        mask[index] = np.asarray(encoded["attention_mask"], dtype=np.uint8)
        labels[index] = int(graph_row["label_int"])
        metadata.append(
            {
                "row_index": index,
                "sample_id": sample_id,
                "y_true": int(graph_row["label_int"]),
                "source_group": graph_row.get("source_group", ""),
                "source_clone_component_id": graph_row.get("source_clone_component_id", ""),
            }
        )
        if (index + 1) % 500 == 0 or index + 1 == EXPECTED_ROWS:
            print(f"[S10 ModernBERT cache] {index + 1:,}/{EXPECTED_ROWS:,}", flush=True)
    ids.flush(); mask.flush(); labels.flush()
    del ids, mask, labels
    os.replace(ids_path.with_suffix(".npy.tmp"), ids_path)
    os.replace(mask_path.with_suffix(".npy.tmp"), mask_path)
    os.replace(labels_path.with_suffix(".npy.tmp"), labels_path)
    atomic_csv(metadata, output / "metadata.csv")
    atomic_json(
        {
            "status": "PASS_AUTHORIZED_CACHE",
            "rows": EXPECTED_ROWS,
            "files_sha256": {
                path.name: sha256_file(path)
                for path in (ids_path, mask_path, labels_path, output / "metadata.csv")
            },
        },
        output / "cache_summary.json",
    )


def worker_modernbert_infer(args: argparse.Namespace) -> None:
    import numpy as np
    import torch
    from transformers import AutoConfig, ModernBertForSequenceClassification

    cache = Path(args.cache_dir)
    ids = np.load(cache / "input_ids.npy", mmap_mode="r")
    mask = np.load(cache / "attention_mask.npy", mmap_mode="r")
    labels = np.load(cache / "labels.npy", mmap_mode="r")
    metadata = read_csv(cache / "metadata.csv")
    if ids.shape != (EXPECTED_ROWS, 512) or mask.shape != (EXPECTED_ROWS, 512) or len(metadata) != EXPECTED_ROWS:
        raise RuntimeError("ModernBERT cache shape drift")
    device = torch.device(args.device)
    config = AutoConfig.from_pretrained(Path(args.snapshot), local_files_only=True)
    config.num_labels = 2
    config.reference_compile = False
    config._attn_implementation = "sdpa"
    config.use_cache = False
    model = ModernBertForSequenceClassification.from_pretrained(
        Path(args.snapshot), config=config, local_files_only=True
    )
    state = torch.load(Path(args.checkpoint), map_location=device, weights_only=True)
    model.load_state_dict(state, strict=True)
    model.to(device).eval()
    margins: list[float] = []
    batch_size = int(args.batch_size)
    with torch.no_grad():
        for start in range(0, EXPECTED_ROWS, batch_size):
            end = min(start + batch_size, EXPECTED_ROWS)
            input_ids = torch.from_numpy(np.asarray(ids[start:end], dtype=np.int64)).to(device)
            attention = torch.from_numpy(np.asarray(mask[start:end], dtype=np.int64)).to(device)
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits = model(input_ids=input_ids, attention_mask=attention).logits
            values = (logits[:, 1] - logits[:, 0]).detach().float().cpu().tolist()
            margins.extend(map(float, values))
    rows = [
        {
            "sample_id": meta["sample_id"],
            "y_true": int(labels[index]),
            "logit_margin": margins[index],
        }
        for index, meta in enumerate(metadata)
    ]
    output = Path(args.output)
    atomic_csv(rows, output)
    atomic_json(
        {
            "status": "PASS_FROZEN_TEST_INFERENCE",
            "seed": int(args.seed),
            "checkpoint_sha256": sha256_file(Path(args.checkpoint)),
            "predictions_sha256": sha256_file(output),
        },
        output.with_suffix(".summary.json"),
    )


def worker_ea4mp_ensemble(args: argparse.Namespace) -> None:
    import pickle
    import numpy as np

    bert_rows = read_csv(Path(args.bert_predictions))
    metadata_rows = read_csv(Path(args.metadata_predictions))
    graph_rows = read_csv(Path(args.graph_manifest))
    canonical_order = [row["sample_id"] for row in graph_rows]
    canonical_labels = {row["sample_id"]: int(row["label_int"]) for row in graph_rows}
    if (
        len(graph_rows) != EXPECTED_ROWS
        or len(canonical_labels) != EXPECTED_ROWS
        or len(canonical_order) != len(set(canonical_order))
    ):
        raise RuntimeError("EA4MP canonical graph population drift")
    metadata = {row["sample_id"]: row for row in metadata_rows}
    bert_ids = [row["sample_id"] for row in bert_rows]
    if (
        len(bert_rows) != EXPECTED_ROWS
        or len(set(bert_ids)) != EXPECTED_ROWS
        or len(metadata_rows) != EXPECTED_ROWS
        or len(metadata) != EXPECTED_ROWS
        or set(bert_ids) != set(canonical_order)
        or set(metadata) != set(canonical_order)
    ):
        raise RuntimeError("EA4MP ensemble population drift")
    features = []
    labels = []
    sample_ids = []
    for row in bert_rows:
        peer = metadata.get(row["sample_id"])
        if peer is None:
            raise RuntimeError(f"EA4MP metadata missing sample: {row['sample_id']}")
        y = int(row["label_id"])
        peer_label = int(peer.get("label_id", peer.get("label_int", peer.get("label", -1))))
        if y != peer_label or y != canonical_labels[row["sample_id"]]:
            raise RuntimeError("EA4MP channel label drift")
        features.append(
            [float(row["logit_malicious"]), float(peer["metadata_nb_malicious_probability"])]
        )
        labels.append(y)
        sample_ids.append(row["sample_id"])
    with Path(args.model).open("rb") as handle:
        model = pickle.load(handle)
    scores = model.predict_proba(np.asarray(features, dtype=np.float64))[:, 1]
    threshold = float(args.threshold)
    rows = [
        {
            "sample_id": sample_id,
            "y_true": labels[index],
            "score": float(scores[index]),
            "prediction": int(float(scores[index]) >= threshold),
        }
        for index, sample_id in enumerate(sample_ids)
    ]
    output = Path(args.output)
    atomic_csv(rows, output)
    metrics, _ = metric_bundle(labels, list(map(float, scores)), threshold)
    atomic_json(
        {
            "status": "PASS_FROZEN_TEST_INFERENCE",
            "seed": int(args.seed),
            "model_sha256": sha256_file(Path(args.model)),
            "threshold": threshold,
            "metrics": metrics,
            "predictions_sha256": sha256_file(output),
        },
        output.with_suffix(".summary.json"),
    )


def _bind_static_paths(module: Any, root: Path, tool: str) -> None:
    module.STAGE_ROOT = root
    module.INPUT_DIR = root / "inputs"
    module.OUTPUT_DIR = root / "outputs"
    module.ANALYSIS_DIR = root / "analysis"
    if tool == "Bandit4Mal":
        module.RAW_JSON_DIR = module.OUTPUT_DIR / "raw_json"
        module.TEMP_UNPACK_DIR = root / "_temporary_unpacked"
        module.READY_CSV = module.INPUT_DIR / "test_index_bandit4mal_ready.csv"
        module.PREFLIGHT_JSON = module.INPUT_DIR / "preflight_report.json"
        module.STATUS_CSV = module.OUTPUT_DIR / "run_status_bandit4mal.csv"
        module.PREDICTIONS_CSV = module.ANALYSIS_DIR / "bandit4mal_predictions.csv"
        module.METRICS_CSV = module.ANALYSIS_DIR / "bandit4mal_policy_metrics.csv"
        module.METRICS_E2E_CSV = module.ANALYSIS_DIR / "bandit4mal_policy_metrics_end_to_end.csv"
        module.RULE_SUMMARY_CSV = module.ANALYSIS_DIR / "bandit4mal_rule_summary.csv"
        module.UNRESOLVED_CSV = module.ANALYSIS_DIR / "bandit4mal_unresolved.csv"
    elif tool == "GuardDog":
        module.RAW_JSON_DIR = module.OUTPUT_DIR / "raw_json"
        module.READY_CSV = module.INPUT_DIR / "test_index_guarddog_ready.csv"
        module.PREFLIGHT_JSON = module.INPUT_DIR / "preflight_report.json"
        module.STATUS_CSV = module.OUTPUT_DIR / "run_status_guarddog.csv"
        module.PREDICTIONS_CSV = module.ANALYSIS_DIR / "guarddog_predictions.csv"
        module.METRICS_CSV = module.ANALYSIS_DIR / "guarddog_policy_metrics.csv"
        module.METRICS_E2E_CSV = module.ANALYSIS_DIR / "guarddog_policy_metrics_end_to_end.csv"
        module.RULE_SUMMARY_CSV = module.ANALYSIS_DIR / "guarddog_rule_summary.csv"
        module.UNRESOLVED_CSV = module.ANALYSIS_DIR / "guarddog_unresolved.csv"
    elif tool == "OSSGadget":
        module.HTTP_REPO_DIR = root / "http_repo"
        module.RAW_LOG_DIR = module.OUTPUT_DIR / "raw_logs"
        module.READY_CSV = module.INPUT_DIR / "test_index_ossgadget_ready.csv"
        module.PKGURL_CSV = module.INPUT_DIR / "test_index_ossgadget_pkgurl_ready.csv"
        module.PREFLIGHT_JSON = module.INPUT_DIR / "preflight_report.json"
        module.STATUS_CSV = module.OUTPUT_DIR / "run_status_ossgadget.csv"
        module.PREDICTIONS_CSV = module.ANALYSIS_DIR / "ossgadget_predictions.csv"
        module.METRICS_CSV = module.ANALYSIS_DIR / "ossgadget_policy_metrics.csv"
        module.METRICS_E2E_CSV = module.ANALYSIS_DIR / "ossgadget_policy_metrics_end_to_end.csv"
        module.CONFUSION_CSV = module.ANALYSIS_DIR / "ossgadget_policy_confusion.csv"
        module.CONFUSION_E2E_CSV = module.ANALYSIS_DIR / "ossgadget_policy_confusion_end_to_end.csv"
        module.RULE_SUMMARY_CSV = module.ANALYSIS_DIR / "ossgadget_rule_summary.csv"
        module.UNRESOLVED_CSV = module.ANALYSIS_DIR / "ossgadget_unresolved.csv"
    else:
        raise ValueError(tool)


def worker_static_tool(args: argparse.Namespace) -> None:
    import pandas as pd

    audit = load_json(Path(args.policy_audit))
    method = audit["methods"][args.tool]
    pipeline = Path(method["integrity"]["pipeline"]["path"])
    module = _import_from_path(f"s10_static_{args.tool.lower()}", pipeline)
    root = Path(args.output_dir).resolve()
    _bind_static_paths(module, root, args.tool)
    module.TASK_CSV = Path(args.task_index).resolve()
    root.mkdir(parents=True, exist_ok=True)
    common = dict(workers=int(args.workers), timeout_seconds=int(args.timeout_seconds), max_samples=0)
    if args.tool == "Bandit4Mal":
        stage_args = SimpleNamespace(
            **common,
            scan_scope="full_package",
            max_entry_files=64,
            rerun_samples_csv="",
            rerun_sample_column="sample_id",
            only_rerun_samples=False,
        )
        module.stage_prepare(stage_args)
        module.stage_preflight(stage_args)
    elif args.tool == "GuardDog":
        stage_args = SimpleNamespace(
            **common,
            balanced_smoke=None,
            resume_check_only=False,
            force=False,
        )
        module.stage_prepare(stage_args)
        module.stage_preflight(stage_args)
    else:
        stage_args = SimpleNamespace(
            **common,
            no_prefer_datadog_fixed=False,
            rerun_samples_csv="",
            rerun_sample_column="sample_id",
            only_rerun_samples=False,
        )
        module.stage_prepare(stage_args)
        module.stage_preflight(stage_args)
        module.stage_build_http_repo(stage_args)

    # Reuse historical raw outputs only after an exact sample_id+archive hash join.
    new_ready = pd.read_csv(module.READY_CSV, low_memory=False)
    old_ready = pd.read_csv(method["integrity"]["ready_csv"]["path"], low_memory=False)
    old_status = pd.read_csv(method["integrity"]["status_csv"]["path"], low_memory=False)
    if "archive_sha256" not in new_ready or "archive_sha256" not in old_ready:
        raise RuntimeError("static-tool exact SHA join fields missing")
    joined = new_ready[["sample_id", "archive_sha256"]].merge(
        old_ready[["sample_id", "archive_sha256"]],
        on=["sample_id", "archive_sha256"],
        how="inner",
    )
    reusable_ids = set(joined["sample_id"].astype(str))
    reused = old_status.loc[old_status["sample_id"].astype(str).isin(reusable_ids)].copy()
    module.STATUS_CSV.parent.mkdir(parents=True, exist_ok=True)
    reused.to_csv(module.STATUS_CSV, index=False, encoding="utf-8")
    module.stage_run(stage_args)
    module.stage_parse(stage_args)
    if not module.PREDICTIONS_CSV.is_file():
        raise RuntimeError("static-tool parser did not produce predictions")
    atomic_json(
        {
            "status": "PASS_EXACT_V2_NATIVE_POLICY",
            "tool": args.tool,
            "reused_exact_sha_rows": len(reusable_ids),
            "newly_inferred_rows": EXPECTED_ROWS - len(reusable_ids),
            "predictions": str(module.PREDICTIONS_CSV),
            "predictions_sha256": sha256_file(module.PREDICTIONS_CSV),
        },
        root / "s10_static_summary.json",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="worker", required=True)
    hgt = sub.add_parser("hgt")
    hgt.add_argument("--manifest", required=True)
    hgt.add_argument("--checkpoint", required=True)
    hgt.add_argument("--seed", type=int, required=True)
    hgt.add_argument("--output", required=True)
    hgt.add_argument("--device", default="cuda:0")
    hgt.add_argument("--batch-size", type=int, default=4)
    hgt.add_argument("--workers", type=int, default=2)

    cache = sub.add_parser("modernbert-cache")
    cache.add_argument("--sequence-index", required=True)
    cache.add_argument("--package-index", required=True)
    cache.add_argument("--graph-manifest", required=True)
    cache.add_argument("--snapshot", required=True)
    cache.add_argument("--output-dir", required=True)

    modern = sub.add_parser("modernbert-infer")
    modern.add_argument("--cache-dir", required=True)
    modern.add_argument("--snapshot", required=True)
    modern.add_argument("--checkpoint", required=True)
    modern.add_argument("--seed", type=int, required=True)
    modern.add_argument("--output", required=True)
    modern.add_argument("--device", default="cuda:0")
    modern.add_argument("--batch-size", type=int, default=24)

    ea = sub.add_parser("ea4mp-ensemble")
    ea.add_argument("--bert-predictions", required=True)
    ea.add_argument("--metadata-predictions", required=True)
    ea.add_argument("--graph-manifest", required=True)
    ea.add_argument("--model", required=True)
    ea.add_argument("--threshold", type=float, required=True)
    ea.add_argument("--seed", type=int, required=True)
    ea.add_argument("--output", required=True)

    static = sub.add_parser("static-tool")
    static.add_argument("--tool", choices=["Bandit4Mal", "GuardDog", "OSSGadget"], required=True)
    static.add_argument("--task-index", required=True)
    static.add_argument("--policy-audit", required=True)
    static.add_argument("--output-dir", required=True)
    static.add_argument("--workers", type=int, default=4)
    static.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.monotonic()
    {
        "hgt": worker_hgt,
        "modernbert-cache": worker_modernbert_cache,
        "modernbert-infer": worker_modernbert_infer,
        "ea4mp-ensemble": worker_ea4mp_ensemble,
        "static-tool": worker_static_tool,
    }[args.worker](args)
    print(f"[S10 adapter] worker={args.worker} complete elapsed={time.monotonic()-started:.2f}s")


if __name__ == "__main__":
    main()
