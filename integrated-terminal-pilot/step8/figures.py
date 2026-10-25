"""Reproducible scientific figures from derived arrays, never scientific replay."""
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from evidence import publish_bytes

COLORS = {"A1": "#555555", "A1n": "#999999", "B1": "#CC79A7", "A2": "#0072B2",
          "A3": "#D55E00", "B2-T": "#E69F00", "B2": "#009E73"}


def render(output, analysis, diagnostics, provenance):
    plt.rcParams.update({"font.size": 10, "svg.hashsalt": "itp-step8-v1", "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.facecolor": "white"})
    figures = []
    families = ("itp_medium", "itp_heavy")
    groups = {(r["family"], r["arm"]): r for r in analysis["groups"]
              if r["split"] == "test" and r["world"] == "integrated"}
    result = {(r["family"], r["comparison"]): r for r in analysis["results"]}
    diag = {(r["family"], r["arm"]): r for r in diagnostics["rows"] if r["split"] == "test"}
    def save(fig, name, title):
        fig.suptitle(title, fontsize=13)
        fig.text(.01, .012, "PROVISIONAL | 50 traffic scenarios/family; A3=within-scenario 3-model mean | source " +
                 provenance["manifest_sha256"][:12] + " | 95% time CIs unadjusted", fontsize=7)
        fig.tight_layout(rect=(0, .055, 1, .94))
        for suffix in ("png", "svg"):
            stream = io.BytesIO()
            metadata = {"Software": "Project I Step8"} if suffix == "png" else {"Date": None, "Creator": "Project I Step8"}
            fig.savefig(stream, format=suffix, dpi=220, metadata=metadata)
            publish_bytes(output / "figures" / (name + "." + suffix), stream.getvalue())
        plt.close(fig)
        figures.append(name)
    arms = list(COLORS)
    fig, axes = plt.subplots(2, 1, figsize=(12, 6.5))
    for ax, f in zip(axes, families):
        ax.axis("off")
        data = [[a, f"{groups[f,a]['mean_TA_per_vessel']:.2f}",
                 f"{groups[f,a]['pooled_vessel_median_TA']:.2f}",
                 f"{groups[f,a]['pooled_vessel_p95_TA']:.2f}",
                 f"{groups[f,a]['mean_waiting']:.2f}",
                 f"{groups[f,a]['mean_p95_waiting']:.2f}",
                 f"{groups[f,a]['mean_U']:.2f}", f"{100*groups[f,a]['mean_R']:.4f}", "50/0"] for a in arms]
        table = ax.table(cellText=data, colLabels=["Arm", "Mean TA", "Median TA*", "P95 TA*", "Mean wait",
                         "Mean scen.P95 wait", "Mean U", "Mean R (%)", "Complete/fail"], loc="center")
        table.auto_set_font_size(False); table.set_fontsize(8); table.scale(1, 1.35)
        ax.set_title(f.replace("itp_", "").title() + "; times in simulated minutes; *pooled vessel TA (A3 vesselwise 3-model mean)")
    save(fig, "01_primary_outcome_table", "Primary test outcomes: time, cargo and completion")
    comparisons = ["B2-A2", "B2-A1", "A3-A1", "A3-A2", "B2-B2-T"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for i, f in enumerate(families):
        for j, field in enumerate(("TA_per_vessel_CI95", "paired_percent_CI95")):
            ax = axes[i, j]
            for y, c in enumerate(comparisons):
                ci = result[f,c][field]; v = ci["estimate"]
                ax.errorbar(v, y, xerr=[[v-ci["lower"]], [ci["upper"]-v]], fmt="o", color=COLORS[c.split("-")[0]], capsize=3)
            ax.axvline(0, color="black", linewidth=.7); ax.set_yticks(range(5), comparisons)
            ax.set_xlabel("Paired mean delta TA/vessel (min)" if j == 0 else "Mean paired TA change (%)")
            ax.set_title(f.replace("itp_", "").title() + "; negative favors first method")
    save(fig, "02_paired_time_effects", "Paired time effects with percentile 95% intervals; primary Holm claim pending")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    pairs = ["A2-A1", "A3-A1", "B1-A1", "B2-A2", "B2-T-A2", "B2-B2-T"]
    for ax, f in zip(axes, families):
        for y, c in enumerate(pairs):
            cargo = result[f,c]["cargo_NI"]; mean, upper = 100*cargo["estimate"], 100*cargo["upper"]
            ax.plot([mean, upper], [y, y], color="black"); ax.scatter(mean, y, marker="o", color="#0072B2")
            ax.scatter(upper, y, marker="|", s=130, color="#D55E00")
            short=lambda value: "pass" if value=="PASSED" else "ND"
            ax.annotate("1pp:" + short(cargo["verdict"]) + " / 0:" + short(cargo["zero_margin"]), (upper, y), xytext=(4, 5),
                        textcoords="offset points", fontsize=6)
        ax.axvline(1, linestyle="--", color="#D55E00", label="+1 pp NI margin")
        ax.axvline(0, linestyle=":", color="grey", label="0 pp sensitivity")
        ax.set_yticks(range(6), pairs); ax.set_xlabel("Delta cargo loss rate (percentage points)")
        ax.set_title(f.replace("itp_", "").title() + "; ND = not demonstrated"); ax.legend(fontsize=8)
        ax.margins(x=.28)
    save(fig, "03_cargo_noninferiority", "Cargo NI: dot=paired mean; right tick=one-sided 95% UPPER bound")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.7))
    for ax, f in zip(axes, families):
        for a in arms:
            g = groups[f,a]; ax.scatter(g["mean_TA_per_vessel"], 100*g["mean_R"], color=COLORS[a], label=a)
            ax.annotate(a, (g["mean_TA_per_vessel"],100*g["mean_R"]), xytext=(4,4), textcoords="offset points", fontsize=8)
        ax.set_xlabel("Mean turnaround/vessel (simulated min)"); ax.set_ylabel("Mean scenario cargo loss R (%)")
        ax.set_title(f.replace("itp_", "").title() + "; lower/left favorable")
    save(fig, "04_time_cargo_tradeoff", "Observed time/cargo tradeoffs; no fitted counterfactual or dollar savings")
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    labels = ["A3-train11", "A3-train23", "A3-train37", "A3"]
    for i, f in enumerate(families):
        for j, metric in enumerate(("mean_TA_per_vessel", "mean_R")):
            ax = axes[i,j]; scale = 100 if j else 1
            ax.bar(range(4), [scale*groups[f,a][metric] for a in labels], color=["#E69F00", "#D55E00", "#CC79A7", "#0072B2"])
            ax.axhline(scale*groups[f,"A1"][metric], label="A1 FCFS", color="black", linestyle="--")
            ax.axhline(scale*groups[f,"A2"][metric], label="A2", color="#009E73", linestyle=":")
            ax.set_xticks(range(4), ["seed11", "seed23", "seed37", "3-model mean"])
            ax.set_ylabel("TA/vessel (min)" if not j else "Cargo loss R (%)"); ax.set_title(f.replace("itp_", "").title())
            ax.legend(fontsize=8)
    save(fig, "05_ppo_all_seeds", "Frozen PPO transfer: all models, no best-seed selection")
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for ax, f in zip(axes[0], families):
        aa = ["A2", "A3", "B2-T", "B2"]
        ax.bar(aa, [100*diag[f,a]["waits"]/diag[f,a]["decisions"] for a in aa], color=[COLORS[a] for a in aa])
        ax.set_ylabel("Selected WAIT / decisions (%)"); ax.set_title(f.replace("itp_", "").title() + "; repeated trajectory decisions")
    for ax, f in zip(axes[1], families):
        aa = ["B2-T", "B2"]
        ax.bar(aa, [diag[f,a]["TA_error"]["mean"] for a in aa], color=[COLORS[a] for a in aa])
        ax.set_ylabel("Predicted - realized cohort TA (vessel-min)")
        ax.set_title("Selected-state forecast error; different visited states")
    save(fig, "06_wait_and_forecast", "WAIT and uncalibrated forecast diagnostics; no causal WAIT claim")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.8))
    aa = ["A2", "A3", "B2-T", "B2"]
    for ax, metric, title in zip(axes, ("mean", "p95", "outer"), ("Mean selection seconds", "P95 selection seconds", "Mean outer episode wall seconds")):
        for i, f in enumerate(families):
            vals = [groups[f,a]["mean_wall_seconds"] if metric == "outer" else diag[f,a]["cost"][metric] for a in aa]
            ax.bar(np.arange(4)+i*.36, vals, width=.34, label=f.replace("itp_", "").title(), color=("#0072B2", "#E69F00")[i])
        ax.set_xticks(np.arange(4)+.18, aa); ax.set_yscale("log"); ax.set_title(title); ax.set_ylabel("Real seconds (log scale)"); ax.legend(fontsize=8)
    save(fig, "07_compute_cost", "CPU inference/evaluation costs versus full outer execution; different boundaries")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    for ax, field, title in zip(axes, ("TA_per_vessel_CI95", "U_CI95"), ("Time cost (min/vessel)", "Unloaded obligations delta (containers/scenario)")):
        for y, f in enumerate(families):
            r = result[f,"B2-B2-T"]; ci=r[field]; v=ci["estimate"]
            ax.errorbar(v, y, xerr=[[v-ci["lower"]],[ci["upper"]-v]], fmt="o", capsize=4, color="#009E73")
            ax.annotate(f"TA wins/losses/ties {r['tail']['wins']}/{r['tail']['losses']}/{r['tail']['ties']}",
                        (v,y), xytext=(0,14), textcoords="offset points", fontsize=8)
        ax.axvline(0,color="black",linewidth=.7); ax.set_yticks(range(2), ["Medium","Heavy"]); ax.set_xlabel(title)
        ax.set_ylim(-.5,1.5)
    save(fig, "08_cargo_first_objective_ablation", "Matched B2 minus B2-T: cargo-first priority trades time against cargo")
    return figures
