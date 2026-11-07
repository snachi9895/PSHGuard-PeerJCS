"""Regenerate the PeerJ data figures from saved aggregate result files."""

from pathlib import Path
import argparse
import csv
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
MANUSCRIPT = HERE.parents[1]
BLUE, PLUM, GOLD = "#416F96", "#946684", "#B88942"
GRAY, LIGHT, INK = "#74818A", "#DCE6ED", "#26333C"
METRICS = [("AP", BLUE, "o", "-"), ("Recall", PLUM, "s", "--"), ("F1", GOLD, "^", "-.")]
POINTS = []
OUTPUTS = {}


def read_csv(name):
    with (DATA / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def record(figure, panel, label, mean, spread=None, lower=None, upper=None):
    POINTS.append({
        "figure": figure, "panel": panel, "label": label,
        "mean": float(mean),
        "sample_sd": None if spread is None else float(spread),
        "ci_lower": None if lower is None else float(lower),
        "ci_upper": None if upper is None else float(upper),
    })


def axis_style(ax, grid="y"):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis=grid, color="#E2E7EB", linewidth=0.55)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, width=0.6, colors=INK, pad=3)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)


def panel_title(ax, label, title):
    ax.set_title(f"{label}  {title}", loc="left", fontsize=11, fontweight="bold", pad=12)


