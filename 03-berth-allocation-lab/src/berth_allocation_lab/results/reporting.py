"""Deterministic scientific CSV exports and table-backed technical figures."""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

from berth_allocation_lab.results.queries import (
    DYNAMIC_BY_SEED, DYNAMIC_SUMMARY, LATENCY, STATIC_SUMMARY, TAIL_RISK,
    WAIT_DIAGNOSTICS,
)

EXPORTS = {
    "static_summary.csv": STATIC_SUMMARY,
    "dynamic_summary.csv": DYNAMIC_SUMMARY,
    "dynamic_by_seed.csv": DYNAMIC_BY_SEED,
    "paired_comparisons.csv": """SELECT branch, split, regime, source_version, family,
        candidate_method, reference_method, seed_label, mean_delta_min,
        median_delta_min, wins, ties, losses, win_fraction, n_physical_scenarios,
        source_artifact FROM paired_comparisons
        ORDER BY branch, regime, source_version, family, candidate_method, reference_method, seed_label;""",
    "bootstrap_intervals.csv": """SELECT branch, split, regime, source_version, family,
        candidate_method, reference_method, training_seed_rule, metric_name,
        estimate, lower_bound, upper_bound, confidence_level, bootstrap_resamples,
        bootstrap_seed, n_physical_scenarios, source_artifact
        FROM uncertainty_intervals ORDER BY branch, regime, source_version,
        family, candidate_method, reference_method, training_seed_rule;""",
    "wait_diagnostics.csv": WAIT_DIAGNOSTICS,
    "tail_risk.csv": TAIL_RISK,
    "latency_summary.csv": LATENCY,
}

LIMITATIONS = [
    ("traffic", "Frozen, uncalibrated synthetic scenarios", "Real terminal external validity"),
    ("horizon", "H=240 observations in tested Dynamic PPO", "Causal information value without H=0-trained control"),
    ("device", "CUDA training and CPU held-out inference", "CPU/CUDA action-by-action parity"),
    ("rollout", "Causal visible-only heuristic", "Dynamic global optimality"),
    ("exact", "Fixed-order finite-candidate tiny Static reference", "Unrestricted continuous BAP optimum"),
    ("uncertainty", "Paired scenario bootstrap conditional on three models", "Training-seed uncertainty from only three seeds"),
    ("wait", "Observed intentional WAIT decisions", "Causal contribution of WAIT"),
    ("integration", "BAP-only berth decisions", "Crane/Yard/whole-terminal effects"),
    ("commercial", "Waiting in synthetic vessel-minutes", "Real productivity, cost savings or ROI"),
]


def _write_csv(path: Path, fields: list[str], rows: list[tuple]) -> None:
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(rows)


def export_tables(connection: sqlite3.Connection, target: Path) -> dict[str, int]:
    target.mkdir(exist_ok=False)
    counts = {}
    for filename, sql in EXPORTS.items():
        cursor = connection.execute(sql)
        rows = cursor.fetchall()
        _write_csv(target / filename, [item[0] for item in cursor.description], rows)
        counts[filename] = len(rows)
    _write_csv(target / "limitations.csv", ["topic", "known", "unknown"], LIMITATIONS)
    counts["limitations.csv"] = len(LIMITATIONS)
    return counts


def verify_tables(connection: sqlite3.Connection, target: Path) -> None:
    """Check every published CSV against a fresh query of the warehouse."""
    for filename, sql in EXPORTS.items():
        cursor = connection.execute(sql)
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow([item[0] for item in cursor.description])
        writer.writerows(cursor.fetchall())
        if (target / filename).read_bytes() != stream.getvalue().encode("utf-8"):
            raise ValueError(f"Published table differs from warehouse query: {filename}")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["topic", "known", "unknown"])
    writer.writerows(LIMITATIONS)
    if (target / "limitations.csv").read_bytes() != stream.getvalue().encode("utf-8"):
        raise ValueError("Published limitations table changed.")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


FIGURE_SOURCES = {
    "static_method_comparison.png": "static_summary.csv",
    "dynamic_method_comparison.png": "dynamic_summary.csv",
    "dynamic_gap_closure.png": "dynamic_summary.csv",
    "dynamic_seed_variability.png": "dynamic_by_seed.csv",
    "paired_delta_intervals.png": "dynamic_summary.csv",
    "decision_latency.png": "latency_summary.csv",
}


