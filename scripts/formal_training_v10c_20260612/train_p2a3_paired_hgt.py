#!/usr/bin/env python3
"""P2-A3a validation-only trainer without modifying the frozen P1 trainer.

The module binds one of three frozen PT representations to the existing P1
training implementation.  It never opens the combined test-bearing index and
never constructs a test loader.  Formal hyperparameters are deliberately not
exposed on the command line: representation, seed, and the preflight/full-hash
diagnostic switches are the only varying inputs.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path


os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import pandas as pd


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import train_v10c_formal_hgt as base


ROOT = Path("/home/junwei/projects/pypi_dataset_cutoff20260101")
TRAIN_ROOT = ROOT / "experiment_outputs/train_final_v10c_filtered700k_20260612"
P2A2_ROOT = TRAIN_ROOT / "p2a2_full_dev_pt_conversion_20260806_v1"
P2A3_ROOT = TRAIN_ROOT / "p2a3_primary_paired_validation_20260806_v1"
RUNS_ROOT = P2A3_ROOT / "runs"

SPEC_PATH = HERE / "p2a3_primary_training_spec_v1.json"
FREEZE_MANIFEST_PATH = HERE / "p2a3_primary_freeze_manifest_v1.json"
CONVERSION_MANIFEST_PATH = P2A2_ROOT / "full_conversion_manifest.csv"
P2A2_SUMMARY_PATH = P2A2_ROOT / "p2a2_full_summary.json"

EXPECTED_SPLIT_COUNTS = {"train": 16_613, "val": 2_137}
EXPECTED_ROWS = sum(EXPECTED_SPLIT_COUNTS.values())
SEEDS = (1001, 1002, 1003)
REPRESENTATION_ORDER = ("practical", "controlled_zero", "candidate")
REPRESENTATIONS = {
    "practical": {
        "path_column": "old_pt_path",
        "sha256_column": "old_pt_sha256",
        "bytes_column": "old_pt_bytes",
        "dimensions": {"module": 4, "ast": 12, "param": 29, "event": 18},
        "feature_profile": "p2a3_practical_coarse_v10c_v1",
    },
    "controlled_zero": {
        "path_column": "controlled_zero_pt_path",
        "sha256_column": "controlled_zero_pt_sha256",
        "bytes_column": "controlled_zero_pt_bytes",
        "dimensions": {"module": 4, "ast": 29, "param": 42, "event": 28},
        "feature_profile": "p2a3_widened_controlled_zero_v1",
    },
    "candidate": {
        "path_column": "candidate_pt_path",
        "sha256_column": "candidate_pt_sha256",
        "bytes_column": "candidate_pt_bytes",
        "dimensions": {"module": 4, "ast": 29, "param": 42, "event": 28},
        "feature_profile": "p2a3_identity_suppressed_behavior_candidate_v1",
    },
}

ORIGINAL_READ_DEVELOPMENT_MANIFESTS = base.read_frozen_v2_development_manifests
ORIGINAL_CONFIG_FROM_ARGS = base.config_from_args
ORIGINAL_VALIDATE_RESUME_CONFIG = base.validate_resume_config

_ACTIVE_REPRESENTATION: str | None = None
_FULL_INPUT_HASH_AUDIT = False
_FREEZE_MANIFEST: dict | None = None


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


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected a JSON object: {path}")
    return payload


def validate_freeze_manifest() -> dict:
    """Verify every source/input artifact frozen for P2-A3a."""

    global _FREEZE_MANIFEST
    freeze = _load_json(FREEZE_MANIFEST_PATH)
    artifact = freeze.get("artifact", {})
    if artifact.get("status") != "frozen_before_p2a3_validation_predictions_or_training":
        raise RuntimeError(f"invalid P2-A3 freeze status: {artifact.get('status')!r}")

    file_hashes = freeze.get("files_sha256")
    if not isinstance(file_hashes, dict) or not file_hashes:
        raise RuntimeError("P2-A3 freeze manifest has no files_sha256 mapping")
    for relative_path, expected_sha256 in file_hashes.items():
        path = ROOT / relative_path
        if not path.is_file():
            raise FileNotFoundError(path)
        actual_sha256 = sha256_file(path)
        if actual_sha256 != str(expected_sha256):
            raise RuntimeError(
                f"P2-A3 frozen file drift: path={path} "
                f"expected={expected_sha256} actual={actual_sha256}"
            )

    spec = _load_json(SPEC_PATH)
    if spec.get("artifact", {}).get("status") != (
        "frozen_before_p2a3_validation_predictions_or_training"
    ):
        raise RuntimeError("P2-A3 training specification is not frozen")

    p2a2_summary = _load_json(P2A2_SUMMARY_PATH)
    p2a2_artifact = p2a2_summary.get("artifact", {})
    if p2a2_artifact.get("status") != "pass":
        raise RuntimeError("P2-A2F summary is not PASS")
    if p2a2_artifact.get("authorization") != (
        "ready_to_freeze_p2a3_validation_only_training_entry_not_test"
    ):
        raise RuntimeError("P2-A2F does not authorize P2-A3 validation-only training")
    coverage = p2a2_summary.get("coverage", {})
    if int(coverage.get("converted_graphs", -1)) != EXPECTED_ROWS:
        raise RuntimeError("P2-A2F converted graph count drift")
    if int(coverage.get("audited_graphs", -1)) != EXPECTED_ROWS:
        raise RuntimeError("P2-A2F audited graph count drift")
    if coverage.get("split_counts") != EXPECTED_SPLIT_COUNTS:
        raise RuntimeError(f"P2-A2F split count drift: {coverage.get('split_counts')}")
    equivalence = p2a2_summary.get("equivalence", {})
    for field in (
        "feature_mismatches",
        "node_identity_mismatches",
        "topology_mismatches",
        "controlled_zero_suffix_nonzero",
    ):
        if int(equivalence.get(field, -1)) != 0:
            raise RuntimeError(f"P2-A2F equivalence gate failed: {field}")
    execution = p2a2_summary.get("execution", {})
    if any(
        bool(execution.get(field))
        for field in ("test_read", "checkpoint_read", "training_or_inference", "gpu_operation")
    ):
        raise RuntimeError("P2-A2F execution boundary drift")

    _FREEZE_MANIFEST = freeze
    return freeze


def load_conversion_manifest() -> pd.DataFrame:
    required_columns = {
        "position",
        "graph_id",
        "split",
        "status",
        "old_pt_path",
        "old_pt_sha256",
        "old_pt_bytes",
        "candidate_pt_path",
        "candidate_pt_sha256",
        "candidate_pt_bytes",
        "controlled_zero_pt_path",
        "controlled_zero_pt_sha256",
        "controlled_zero_pt_bytes",
    }
    frame = pd.read_csv(CONVERSION_MANIFEST_PATH, low_memory=False)
    missing_columns = sorted(required_columns.difference(frame.columns))
    if missing_columns:
        raise RuntimeError(
            f"P2-A2F conversion manifest is missing columns: {missing_columns}"
        )
    if len(frame) != EXPECTED_ROWS:
        raise RuntimeError(
            f"P2-A2F conversion rows: expected={EXPECTED_ROWS} actual={len(frame)}"
        )
    if frame["graph_id"].astype(str).duplicated().any():
        raise RuntimeError("P2-A2F conversion manifest contains duplicate graph_id")
    expected_positions = list(range(1, EXPECTED_ROWS + 1))
    if frame["position"].astype(int).tolist() != expected_positions:
        raise RuntimeError("P2-A2F conversion positions are not the frozen contiguous order")
    split_counts = frame["split"].astype(str).value_counts().to_dict()
    if split_counts != EXPECTED_SPLIT_COUNTS:
        raise RuntimeError(f"P2-A2F conversion split counts drift: {split_counts}")
    statuses = sorted(frame["status"].dropna().astype(str).unique().tolist())
    if statuses != ["pass"] or frame["status"].isna().any():
        raise RuntimeError(f"P2-A2F conversion statuses drift: {statuses}")
    if frame[list(required_columns)].isna().any().any():
        raise RuntimeError("P2-A2F conversion manifest has missing required values")
    return frame


def _verify_selected_pt_artifacts(
    selected: pd.DataFrame,
    path_column: str,
    sha256_column: str,
    bytes_column: str,
) -> None:
    paths = selected[path_column].astype(str)
    if paths.duplicated().any():
        raise RuntimeError(f"duplicate selected PT path in {path_column}")
    for row in selected[["graph_id", path_column, sha256_column, bytes_column]].itertuples(
        index=False, name=None
    ):
        graph_id, raw_path, expected_sha256, expected_bytes = row
        path = Path(str(raw_path))
        if not path.is_absolute():
            raise RuntimeError(f"non-absolute selected PT path for {graph_id}: {path}")
        if not path.is_file():
            raise FileNotFoundError(path)
        actual_bytes = path.stat().st_size
        if actual_bytes != int(expected_bytes):
            raise RuntimeError(
                f"selected PT size drift for {graph_id}: "
                f"expected={expected_bytes} actual={actual_bytes} path={path}"
            )
        if _FULL_INPUT_HASH_AUDIT:
            actual_sha256 = sha256_file(path)
            if actual_sha256 != str(expected_sha256):
                raise RuntimeError(
                    f"selected PT SHA256 drift for {graph_id}: "
                    f"expected={expected_sha256} actual={actual_sha256} path={path}"
                )


def read_p2_development_manifests(
    representation: str,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Read only frozen train/val rows and remap their PT path one-to-one."""

    original_frame, original_parts = ORIGINAL_READ_DEVELOPMENT_MANIFESTS()
    conversion = load_conversion_manifest()
    original_keys = set(
        zip(original_frame["graph_id"].astype(str), original_frame["split"].astype(str))
    )
    conversion_keys = set(
        zip(conversion["graph_id"].astype(str), conversion["split"].astype(str))
    )
    if original_keys != conversion_keys:
        missing = sorted(original_keys.difference(conversion_keys))[:3]
        extra = sorted(conversion_keys.difference(original_keys))[:3]
        raise RuntimeError(
            f"P2-A2F graph membership mismatch: missing={missing} extra={extra}"
        )

    settings = REPRESENTATIONS[representation]
    selected_columns = [
        "graph_id",
        "split",
        settings["path_column"],
        settings["sha256_column"],
        settings["bytes_column"],
    ]
    selected = conversion[selected_columns].copy()
    _verify_selected_pt_artifacts(
        selected,
        settings["path_column"],
        settings["sha256_column"],
        settings["bytes_column"],
    )

    remapped_parts: dict[str, pd.DataFrame] = {}
    for split in ("train", "val"):
        part = original_parts[split].copy()
        part["_p2_row_order"] = range(len(part))
        mapping = selected.loc[selected["split"].astype(str) == split].copy()
        joined = part.merge(
            mapping,
            on=["graph_id", "split"],
            how="left",
            validate="one_to_one",
            sort=False,
        )
        joined = joined.sort_values("_p2_row_order", kind="stable").reset_index(drop=True)
        if len(joined) != EXPECTED_SPLIT_COUNTS[split]:
            raise RuntimeError(f"P2 {split} remap row count drift: {len(joined)}")
        if joined[settings["path_column"]].isna().any():
            raise RuntimeError(f"P2 {split} remap contains missing PT paths")
        if representation == "practical":
            old_paths = joined["pt_path_v9"].astype(str).tolist()
            mapped_paths = joined[settings["path_column"]].astype(str).tolist()
            if old_paths != mapped_paths:
                raise RuntimeError("practical reference PT paths differ from frozen V2 manifests")
            if joined["pt_path_v8"].astype(str).tolist() != mapped_paths:
                raise RuntimeError(
                    "practical reference loader PT paths differ from frozen V2 manifests"
                )
        # The inherited GraphDatasetV8B implementation loads ``pt_path_v8``;
        # the formal manifests keep pt_path_v8 and pt_path_v9 identical.  Bind
        # both columns so the P2 path is explicit to both the loader and every
        # newer audit consumer.
        joined["pt_path_v9"] = joined[settings["path_column"]].astype(str)
        joined["pt_path_v8"] = joined[settings["path_column"]].astype(str)
        joined["_p2_expected_pt_sha256"] = joined[settings["sha256_column"]].astype(str)
        joined["_p2_expected_pt_bytes"] = joined[settings["bytes_column"]].astype(int)
        joined["_p2_representation"] = representation
        joined = joined.drop(columns=["_p2_row_order"])
        remapped_parts[split] = joined

    remapped_frame = pd.concat(
        [remapped_parts["train"], remapped_parts["val"]], ignore_index=True
    )
    for identifier in ("sample_id", "graph_id", "pt_path_v8", "pt_path_v9"):
        if remapped_frame[identifier].astype(str).duplicated().any():
            raise RuntimeError(f"P2 train/validation overlap after remap on {identifier}")
    return remapped_frame, remapped_parts