def save(fig, name, pdf_dir, preview_dir):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    clipped = []
    for item in fig.findobj(matplotlib.text.Text):
        if item.get_visible() and item.get_text().strip():
            box = item.get_window_extent(renderer)
            if box.x0 < -1 or box.y0 < -1 or box.x1 > fig.bbox.width + 1 or box.y1 > fig.bbox.height + 1:
                clipped.append(item.get_text())
    if clipped:
        raise RuntimeError(f"{name} has text outside the canvas: {clipped}")
    paths = [pdf_dir / f"{name}.pdf", preview_dir / f"{name}.png", preview_dir / f"{name}.svg"]
    for path in paths:
        kwargs = {"dpi": 300, "facecolor": "white"}
        if path.suffix == ".pdf":
            kwargs["metadata"] = {"CreationDate": None, "ModDate": None}
        fig.savefig(path, **kwargs)
        OUTPUTS[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    plt.close(fig)


def branch_comparison(pdf_dir, preview_dir):
    rows = read_csv("branch_comparison.csv")
    absolute = [row for row in rows if row["panel"] == "a"]
    paired = [row for row in rows if row["panel"] == "b"]
    fig = plt.figure(figsize=(6.5, 3.5))
    left = fig.add_axes([0.10, 0.22, 0.32, 0.61])
    right = fig.add_axes([0.65, 0.22, 0.32, 0.61])
    for i, (row, color, marker) in enumerate(zip(absolute, [BLUE, PLUM, GOLD], ["o", "s", "^"])):
        mean, sd = float(row["mean_pp"]), float(row["sample_sd_pp"])
        left.errorbar(i, mean, yerr=sd, fmt=marker, color=color, capsize=3.5, markersize=6)
        left.text(i, mean + sd + 0.45, f"{mean:.3f}", ha="center", fontsize=9)
        record(3, "a", row["name"], mean, sd)
    left.set(xticks=[0, 1, 2], xticklabels=["HGT", "Modern-\nBERT", "PSHGuard"],
             xlim=(-0.55, 2.55), ylim=(84, 97.7), yticks=[84, 88, 92, 96], ylabel="Test F1 (%)")
    left.tick_params(axis="x", labelsize=9.3)
    labels = []
    for i, row in enumerate(paired):
        mean, low, high = (float(row[key]) for key in ("mean_pp", "ci95_lower_pp", "ci95_upper_pp"))
        y = i + (i >= 3)
        right.errorbar(mean, y, xerr=[[mean-low], [high-mean]], fmt="o",
                       color=BLUE if i < 3 else PLUM, capsize=3, markersize=5)
        labels.append({"f1": "F1", "recall": "Recall", "precision": "Precision"}[row["metric"]])
        record(3, "b", row["name"], mean, lower=low, upper=high)
    right.set(yticks=[0, 1, 2, 4, 5, 6], yticklabels=labels, ylim=(6.75, -1.1),
              xlim=(-3.3, 9.1), xticks=[-3, 0, 3, 6, 9], xlabel="PSHGuard − branch (pp)")
    right.text(8.85, -0.5, "vs HGT", ha="right", color=BLUE, fontsize=9.2)
    right.text(8.85, 3.5, "vs ModernBERT", ha="right", color=PLUM, fontsize=9.2)
    right.axvline(0, color=GRAY, ls="--", lw=0.8)
    right.axhline(2.9, color="#CCD4DA", lw=0.7)
    panel_title(left, "a", "Branch F1")
    panel_title(right, "b", "Paired differences")
    axis_style(left)
    axis_style(right, "x")
    fig.text(0.10, 0.035, "2,128 test packages · 3 runs", fontsize=9.5, color=GRAY)
    save(fig, "figure_03_branch_complementarity", pdf_dir, preview_dir)


def ablation_and_budget(pdf_dir, preview_dir):
    graph = read_csv("single_hgt.csv")
    reference = json.loads((DATA / "fusion_reference.json").read_text(encoding="utf-8"))
    fusion = reference["same_seed_one_graph_one_sequence_fusion"]["three_seed_summary_mean_sample_sd"]
    budgets = read_csv("dual_branch_budgets.csv")
    intervals = read_csv("fusion_ablation_ci.csv")
    conditions = ["practical", "without_event", "without_param_context", "ast_module_only"]
    fig = plt.figure(figsize=(6.5, 5.5))
    a = fig.add_axes([0.10, 0.61, 0.36, 0.25])
    b = fig.add_axes([0.61, 0.61, 0.36, 0.25])
    c = fig.add_axes([0.10, 0.14, 0.36, 0.27])
    d = fig.add_axes([0.68, 0.14, 0.29, 0.27])
    for metric, color, marker, line in METRICS:
        key = {"AP": "average_precision", "Recall": "recall", "F1": "f1"}[metric]
        protocol = "raw_argmax" if metric == "AP" else "component_isolated_oof"
        means, deviations = [], []
        for condition in conditions:
            row = next(row for row in graph if row["condition"] == condition and row["metric"] == key and row["metric_protocol"] == protocol)
            means.append(float(row["mean_percent"]))
            deviations.append(float(row["sample_sd_percentage_points"]))
            record(4, "a", f"{condition}/{metric}/{protocol}", means[-1], deviations[-1])
        a.errorbar(range(4), means, yerr=deviations, color=color, marker=marker, ls=line,
                   markersize=4.3, capsize=2, lw=1.0, label=metric)
        means, deviations = [], []
        for condition in conditions:
            means.append(fusion[condition][key]["mean"] * 100)
            deviations.append(fusion[condition][key]["sample_standard_deviation"] * 100)
            record(4, "b", f"{condition}/{metric}", means[-1], deviations[-1])
        b.errorbar(range(4), means, yerr=deviations, color=color, marker=marker, ls=line,
                   markersize=4.3, capsize=2, lw=1.0)
        means = [float(row[f"{key}_mean"]) * 100 for row in budgets]
        deviations = [float(row[f"{key}_sample_standard_deviation"]) * 100 for row in budgets]
        c.errorbar(range(4), means, yerr=deviations, color=color, marker=marker, ls=line,
                   markersize=4.3, capsize=2, lw=1.0)
        for row, mean, sd in zip(budgets, means, deviations):
            record(4, "c", f"{row['budget']}/{metric}", mean, sd)
    categories = ["Full", "−Event", "−Param/\ncontext", "Module+\nAST"]
    for ax in [a, b]:
        ax.set(xticks=range(4), xticklabels=categories, xlim=(-0.35, 3.35))
        ax.tick_params(axis="x", labelsize=9.1)
        axis_style(ax)
    a.set(ylim=(80, 100), yticks=[80, 85, 90, 95, 100], ylabel="Validation score (%)")
    b.set(ylim=(89, 100), yticks=[90, 95, 100], ylabel="Validation OOF score (%)")
    c.set(xticks=range(4), xticklabels=["4", "8", "16", "32"], xlim=(-0.35, 3.35),
          ylim=(90, 100), yticks=[90, 95, 100], ylabel="Validation OOF score (%)", xlabel="Graph-file limit")
    c.axvspan(1.75, 2.25, color=LIGHT, alpha=0.65, zorder=0)
    c.get_xticklabels()[2].set_fontweight("bold")
    labels = ["−Event", "−Param/\ncontext", "Module+\nAST"]
    for i, row in enumerate(intervals):
        mean, low, high = (float(row[key]) for key in ("observed_full_minus_ablation_pp", "ci95_lower_pp", "ci95_upper_pp"))
        d.errorbar(mean, i, xerr=[[mean-low], [high-mean]], fmt="o", color=GOLD,
                   capsize=3, markersize=5)
        record(4, "d", row["ablation"], mean, lower=low, upper=high)
    d.set(yticks=range(3), yticklabels=labels, ylim=(2.55, -0.55),
          xlim=(-1.0, 2.2), xticks=[-1, 0, 1, 2], xlabel="Full − ablated F1 (pp)")
    d.axvline(0, color=GRAY, lw=0.8, ls="--")
    panel_title(a, "a", "Single HGT")
    panel_title(b, "b", "Same-seed fusion")
    panel_title(c, "c", "File budget")
    panel_title(d, "d", "Fusion F1 differences")
    axis_style(c)
    axis_style(d, "x")
    handles = [Line2D([], [], color=color, marker=marker, ls=line, label=label) for label, color, marker, line in METRICS]
    fig.legend(handles=handles, ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.51, 0.995))
    fig.text(0.10, 0.018, "2,137 validation packages · 3 runs · Adopted graph-file limit: 16", fontsize=9.4, color=GRAY)
    save(fig, "figure_04_ablation_budget", pdf_dir, preview_dir)


