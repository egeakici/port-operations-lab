"""Pure read-only scenario analysis, conditional on the three frozen PPO models."""
from collections import defaultdict
import csv
import gzip
import hashlib
import json
import math

import numpy as np
from tqdm import tqdm

from evidence import close, manifest_file, sha, trusted_review, REPORT
from statistical import (SEEDS, FAMILIES, ContractError, nested_mean, interval,
                         cargo_noninferiority, tails, relative_difference,
                         time_label, combined_label, wilcoxon_robustness, ranking_agreement, TIE)

ARMS = ("A1", "A1n", "B1", "A2", "A3", "B2-T", "B2")
CONTRASTS = (("B1", "A1n"), ("B2", "A2"), ("B1", "A1"), ("A1n", "A1"),
             ("A2", "A1"), ("A3", "A1"), ("A3", "A2"), ("B2", "A1"),
             ("B2-T", "A2"), ("B2", "B2-T"))
PRIMARY = ("B1-A1n", "B2-A2")
CARGO_PAIRS = ("A2-A1", "A3-A1", "B1-A1", "B2-A2", "B2-T-A2", "B2-B2-T")


def signed_effect(value):
    """Use the inherited1e-6 vessel-minute tie convention, not float noise."""
    return 0 if abs(value) <= TIE else (-1 if value < 0 else 1)


def tolerant_ranks(values):
    """Stable complete-link clusters within inherited absolute tie tolerance.

    Sort values; each cluster spans at most TIE from its lowest member and gets
    its average rank. This avoids turning 1e-12 serialization noise into a rank.
    """
    ordered=sorted(enumerate(values),key=lambda p:p[1]); ranks=np.zeros(len(values))
    start=0
    while start<len(ordered):
        end=start+1
        while end<len(ordered) and ordered[end][1]-ordered[start][1]<=TIE:
            end+=1
        rank=(start+1+end)/2
        for index,_ in ordered[start:end]:ranks[index]=rank
        start=end
    return ranks


def tolerant_ranking_agreement(reference, integrated):
    return ranking_agreement(tolerant_ranks(reference),tolerant_ranks(integrated))


def average_rows(members):
    if {r["training_seed"] for r in members} != set(SEEDS) or len(members) != 3:
        raise ContractError("MISSING_INCOMPLETE_SEEDS")
    if any(r["status"] != "COMPLETED" for r in members):
        return None
    members = sorted(members, key=lambda r: r["training_seed"])
    r = dict(members[0], arm="A3", training_seed=None, eligible_model_seeds=list(SEEDS))
    for metric in ("TA", "U", "R", "wall", "cpu", "waiting", "waiting_total", "p95_waiting"):
        if metric in r:
            if r[metric] is None:
                continue
            r[metric] = nested_mean({m["training_seed"]: m[metric] for m in members})
    for metric in ("vessel_TA", "vessel_wait"):
        if metric in r:
            r[metric] = np.mean([m[metric] for m in members], axis=0).tolist()
    r["source_row_ids"] = [m["row_id"] for m in members]
    return r


def scenario_lookup(panel):
    grouped = defaultdict(list)
    for r in panel["rows"]:
        grouped[(r["split"], r["family"], r["scenario_id"], r["world"], r["arm"])].append(r)
    lookup = {}
    for key, members in grouped.items():
        if key[-1] == "A3":
            avg = average_rows(members)
            if avg is not None:
                lookup[key] = avg
        elif len(members) == 1 and members[0]["status"] == "COMPLETED":
            lookup[key] = members[0]
        elif len(members) != 1:
            raise ContractError("Ambiguous scenario/arm identity")
    return lookup