def _p2_config_from_args(
    args: argparse.Namespace,
    index_csv: Path,
    index_sha256: str,
    feature_profile: str,
    component_weight_stats: dict,
    input_rows: int,
    input_split_counts: dict[str, int],
) -> dict:
    if _ACTIVE_REPRESENTATION is None:
        raise RuntimeError("P2 representation was not installed")
    config = ORIGINAL_CONFIG_FROM_ARGS(
        args,
        index_csv,
        index_sha256,
        feature_profile,
        component_weight_stats,
        input_rows,
        input_split_counts,
    )
    settings = REPRESENTATIONS[_ACTIVE_REPRESENTATION]
    config.update(
        {
            "trainer_script_sha256": sha256_file(Path(__file__)),
            "base_trainer_script_sha256": sha256_file(HERE / "train_v10c_formal_hgt.py"),
            "base_architecture_sha256": sha256_file(
                HERE.parent / "final_graph_v9_20260608/train_v9_small_hgt_readout.py"
            ),
            "p2a3_stage": "P2-A3a_primary_paired_performance_screen",
            "p2_representation": _ACTIVE_REPRESENTATION,
            "p2_input_dimensions": dict(settings["dimensions"]),
            "p2_pt_path_column": settings["path_column"],
            "p2_trainer_loader_pt_column": "pt_path_v8",
            "p2_pt_sha256_column": settings["sha256_column"],
            "p2_pt_bytes_column": settings["bytes_column"],
            "p2_behavior_protocol_sha256": sha256_file(
                HERE / "p2_behavior_first_protocol_v1.json"
            ),
            "p2a3_training_spec_sha256": sha256_file(SPEC_PATH),
            "p2a3_freeze_manifest_sha256": sha256_file(FREEZE_MANIFEST_PATH),
            "p2a2_full_conversion_manifest": str(CONVERSION_MANIFEST_PATH),
            "p2a2_full_conversion_manifest_sha256": sha256_file(
                CONVERSION_MANIFEST_PATH
            ),
            "p2_selected_pt_integrity_check": (
                "current_sha256_and_bytes"
                if _FULL_INPUT_HASH_AUDIT
                else "current_bytes_plus_frozen_p2a2_full_sha256_audit"
            ),
            "test_artifacts_authorized": False,
        }
    )
    development = dict(config["development_only_contract"])
    development.update(
        {
            "name": "p2a3_frozen_v2_train_plus_original_validation_only",
            "combined_test_bearing_index_read": False,
            "p2a2_train_validation_conversion_manifest_read": True,
            "p2_representation": _ACTIVE_REPRESENTATION,
            "test_pt_read": False,
            "test_prediction_read": False,
            "test_checkpoint_inference": False,
        }
    )
    config["development_only_contract"] = development
    return config


