#!/usr/bin/env python3
"""Batch-safe practical-vs-RCBER paired validation-only trainer (P3 v2)."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path


os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import pandas as pd


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import train_p2a3_paired_hgt as p2trainer
from p3_rcber_model import (
    BEHAVIOR_EVIDENCE_RELATIONS,
    PracticalTypeBalancedHGTV9,
    RelationConditionedBehaviorEvidenceReadout,
)
from p3_schema_complete_batching import (
    COLLATION_REPAIR_NAME,
    COLLATION_REPAIR_VERSION,
    SchemaCompleteFormalDataset,
    install_schema_complete_dataset,
)


ROOT = p2trainer.ROOT
TRAIN_ROOT = p2trainer.TRAIN_ROOT
P3_ROOT = TRAIN_ROOT / "p3_rcber_batchsafe_paired_validation_20260807_v2"
RUNS_ROOT = P3_ROOT / "runs"
SPEC_PATH = HERE / "p3_rcber_primary_spec_v2.json"
FREEZE_MANIFEST_PATH = HERE / "p3_rcber_freeze_manifest_v2.json"
MODEL_PATH = HERE / "p3_rcber_model.py"
BATCHING_PATH = HERE / "p3_schema_complete_batching.py"

SEEDS = p2trainer.SEEDS
MODELS = ("practical", "rcber")
MATRIX = tuple((model, seed) for seed in SEEDS for model in MODELS)
EXPECTED_SPLIT_COUNTS = p2trainer.EXPECTED_SPLIT_COUNTS
EXPECTED_ROWS = p2trainer.EXPECTED_ROWS
REPRESENTATION = "practical"
RUN_LABELS = {
    "practical": "p3_batchsafe_practical_v2",
    "rcber": "p3_batchsafe_rcber_v2",
}
MODEL_CONTRACTS = {
    "practical": "batchsafe_practical_reference_v2",
    "rcber": "relation_conditioned_behavior_evidence_readout_v1_batchsafe_v2",
}

_ACTIVE_MODEL = ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json_save(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    temporary.replace(path)


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object: {path}")
    return value


def validate_freeze_manifest() -> dict:
    """Fail closed if any P3-v2 protocol, code, or upstream input drifts."""

    p2trainer.validate_freeze_manifest()
    freeze = load_json(FREEZE_MANIFEST_PATH)
    expected_status = (
        "frozen_after_v1_pre_epoch_collation_abort_before_v2_training_or_predictions"
    )
    if freeze.get("artifact", {}).get("status") != expected_status:
        raise RuntimeError("invalid P3-v2 freeze status")
    files = freeze.get("files_sha256")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("P3-v2 freeze manifest has no files_sha256 mapping")
    for relative_path, expected_sha256 in files.items():
        path = ROOT / str(relative_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        actual_sha256 = sha256_file(path)
        if actual_sha256 != str(expected_sha256):
            raise RuntimeError(
                f"P3-v2 frozen file drift: path={path} "
                f"expected={expected_sha256} actual={actual_sha256}"
            )

    spec = load_json(SPEC_PATH)
    if spec.get("artifact", {}).get("status") != expected_status:
        raise RuntimeError("P3-v2 primary specification is not frozen")
    if int(spec.get("stage_boundary", {}).get("paired_runs", -1)) != 6:
        raise RuntimeError("P3-v2 must retrain a three-seed practical reference")
    if bool(spec.get("input_contract", {}).get("test_access", True)):
        raise RuntimeError("P3-v2 specification unexpectedly authorizes test access")
    return freeze


def _p3_v2_config_from_args(
    args: argparse.Namespace,
    index_csv: Path,
    index_sha256: str,
    feature_profile: str,
    component_weight_stats: dict,
    input_rows: int,
    input_split_counts: dict[str, int],
) -> dict:
    if _ACTIVE_MODEL not in MODELS:
        raise RuntimeError("P3-v2 model was not installed before config creation")
    config = p2trainer._p2_config_from_args(
        args,
        index_csv,
        index_sha256,
        feature_profile,
        component_weight_stats,
        input_rows,
        input_split_counts,
    )
    config.update(
        {
            "p3_stage": "P3_RCBER_batchsafe_paired_primary_validation_only",
            "p3_model_kind": _ACTIVE_MODEL,
            "p3_model_contract": MODEL_CONTRACTS[_ACTIVE_MODEL],
            "p3_v2_trainer_sha256": sha256_file(Path(__file__)),
            "p3_model_script_sha256": sha256_file(MODEL_PATH),
            "p3_batching_script_sha256": sha256_file(BATCHING_PATH),
            "p3_primary_spec_sha256": sha256_file(SPEC_PATH),
            "p3_freeze_manifest_sha256": sha256_file(FREEZE_MANIFEST_PATH),
            "p3_collation_repair_name": COLLATION_REPAIR_NAME,
            "p3_collation_repair_version": COLLATION_REPAIR_VERSION,
            "p3_schema_completion": "missing allowed relations become empty [2,0] long tensors before PyG collation",
            "p3_behavior_evidence_relations": (
                [list(edge_type) for edge_type in BEHAVIOR_EVIDENCE_RELATIONS]
                if _ACTIVE_MODEL == "rcber"
                else []
            ),
            "p3_raw_api_name_read": False,
            "p3_raw_param_text_read": False,
            "p3_package_or_family_identity_read": False,
            "p3_graph_rebuild": False,
            "p3_pt_rewrite": False,
            "p3_test_artifacts_authorized": False,
        }
    )
    development = dict(config["development_only_contract"])
    development.update(
        {
            "name": "p3_v2_frozen_train_plus_original_validation_only",
            "p3_model_kind": _ACTIVE_MODEL,
            "combined_test_bearing_index_read": False,
            "test_pt_read": False,
            "test_prediction_read": False,
            "test_checkpoint_inference": False,
        }
    )
    config["development_only_contract"] = development
    return config


def _p3_v2_validate_resume_config(saved: dict, current: dict) -> None:
    p2trainer._p2_validate_resume_config(saved, current)
    keys = (
        "p3_stage",
        "p3_model_kind",
        "p3_model_contract",
        "p3_v2_trainer_sha256",
        "p3_model_script_sha256",
        "p3_batching_script_sha256",
        "p3_primary_spec_sha256",
        "p3_freeze_manifest_sha256",
        "p3_collation_repair_name",
        "p3_collation_repair_version",
        "p3_schema_completion",
        "p3_behavior_evidence_relations",
        "p3_raw_api_name_read",
        "p3_raw_param_text_read",
        "p3_package_or_family_identity_read",
        "p3_graph_rebuild",
        "p3_pt_rewrite",
        "p3_test_artifacts_authorized",
    )
    mismatches = {
        key: (saved.get(key), current.get(key))
        for key in keys
        if saved.get(key) != current.get(key)
    }
    if mismatches:
        raise RuntimeError(f"P3-v2 resume configuration mismatch: {mismatches}")


def install_model(model: str, full_input_hash_audit: bool = False) -> None:
    """Bind one paired arm plus schema-complete batching to the frozen trainer."""

    global _ACTIVE_MODEL
    if model not in MODELS:
        raise ValueError(f"unsupported P3-v2 model: {model!r}")
    _ACTIVE_MODEL = model
    p2trainer.install_representation(
        REPRESENTATION, full_input_hash_audit=full_input_hash_audit
    )
    base = p2trainer.base
    contract = copy.deepcopy(base.SPLIT_CONTRACTS["v2_strict40"])
    contract["output_root"] = RUNS_ROOT
    contract["feature_profile"] = "p3_practical_v10c_batchsafe_v2"
    base.SPLIT_CONTRACTS["v2_strict40"] = contract
    install_schema_complete_dataset()
    base.architecture.TypeBalancedHGTV9 = (
        PracticalTypeBalancedHGTV9
        if model == "practical"
        else RelationConditionedBehaviorEvidenceReadout
    )
    base.config_from_args = _p3_v2_config_from_args
    base.validate_resume_config = _p3_v2_validate_resume_config


def fixed_base_args(
    model: str,
    seed: int,
    preflight_only: bool,
) -> argparse.Namespace:
    if model not in MODELS:
        raise ValueError(model)
    args = p2trainer.fixed_base_args(REPRESENTATION, seed, preflight_only)
    args.run_label = RUN_LABELS[model]
    return args


def run_tag(model: str, seed: int) -> str:
    return (
        "v10c_formal_v2_strict40_ast_event_param_context_type_balanced_"
        f"ckpt_ap_inverse_sqrt_{RUN_LABELS[model]}_seed{seed}"
    )


def run_directory(model: str, seed: int) -> Path:
    return RUNS_ROOT / run_tag(model, seed)


def validate_completed_result(model: str, seed: int) -> dict:
    if model not in MODELS or seed not in SEEDS:
        raise ValueError((model, seed))
    out_dir = run_directory(model, seed)
    result_path = out_dir / "validation_result.json"
    result = load_json(result_path)
    if result.get("status") != "validation_complete":
        raise RuntimeError(f"invalid completed status in {result_path}")
    if int(result.get("seed", -1)) != seed:
        raise RuntimeError(f"completed seed mismatch in {result_path}")
    if result.get("mode") != "ast_event_param_context":
        raise RuntimeError(f"completed mode mismatch in {result_path}")
    if bool(result.get("test_evaluated", True)):
        raise RuntimeError(f"P3-v2 result claims test evaluation: {result_path}")
    config = result.get("config", {})
    expected = {
        "p2_representation": REPRESENTATION,
        "p3_model_kind": model,
        "p3_model_contract": MODEL_CONTRACTS[model],
        "p3_collation_repair_name": COLLATION_REPAIR_NAME,
        "p3_collation_repair_version": COLLATION_REPAIR_VERSION,
        "seed": seed,
        "checkpoint_metric": "ap",
        "component_weighting": "inverse_sqrt",
        "optimizer": "adam",
        "weight_decay": 0.0,
        "p3_graph_rebuild": False,
        "p3_pt_rewrite": False,
        "p3_test_artifacts_authorized": False,
    }
    for key, expected_value in expected.items():
        if config.get(key) != expected_value:
            raise RuntimeError(
                f"completed P3-v2 config mismatch for {key}: "
                f"expected={expected_value!r} actual={config.get(key)!r}"
            )
    current_hashes = {
        "p3_v2_trainer_sha256": sha256_file(Path(__file__)),
        "p3_model_script_sha256": sha256_file(MODEL_PATH),
        "p3_batching_script_sha256": sha256_file(BATCHING_PATH),
        "p3_primary_spec_sha256": sha256_file(SPEC_PATH),
        "p3_freeze_manifest_sha256": sha256_file(FREEZE_MANIFEST_PATH),
    }
    for key, current in current_hashes.items():
        if config.get(key) != current:
            raise RuntimeError(
                f"completed P3-v2 result was created under a different {key}"
            )

    required_files = (
        out_dir / "checkpoints/best_model.pt",
        out_dir / "checkpoints/last_state.pt",
        out_dir / "train_log.csv",
        out_dir / "validation_predictions.csv",
        out_dir / "validation_operating_points.json",
        out_dir / "reproducibility_manifest.json",
    )
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        raise RuntimeError(f"completed P3-v2 result is missing artifacts: {missing}")
    forbidden = [
        path
        for path in (out_dir / "test_predictions.csv", out_dir / "final_result.json")
        if path.exists()
    ]
    if forbidden:
        raise RuntimeError(f"test artifacts are forbidden in P3-v2: {forbidden}")
    predictions = pd.read_csv(
        out_dir / "validation_predictions.csv", low_memory=False
    )
    if len(predictions) != EXPECTED_SPLIT_COUNTS["val"]:
        raise RuntimeError(
            f"completed validation prediction count drift: {len(predictions)}"
        )
    if predictions["graph_id"].astype(str).duplicated().any():
        raise RuntimeError("completed P3-v2 predictions contain duplicate graph_id")
    return result


def run_one(
    model: str,
    seed: int,
    preflight_only: bool = False,
    full_input_hash_audit: bool = False,
) -> int:
    validate_freeze_manifest()
    install_model(model, full_input_hash_audit=full_input_hash_audit)
    if not preflight_only:
        out_dir = run_directory(model, seed)
        forbidden = [
            path
            for path in (out_dir / "test_predictions.csv", out_dir / "final_result.json")
            if path.exists()
        ]
        if forbidden:
            raise RuntimeError(f"test artifacts are forbidden in P3-v2: {forbidden}")
        if (out_dir / "validation_result.json").is_file():
            validate_completed_result(model, seed)
            print(f"[SKIP COMPLETE] model={model} seed={seed} result={out_dir}")
            return 0

    args = fixed_base_args(model, seed, preflight_only)
    print(
        f"[P3-v2] model={model} seed={seed} "
        f"mode={'preflight' if preflight_only else 'validation-only training'}"
    )
    print("[P3-v2] graph/PT=existing practical V10c; graph rebuild/PT rewrite=NO")
    print("[P3-v2] batching=schema-complete empty relation stores before collation")
    print("[P3-v2] test manifest/PT/predictions/loader: LOCKED")
    p2trainer.base.train(args)
    if preflight_only:
        return 0

    if (run_directory(model, seed) / "validation_result.json").is_file():
        validate_completed_result(model, seed)
        return 0
    last_checkpoint = run_directory(model, seed) / "checkpoints/last_state.pt"
    if last_checkpoint.is_file():
        print(
            "[P3-v2 INTERRUPTED] Rerun the identical matrix command to resume "
            f"from {last_checkpoint}"
        )
    else:
        print(
            "[P3-v2 INTERRUPTED] No epoch completed; rerunning the identical "
            "matrix command restarts this arm at epoch 1."
        )
    return 130


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--seed", type=int, choices=SEEDS, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--full-input-hash-audit", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.full_input_hash_audit and not args.preflight_only:
        raise ValueError("--full-input-hash-audit is allowed only with --preflight-only")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", RUN_LABELS[args.model]):
        raise RuntimeError("invalid frozen P3-v2 run label")
    return run_one(
        args.model,
        args.seed,
        preflight_only=args.preflight_only,
        full_input_hash_audit=args.full_input_hash_audit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