def summarize_groups(panel, lookup):
    grouped = defaultdict(list)
    for key, row in lookup.items():
        grouped[(key[0], key[1], key[3], key[4])].append(row)
    for r in panel["rows"]:
        if r["arm"] == "A3" and r["status"] == "COMPLETED":
            grouped[(r["split"], r["family"], r["world"], f"A3-train{r['training_seed']}")].append(r)
    results = []
    for (split, family, world, arm), rows in sorted(grouped.items()):
        per_scenario = [r["TA"] / r["n_vessels"] for r in rows]
        vessel = [x for r in rows for x in r["vessel_TA"]]
        result = dict(split=split, family=family, world=world, arm=arm, n_traffic_scenarios=len(rows),
                      eligible_model_seeds=list(SEEDS) if arm == "A3" else [],
                      mean_total_TA=float(np.mean([r["TA"] for r in rows])),
                      mean_TA_per_vessel=float(np.mean(per_scenario)),
                      median_scenario_mean_TA_per_vessel=float(np.median(per_scenario)),
                      p95_scenario_mean_TA_per_vessel=float(np.quantile(per_scenario, .95)),
                      pooled_vessel_median_TA=float(np.median(vessel)),
                      pooled_vessel_p95_TA=float(np.quantile(vessel, .95)),
                      completed=sum(r["status"] == "COMPLETED" for r in rows), failed=0, G_blocked=0,
                      mean_waiting_total=float(np.mean([r["waiting_total"] for r in rows])),
                      mean_wall_seconds=float(np.mean([r["wall"] for r in rows])),
                      mean_cpu_seconds=float(np.mean([r["cpu"] for r in rows])))
        if world == "integrated":
            for name in ("U", "R", "N_out", "waiting", "p95_waiting", "loaded_not_departed"):
                # loaded_not_departed is constant zero in this campaign; aggregate
                # from seed members rather than treating model 11 as representative.
                if name == "loaded_not_departed" and arm == "A3":
                    vals = [m[name] for m in panel["rows"] if m["split"] == split and
                            m["family"] == family and m["world"] == world and m["arm"] == "A3"]
                else:
                    vals = [r[name] for r in rows if r.get(name) is not None]
                result["mean_" + name] = float(np.mean(vals)) if vals else None
            result["pooled_vessel_p95_waiting"] = float(np.quantile([x for r in rows for x in r["vessel_wait"]], .95))
            result["terminal_completed"] = sum(r["terminal_end"] == "COMPLETED" for r in rows)
            result["deadlock"] = sum(r["terminal_end"] == "DEADLOCK" for r in rows)
            result["truncated"] = sum(r["terminal_end"] == "TRUNCATED_DRAIN_LIMIT" for r in rows)
            for metric in sorted(rows[0]["kpi"]):
                if isinstance(rows[0]["kpi"][metric], (float, int)):
                    # Model nesting for every resource metric.
                    vals = []
                    for r in rows:
                        if arm == "A3":
                            source = [m for m in panel["rows"] if m["row_id"] in r["source_row_ids"]]
                            vals.append(np.mean([m["kpi"][metric] for m in source]))
                        else:
                            vals.append(r["kpi"][metric])
                    result["resource_mean_" + metric] = float(np.mean(vals))
        results.append(result)
    return results


def paired_rows(lookup, policy, comparator, *, world="integrated", split="test"):
    out, excluded = [], []
    scenarios = sorted({(k[1], k[2]) for k in lookup if k[0] == split})
    for family, sid in scenarios:
        a = lookup.get((split, family, sid, world, policy))
        b = lookup.get((split, family, sid, world, comparator))
        if a is None or b is None:
            excluded.append(dict(scenario_id=sid, reason="FAILED_OR_BLOCKED_OR_MISSING_ARM"))
            continue
        if a["pairing"] != b["pairing"]:
            raise ContractError("Cross-arm/source pairing drift")
        row = dict(family=family, scenario_id=sid, difference=a["TA"] - b["TA"],
                   difference_per_vessel=(a["TA"] - b["TA"]) / a["n_vessels"],
                   percent=relative_difference(a["TA"], b["TA"]),
                   waiting=a["waiting_total"] - b["waiting_total"],
                   policy_TA=a["TA"], comparator_TA=b["TA"],
                   U=None if a["U"] is None else a["U"] - b["U"],
                   R=None if a["R"] is None or b["R"] is None else a["R"] - b["R"])
        out.append(row)
    return out, excluded


