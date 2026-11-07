#!/usr/bin/env python3
"""Fail-closed S10-B/S10-C exact-V2 one-shot final-test orchestrator.

S10-B uses ``--preflight`` only.  ``--run`` is intentionally unusable until a
separate authorization JSON, created after an explicit user decision, supplies
every test-bearing path and its frozen SHA256.  No test path is hard-coded.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence


SCRIPT_PATH = Path(__file__).resolve()
HERE = SCRIPT_PATH.parent
PROJECT_ROOT = SCRIPT_PATH.parents[2]
SPEC_PATH = HERE / "s10b_one_shot_test_runner_spec_v1.json"
CORRIGENDUM_PATH = HERE / "s10b_one_shot_test_runner_corrigendum_v1_1.json"
ADAPTER_PATH = HERE / "s10b_final_test_adapters.py"
UNIT_TEST_PATH = HERE / "test_s10b_one_shot_test_runner.py"
SHELL_PATH = HERE / "run_s10b_one_shot_test_runner.sh"
FREEZE_PATH = HERE / "s10b_one_shot_test_runner_freeze_manifest_v1_1.json"
PREFLIGHT_ROOT = (
    PROJECT_ROOT
    / "experiment_outputs/train_final_v10c_filtered700k_20260612"
    / "s10b_one_shot_test_runner_preflight_20260822_v1_1"
)
PREFLIGHT_PATH = PREFLIGHT_ROOT / "s10b_one_shot_test_runner_preflight.json"
LOCK_PATH = PREFLIGHT_ROOT / ".s10b.lock"

GRAPH_PYTHON = Path("/home/junwei/miniconda3/envs/pypi_260522/bin/python")
MODERNBERT_PYTHON = Path("/home/junwei/miniconda3/envs/modernbert_20260815/bin/python")
EA4MP_BERT_PYTHON = Path("/home/junwei/miniconda3/envs/ea4mp_bert_20260721/bin/python")
EA4MP_ENSEMBLE_PYTHON = Path("/home/junwei/miniconda3/envs/ea4mp_20260718/bin/python")

sys.path.insert(0, str(HERE))
import s10b_final_test_adapters as core  # noqa: E402


STAGE_IDS = (
    "00_authorization",
    "10_hgt",
    "20_modernbert",
    "30_proposed_metrics",
    "40_ea4mp",
    "50_static_tools",
    "60_archived_baselines",
    "70_report",
    "80_seal",
)

SUBSTAGE_IDS = {
    "10_hgt": tuple(f"hgt_seed{seed}" for seed in (1001, 1002, 1003)),
    "20_modernbert": (
        "modernbert_cache",
        "modernbert_seed1001",
        "modernbert_seed1002",
        "modernbert_seed1003",
    ),
    "40_ea4mp": tuple(f"ea4mp_seed{seed}" for seed in (42, 43, 44)),
    "50_static_tools": tuple(
        f"static_{tool}" for tool in ("bandit4mal", "guarddog", "ossgadget")
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--status", action="store_true")
    group.add_argument("--run", action="store_true")
    parser.add_argument("--authorization", default="")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    return core.sha256_file(path)


def load_spec() -> dict[str, Any]:
    value = core.load_json(SPEC_PATH)
    if value.get("artifact", {}).get("version") != "1.0.0":
        raise RuntimeError("S10-B specification version drift")
    if value.get("scope", {}).get("test_authorized") is not False:
        raise RuntimeError("S10-B specification unexpectedly authorizes test")
    if tuple(value.get("main_table", {}).get("rows_in_order", ())) != core.MAIN_ROWS:
        raise RuntimeError("canonical nine-row order drift")
    corrigendum = core.load_json(CORRIGENDUM_PATH)
    if corrigendum.get("artifact", {}).get("version") != "1.1.0":
        raise RuntimeError("S10-B corrigendum version drift")
    if corrigendum.get("base_contract", {}).get("spec_sha256") != sha256_file(SPEC_PATH):
        raise RuntimeError("S10-B base specification drift against corrigendum")
    prior_freeze = core.resolve_project_path(corrigendum["base_contract"]["superseded_freeze"])
    if (
        not prior_freeze.is_file()
        or sha256_file(prior_freeze)
        != corrigendum["base_contract"]["superseded_freeze_sha256"]
    ):
        raise RuntimeError("S10-B superseded freeze record is missing or drifted")
    value["corrigendum"] = corrigendum
    return value


def validate_freeze() -> dict[str, Any]:
    freeze = core.load_json(FREEZE_PATH)
    if freeze.get("artifact", {}).get("status") != "FROZEN_BEFORE_TEST_AUTHORIZATION_CORRIGENDUM_1_1":
        raise RuntimeError("S10-B freeze status drift")
    files = freeze.get("files_sha256", {})
    if not files:
        raise RuntimeError("S10-B freeze manifest is empty")
    for value, expected in files.items():
        path = core.resolve_project_path(value)
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(
                f"S10-B frozen file drift: {value} expected={expected} actual={actual}"
            )
    return freeze


def _all_frozen_paths(spec: dict[str, Any]) -> list[Path]:
    paths = [core.resolve_project_path(value) for value in spec["frozen_inputs"].values()]
    for family in ("hgt", "modernbert", "ea4mp"):
        item = spec["model_inputs"][family]
        for key in ("checkpoints", "bert_models", "adaboost_models"):
            for value in item.get(key, []):
                path = core.resolve_project_path(value)
                if path.is_dir():
                    paths.extend(sorted(child for child in path.iterdir() if child.is_file()))
                else:
                    paths.append(path)
        if "local_snapshot" in item:
            snapshot = core.resolve_project_path(item["local_snapshot"])
            paths.extend(sorted(child for child in snapshot.iterdir() if child.is_file()))
    return paths


def _source_contains_forbidden_test_path() -> bool:
    # This is intentionally a narrow literal-path check.  The split name and
    # expected hash are allowed; a path capable of opening the test is not.
    forbidden_fragments = (
        "graph_eligible_v2_" + "test.csv",
        "final_filtered700k_graph_eligible_v2_" + "test",
        "filtered700k_v2_" + "test.csv",
    )
    for path in (SCRIPT_PATH, ADAPTER_PATH, SPEC_PATH, CORRIGENDUM_PATH, SHELL_PATH, UNIT_TEST_PATH):
        text = path.read_text(encoding="utf-8")
        if any(fragment in text for fragment in forbidden_fragments):
            return True
    return False


def run_command(command: Sequence[str], *, cwd: Path = PROJECT_ROOT) -> None:
    print("[S10 CMD]", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=cwd, check=True)


def run_preflight() -> dict[str, Any]:
    started = time.monotonic()
    spec = load_spec()
    freeze = validate_freeze()
    checks: dict[str, bool] = {}
    checks["spec_test_authorized_false"] = spec["scope"]["test_authorized"] is False
    checks["spec_test_path_constructed_false"] = spec["scope"]["test_manifest_path_constructed"] is False
    checks["spec_test_read_false"] = spec["scope"]["test_rows_read"] is False
    checks["spec_gpu_false"] = spec["scope"]["gpu_compute"] is False
    checks["main_rows_exact"] = tuple(spec["main_table"]["rows_in_order"]) == core.MAIN_ROWS
    checks["stage_order_exact"] = tuple(row["id"] for row in spec["execution_stages"]) == STAGE_IDS
    checks["required_authorization_inputs_exact"] = tuple(
        spec["authorization_contract"]["required_inputs"]
    ) == core.REQUIRED_AUTH_INPUTS
    checks["expected_rows_exact"] = int(spec["locked_test_contract"]["expected_rows"]) == core.EXPECTED_ROWS
    checks["expected_manifest_sha_exact"] = (
        spec["locked_test_contract"]["expected_manifest_sha256"]
        == core.EXPECTED_MANIFEST_SHA256
    )
    checks["source_has_no_literal_test_path"] = not _source_contains_forbidden_test_path()
    checks["corrigendum_test_authorized_false"] = spec["corrigendum"]["scope"]["test_authorized"] is False
    checks["paired_bootstrap_pre_registered"] = (
        int(spec["corrigendum"]["final_test_statistics"]["replicates"]) == 20000
        and int(spec["corrigendum"]["final_test_statistics"]["random_state"]) == 20260822
    )
    checks["fine_grained_resume_registered"] = sum(map(len, SUBSTAGE_IDS.values())) == 13
    checks["freeze_self_sha_matches"] = freeze["files_sha256"][str(SPEC_PATH.relative_to(PROJECT_ROOT))] == sha256_file(SPEC_PATH)
    for executable in (GRAPH_PYTHON, MODERNBERT_PYTHON, EA4MP_BERT_PYTHON, EA4MP_ENSEMBLE_PYTHON):
        checks[f"runtime_exists::{executable.parent.parent.name}"] = executable.is_file()
    frozen_paths = _all_frozen_paths(spec)
    checks["frozen_path_inventory_nonempty"] = len(frozen_paths) >= 20
    for path in frozen_paths:
        checks[f"frozen_exists::{path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path}"] = path.is_file()
        if path.is_file():
            sha256_file(path)
    unit = subprocess.run(
        [str(GRAPH_PYTHON), str(UNIT_TEST_PATH)],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    checks["synthetic_unit_tests_pass"] = unit.returncode == 0
    checks["no_authorization_file_created"] = not any(
        PREFLIGHT_ROOT.glob("*authorization*.json")
    )
    checks["test_path_constructed_false"] = True
    checks["test_rows_read_false"] = True
    checks["test_predictions_read_false"] = True
    checks["test_metrics_computed_false"] = True
    checks["gpu_compute_false"] = True
    payload = {
        "artifact": {
            "name": "S10-B one-shot exact-V2 runner no-test preflight with closure corrigendum",
            "version": "1.1.0",
            "status": "PASS" if all(checks.values()) else "FAIL",
        },
        "checks": checks,
        "checks_total": len(checks),
        "checks_passed": sum(checks.values()),
        "unit_test_output": unit.stdout[-12000:],
        "spec_sha256": sha256_file(SPEC_PATH),
        "corrigendum_sha256": sha256_file(CORRIGENDUM_PATH),
        "runner_sha256": sha256_file(SCRIPT_PATH),
        "adapter_sha256": sha256_file(ADAPTER_PATH),
        "freeze_manifest_sha256": sha256_file(FREEZE_PATH),
        "scope": {
            "test_authorized": False,
            "test_manifest_path_constructed": False,
            "test_rows_read": False,
            "test_predictions_read": False,
            "test_metrics_computed": False,
            "gpu_compute": False,
        },
        "authorization": "BLOCKED_UNTIL_EXPLICIT_USER_DECISION_AND_SEPARATE_AUTHORIZATION_FILE",
        "next_stage": "S10-C one authorized exact-V2 evaluation phase",
        "elapsed_seconds": time.monotonic() - started,
    }
    PREFLIGHT_ROOT.mkdir(parents=True, exist_ok=True)
    core.atomic_json(payload, PREFLIGHT_PATH)
    if payload["artifact"]["status"] != "PASS":
        failed = [key for key, value in checks.items() if not value]
        raise RuntimeError(f"S10-B preflight failed: {failed}")
    return payload


def print_status(authorization_text: str = "") -> None:
    print("S10-B ONE-SHOT EXACT-V2 FINAL-TEST RUNNER STATUS")
    print("=" * 84)
    if not PREFLIGHT_PATH.is_file():
        print("preflight=PENDING test_authorized=NO test=LOCKED")
        return
    payload = core.load_json(PREFLIGHT_PATH)
    print(
        f"preflight={payload['artifact']['status']} "
        "test_authorized=NO test_path=NOT_CONSTRUCTED test=LOCKED GPU=NO"
    )
    print(f"checks={payload['checks_passed']}/{payload['checks_total']}")
    print(f"result={PREFLIGHT_PATH}")
    if not authorization_text:
        return
    authorization_path = Path(authorization_text).resolve()
    auth = core.validate_authorization(authorization_path, verify_input_hashes=False)
    run_root = (
        PROJECT_ROOT
        / "experiment_outputs/train_final_v10c_filtered700k_20260612"
        / f"s10c_one_shot_exact_v2_final_test_{auth['nonce'][:12]}"
    )
    print("-" * 84)
    print(f"test_authorized=YES run_root={run_root}")
    for stage in STAGE_IDS:
        receipt = _stage_receipt(run_root, stage)
        status = "COMPLETE" if receipt.is_file() else "PENDING"
        print(f"{stage}={status}")
        for substage in SUBSTAGE_IDS.get(stage, ()):
            subreceipt = run_root / "stages" / stage / "subreceipts" / f"{substage}.json"
            print(
                f"  {stage}/{substage}="
                f"{'COMPLETE' if subreceipt.is_file() else 'PENDING'}"
            )
    seal = run_root / "stages/80_seal/s10_exact_v2_one_shot_seal.json"
    print(f"one_shot_seal={'COMPLETE' if seal.is_file() else 'PENDING'}")


def _stage_receipt(root: Path, stage: str) -> Path:
    return root / "receipts" / f"{stage}.json"


def execute_stage(
    *,
    root: Path,
    stage: str,
    inputs: dict[str, str],
    callback: Callable[[Path], list[Path]],
) -> list[Path]:
    receipt_path = _stage_receipt(root, stage)
    receipt = core.validate_receipt(receipt_path, stage=stage, input_sha256=inputs)
    if receipt is not None:
        print(f"[S10 REUSE] {stage} complete and hash-verified", flush=True)
        return [Path(path) for path in receipt["output_sha256"]]
    stage_root = root / "stages" / stage
    if stage_root.exists():
        for temporary in stage_root.rglob("*.tmp"):
            temporary.unlink()
    stage_root.mkdir(parents=True, exist_ok=True)
    outputs = callback(stage_root)
    payload = core.receipt_payload(stage=stage, input_sha256=inputs, outputs=outputs)
    core.atomic_json(payload, receipt_path)
    print(f"[S10 COMPLETE] {stage}", flush=True)
    return outputs


def execute_substage(
    *,
    root: Path,
    name: str,
    inputs: dict[str, str],
    callback: Callable[[], list[Path]],
) -> list[Path]:
    """Resume an expensive cache/seed/tool independently inside a parent stage."""
    receipt_path = root / "subreceipts" / f"{name}.json"
    receipt = core.validate_receipt(receipt_path, stage=name, input_sha256=inputs)
    if receipt is not None:
        print(f"[S10 REUSE] substage={name} complete and hash-verified", flush=True)
        return [Path(path) for path in receipt["output_sha256"]]
    outputs = callback()
    core.atomic_json(
        core.receipt_payload(stage=name, input_sha256=inputs, outputs=outputs),
        receipt_path,
    )
    print(f"[S10 COMPLETE] substage={name}", flush=True)
    return outputs


def _read_margin_file(path: Path) -> dict[str, tuple[int, float]]:
    rows = core.read_csv(path)
    result: dict[str, tuple[int, float]] = {}
    for row in rows:
        sample_id = row["sample_id"]
        if sample_id in result:
            raise RuntimeError(f"duplicate prediction sample: {sample_id}")
        result[sample_id] = (int(row["y_true"]), float(row["logit_margin"]))
    if len(result) != core.EXPECTED_ROWS:
        raise RuntimeError(f"raw prediction population drift: {path}")
    return result


def stage_hgt(root: Path, spec: dict[str, Any], auth: dict[str, Any]) -> list[Path]:
    manifest = auth["resolved_inputs"]["graph_manifest"]["path"]
    outputs: list[Path] = []
    for seed, checkpoint in zip(
        spec["model_inputs"]["hgt"]["seeds"],
        spec["model_inputs"]["hgt"]["checkpoints"],
    ):
        output = root / f"hgt_seed{seed}_raw_predictions.csv"
        checkpoint_path = core.resolve_project_path(checkpoint)

        def run_seed() -> list[Path]:
            run_command(
                [
                    GRAPH_PYTHON,
                    ADAPTER_PATH,
                    "hgt",
                    "--manifest",
                    manifest,
                    "--checkpoint",
                    checkpoint_path,
                    "--seed",
                    str(seed),
                    "--output",
                    output,
                ]
            )
            return [output, output.with_suffix(".summary.json")]

        outputs.extend(
            execute_substage(
                root=root,
                name=f"hgt_seed{seed}",
                inputs={
                    "manifest": auth["resolved_inputs"]["graph_manifest"]["sha256"],
                    "checkpoint": sha256_file(checkpoint_path),
                    "adapter": sha256_file(ADAPTER_PATH),
                },
                callback=run_seed,
            )
        )
    return outputs


def stage_modernbert(root: Path, spec: dict[str, Any], auth: dict[str, Any]) -> list[Path]:
    item = spec["model_inputs"]["modernbert"]
    cache = root / "cache"
    cache_outputs = [cache / name for name in ("input_ids.npy", "attention_mask.npy", "labels.npy", "metadata.csv", "cache_summary.json")]

    def run_cache() -> list[Path]:
        run_command(
            [
                MODERNBERT_PYTHON,
                ADAPTER_PATH,
                "modernbert-cache",
                "--sequence-index",
                auth["resolved_inputs"]["modernbert_sequence_index"]["path"],
                "--package-index",
                auth["resolved_inputs"]["modernbert_package_input_index"]["path"],
                "--graph-manifest",
                auth["resolved_inputs"]["graph_manifest"]["path"],
                "--snapshot",
                core.resolve_project_path(item["local_snapshot"]),
                "--output-dir",
                cache,
            ]
        )
        return cache_outputs

    outputs = execute_substage(
        root=root,
        name="modernbert_cache",
        inputs={
            name: auth["resolved_inputs"][name]["sha256"]
            for name in ("graph_manifest", "modernbert_sequence_index", "modernbert_package_input_index")
        }
        | {"adapter": sha256_file(ADAPTER_PATH)},
        callback=run_cache,
    )
    for seed, checkpoint in zip(item["seeds"], item["checkpoints"]):
        output = root / f"modernbert_seed{seed}_raw_predictions.csv"
        checkpoint_path = core.resolve_project_path(checkpoint)

        def run_seed() -> list[Path]:
            run_command(
                [
                    MODERNBERT_PYTHON,
                    ADAPTER_PATH,
                    "modernbert-infer",
                    "--cache-dir",
                    cache,
                    "--snapshot",
                    core.resolve_project_path(item["local_snapshot"]),
                    "--checkpoint",
                    checkpoint_path,
                    "--seed",
                    str(seed),
                    "--output",
                    output,
                ]
            )
            return [output, output.with_suffix(".summary.json")]

        outputs.extend(
            execute_substage(
                root=root,
                name=f"modernbert_seed{seed}",
                inputs={
                    "cache_summary": sha256_file(cache / "cache_summary.json"),
                    "checkpoint": sha256_file(checkpoint_path),
                    "adapter": sha256_file(ADAPTER_PATH),
                },
                callback=run_seed,
            )
        )
    return outputs


def stage_proposed_metrics(root: Path, run_root: Path, spec: dict[str, Any], auth: dict[str, Any]) -> list[Path]:
    graph_manifest = core.read_csv(Path(auth["resolved_inputs"]["graph_manifest"]["path"]))
    order = [row["sample_id"] for row in graph_manifest]
    labels = [int(row["label_int"]) for row in graph_manifest]
    if len(order) != core.EXPECTED_ROWS or len(set(order)) != core.EXPECTED_ROWS:
        raise RuntimeError("canonical test manifest identity drift")
    branch_fits = core.load_json(core.resolve_project_path(spec["frozen_inputs"]["branch_fits"]))["fits"]
    fusion_fits = core.load_json(core.resolve_project_path(spec["frozen_inputs"]["fusion_fits"]))["fits"]
    summary: dict[str, Any] = {"status": "PASS", "seeds": {}}
    outputs: list[Path] = []
    for seed in (1001, 1002, 1003):
        graph = _read_margin_file(run_root / "stages/10_hgt" / f"hgt_seed{seed}_raw_predictions.csv")
        modern = _read_margin_file(run_root / "stages/20_modernbert" / f"modernbert_seed{seed}_raw_predictions.csv")
        graph_margins = []
        modern_margins = []
        for sample_id, label in zip(order, labels):
            if graph[sample_id][0] != label or modern[sample_id][0] != label:
                raise RuntimeError("proposed branch label drift")
            graph_margins.append(graph[sample_id][1])
            modern_margins.append(modern[sample_id][1])
        family_scores = {
            "graph": core.apply_single_calibrator(graph_margins, branch_fits[str(seed)]["graph"]),
            "modernbert": core.apply_single_calibrator(modern_margins, branch_fits[str(seed)]["modernbert"]),
            "fusion": core.apply_fusion(graph_margins, modern_margins, fusion_fits[str(seed)]),
        }
        family_thresholds = {
            "graph": float(branch_fits[str(seed)]["graph"]["probability_threshold"]),
            "modernbert": float(branch_fits[str(seed)]["modernbert"]["probability_threshold"]),
            "fusion": float(fusion_fits[str(seed)]["probability_threshold"]),
        }
        seed_summary: dict[str, Any] = {}
        for family, scores in family_scores.items():
            metrics, predictions = core.metric_bundle(labels, scores, family_thresholds[family])
            rows = [
                {
                    "sample_id": sample_id,
                    "y_true": labels[index],
                    "score": scores[index],
                    "prediction": predictions[index],
                }
                for index, sample_id in enumerate(order)
            ]
            path = root / f"{family}_seed{seed}_test_predictions.csv"
            core.atomic_csv(rows, path)
            outputs.append(path)
            seed_summary[family] = metrics
        summary["seeds"][str(seed)] = seed_summary
    summary_path = root / "proposed_system_test_metrics.json"
    core.atomic_json(summary, summary_path)
    outputs.append(summary_path)
    return outputs


def _ea4mp_base_configs() -> dict[int, Path]:
    return {
        42: PROJECT_ROOT / "baselines/ea4mp/configs/public_code_head512_validation_eval_v3_leakage_safe.json",
        43: PROJECT_ROOT / "experiment_outputs/train_final_v10c_filtered700k_20260612/s9d_ea4mp_confirmatory_seeds43_44_validation_20260820_v1/seed43/configs/validation.json",
        44: PROJECT_ROOT / "experiment_outputs/train_final_v10c_filtered700k_20260612/s9d_ea4mp_confirmatory_seeds43_44_validation_20260820_v1/seed44/configs/validation.json",
    }


def stage_ea4mp(root: Path, spec: dict[str, Any], auth: dict[str, Any]) -> list[Path]:
    graph = core.read_csv(Path(auth["resolved_inputs"]["graph_manifest"]["path"]))
    label_counts = {
        "benign": sum(int(row["label_int"]) == 0 for row in graph),
        "malicious": sum(int(row["label_int"]) == 1 for row in graph),
    }
    thresholds = {
        int(row["seed"]): float(row["threshold"])
        for row in core.load_json(core.resolve_project_path(spec["frozen_inputs"]["ea4mp_thresholds"]))["thresholds"]
    }
    item = spec["model_inputs"]["ea4mp"]
    metadata_predictions = Path(
        auth["resolved_inputs"]["ea4mp_metadata_predictions"]["path"]
    )
    runner41 = PROJECT_ROOT / "baselines/ea4mp/scripts/41_evaluate_public_code_head512_validation.py"
    outputs: list[Path] = []
    for seed, model, ensemble in zip(item["seeds"], item["bert_models"], item["adaboost_models"]):
        seed = int(seed)
        base_config = _ea4mp_base_configs()[seed]
        model_path = core.resolve_project_path(model)
        ensemble_path = core.resolve_project_path(ensemble)
        config_path = root / f"seed{seed}_bert_test_config.json"
        bert_out = root / f"seed{seed}_bert"
        preflight = root / f"seed{seed}_bert_preflight.json"
        bert_predictions = bert_out / "test_predictions.csv"
        ensemble_out = root / f"ea4mp_seed{seed}_test_predictions.csv"

        def run_seed() -> list[Path]:
            config = core.load_json(base_config)
            config["schema_version"] = "ea4mp-public-code-head512-test-evaluation-contract-v1"
            config["reporting_label"] = f"S10 exact-V2 frozen EA4MP seed{seed} test"
            config["input"].update(
                {
                    "split": "test",
                    "path": auth["resolved_inputs"]["ea4mp_grouped_inputs"]["path"],
                    "sha256": auth["resolved_inputs"]["ea4mp_grouped_inputs"]["sha256"],
                    "index": auth["resolved_inputs"]["ea4mp_package_input_index"]["path"],
                    "index_sha256": auth["resolved_inputs"]["ea4mp_package_input_index"]["sha256"],
                    "summary": auth["resolved_inputs"]["ea4mp_input_summary"]["path"],
                    "summary_sha256": auth["resolved_inputs"]["ea4mp_input_summary"]["sha256"],
                    "expected_packages": core.EXPECTED_ROWS,
                    "expected_package_labels": label_counts,
                    "validation_content_read": False,
                    "test_content_read": True,
                }
            )
            config["input"].pop("safety_audit", None)
            config["model"]["path"] = str(model_path)
            config["reproducibility"]["seed"] = seed
            config["reproducibility"]["pythonhashseed"] = seed
            core.atomic_json(config, config_path)
            run_command(
                [
                    EA4MP_BERT_PYTHON,
                    runner41,
                    "--config",
                    config_path,
                    "--output-dir",
                    bert_out,
                    "--preflight-output",
                    preflight,
                    "--confirm-formal-evaluation",
                ]
            )
            run_command(
                [
                    EA4MP_ENSEMBLE_PYTHON,
                    ADAPTER_PATH,
                    "ea4mp-ensemble",
                    "--bert-predictions",
                    bert_predictions,
                    "--metadata-predictions",
                    metadata_predictions,
                    "--graph-manifest",
                    auth["resolved_inputs"]["graph_manifest"]["path"],
                    "--model",
                    ensemble_path,
                    "--threshold",
                    str(thresholds[seed]),
                    "--seed",
                    str(seed),
                    "--output",
                    ensemble_out,
                ]
            )
            return [
                config_path,
                preflight,
                bert_predictions,
                ensemble_out,
                ensemble_out.with_suffix(".summary.json"),
            ]

        outputs.extend(
            execute_substage(
                root=root,
                name=f"ea4mp_seed{seed}",
                inputs={
                    "graph_manifest": auth["resolved_inputs"]["graph_manifest"]["sha256"],
                    "grouped_inputs": auth["resolved_inputs"]["ea4mp_grouped_inputs"]["sha256"],
                    "package_index": auth["resolved_inputs"]["ea4mp_package_input_index"]["sha256"],
                    "input_summary": auth["resolved_inputs"]["ea4mp_input_summary"]["sha256"],
                    "metadata_predictions": auth["resolved_inputs"]["ea4mp_metadata_predictions"]["sha256"],
                    "base_config": sha256_file(base_config),
                    "bert_model": sha256_file(model_path),
                    "adaboost_model": sha256_file(ensemble_path),
                    "ea4mp_thresholds": sha256_file(
                        core.resolve_project_path(spec["frozen_inputs"]["ea4mp_thresholds"])
                    ),
                    "bert_runner": sha256_file(runner41),
                    "adapter": sha256_file(ADAPTER_PATH),
                },
                callback=run_seed,
            )
        )
    return outputs


def stage_static(root: Path, spec: dict[str, Any], auth: dict[str, Any]) -> list[Path]:
    outputs: list[Path] = []
    policy_audit = core.resolve_project_path(spec["frozen_inputs"]["static_policy_audit"])
    for tool in ("Bandit4Mal", "GuardDog", "OSSGadget"):
        tool_root = root / tool.lower()
        summary = tool_root / "s10_static_summary.json"

        def run_tool() -> list[Path]:
            run_command(
                [
                    GRAPH_PYTHON,
                    ADAPTER_PATH,
                    "static-tool",
                    "--tool",
                    tool,
                    "--task-index",
                    auth["resolved_inputs"]["static_tool_task_index"]["path"],
                    "--policy-audit",
                    policy_audit,
                    "--output-dir",
                    tool_root,
                ]
            )
            predictions = Path(core.load_json(summary)["predictions"])
            return [summary, predictions]

        outputs.extend(
            execute_substage(
                root=root,
                name=f"static_{tool.lower()}",
                inputs={
                    "task_index": auth["resolved_inputs"]["static_tool_task_index"]["sha256"],
                    "policy_audit": sha256_file(policy_audit),
                    "adapter": sha256_file(ADAPTER_PATH),
                },
                callback=run_tool,
            )
        )
    return outputs


def stage_archived(root: Path, spec: dict[str, Any], auth: dict[str, Any]) -> list[Path]:
    graph = core.read_csv(Path(auth["resolved_inputs"]["graph_manifest"]["path"]))
    order = [row["sample_id"] for row in graph]
    labels = [int(row["label_int"]) for row in graph]
    truth = dict(zip(order, labels))
    cerebro_rows = core.read_csv(core.resolve_project_path(spec["frozen_inputs"]["cerebro_predictions"]))
    cerebro = {row["sample_id"]: row for row in cerebro_rows}
    if len(cerebro_rows) != core.EXPECTED_ROWS or len(cerebro) != core.EXPECTED_ROWS or set(cerebro) != set(order):
        raise RuntimeError("Cerebro archived population identity drift")
    result: dict[str, Any] = {"status": "PASS", "Cerebro": {}}
    for seed in (42, 43, 44):
        scores = []
        predictions = []
        for sample_id in order:
            row = cerebro[sample_id]
            if int(row[f"seed{seed}_label"]) != truth[sample_id]:
                raise RuntimeError("Cerebro archived label drift")
            scores.append(float(row[f"seed{seed}_prob_malicious"]))
            predictions.append(int(row[f"seed{seed}_validation_threshold_prediction"]))
        result["Cerebro"][str(seed)] = core.metric_bundle_from_predictions(labels, scores, predictions)
    vt_rows = core.read_csv(core.resolve_project_path(spec["frozen_inputs"]["virustotal_metrics"]))
    vt = next(row for row in vt_rows if row["threshold_malicious"] == "1" and row["metric_status"] == "ok")
    if int(vt["total"]) != core.EXPECTED_ROWS:
        raise RuntimeError("VirusTotal archived population drift")
    result["VirusTotal"] = {
        "rows": int(vt["total"]),
        "average_precision": None,
        "auroc": None,
        "precision": float(vt["precision"]),
        "recall": float(vt["recall"]),
        "f1": float(vt["f1"]),
        "fpr": float(vt["fpr"]),
        "confusion_matrix": {
            key: int(vt[key]) for key in ("tn", "fp", "fn", "tp")
        },
    }
    path = root / "archived_baseline_test_metrics.json"
    core.atomic_json(result, path)
    return [path]


def _mean_sd(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in ("average_precision", "auroc", "precision", "recall", "f1", "fpr"):
        values = [float(row[field]) for row in rows]
        output[f"{field}_mean"] = statistics.mean(values)
        output[f"{field}_sd"] = statistics.stdev(values)
    return output


def _canonical_population(
    auth: dict[str, Any],
) -> tuple[list[str], list[int], list[str], dict[str, int]]:
    rows = core.read_csv(Path(auth["resolved_inputs"]["graph_manifest"]["path"]))
    order = [row["sample_id"] for row in rows]
    labels = [int(row["label_int"]) for row in rows]
    components = [str(row["source_clone_component_id"]) for row in rows]
    if (
        len(rows) != core.EXPECTED_ROWS
        or len(set(order)) != core.EXPECTED_ROWS
        or set(labels) != {0, 1}
        or any(not value for value in components)
    ):
        raise RuntimeError("canonical exact-V2 test population drift")
    return order, labels, components, dict(zip(order, labels))


def _aligned_prediction_rows(
    path: Path,
    *,
    order: Sequence[str],
    truth: dict[str, int],
    label_fields: Sequence[str] = ("y_true", "label_int"),
) -> list[dict[str, str]]:
    rows = core.read_csv(path)
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        sample_id = str(row.get("sample_id", ""))
        if not sample_id or sample_id in by_id:
            raise RuntimeError(f"empty or duplicate prediction identity: {path}")
        label_field = next((name for name in label_fields if row.get(name, "") != ""), None)
        if label_field is None or int(row[label_field]) != truth.get(sample_id, -1):
            raise RuntimeError(f"prediction label/identity drift: {path} sample={sample_id}")
        by_id[sample_id] = row
    if len(by_id) != core.EXPECTED_ROWS or set(by_id) != set(order):
        raise RuntimeError(f"prediction population mismatch against canonical manifest: {path}")
    return [by_id[sample_id] for sample_id in order]


def _static_metrics(
    path: Path,
    policy_column: str,
    *,
    order: Sequence[str],
    truth: dict[str, int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = _aligned_prediction_rows(path, order=order, truth=truth)
    labels = [truth[sample_id] for sample_id in order]
    predictions = [core.parse_binary_prediction(row[policy_column]) for row in rows]
    metrics = core.metric_bundle_from_predictions(labels, list(map(float, predictions)), predictions)
    metrics["average_precision"] = None
    metrics["auroc"] = None
    identity = {
        "status": "PASS_EXACT_CANONICAL_IDENTITY",
        "rows": len(rows),
        "unique_sample_ids": len({row["sample_id"] for row in rows}),
        "labels_exact": True,
        "predictions_sha256": sha256_file(path),
    }
    return metrics, identity


def stage_report(
    root: Path,
    run_root: Path,
    spec: dict[str, Any],
    auth: dict[str, Any],
) -> list[Path]:
    order, labels, components, truth = _canonical_population(auth)
    proposed = core.load_json(run_root / "stages/30_proposed_metrics/proposed_system_test_metrics.json")
    archived = core.load_json(run_root / "stages/60_archived_baselines/archived_baseline_test_metrics.json")
    learned = {
        "Practical HGT (ours, graph branch)": _mean_sd([proposed["seeds"][str(seed)]["graph"] for seed in (1001, 1002, 1003)]),
        "ModernBERT (auxiliary sequence branch)": _mean_sd([proposed["seeds"][str(seed)]["modernbert"] for seed in (1001, 1002, 1003)]),
        "HGT plus ModernBERT (ours)": _mean_sd([proposed["seeds"][str(seed)]["fusion"] for seed in (1001, 1002, 1003)]),
        "Cerebro": _mean_sd([archived["Cerebro"][str(seed)] for seed in (42, 43, 44)]),
    }
    ea_rows = [
        core.load_json(run_root / f"stages/40_ea4mp/ea4mp_seed{seed}_test_predictions.summary.json")["metrics"]
        for seed in (42, 43, 44)
    ]
    learned["EA4MP"] = _mean_sd(ea_rows)
    identity: dict[str, Any] = {
        "status": "PASS_EXACT_V2_CANONICAL_IDENTITY",
        "canonical_manifest_sha256": auth["resolved_inputs"]["graph_manifest"]["sha256"],
        "rows": len(order),
        "unique_sample_ids": len(set(order)),
        "source_clone_components": len(set(components)),
        "methods": {},
    }
    systems: dict[int, dict[str, dict[str, Sequence[Any]]]] = {}
    for seed in (1001, 1002, 1003):
        systems[seed] = {}
        for family in ("graph", "modernbert", "fusion"):
            path = run_root / f"stages/30_proposed_metrics/{family}_seed{seed}_test_predictions.csv"
            aligned = _aligned_prediction_rows(path, order=order, truth=truth)
            systems[seed][family] = {
                "scores": [float(row["score"]) for row in aligned],
                "predictions": [core.parse_binary_prediction(row["prediction"]) for row in aligned],
            }
            identity["methods"][f"{family}_seed{seed}"] = {
                "status": "PASS",
                "rows": len(aligned),
                "predictions_sha256": sha256_file(path),
            }
    for seed in (42, 43, 44):
        path = run_root / f"stages/40_ea4mp/ea4mp_seed{seed}_test_predictions.csv"
        aligned = _aligned_prediction_rows(path, order=order, truth=truth)
        identity["methods"][f"EA4MP_seed{seed}"] = {
            "status": "PASS",
            "rows": len(aligned),
            "predictions_sha256": sha256_file(path),
        }

    cerebro_rows = core.read_csv(core.resolve_project_path(spec["frozen_inputs"]["cerebro_predictions"]))
    cerebro = {row["sample_id"]: row for row in cerebro_rows}
    if (
        len(cerebro_rows) != core.EXPECTED_ROWS
        or len(cerebro) != core.EXPECTED_ROWS
        or set(cerebro) != set(order)
    ):
        raise RuntimeError("Cerebro canonical identity drift in final report")
    for seed in (42, 43, 44):
        if any(int(cerebro[sample_id][f"seed{seed}_label"]) != truth[sample_id] for sample_id in order):
            raise RuntimeError(f"Cerebro seed{seed} canonical label drift")
        identity["methods"][f"Cerebro_seed{seed}"] = {
            "status": "PASS",
            "rows": core.EXPECTED_ROWS,
            "predictions_sha256": sha256_file(
                core.resolve_project_path(spec["frozen_inputs"]["cerebro_predictions"])
            ),
        }
    policy = {
        "Bandit4Mal": "pred_custom_rule",
        "GuardDog": "pred_any_issue",
        "OSSGadget": "pred_any_rule",
    }
    static: dict[str, Any] = {}
    for method, column in policy.items():
        summary = core.load_json(run_root / f"stages/50_static_tools/{method.lower()}/s10_static_summary.json")
        static[method], identity["methods"][method] = _static_metrics(
            Path(summary["predictions"]), column, order=order, truth=truth
        )
    static["VirusTotal (>=1 malicious engine)"] = archived["VirusTotal"]
    if int(archived["VirusTotal"]["rows"]) != core.EXPECTED_ROWS:
        raise RuntimeError("VirusTotal aggregate population drift in final report")
    identity["methods"]["VirusTotal (>=1 malicious engine)"] = {
        "status": "PASS_FROZEN_AGGREGATE_ONLY",
        "rows": core.EXPECTED_ROWS,
        "row_level_predictions_available": False,
        "metrics_sha256": sha256_file(core.resolve_project_path(spec["frozen_inputs"]["virustotal_metrics"])),
    }
    rows: list[dict[str, Any]] = []
    for method in core.MAIN_ROWS:
        if method in learned:
            value = learned[method]
            row = {"method": method, "reporting": "mean±sample_SD_3_seeds"}
            for field in ("average_precision", "auroc", "precision", "recall", "f1", "fpr"):
                row[f"{field}_mean"] = value[f"{field}_mean"]
                row[f"{field}_sd"] = value[f"{field}_sd"]
        else:
            value = static[method]
            row = {"method": method, "reporting": "single_frozen_native_policy"}
            for field in ("average_precision", "auroc", "precision", "recall", "f1", "fpr"):
                row[f"{field}_mean"] = value.get(field)
                row[f"{field}_sd"] = None
        rows.append(row)
    table = root / "s10_exact_v2_final_test_main_table.csv"
    core.atomic_csv(rows, table)
    identity_path = root / "s10_exact_v2_final_test_identity_audit.json"
    core.atomic_json(identity, identity_path)
    stat_spec = spec["corrigendum"]["final_test_statistics"]
    paired_statistics, replicate_rows = core.hierarchical_component_bootstrap(
        labels=labels,
        component_ids=components,
        systems=systems,
        replicates=int(stat_spec["replicates"]),
        random_state=int(stat_spec["random_state"]),
    )
    statistics_path = root / "s10_exact_v2_paired_statistics.json"
    core.atomic_json(paired_statistics, statistics_path)
    replicates_path = root / "s10_exact_v2_paired_bootstrap_replicates.csv"
    core.atomic_csv(replicate_rows, replicates_path)
    machine = root / "s10_exact_v2_final_test_results.json"
    core.atomic_json(
        {
            "status": "PASS_ONE_SHOT_REPORT_COMPLETE",
            "rows_in_order": list(core.MAIN_ROWS),
            "learned": learned,
            "deterministic": static,
            "table_sha256": sha256_file(table),
            "identity_audit_sha256": sha256_file(identity_path),
            "paired_statistics_sha256": sha256_file(statistics_path),
            "paired_bootstrap_replicates_sha256": sha256_file(replicates_path),
            "no_test_driven_model_threshold_or_claim_selection": True,
        },
        machine,
    )
    return [table, identity_path, statistics_path, replicates_path, machine]


def stage_seal(root: Path, run_root: Path, auth: dict[str, Any]) -> list[Path]:
    inventory: dict[str, str] = {}
    for path in sorted((run_root / "stages").rglob("*")):
        if path.is_file() and not path.name.endswith(".tmp"):
            inventory[str(path.relative_to(run_root))] = sha256_file(path)
    for path in sorted((run_root / "receipts").glob("*.json")):
        inventory[str(path.relative_to(run_root))] = sha256_file(path)
    seal = root / "s10_exact_v2_one_shot_seal.json"
    core.atomic_json(
        {
            "status": "SEALED_ONE_SHOT_EXACT_V2_FINAL_TEST",
            "authorization_nonce_sha256": hashlib.sha256(auth["nonce"].encode()).hexdigest(),
            "authorization_file_sha256": auth["authorization_file_sha256"],
            "inventory": inventory,
            "no_refit_retraining_threshold_search_or_model_selection": True,
        },
        seal,
    )
    return [seal]


def run_authorized(authorization_text: str) -> None:
    # Fail before path resolution: an absent argument is rejected before even
    # constructing a Path object for any test-bearing input.
    if not authorization_text:
        raise RuntimeError(
            "--run is locked: --authorization is required; no test path was resolved"
        )
    spec = load_spec()
    validate_freeze()
    authorization_path = Path(authorization_text).resolve()
    auth = core.validate_authorization(authorization_path, verify_input_hashes=True)
    auth["authorization_file_sha256"] = sha256_file(authorization_path)
    run_root = (
        PROJECT_ROOT
        / "experiment_outputs/train_final_v10c_filtered700k_20260612"
        / f"s10c_one_shot_exact_v2_final_test_{auth['nonce'][:12]}"
    )
    run_root.mkdir(parents=True, exist_ok=True)
    lock_handle = (run_root / ".one_shot.lock").open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock_handle.close()
        raise RuntimeError("another authorized S10 one-shot process is active") from error
    frozen_hashes = {
        "spec": sha256_file(SPEC_PATH),
        "corrigendum": sha256_file(CORRIGENDUM_PATH),
        "runner": sha256_file(SCRIPT_PATH),
        "adapter": sha256_file(ADAPTER_PATH),
        "freeze": sha256_file(FREEZE_PATH),
        "authorization": auth["authorization_file_sha256"],
    }
    execute_stage(
        root=run_root,
        stage="00_authorization",
        inputs=frozen_hashes,
        callback=lambda root: _stage_authorization(root, auth),
    )
    execute_stage(
        root=run_root,
        stage="10_hgt",
        inputs=frozen_hashes | {"graph_manifest": auth["resolved_inputs"]["graph_manifest"]["sha256"]},
        callback=lambda root: stage_hgt(root, spec, auth),
    )
    execute_stage(
        root=run_root,
        stage="20_modernbert",
        inputs=frozen_hashes
        | {name: auth["resolved_inputs"][name]["sha256"] for name in ("graph_manifest", "modernbert_sequence_index", "modernbert_package_input_index")},
        callback=lambda root: stage_modernbert(root, spec, auth),
    )
    execute_stage(
        root=run_root,
        stage="30_proposed_metrics",
        inputs=frozen_hashes
        | {
            "hgt_receipt": sha256_file(_stage_receipt(run_root, "10_hgt")),
            "modernbert_receipt": sha256_file(_stage_receipt(run_root, "20_modernbert")),
        },
        callback=lambda root: stage_proposed_metrics(root, run_root, spec, auth),
    )
    execute_stage(
        root=run_root,
        stage="40_ea4mp",
        inputs=frozen_hashes
        | {
            name: auth["resolved_inputs"][name]["sha256"]
            for name in (
                "graph_manifest",
                "ea4mp_grouped_inputs",
                "ea4mp_package_input_index",
                "ea4mp_input_summary",
                "ea4mp_metadata_predictions",
            )
        },
        callback=lambda root: stage_ea4mp(root, spec, auth),
    )
    execute_stage(
        root=run_root,
        stage="50_static_tools",
        inputs=frozen_hashes | {"task_index": auth["resolved_inputs"]["static_tool_task_index"]["sha256"]},
        callback=lambda root: stage_static(root, spec, auth),
    )
    execute_stage(
        root=run_root,
        stage="60_archived_baselines",
        inputs=frozen_hashes | {"graph_manifest": auth["resolved_inputs"]["graph_manifest"]["sha256"]},
        callback=lambda root: stage_archived(root, spec, auth),
    )
    execute_stage(
        root=run_root,
        stage="70_report",
        inputs=frozen_hashes
        | {"graph_manifest": auth["resolved_inputs"]["graph_manifest"]["sha256"]}
        | {stage: sha256_file(_stage_receipt(run_root, stage)) for stage in ("30_proposed_metrics", "40_ea4mp", "50_static_tools", "60_archived_baselines")},
        callback=lambda root: stage_report(root, run_root, spec, auth),
    )
    execute_stage(
        root=run_root,
        stage="80_seal",
        inputs=frozen_hashes | {"report_receipt": sha256_file(_stage_receipt(run_root, "70_report"))},
        callback=lambda root: stage_seal(root, run_root, auth),
    )
    print(f"[S10 SEALED] {run_root}")


def _stage_authorization(root: Path, auth: dict[str, Any]) -> list[Path]:
    ledger = root / "authorization_ledger.json"
    redacted = {
        "status": auth["status"],
        "version": auth["version"],
        "nonce_sha256": hashlib.sha256(auth["nonce"].encode()).hexdigest(),
        "authorization_file_sha256": auth["authorization_file_sha256"],
        "test_contract": auth["test_contract"],
        "input_sha256": {
            name: value["sha256"] for name, value in auth["resolved_inputs"].items()
        },
    }
    core.atomic_json(redacted, ledger)
    return [ledger]


def main() -> None:
    args = parse_args()
    if args.status:
        print_status(args.authorization)
        return
    if args.preflight:
        payload = run_preflight()
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    run_authorized(args.authorization)


if __name__ == "__main__":
    main()
