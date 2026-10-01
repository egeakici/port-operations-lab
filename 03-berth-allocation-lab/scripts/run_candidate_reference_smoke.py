"""Small Step 7 audit, not the future scientific benchmark suite.

Run from Project 03: python scripts/run_candidate_reference_smoke.py --output PATH
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

import yaml

from berth_allocation_lab.core import NUMERICAL_TOLERANCE
from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput as Vessel
from berth_allocation_lab.evaluation import compare_static_baselines, run_static_policy
from berth_allocation_lab.evaluation.comparison import compare_to_candidate_reference
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator
from berth_allocation_lab.solvers import CandidateEnumerationConfig, StaticCandidateEnumeration


def manual_scenarios():
    populations = (
        (Vessel("A", 0.0, 240.0, 7.5), Vessel("B", 0.0, 260.0, 12.0)),
        (Vessel("A", 0.0, 100.0, 100.0), Vessel("B", 0.0, 250.0, 1000.0),
         Vessel("C", 100.0, 200.0, 100.0)),
        (Vessel("A", 0.0, 300.0, 100.0), Vessel("B", 0.0, 300.0, 100.0),
         Vessel("C", 1.0, 180.0, 10.0), Vessel("D", 2.0, 180.0, 20.0)),
    )
    for vessels in populations:
        yield BAPScenarioInstance(
            scenario_id=f"step7_manual_n{len(vessels)}", scenario_version=2,
            scenario_family="manual", formulation="static", data_provenance="synthetic",
            split="test", seed=0, generator_version="step7_manual_v2", scenario_schema_version=1,
            berth_length_m=500.0, min_clearance_m=20.0 if len(vessels) == 2 else 10.0,
            nominal_duration_min=vessels[-1].arrival_time_min,
            arrival_generation_end_min=vessels[-1].arrival_time_min, vessels=vessels,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    config_dir = args.output / "configs"
    config_dir.mkdir()
    base = SyntheticScenarioConfig.load_yaml(
        Path(__file__).resolve().parents[1] / "configs/scenarios/synthetic_tiny_congested.yaml"
    )
    scenarios = list(manual_scenarios())
    for count, seed in [*((n, 42) for n in range(2, 9)), (6, 0), (6, 1)]:
        config = replace(base, scenario_id=f"synthetic_tiny_congested_n{count}_seed{seed}",
                         seed=seed, traffic=replace(base.traffic, vessel_count=count))
        (config_dir / f"{config.scenario_id}.yaml").write_text(
            yaml.safe_dump(asdict(config), sort_keys=False), encoding="utf-8",
        )
        scenarios.append(SyntheticScenarioGenerator().generate(config))
    rows = []
    report = ["# Step 7 Measured Smoke Audit", "",
              "Controlled synthetic cases; these are not population-level performance claims.",
              "All gaps below are candidate-space reference gaps. Times are minutes unless labeled seconds.",
              "Limits: max_vessels=8, max_search_nodes=250000, no time cutoff; FCFS initial upper bound.", ""]
    zero_fcfs = zero_generated = 0
    for scenario in scenarios:
        fcfs, rollout = compare_static_baselines(scenario, args.output / "runs")
        exact = run_static_policy(scenario, StaticCandidateEnumeration(
            CandidateEnumerationConfig(max_vessels=8)), args.output / "runs")
        if not fcfs.summary.is_valid or not rollout.summary.is_valid:
            raise RuntimeError("Baseline validation failed.")
        certified = exact.solver_diagnostics.optimality_status == "optimal"
        if fcfs.summary.objective_value == 0:
            zero_fcfs += 1
            zero_generated += scenario.scenario_family == "tiny_congested"
        if rollout.summary.objective_value > fcfs.summary.objective_value + NUMERICAL_TOLERANCE:
            raise RuntimeError("Rollout dominance failed.")
        if certified and exact.summary.objective_value > rollout.summary.objective_value + NUMERICAL_TOLERANCE:
            raise RuntimeError("Candidate reference ordering failed.")
        report.extend([f"## {scenario.scenario_id}", "",
                       f"Fingerprint: `{scenario.content_fingerprint}`", "",
                       "| Metric | FCFS | Rollout | Candidate reference |",
                       "| --- | ---: | ---: | ---: |"])
        for label, field in (
            ("Total waiting", "total_waiting_time_min"), ("Mean waiting", "mean_waiting_time_min"),
            ("P95 waiting", "p95_waiting_time_min"), ("Mean turnaround", "mean_turnaround_time_min"),
            ("Algorithm runtime (s)", "algorithm_runtime_seconds"),
        ):
            values = [getattr(run.summary, field) for run in (fcfs, rollout, exact)]
            report.append(f"| {label} | " + " | ".join(f"{value:.6f}" if value is not None else "uncertified" for value in values) + " |")
        gaps = [compare_to_candidate_reference(run, exact).absolute_gap_min if certified else None
                for run in (fcfs, rollout, exact)]
        report.append("| Absolute candidate-space gap | " + " | ".join(
            f"{value:.6f}" if value is not None else "undefined" for value in gaps) + " |")
        d = exact.solver_diagnostics
        report.extend(["", f"Status: `{d.optimality_status}`; reason: `{d.termination_reason}`; "
                       f"nodes: {d.nodes_explored}; pruned: {d.branches_pruned}; leaves: {d.complete_schedules_evaluated}; "
                       f"solver runtime: {d.solver_runtime_seconds:.6f} s.",
                       f"Run IDs (FCFS, Rollout, reference): `{fcfs.manifest.run_id}`, "
                       f"`{rollout.manifest.run_id}`, `{exact.manifest.run_id}`.", ""])
        row = {"scenario_id": scenario.scenario_id, "scenario_fingerprint": scenario.content_fingerprint,
               "vessel_count": scenario.vessel_count, "seed": scenario.seed,
               "fcfs": asdict(fcfs.summary), "rollout": asdict(rollout.summary),
               "reference": asdict(exact.summary), "diagnostics": asdict(d),
               "candidate_space_absolute_gaps": gaps}
        rows.append(row)
        print(f"{scenario.scenario_id}: FCFS={fcfs.summary.objective_value:.6f}, "
              f"rollout={rollout.summary.objective_value:.6f}, reference={exact.summary.objective_value}, "
              f"{d.optimality_status}, nodes={d.nodes_explored}, seconds={d.solver_runtime_seconds:.6f}", flush=True)
    report.extend(["## Scope And Complexity", "",
                   f"Zero FCFS waiting: {zero_fcfs}/{len(scenarios)} total; {zero_generated}/9 generated cases.",
                   "The seed-42 series varies size from 2 to 8 with new scenario IDs and generated inputs.",
                   "FCFS checks candidates once per construction step. Rollout repeatedly constructs future FCFS suffixes.",
                   "Enumeration explores a branching tree and grows combinatorially; pruning and zero-cost certificates make workload instance-dependent.",
                   "These timings do not predict production-scale runtime. A limit result is not a certified reference.", ""])
    (args.output / "summary.json").write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Zero FCFS waiting: {zero_fcfs}/{len(scenarios)} total, {zero_generated}/9 generated.")
    print(f"Report: {args.output / 'report.md'}")


if __name__ == "__main__":
    main()