def inference(rows, label, *, primary=False, cargo_pair=False, excluded=()):
    output = []
    for family in (*FAMILIES, "equal_family_overall"):
        families = FAMILIES if family == "equal_family_overall" else (family,)
        selected = [r for r in rows if r["family"] in families]
        def values(metric):
            return {f: [r[metric] for r in selected if r["family"] == f] for f in families}
        if any(not any(r["family"] == f for r in selected) for f in families):
            raise ContractError("Empty primary family; no silent renormalization")
        ta = interval(values("difference"))
        per_vessel = interval(values("difference_per_vessel"))
        percent = interval(values("percent")) if all(r["percent"] is not None for r in selected) else None
        waiting = interval(values("waiting"))
        cargo = None
        if cargo_pair:
            eligible = {f: [r["R"] for r in selected if r["family"] == f and r["R"] is not None] for f in families}
            cargo = (cargo_noninferiority(eligible) if all(eligible.values()) else
                     dict(estimate=None, upper=None, n=0, margin=.01,
                          verdict="NOT_APPLICABLE_NO_ELIGIBLE_PAIRS", zero_margin="NOT_APPLICABLE"))
            cargo["not_applicable_scenarios"] = [r["scenario_id"] for r in selected if r["R"] is None]
        time = time_label(ta, primary=primary)
        u = interval(values("U")) if all(r["U"] is not None for r in selected) else None
        # Percentage of means explicitly distinct from average paired percentage.
        meanp = np.mean([np.mean([r["policy_TA"] for r in selected if r["family"] == f]) for f in families])
        meanb = np.mean([np.mean([r["comparator_TA"] for r in selected if r["family"] == f]) for f in families])
        item = dict(comparison=label, family=family, n_traffic_scenarios=len(selected),
                    eligible_model_seeds=list(SEEDS) if "A3" in label else [],
                    mean_turnaround_difference=ta["estimate"], time_CI95=ta,
                    TA_per_vessel_CI95=per_vessel, paired_percent_CI95=percent,
                    percent_change_of_group_means=relative_difference(meanp, meanb),
                    waiting_total_CI95=waiting, mean_U_difference=None if u is None else u["estimate"],
                    U_CI95=u, cargo_NI=cargo,
                    mean_cargo_rate_difference=(float(np.mean([np.mean([r["R"] for r in selected if r["family"] == f]) for f in families]))
                                               if all(r["R"] is not None for r in selected) else None),
                    one_sided_95_cargo_upper=None if cargo is None else cargo["upper"],
                    NI_margin=.01 if cargo_pair else None,
                    NI_verdict="NOT_PREREGISTERED_FOR_PAIR" if cargo is None else cargo["verdict"],
                    time_verdict=time, combined_time_and_cargo_verdict=combined_label(time, cargo),
                    pre_registered_or_descriptive="PRIMARY_HOLM_FAMILY_IMPLEMENTATION_GAP" if primary else "PREREGISTERED_SECONDARY",
                    tail=tails([r["difference"] for r in selected], [r["scenario_id"] for r in selected]),
                    excluded=list(excluded), unadjusted_time_label=time_label(ta))
        if family != "equal_family_overall":
            item["wilcoxon_robustness"] = wilcoxon_robustness([r["difference"] for r in selected])
        else:
            item["wilcoxon_robustness"] = {"role": "NOT_POOLED_ACROSS_HETEROGENEOUS_FAMILIES"}
        if u is not None:
            item["cargo_count_tail"] = tails([r["U"] for r in selected], [r["scenario_id"] for r in selected], tolerance=1e-9)
        output.append(item)
    return output