def _p2_validate_resume_config(saved: dict, current: dict) -> None:
    ORIGINAL_VALIDATE_RESUME_CONFIG(saved, current)
    keys = (
        "p2a3_stage",
        "p2_representation",
        "p2_input_dimensions",
        "p2_pt_path_column",
        "p2_trainer_loader_pt_column",
        "p2_pt_sha256_column",
        "p2_pt_bytes_column",
        "base_trainer_script_sha256",
        "base_architecture_sha256",
        "p2_behavior_protocol_sha256",
        "p2a3_training_spec_sha256",
        "p2a3_freeze_manifest_sha256",
        "p2a2_full_conversion_manifest",
        "p2a2_full_conversion_manifest_sha256",
        "test_artifacts_authorized",
    )
    mismatches = {
        key: (saved.get(key), current.get(key))
        for key in keys
        if saved.get(key) != current.get(key)
    }
    if mismatches:
        raise RuntimeError(f"P2 resume configuration mismatch: {mismatches}")


def install_representation(representation: str, full_input_hash_audit: bool = False) -> None:
    global _ACTIVE_REPRESENTATION, _FULL_INPUT_HASH_AUDIT
    if representation not in REPRESENTATIONS:
        raise ValueError(f"unsupported P2 representation: {representation}")
    _ACTIVE_REPRESENTATION = representation
    _FULL_INPUT_HASH_AUDIT = bool(full_input_hash_audit)
    settings = REPRESENTATIONS[representation]

    base.IN_DIMS.clear()
    base.IN_DIMS.update(settings["dimensions"])
    contract = copy.deepcopy(base.SPLIT_CONTRACTS["v2_strict40"])
    contract["output_root"] = RUNS_ROOT
    contract["feature_profile"] = settings["feature_profile"]
    base.SPLIT_CONTRACTS["v2_strict40"] = contract
    base.read_frozen_v2_development_manifests = (
        lambda: read_p2_development_manifests(representation)
    )
    base.config_from_args = _p2_config_from_args
    base.validate_resume_config = _p2_validate_resume_config