def efficiency(pdf_dir, preview_dir):
    rows = read_csv("efficiency.csv")
    fig, axes = plt.subplots(1, 3, figsize=(6.5, 3.0))
    fig.subplots_adjust(left=0.08, right=0.985, bottom=0.29, top=0.79, wspace=0.55)
    specs = [("throughput", "a", "Throughput", "Packages/s", [0, 125]),
             ("p95", "b", "p95 latency", "ms", [0, 34]),
             ("checkpoint_mib", "c", "Checkpoint", "MiB (log scale)", None)]
    for ax, (key, letter, title, ylabel, limits) in zip(axes, specs):
        values = [float(row[key]) for row in rows]
        ax.bar(range(3), values, color=[BLUE, PLUM, GOLD], width=0.56)
        if limits:
            ax.set_ylim(limits)
        else:
            ax.set_yscale("log")
            ax.set_ylim(0.65, 4500)
            ax.set_yticks([1, 10, 100, 1000], labels=["1", "10", "100", "1000"])
        for i, (row, value) in enumerate(zip(rows, values)):
            offset = value * 1.12 if key == "checkpoint_mib" else value + (1 if key == "p95" else 3)
            label = f"{value:.2f}" if value < 10 else f"{value:.1f}"
            ax.text(i, offset, label, ha="center", va="bottom", fontsize=9.2)
            record(5, letter, row["name"], value)
        ax.set(xticks=range(3), xticklabels=["HGT", "Modern-\nBERT", "PSH-\nGuard*"], ylabel=ylabel, xlim=(-0.65, 2.85))
        ax.tick_params(axis="x", labelsize=9.1)
        panel_title(ax, letter, title)
        axis_style(ax)
    fig.text(0.08, 0.055, "* Serial combination estimate from the two branch profiles.", fontsize=9.4, color=GRAY)
    save(fig, "figure_05_efficiency", pdf_dir, preview_dir)


def perturbations_and_coverage(pdf_dir, preview_dir):
    rows = read_csv("perturbations_and_strata.csv")
    fig = plt.figure(figsize=(6.5, 3.8))
    left = fig.add_axes([0.11, 0.25, 0.35, 0.54])
    right = fig.add_axes([0.73, 0.18, 0.24, 0.61])
    metrics = ["AP", "AUROC", "Precision", "Recall", "F1", "FPR"]
    conditions = ["Identifier rename", "Benign-file padding"]
    for j, (condition, color) in enumerate(zip(conditions, [BLUE, PLUM])):
        values = [float(next(row["value_percent_or_pp"] for row in rows if row["panel"] == "perturbation_delta" and row["condition"] == condition and row["metric"] == metric)) for metric in metrics]
        left.bar(np.arange(6) + (j-0.5)*0.34, values, width=0.31, color=color,
                 label=condition, hatch="" if j == 0 else "///", edgecolor="white", linewidth=0.25)
        for metric, value in zip(metrics, values):
            record(6, "a", f"{condition}/{metric}", value)
    left.set(xticks=range(6), xticklabels=["AP", "AUROC", "Prec.", "Recall", "F1", "FPR"],
             ylim=(-0.16, 0.25), ylabel="Change (pp)")
    left.tick_params(axis="x", labelrotation=45, labelsize=9)
    left.axhline(0, color=INK, lw=0.7)
    left.legend(fontsize=8.7, loc="upper left", bbox_to_anchor=(-0.03, 1.015), handlelength=1.2)
    group_rows = [row for row in rows if row["panel"] == "observational_subgroup"]
    groups = list(dict.fromkeys(row["condition"] for row in group_rows))
    for j, (metric, color, marker) in enumerate([("Recall", PLUM, "o"), ("F1", GOLD, "s")]):
        values = [float(next(row["value_percent_or_pp"] for row in group_rows if row["condition"] == group and row["metric"] == metric)) for group in groups]
        right.plot(values, np.arange(8)+(j-0.5)*0.18, linestyle="none", marker=marker,
                   color=color, markersize=4.8, label=metric)
        for group, value in zip(groups, values):
            record(6, "b", f"{group}/{metric}", value)
    right.set(yticks=range(8), yticklabels=[s.replace(": ", ":\n") for s in groups],
              ylim=(7.6, -0.6), xlim=(70, 101), xticks=[70, 80, 90, 100], xlabel="OOF score (%)")
    right.tick_params(axis="y", labelsize=9)
    fig.legend(*right.get_legend_handles_labels(), fontsize=9.2, ncol=2, loc="upper right", bbox_to_anchor=(0.99, 1.0), columnspacing=0.8)
    panel_title(left, "a", "Static perturbations")
    panel_title(right, "b", "Error strata")
    axis_style(left)
    axis_style(right, "x")
    fig.text(0.11, 0.025, "Validation results · Fixed perturbations and observational groups", fontsize=9.2, color=GRAY)
    save(fig, "figure_06_coverage_perturbations", pdf_dir, preview_dir)