def analyze(panel):
    lookup = scenario_lookup(panel)
    groups = summarize_groups(panel, lookup)
    results, sourcepairs = [], {}
    for policy, comparator in CONTRASTS:
        label = policy + "-" + comparator
        rows, excluded = paired_rows(lookup, policy, comparator)
        sourcepairs[label] = rows
        results.extend(inference(rows, label, primary=label in PRIMARY,
                                 cargo_pair=label in CARGO_PAIRS, excluded=excluded))
    # Interaction C4 has no natural percentage/cargo NI comparator.
    a = {r["scenario_id"]: r for r in sourcepairs["B2-A2"]}
    b = {r["scenario_id"]: r for r in sourcepairs["B1-A1n"]}
    interaction = []
    for sid in sorted(set(a) & set(b)):
        row = dict(a[sid])
        for metric in ("difference", "difference_per_vessel", "waiting", "U", "R"):
            row[metric] = a[sid][metric] - b[sid][metric]
        row["percent"] = None
        interaction.append(row)
    c4 = inference(interaction, "(B2-A2)-(B1-A1n)")
    for row in c4:
        row["percent_change_of_group_means"] = None
    results.extend(c4)
    s1, rank = [], []
    for arm in ("A2", "A3"):
        integ = {r["scenario_id"]: r for r in sourcepairs[arm + "-A1"]}
        refs, excluded = paired_rows(lookup, arm, "A1", world="reference")
        did = []
        for ref in refs:
            original = integ.get(ref["scenario_id"])
            if original is None:
                continue
            row = dict(original)
            for metric in ("difference", "difference_per_vessel", "waiting"):
                row[metric] = original[metric] - ref[metric]
            row.update(percent=None, U=None, R=None)
            did.append(row)
        estimates = inference(did, f"({arm}-A1)_integrated-({arm}-A1)_reference")
        for row in estimates:
            row.update(pre_registered_or_descriptive="PREREGISTERED_S1_DESCRIPTIVE_ENVIRONMENT_DID",
                       percent_change_of_group_means=None,
                       interpretation="Difference of policy-relative contrasts across different physical models; NOT causal integration effect")
        s1.extend(estimates)
        for family in FAMILIES:
            rr = [r for r in refs if r["family"] == family]
            signs = [signed_effect(r["difference"]) == signed_effect(integ[r["scenario_id"]]["difference"]) for r in rr]
            rank.append(dict(family=family, contrast=arm + "-A1", n=len(rr),
                             sign_agreement=float(np.mean(signs)),
                             reference_CI95=interval({family: [r["difference"] for r in rr]})))
    ranks = []
    for family in FAMILIES:
        sids = sorted({k[2] for k in lookup if k[0] == "test" and k[1] == family})
        taus = []
        for sid in sids:
            ref = [lookup[("test", family, sid, "reference", a)]["TA"] for a in ("A1", "A2", "A3")]
            integ = [lookup[("test", family, sid, "integrated", a)]["TA"] for a in ("A1", "A2", "A3")]
            tau = tolerant_ranking_agreement(ref, integ)
            taus.append(dict(scenario_id=sid, tau_b=tau if math.isfinite(tau) else None))
        order = {}
        for world in ("reference", "integrated"):
            means = {a: float(np.mean([lookup[("test", family, sid, world, a)]["TA"] for sid in sids])) for a in ("A1", "A2", "A3")}
            order[world] = sorted(means, key=means.get)
        ranks.append(dict(family=family, mean_order=order, per_scenario_kendall_tau_b=taus,
                          mean_finite_tau=float(np.mean([r["tau_b"] for r in taus if r["tau_b"] is not None]))))
    # Seed-specific cargo NI is preregistered descriptive, never best-model choice.
    seed_results = []
    for seed in SEEDS:
        replaced = dict(lookup)
        for r in panel["rows"]:
            if r["arm"] == "A3" and r["training_seed"] == seed:
                replaced[(r["split"], r["family"], r["scenario_id"], r["world"], "A3")] = r
        rows, excluded = paired_rows(replaced, "A3", "A1")
        for row in inference(rows, f"A3-train{seed}-A1", cargo_pair=True, excluded=excluded):
            row["pre_registered_or_descriptive"] = "PER_SEED_DESCRIPTIVE_CONDITIONAL_NO_SELECTION"
            seed_results.append(row)
    reconciliation = reconcile(groups, results, s1)
    return dict(groups=groups, results=results, S1_difference_in_differences=s1,
                S1_sign_agreement=rank, S1_rankings=ranks, seed_results=seed_results,
                source_pairs=sourcepairs, reconciliation=reconciliation)