def fixed_base_args(
    representation: str,
    seed: int,
    preflight_only: bool,
) -> argparse.Namespace:
    return argparse.Namespace(
        mode="ast_event_param_context",
        split_contract="v2_strict40",
        run_label=f"p2a3_primary_{representation}_v1",
        seed=seed,
        determinism="strict",
        device="cpu" if preflight_only else "cuda",
        batch_size=4,
        num_workers=2,
        max_epochs=30,
        min_epochs=8,
        patience=6,
        min_delta=0.0005,
        learning_rate=3e-4,
        optimizer="adam",
        weight_decay=0.0,
        hidden_dim=64,
        gradient_accumulation_steps=1,
        gradient_clip=1.0,
        malicious_class_weight=1.5,
        component_weighting="inverse_sqrt",
        progress_every=500,
        resume="auto",
        checkpoint_metric="ap",
        validation_only=True,
        preflight_only=preflight_only,
    )


def run_tag(representation: str, seed: int) -> str:
    return (
        "v10c_formal_v2_strict40_ast_event_param_context_type_balanced_"
        f"ckpt_ap_inverse_sqrt_p2a3_primary_{representation}_v1_seed{seed}"
    )


def run_directory(representation: str, seed: int) -> Path:
    return RUNS_ROOT / run_tag(representation, seed)


