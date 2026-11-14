#!/usr/bin/env python3
"""Inspect the frozen PSHGuard tables using Python's standard library only."""
import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_samples(artifact):
    folder = artifact / "data/manifests"
    spec = json.loads((folder / "pshguard_split_manifest.summary.json").read_text())
    rows = []
    for part in spec["manifest_parts"]:
        chunk = read_csv(folder / part["file"])
        if len(chunk) != part["rows"]:
            raise ValueError(f"Wrong row count: {part['file']}")
        rows.extend(chunk)
    if len(rows) != 20878 or len({r["sample_id"] for r in rows}) != len(rows):
        raise ValueError("Expected exactly 20,878 distinct sample IDs")
    return rows


def summarize(artifact):
    rows = load_samples(artifact)
    access = read_csv(artifact / "data/access/ORIGINAL_PACKAGE_ACCESS.csv")
    by_id = {r["sample_id"]: r for r in access}
    if len(by_id) != len(access) or set(by_id) != {r["sample_id"] for r in rows}:
        raise ValueError("Access index and split manifest differ")
    components = defaultdict(set)
    for row in rows:
        components[row["source_clone_component_id"]].add(row["split"])
        original = by_id[row["sample_id"]]
        for field in ("package_name", "version", "label_int", "split", "archive_sha256"):
            if row[field] != original[field]:
                raise ValueError(f"Mismatched {field}: {row['sample_id']}")
    if any(len(v) != 1 for v in components.values()):
        raise ValueError("A relatedness component crosses data partitions")
    return {
        "samples": len(rows),
        "splits": dict(sorted(Counter(r["split"] for r in rows).items())),
        "labels": dict(sorted(Counter(r["label_int"] for r in rows).items())),
        "relatedness_components": len(components),
        "manifest_source_groups": dict(sorted(Counter(r["source_group"] for r in rows).items())),
        "retrieval_channels": dict(sorted(Counter(r["source_kind"] for r in access).items())),
        "original_archive_bytes_not_embedded": sum(int(r["archive_size_bytes"]) for r in access),
        "access_manifest_join": "PASS",
        "component_partition_isolation": "PASS",
    }


def point_metrics(rows):
    labels = [int(r["y_true"]) for r in rows]
    decisions = [int(r["prediction"]) for r in rows]
    scores = [float(r["score"]) for r in rows]
    if any(x not in (0, 1) for x in labels + decisions) or not all(map(math.isfinite, scores)):
        raise ValueError("Non-binary labels/decisions or non-finite scores")
    tp = sum(y == 1 and p == 1 for y, p in zip(labels, decisions))
    fp = sum(y == 0 and p == 1 for y, p in zip(labels, decisions))
    fn = sum(y == 1 and p == 0 for y, p in zip(labels, decisions))
    tn = sum(y == 0 and p == 0 for y, p in zip(labels, decisions))
    positives, negatives = tp + fn, fp + tn
    if not positives or not negatives:
        raise ValueError("Both classes are required for AP/AUROC")
    # Average precision: group tied scores at a common decision threshold.
    grouped = defaultdict(lambda: [0, 0])
    for score, label in zip(scores, labels):
        grouped[score][label] += 1
    cumulative_total = cumulative_positive = 0
    average_precision = 0.0
    for score in sorted(grouped, reverse=True):
        negative, positive = grouped[score]
        cumulative_total += positive + negative
        cumulative_positive += positive
        average_precision += (positive / positives) * (cumulative_positive / cumulative_total)
    # AUROC: pairwise ordering with half credit for tied positive/negative scores.
    negatives_below = 0
    correctly_ranked = 0.0
    for score in sorted(grouped):
        negative, positive = grouped[score]
        correctly_ranked += positive * (negatives_below + 0.5 * negative)
        negatives_below += negative
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "average_precision": average_precision,
        "auroc": correctly_ranked / (positives * negatives),
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / positives,
        "f1": 2 * tp / (2 * tp + fp + fn),
        "fpr": fp / negatives,
    }


def verify_metrics(artifact):
    manifest = {r["sample_id"]: r for r in load_samples(artifact) if r["split"] == "test"}
    reference = {r["method"]: r for r in read_csv(
        artifact / "data/statistics/final_test/s10_exact_v2_final_test_main_table.csv")}
    identities = {
        "graph": "Practical HGT (ours, graph branch)",
        "modernbert": "ModernBERT (auxiliary sequence branch)",
        "fusion": "HGT plus ModernBERT (ours)",
    }
    report = {"scope": "Recalculation from saved final-test predictions; no model inference",
              "units": "Ratios in [0,1]; sample SD across three runs", "branches": {}}
    largest_error = 0.0
    for prefix, method in identities.items():
        per_seed = []
        for seed in (1001, 1002, 1003):
            rows = read_csv(artifact / f"data/predictions/final_test/{prefix}_seed{seed}_test_predictions.csv")
            ids = [r["sample_id"] for r in rows]
            if len(ids) != 2128 or len(set(ids)) != 2128 or set(ids) != set(manifest):
                raise ValueError(f"Incorrect test identities: {prefix}, seed {seed}")
            if any(r["y_true"] != manifest[r["sample_id"]]["label_int"] for r in rows):
                raise ValueError(f"Incorrect test labels: {prefix}, seed {seed}")
            per_seed.append({"seed": seed, **point_metrics(rows)})
        aggregate = {}
        for metric in ("average_precision", "auroc", "precision", "recall", "f1", "fpr"):
            values = [r[metric] for r in per_seed]
            for suffix, value in (("mean", statistics.mean(values)), ("sd", statistics.stdev(values))):
                key = f"{metric}_{suffix}"
                error = abs(value - float(reference[method][key]))
                largest_error = max(largest_error, error)
                if error > 1e-12:
                    raise ValueError(f"Saved table mismatch: {method}, {key}, error={error}")
                aggregate[key] = value
        report["branches"][prefix] = {"runs": per_seed, "aggregate": aggregate}
    report["largest_absolute_error_against_frozen_table"] = largest_error
    report["status"] = "PASS"
    return report


def export_samples(artifact, destination):
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite {destination}")
    rows = load_samples(artifact)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return {"export": str(destination), "rows": len(rows),
            "operation": "Concatenation of the eleven original CSV shards; no field/value changes"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=ROOT, help="Repository root containing data/ and metadata/ (default: this repository)")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--summary", action="store_true")
    actions.add_argument("--verify-metrics", action="store_true")
    actions.add_argument("--export-samples", metavar="NEW_CSV")
    args = parser.parse_args()
    if args.verify_metrics:
        report = verify_metrics(args.artifact)
    elif args.export_samples:
        report = export_samples(args.artifact, args.export_samples)
    else:
        report = summarize(args.artifact)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