def render_figures(tables: Path, figures: Path) -> dict[str, str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    figures.mkdir(exist_ok=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "figure.facecolor": "white", "axes.facecolor": "white",
                         "savefig.facecolor": "white"})
    colors = {"FCFS": "#455A64", "PPO": "#147D70", "Rollout": "#E0784B",
              "Exact": "#8768A8"}

    static = _rows(tables / "static_summary.csv")
    labels = [f"{r['regime'].replace('_','/')}\n{r['source_version']}" for r in static]
    x = np.arange(len(static))
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    for j, (method, field) in enumerate((("FCFS", "fcfs_min"), ("Rollout", "rollout_min"),
                                         ("PPO", "ppo_seed_mean_min"),
                                         ("Exact", "candidate_space_exact_min"))):
        vals = [float(r[field]) if r[field] else np.nan for r in static]
        ax.bar(x + (j-1.5)*0.19, vals, width=0.18, color=colors[method], label=method)
    ax.set_xticks(x, labels)
    ax.set_ylabel("Weighted total waiting (vessel-minutes; lower is better)")
    ax.set_title("Static BAP | held-out synthetic test | PPO seed mean")
    ax.legend(ncol=4, loc="upper right", frameon=False)
    fig.tight_layout()
    fig.savefig(figures / "static_method_comparison.png", dpi=190)
    plt.close(fig)

    dynamic = _rows(tables / "dynamic_summary.csv")
    x = np.arange(len(dynamic))
    labels = [r["regime"].replace("_", "/") for r in dynamic]
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    for j, (method, field) in enumerate((("FCFS", "fcfs_min"),
                                         ("PPO", "ppo_seed_mean_min"),
                                         ("Rollout", "rollout_min"))):
        ax.bar(x + (j-1)*0.23, [float(r[field]) for r in dynamic], width=0.22,
               color=colors[method], label=method)
    ax.set_xticks(x, labels)
    ax.set_ylabel("Weighted total waiting (vessel-minutes; lower is better)")
    ax.set_title("Dynamic BAP, H=240 | held-out synthetic test")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(figures / "dynamic_method_comparison.png", dpi=190)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    gaps = [100 * float(r["gap_closed"]) for r in dynamic]
    bars = ax.bar(labels, gaps, color=colors["PPO"], width=0.55)
    for bar, value in zip(bars, gaps):
        ax.text(bar.get_x()+bar.get_width()/2, value+1, f"{value:.1f}%", ha="center")
    ax.set_ylim(0, max(gaps)*1.25)
    ax.set_ylabel("FCFS-to-Rollout gap closed (%)")
    ax.set_title("Dynamic PPO seed mean | held-out synthetic test")
    fig.tight_layout()
    fig.savefig(figures / "dynamic_gap_closure.png", dpi=190)
    plt.close(fig)

    seed_rows = _rows(tables / "dynamic_by_seed.csv")
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    for index, regime in enumerate(("tiny", "medium_heavy")):
        subset = [r for r in seed_rows if r["regime"] == regime]
        for row in subset:
            seed = int(row["training_seed"])
            ax.scatter(index + (seed-23)/100, float(row["ppo_min"]), s=65,
                       label=f"seed {seed}" if index == 0 else None)
        ax.plot([index-0.18, index+0.18],
                [sum(float(r["ppo_min"]) for r in subset)/len(subset)]*2,
                color=colors["PPO"], lw=2)
    ax.set_xticks(range(2), ["tiny", "medium/heavy"])
    ax.set_ylabel("Weighted total waiting (vessel-minutes; lower is better)")
    ax.set_title("Dynamic PPO | three training seeds | held-out test")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(figures / "dynamic_seed_variability.png", dpi=190)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    effects = [-float(r["improvement_vs_fcfs_min"]) for r in dynamic]
    low = [float(r["ci_lower_min"]) for r in dynamic]
    high = [float(r["ci_upper_min"]) for r in dynamic]
    ax.errorbar(effects, range(len(dynamic)),
                xerr=[[e-l for e, l in zip(effects, low)],
                      [h-e for h, e in zip(high, effects)]],
                fmt="o", color=colors["PPO"], capsize=5, lw=2)
    ax.axvline(0, color=colors["FCFS"], lw=1, ls="--")
    ax.set_yticks(range(len(dynamic)), labels)
    ax.set_xlabel("PPO seed mean minus FCFS (vessel-minutes; negative is better)")
    ax.set_title("Dynamic BAP | paired 95% scenario bootstrap | held-out test")
    fig.tight_layout()
    fig.savefig(figures / "paired_delta_intervals.png", dpi=190)
    plt.close(fig)

    latency = _rows(tables / "latency_summary.csv")
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    entries = [(r["regime"], r["method"], float(r["mean_decision_ms"])) for r in latency]
    y = np.arange(len(entries))
    ax.barh(y, [v for _, _, v in entries],
            color=[colors[{"fcfs": "FCFS", "ppo": "PPO", "rollout": "Rollout"}[m]]
                   for _, m, _ in entries])
    ax.set_yticks(y, [f"{regime.replace('_','/')} | {method}" for regime, method, _ in entries])
    ax.set_xscale("log")
    ax.set_xlabel("Mean CPU policy-decision time (ms, log scale)")
    ax.set_title("Validation fixtures | 1 warmup + 3 timed passes")
    fig.tight_layout()
    fig.savefig(figures / "decision_latency.png", dpi=190)
    plt.close(fig)
    return FIGURE_SOURCES.copy()