def validate_completed_result(representation: str, seed: int) -> dict:
    out_dir = run_directory(representation, seed)
    result_path = out_dir / "validation_result.json"
    result = _load_json(result_path)
    if result.get("status") != "validation_complete":
        raise RuntimeError(f"invalid completed status in {result_path}")
    if int(result.get("seed", -1)) != seed:
        raise RuntimeError(f"completed seed mismatch in {result_path}")
    if result.get("mode") != "ast_event_param_context":
        raise RuntimeError(f"completed mode mismatch in {result_path}")
    if bool(result.get("test_evaluated", True)):
        raise RuntimeError(f"completed P2 validation result claims test evaluation: {result_path}")
    config = result.get("config", {})
    expected = {
        "p2_representation": representation,
        "seed": seed,
        "checkpoint_metric": "ap",
        "component_weighting": "inverse_sqrt",
        "optimizer": "adam",
        "weight_decay": 0.0,
        "validation_only": None,
    }
    for key, expected_value in expected.items():
        if key == "validation_only":
            continue
        if config.get(key) != expected_value:
            raise RuntimeError(
                f"completed config mismatch for {key}: "
                f"expected={expected_value!r} actual={config.get(key)!r}"
            )
    current_freeze_sha256 = sha256_file(FREEZE_MANIFEST_PATH)
    if config.get("p2a3_freeze_manifest_sha256") != current_freeze_sha256:
        raise RuntimeError("completed result was created under a different P2-A3 freeze manifest")
    if config.get("p2a3_training_spec_sha256") != sha256_file(SPEC_PATH):
        raise RuntimeError("completed result was created under a different P2-A3 spec")
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
        raise RuntimeError(f"completed P2 result is missing artifacts: {missing}")
    forbidden = [
        path
        for path in (out_dir / "test_predictions.csv", out_dir / "final_result.json")
        if path.exists()
    ]
    if forbidden:
        raise RuntimeError(f"test artifacts are forbidden in P2-A3a: {forbidden}")
    predictions = pd.read_csv(out_dir / "validation_predictions.csv", low_memory=False)
    if len(predictions) != EXPECTED_SPLIT_COUNTS["val"]:
        raise RuntimeError(
            f"completed validation prediction count drift: {len(predictions)}"
        )
    if predictions["graph_id"].astype(str).duplicated().any():
        raise RuntimeError("completed validation predictions contain duplicate graph_id")
    return result