def ppo_support(panel):
    grouped = defaultdict(list)
    for r in panel["rows"]:
        if r["world"] == "integrated" and r["arm"] == "A3" and r["status"] == "COMPLETED":
            grouped[(r["split"], r["family"], r["training_seed"])].append(r["decisions"]["ppo_support"])
    output=[]
    for (split,family,seed), members in sorted(grouped.items()):
        bounds={r["training_bound"] for r in members}
        if len(bounds)!=1:
            raise ContractError("PPO training-support boundary changed")
        n=sum(r["epochs"] for r in members); above=sum(r["epochs_above_training_max"] for r in members)
        output.append(dict(split=split,family=family,training_seed=seed,episodes=len(members),
                           training_bound=bounds.pop(),epochs=n,epochs_above_training_max=above,
                           fraction=above/n if n else None,
                           max_remaining_occupancy_feature=max(r["max_remaining_occupancy_feature"] for r in members)))
    for family,expected in (("itp_heavy",(1772,3806)),("itp_medium",(1130,2417))):
        selected=[r for r in output if r["split"]=="test" and r["family"]==family]
        actual=(sum(r["epochs_above_training_max"] for r in selected),sum(r["epochs"] for r in selected))
        if actual!=expected:
            raise ContractError("SOURCE_RECONCILIATION_EXCEPTION: PPO support counts")
    return output


def diagnostic_cost_proxy(groups, plan):
    """Historical base episode wall only, not a bound for altered physics."""
    lookup={(r["family"],r["arm"]):r["mean_wall_seconds"] for r in groups
            if r["split"]=="test" and r["world"]=="integrated"}
    full=0.; unsupported=0.
    for cell in plan["sensitivity_cells"]:
        label=cell["arm"] if cell["training_seed"] is None else f"A3-train{cell['training_seed']}"
        cost=lookup[cell["family"],label]
        full+=cost
        if cell["status"].startswith("UNSUPPORTED"):
            unsupported+=cost
    coupling=sum(lookup[c["family"],"B2"] for c in plan["coupling_cells"])
    return dict(sensitivity_base_wall_proxy_seconds=full,
                sensitivity_base_wall_proxy_hours=full/3600,
                unsupported_cells_base_wall_proxy_seconds=unsupported,
                remaining_supported_cells_base_wall_proxy_hours=(full-unsupported)/3600,
                coupling_full_model_wall_proxy_hours=coupling/3600,
                coupling_overlap_note="both/base may overlap sensitivity base only after adapter identity verification; no double-counted campaign total is asserted",
                method="Sum each planned row's matching Step7 test arm/checkpoint/family mean outer episode wall; no new timing run",
                limitations="NOT a guaranteed ETA/bound: changed physics/models may cost more or less; excludes generation, validation, canonical verification, profiling/export overhead; no admission timeout")


def reconcile(groups, results, s1):
    previous = trusted_review("descriptive_review.json")
    checks = []
    for old in previous["arms"]:
        arm = f"A3-train{old['seed']}" if old["arm"] == "A3" else old["arm"]
        new = next(r for r in groups if (r["split"], r["family"], r["world"], r["arm"]) ==
                   (old["split"], old["family"], old["world"], arm))
        for actual, target in (("mean_total_TA", "mean_TA"), ("mean_U", "mean_U"),
                               ("mean_R", "mean_R"), ("mean_waiting", "mean_waiting")):
            if old.get(target) is None:
                continue
            close(new[actual], old[target], f"review {arm} {actual}")
            checks.append(dict(split=old["split"], family=old["family"], arm=arm,
                               metric=actual, actual=new[actual], reviewed=old[target], status="MATCH"))
    for old in previous["paired"]:
        if old["split"] != "test":
            continue
        new = next((r for r in results if r["comparison"] == old["contrast"] and r["family"] == old["family"]), None)
        if new is None:
            raise ContractError("Unaccounted original comparison " + old["contrast"])
        for field, target in (("mean_turnaround_difference", "TA_delta"), ("mean_U_difference", "U_delta")):
            close(new[field], old[target], "review paired " + old["contrast"] + " " + field)
        if new["paired_percent_CI95"] is not None:
            close(new["paired_percent_CI95"]["estimate"], old["TA_mean_paired_percent"], "review paired percentage")
        checks.append(dict(family=old["family"], comparison=old["contrast"], status="MATCH"))
    for old in previous["reference"]:
        if old["split"] != "test":
            continue
        new = next(r for r in s1 if r["family"] == old["family"] and
                   r["comparison"].startswith("(" + old["contrast"] + ")"))
        close(new["mean_turnaround_difference"], old["difference_in_differences"], "S1 review DID")
    return dict(status="RECONCILED", tolerance="abs1e-7/rel1e-11 for full precision reviewed CSV; printed tables round only",
                discrepancies=[], checks=checks)