def size_strata(pdf_dir, preview_dir):
    rows = read_csv("size_strata.csv")
    groups = list(dict.fromkeys((row["stratum_type"], row["stratum_value"]) for row in rows))
    labels = [("Files: " if kind == "python_file_count" else "Bytes: ")+label.replace("<=", "≤") for kind, label in groups]
    fig = plt.figure(figsize=(6.5, 3.6))
    left = fig.add_axes([0.20, 0.23, 0.32, 0.55])
    right = fig.add_axes([0.63, 0.23, 0.34, 0.55])
    for i, group in enumerate(groups):
        selected = [row for row in rows if (row["stratum_type"], row["stratum_value"]) == group]
        first = selected[0]
        prevalence = float(first["positive_prevalence"])*100
        left.barh(i, prevalence, color="#9AAFC1", height=0.45)
        left.text(101, i-0.24, f"n={first['rows']}", ha="right", va="center", fontsize=9)
        record(7, "a", "/".join(group), prevalence)
        for row in selected:
            fusion = row["system"] == "same_seed_pair"
            mean = float(row["auroc_mean"])*100
            sd = float(row["auroc_sample_sd"])*100 if fusion else None
            right.errorbar(mean, i+(0.10 if fusion else -0.10), xerr=sd, fmt="o" if fusion else "s",
                           color=GOLD if fusion else GRAY, capsize=2.4, markersize=4.5,
                           label=("PSHGuard" if fusion else "LR") if i == 0 else None)
            record(7, "b", f"{'/'.join(group)}/{row['system']}", mean, sd)
    left.set(yticks=range(7), yticklabels=labels, xlim=(0, 104), xticks=[0, 50, 100], xlabel="Malicious proportion (%)")
    right.set(yticks=range(7), yticklabels=[], xlim=(40, 101), xticks=[40, 60, 80, 100], xlabel="Within-stratum AUROC (%)")
    right.axvline(50, color=GRAY, lw=0.8, ls="--")
    right.legend(frameon=False, ncol=2, loc="upper right", bbox_to_anchor=(1.03, 1.35), fontsize=9.4)
    for ax in [left, right]:
        ax.set_ylim(6.6, -0.6)
        ax.axhline(3.5, color="#CCD4DA", lw=0.7)
        axis_style(ax, "x")
    panel_title(left, "a", "Composition")
    panel_title(right, "b", "Ranking")
    fig.text(0.20, 0.03, "2,137 validation packages · LR: fixed fit · PSHGuard: 3 runs", fontsize=9.4, color=GRAY)
    save(fig, "figure_07_size_strata", pdf_dir, preview_dir)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview-dir", type=Path, default=HERE / "previews")
    args = parser.parse_args()
    pdf_dir = MANUSCRIPT / "figures/v3"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    args.preview_dir.mkdir(parents=True, exist_ok=True)
    font_dir = Path("/mnt/c/Windows/Fonts")
    if not font_dir.exists():
        font_dir = Path("C:/Windows/Fonts")
    for name in ["arial.ttf", "arialbd.ttf", "ariali.ttf"]:
        font_manager.fontManager.addfont(str(font_dir/name))
    plt.rcParams.update({
        "font.family": "Arial", "font.size": 10,
        "axes.labelsize": 10, "axes.titlesize": 11,
        "xtick.labelsize": 9.5, "ytick.labelsize": 9.5,
        "text.color": INK, "axes.labelcolor": INK,
        "axes.linewidth": 0.7, "legend.frameon": False,
        "pdf.fonttype": 42, "svg.fonttype": "none",
        "svg.hashsalt": "PSHGuard-PeerJCS-v3",
        "savefig.bbox": None,
    })
    for plot in [branch_comparison, ablation_and_budget, efficiency, perturbations_and_coverage, size_strata]:
        plot(pdf_dir, args.preview_dir)
    (HERE/"plotted_values.json").write_text(json.dumps(POINTS, indent=2)+"\n", encoding="utf-8")
    (HERE/"export_sha256.json").write_text(json.dumps(OUTPUTS, indent=2)+"\n", encoding="utf-8")
    print(f"{len(POINTS)} plotted numerical records, five figure bundles.")


if __name__ == "__main__":
    main()