def run_one(
    representation: str,
    seed: int,
    preflight_only: bool = False,
    full_input_hash_audit: bool = False,
) -> int:
    validate_freeze_manifest()
    install_representation(representation, full_input_hash_audit)
    if not preflight_only:
        out_dir = run_directory(representation, seed)
        forbidden = [
            path
            for path in (out_dir / "test_predictions.csv", out_dir / "final_result.json")
            if path.exists()
        ]
        if forbidden:
            raise RuntimeError(f"test artifacts are forbidden in P2-A3a: {forbidden}")
        result_path = out_dir / "validation_result.json"
        if result_path.is_file():
            validate_completed_result(representation, seed)
            print(
                f"[SKIP COMPLETE] representation={representation} seed={seed} "
                f"result={result_path}"
            )
            return 0

    args = fixed_base_args(representation, seed, preflight_only)
    print(
        f"[P2-A3] representation={representation} seed={seed} "
        f"mode={'preflight' if preflight_only else 'validation-only training'}"
    )
    print("[P2-A3] test manifest/PT/predictions/loader: LOCKED")
    base.train(args)
    if preflight_only:
        return 0

    result_path = run_directory(representation, seed) / "validation_result.json"
    if result_path.is_file():
        validate_completed_result(representation, seed)
        return 0

    last_checkpoint = run_directory(representation, seed) / "checkpoints/last_state.pt"
    if last_checkpoint.is_file():
        print(
            "[P2-A3 INTERRUPTED] No completed validation result yet. "
            f"Rerun the identical matrix command; resume checkpoint={last_checkpoint}"
        )
        return 130
    # The inherited trainer catches KeyboardInterrupt and returns normally.  If
    # Ctrl+C arrives during epoch 1, no completed-epoch checkpoint exists yet;
    # that is still a clean interruption, but the first epoch must restart.
    print(
        "[P2-A3 INTERRUPTED] No epoch had completed, so no last_state.pt exists yet. "
        "Rerun the identical matrix command; this configuration restarts at epoch 1."
    )
    return 130


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--representation", choices=REPRESENTATION_ORDER, required=True)
    parser.add_argument("--seed", type=int, choices=SEEDS, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument(
        "--full-input-hash-audit",
        action="store_true",
        help=(
            "Re-hash every selected PT in addition to the already frozen P2-A2F "
            "independent SHA audit. Intended for CPU preflight, not each epoch run."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.full_input_hash_audit and not args.preflight_only:
        raise ValueError("--full-input-hash-audit is authorized only with --preflight-only")
    return run_one(
        args.representation,
        args.seed,
        preflight_only=args.preflight_only,
        full_input_hash_audit=args.full_input_hash_audit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