def diagnostic_summary(ctx):
    """Read archived post-run diagnostic JSON, not policy input pickle/replay.

    Existing reconstructed predictions are observations on selected trajectories.
    Re-reading these small archives is NOT evaluating a policy/simulating again.
    """
    from evidence import read
    manifest = read(ctx["directory"] / "reports/diagnostics_fd979c5222b3.json")
    groups = defaultdict(lambda: dict(episodes=0, decisions=0, waits=0, wait_legal=0,
                                    cargo_pivotal=0, one_container_pivotal=0, losses=0,
                                    two_second_warnings=0, cost=[], wait_minutes=[],
                                    cargo_error=[], TA_error=[], b1_error=[], causes={}))
    input_hashes = {}
    for receipt in tqdm(manifest["rows"], desc="Step8 archived diagnostics", unit="row", ascii=True):
        meta = receipt["row"]
        path = ctx["directory"] / receipt["path"]
        digest = manifest_file(ctx["bundle"], ctx["manifest"], path)
        if digest != receipt["gzip_sha256"]:
            raise ContractError("Diagnostic gzip receipt mismatch")
        input_hashes[path.relative_to(ctx["bundle"]).as_posix()] = digest
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            d = json.load(stream)
        g = groups[(meta["split"], meta["family"], meta["arm"])]
        g["episodes"] += 1
        g["losses"] += len(d["losses"])
        for loss in d["losses"]:
            cause = loss["primary_causal_reason"]
            g["causes"][cause] = g["causes"].get(cause, 0) + 1
        for decision in d["decisions"]:
            g["decisions"] += 1
            g["cost"].append(decision["policy_seconds"])
            g["wait_legal"] += bool(decision.get("wait_legal"))
            g["two_second_warnings"] += bool(decision["two_second_warning"])
            if decision["kind"] == "WAIT":
                g["waits"] += 1
                g["wait_minutes"].append(decision["wait_observed"]["elapsed_min"])
            pivot = decision.get("pivotal", {})
            g["cargo_pivotal"] += bool(pivot.get("cargo_pivotal"))
            g["one_container_pivotal"] += bool(pivot.get("one_container_pivotal"))
            for source, target in (("predicted_minus_actual_unloaded", "cargo_error"),
                                   ("predicted_minus_actual_turnaround", "TA_error")):
                if source in decision:
                    g[target].append(decision[source])
            if decision.get("b1_release_error") and decision["b1_release_error"]["predicted_minus_actual_min"] is not None:
                g["b1_error"].append(decision["b1_release_error"]["predicted_minus_actual_min"])
    output = []
    for key, g in sorted(groups.items()):
        row = dict(split=key[0], family=key[1], arm=key[2])
        for name, value in g.items():
            if isinstance(value, list):
                row[name] = None if not value else dict(n=len(value), mean=float(np.mean(value)),
                    median=float(np.median(value)), p95=float(np.quantile(value, .95, method="linear")),
                    max=float(np.max(value)), min=float(np.min(value)),
                    MAE=float(np.mean(np.abs(value))))
            else:
                row[name] = value
        output.append(row)
    totals = {name: sum(r[name] for r in output) for name in
              ("episodes", "decisions", "waits", "cargo_pivotal", "one_container_pivotal", "two_second_warnings")}
    expected = dict(episodes=1260, decisions=27244, waits=2044, cargo_pivotal=284,
                    one_container_pivotal=0, two_second_warnings=4139)
    if totals != expected:
        raise ContractError("SOURCE_RECONCILIATION_EXCEPTION: archived diagnostic totals")
    return dict(rows=output, totals=totals, input_hashes=input_hashes,
                limits="Repeated selected-trajectory observations, not independent scenarios or causal WAIT/forecast experiments; UNCALIBRATED_SYNTHETIC_FORECAST")
