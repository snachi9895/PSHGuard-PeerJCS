#!/usr/bin/env python3
"""Finalize S10-C after the static-task execution-metadata corrigendum.

The frozen scientific models, thresholds, policies, and canonical test
population are unchanged.  This finalizer overlays only the corrected complete
static-tool predictions, reuses the frozen report implementation, verifies the
full 2,128-row population, and creates an explicit corrigendum seal without
overwriting any original one-shot artifact or receipt.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import run_s10b_one_shot_test_runner as runner


HERE = Path(__file__).resolve().parent
SCRIPT_PATH = Path(__file__).resolve()
EXPECTED_ROWS = 2128


def atomic_json(value: Any, path: Path) -> None:
    runner.core.atomic_json(value, path)


def safe_symlink(target: Path, link: Path) -> None:
    target = target.resolve()
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        if link.resolve() != target:
            raise RuntimeError(f"overlay symlink drift: {link}")
        return
    if link.exists():
        raise RuntimeError(f"overlay path exists and is not a symlink: {link}")
    os.symlink(target, link, target_is_directory=True)


def add_inventory(inventory: dict[str, str], base: Path, prefix: str) -> None:
    for path in sorted(base.rglob("*")):
        if path.is_file() and not path.name.endswith(".tmp"):
            inventory[f"{prefix}/{path.relative_to(base)}"] = runner.sha256_file(path)


def atomic_csv(rows: list[dict[str, str]], fieldnames: list[str], path: Path) -> None:
    """Write a report-only CSV without mutating the frozen native output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def prepare_static_reporting_overlay(static_root: Path, reporting_root: Path) -> None:
    """Materialize the frozen end-to-end treatment of non-evaluable tools.

    The native OSSGadget parser intentionally records an unevaluable prediction
    as ``unknown``.  The frozen experiment policy, however, evaluates such rows
    end-to-end as benign/no-alert.  The main report consumes binary columns, so
    create a separate, auditable report view with only those policy-mandated
    cells mapped to zero.  Native predictions remain byte-for-byte unchanged.
    """
    safe_symlink(static_root / "guarddog", reporting_root / "guarddog")
    configurations = {
        "bandit4mal": ("pred_custom_rule", 1),
        "ossgadget": ("pred_any_rule", 3),
    }
    for tool, (policy_column, expected_unknown) in configurations.items():
        source_summary_path = static_root / tool / "s10_static_summary.json"
        source_summary = runner.core.load_json(source_summary_path)
        source_predictions = Path(source_summary["predictions"])
        rows = runner.core.read_csv(source_predictions)
        if len(rows) != EXPECTED_ROWS:
            raise RuntimeError(f"{tool} reporting source population drift")
        fieldnames = list(rows[0])
        changed: list[str] = []
        for row in rows:
            value = str(row[policy_column]).strip().lower()
            if value == "unknown":
                if str(row.get("is_evaluable", "")).strip().lower() not in {"false", "0"}:
                    raise RuntimeError(f"{tool} unknown prediction marked evaluable")
                row[policy_column] = "0"
                changed.append(row["sample_id"])
            elif value not in {"0", "1", "false", "true", "benign", "malicious"}:
                raise RuntimeError(f"unexpected {tool} policy value: {value!r}")
        if len(changed) != expected_unknown:
            raise RuntimeError(
                f"unexpected {tool} non-evaluable population: {len(changed)}"
            )

        report_predictions = (
            reporting_root / tool / "analysis" / f"{tool}_predictions_end_to_end.csv"
        )
        atomic_csv(rows, fieldnames, report_predictions)
        report_summary = dict(source_summary)
        report_summary.update(
            {
                "predictions": str(report_predictions.resolve()),
                "predictions_sha256": runner.sha256_file(report_predictions),
                "reporting_corrigendum": {
                    "scientific_policy_changed": False,
                    "source_predictions": str(source_predictions.resolve()),
                    "source_predictions_sha256": runner.sha256_file(source_predictions),
                    "policy": "non-evaluable samples are benign/no-alert in end-to-end evaluation",
                    "policy_column": policy_column,
                    "mapped_unknown_to_zero_rows": len(changed),
                    "mapped_sample_ids": sorted(changed),
                },
            }
        )
        atomic_json(report_summary, reporting_root / tool / "s10_static_summary.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--run-root", required=True)
    args = parser.parse_args()

    authorization_path = Path(args.authorization).resolve()
    run_root = Path(args.run_root).resolve()
    if not run_root.is_dir():
        raise FileNotFoundError(run_root)

    spec = runner.load_spec()
    runner.validate_freeze()
    auth = runner.core.validate_authorization(authorization_path, verify_input_hashes=True)
    auth["authorization_file_sha256"] = runner.sha256_file(authorization_path)

    correction_root = run_root / "corrigenda/static_task_split_v1"
    correction_audit_path = correction_root / "s10c_static_task_split_corrigendum_audit.json"
    correction_audit = runner.core.load_json(correction_audit_path)
    if correction_audit.get("pass") is not True:
        raise RuntimeError("static task metadata corrigendum did not pass")
    corrected_task_path = Path(correction_audit["output"]["path"])
    if runner.sha256_file(corrected_task_path) != correction_audit["output"]["sha256"]:
        raise RuntimeError("corrected static task index SHA drift")

    static_root = run_root / "stages/50_static_tools_corrigendum"
    for tool in ("bandit4mal", "guarddog", "ossgadget"):
        summary_path = static_root / tool / "s10_static_summary.json"
        summary = runner.core.load_json(summary_path)
        if summary.get("status") != "PASS_EXACT_V2_NATIVE_POLICY":
            raise RuntimeError(f"incomplete corrected static tool: {tool}")
        if int(summary.get("reused_exact_sha_rows", -1)) != 1597:
            raise RuntimeError(f"unexpected exact-reuse population: {tool}")
        if int(summary.get("newly_inferred_rows", -1)) != 531:
            raise RuntimeError(f"unexpected new-inference population: {tool}")
        predictions = Path(summary["predictions"])
        rows = runner.core.read_csv(predictions)
        if len(rows) != EXPECTED_ROWS or len({row["sample_id"] for row in rows}) != EXPECTED_ROWS:
            raise RuntimeError(f"corrected static prediction population drift: {tool}")
        if runner.sha256_file(predictions) != summary["predictions_sha256"]:
            raise RuntimeError(f"corrected static prediction SHA drift: {tool}")

    static_reporting_root = run_root / "corrigenda/static_reporting_v2"
    prepare_static_reporting_overlay(static_root, static_reporting_root)

    # Earlier overlays are retained as evidence of fail-closed integration
    # attempts. v3 contains only the frozen end-to-end interface corrections.
    overlay = run_root / "corrigenda/report_overlay_v3"
    safe_symlink(run_root / "stages/30_proposed_metrics", overlay / "stages/30_proposed_metrics")
    safe_symlink(run_root / "stages/40_ea4mp", overlay / "stages/40_ea4mp")
    safe_symlink(static_reporting_root, overlay / "stages/50_static_tools")
    safe_symlink(run_root / "stages/60_archived_baselines", overlay / "stages/60_archived_baselines")

    report_root = overlay / "stages/70_report"
    report_root.mkdir(parents=True, exist_ok=True)
    outputs = runner.stage_report(report_root, overlay, spec, auth)
    if len(outputs) != 5 or any(not path.is_file() for path in outputs):
        raise RuntimeError("corrected final report output inventory drift")

    receipt_path = overlay / "receipts/70_report_corrigendum.json"
    receipt = {
        "status": "COMPLETE_EXECUTION_CORRIGENDUM",
        "scientific_protocol_changed": False,
        "authorization_sha256": runner.sha256_file(authorization_path),
        "corrigendum_audit_sha256": runner.sha256_file(correction_audit_path),
        "corrected_task_index_sha256": runner.sha256_file(corrected_task_path),
        "finalizer_sha256": runner.sha256_file(SCRIPT_PATH),
        "static_reporting_overlay_sha256": {
            tool: {
                "summary": runner.sha256_file(
                    static_reporting_root / tool / "s10_static_summary.json"
                ),
                "predictions": runner.sha256_file(
                    static_reporting_root
                    / tool
                    / "analysis"
                    / f"{tool}_predictions_end_to_end.csv"
                ),
            }
            for tool in ("bandit4mal", "ossgadget")
        },
        "outputs_sha256": {str(path.relative_to(overlay)): runner.sha256_file(path) for path in outputs},
    }
    atomic_json(receipt, receipt_path)

    inventory: dict[str, str] = {}
    for stage in (
        "00_authorization",
        "10_hgt",
        "20_modernbert",
        "30_proposed_metrics",
        "40_ea4mp",
        "60_archived_baselines",
    ):
        add_inventory(inventory, run_root / f"stages/{stage}", f"original/stages/{stage}")
        stage_receipt = run_root / f"receipts/{stage}.json"
        if not stage_receipt.is_file():
            raise RuntimeError(f"original completed stage receipt missing: {stage}")
        inventory[f"original/receipts/{stage}.json"] = runner.sha256_file(stage_receipt)
    add_inventory(inventory, correction_root, "corrigendum/static_task_split_v1")
    add_inventory(inventory, static_root, "corrigendum/stages/50_static_tools")
    add_inventory(inventory, static_reporting_root, "corrigendum/static_reporting_v2")
    add_inventory(inventory, report_root, "corrigendum/stages/70_report")
    inventory["corrigendum/receipts/70_report_corrigendum.json"] = runner.sha256_file(receipt_path)

    seal_path = overlay / "stages/80_seal/s10_exact_v2_execution_corrigendum_seal.json"
    seal = {
        "status": "SEALED_ONE_SHOT_EXACT_V2_FINAL_TEST_EXECUTION_CORRIGENDUM",
        "authorization_nonce_sha256": hashlib.sha256(auth["nonce"].encode()).hexdigest(),
        "authorization_file_sha256": auth["authorization_file_sha256"],
        "reason": "historical split/component execution metadata prevented 531 authorized rows from reaching frozen static pipelines",
        "reporting_interface_correction": "four frozen non-evaluable rows (Bandit4Mal=1, OSSGadget=3) mapped from unknown to no-alert exactly as pre-registered",
        "changed_scientific_models_thresholds_policies_or_labels": False,
        "original_artifacts_overwritten": False,
        "canonical_rows": EXPECTED_ROWS,
        "inventory": inventory,
        "no_refit_retraining_threshold_search_or_model_selection": True,
    }
    atomic_json(seal, seal_path)
    print(f"[S10-C FINALIZE CORRIGENDUM] PASS report={report_root}")
    print(f"seal={seal_path}")


if __name__ == "__main__":
    main()
