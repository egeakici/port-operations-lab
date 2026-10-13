"""Step 5 development workflow: compatibility gates, dry run, bounded smoke runs, reports, PASS-EXACT gate.

**Development-only.** Every run uses development-split scenarios (10M band) and is labelled
``development_diagnostic``; nothing here generates or reads validation (11M) or test (12M) data, trains
or modifies a model, builds a coordinator, or ranks policies. This is not the Step 7 campaign runner:
the smoke plan is a small fixed, predeclared list that cannot be widened from the command line.

Layout (Git-ignored)::

    experiments/step5_development/
        <run_id>/manifest.json (+ .sha256)          provenance, approval state, plan and its hash
        <run_id>/runs/<yard_profile>/<arm_label>/<scenario_id>.json   one record per run ("x" mode)
        <run_id>/repeats/<arm_label>/<scenario_id>.json               determinism repeats
        <run_id>/s1_reference/<arm_label>/<scenario_id>.json         Project 03 berth-only reference
        <run_id>/traces/...                         only with --trace-mode full
        <run_id>/reports/report_<sha12>.json|.md    derived summaries (--report)
        exact_gate_<UTC>/report.json                PASS-EXACT gate outputs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT
from integrated_terminal_pilot.scenarios.fingerprints import sha256_of

STEP5_ROOT = PROJECT_ROOT / "experiments" / "step5_development"
SOURCE_RUN = "dev_f5789d8c91_1ee66026"
PLAN_VERSION = "itp_step5_smoke_plan_v1"
SMOKE_SEED = 10_000_000
SMOKE_FAMILIES = ("itp_low", "itp_medium", "itp_heavy", "itp_yard_bottleneck")
SMOKE_ARMS = (("A1", None), ("A2", None), ("A3", 11), ("A3", 23), ("A3", 37))
DIAGNOSTIC_FAMILIES = ("itp_medium",)          # AM-01 balanced compatibility diagnostic
REPEAT_FAMILY = "itp_low"                      # determinism repeats for every arm
SUMMARY_METRICS = ("vessels_departed", "vessels_cargo_fulfilled", "rolled_over_containers",
                   "unfinished_ship_moves_at_stop", "cargo_completion_ratio", "completed_only_vessels",
                   "completed_only_mean_turnaround_min", "restricted_observed_turnaround_total_min")
FLAGS = {"development_only": True, "validation_executed": False, "final_test_executed": False,
         "coordinator_used": False, "rl_training": False, "checkpoints_modified": False,
         "label": "development_diagnostic", "scientific_claims": "none (bounded engineering smoke)"}


class Step5Error(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------- plan

def _source_rows() -> dict[str, dict[str, str]]:
    import csv

    index = PROJECT_ROOT / "experiments" / "scenarios" / "development" / SOURCE_RUN / "scenario_index.csv"
    if not index.exists():
        raise Step5Error(f"development source run {SOURCE_RUN} is missing")
    with index.open(encoding="utf-8") as stream:
        return {row["scenario_id"]: row for row in csv.DictReader(stream)}


def build_plan() -> dict[str, Any]:
    rows = _source_rows()
    scenarios = []
    for family in SMOKE_FAMILIES:
        scenario_id = f"{family}_development_seed{SMOKE_SEED}"
        row = rows.get(scenario_id)
        if row is None or row["status"] != "accepted" or row["split"] != "development":
            raise Step5Error(f"{scenario_id} is not an accepted development scenario of {SOURCE_RUN}")
        scenarios.append({"scenario_id": scenario_id, "family": family, "scenario_seed": SMOKE_SEED,
                          "file": f"experiments/scenarios/development/{SOURCE_RUN}/scenarios/{scenario_id}.scenario.json",
                          "file_sha256": row["file_sha256"], "physical_fingerprint": row["physical_fingerprint"],
                          "exogenous_schedule_fingerprint": row["exogenous_schedule_fingerprint"],
                          "ppo_medium_heavy_support": row["ppo_medium_heavy_support"],
                          "vessel_count": int(row["vessel_count"]), "container_count": int(row["container_count"])})
    runs = [{"kind": "run", "yard_profile": "protocol_v1_first_fit", "arm_id": arm, "ppo_training_seed": seed,
             "scenario_id": s["scenario_id"]} for s in scenarios for arm, seed in SMOKE_ARMS]
    runs += [{"kind": "run", "yard_profile": "am01_balanced_diagnostic", "arm_id": arm, "ppo_training_seed": seed,
              "scenario_id": s["scenario_id"]} for s in scenarios if s["family"] in DIAGNOSTIC_FAMILIES
             for arm, seed in SMOKE_ARMS]
    runs += [{"kind": "repeat", "yard_profile": "protocol_v1_first_fit", "arm_id": arm, "ppo_training_seed": seed,
              "scenario_id": s["scenario_id"]} for s in scenarios if s["family"] == REPEAT_FAMILY
             for arm, seed in SMOKE_ARMS]
    runs += [{"kind": "s1_reference", "yard_profile": None, "arm_id": arm, "ppo_training_seed": seed,
              "scenario_id": s["scenario_id"]} for s in scenarios for arm, seed in SMOKE_ARMS]
    return {
        "plan_version": PLAN_VERSION, "source_run": SOURCE_RUN, "split": "development",
        "scenario_seed": SMOKE_SEED, "scenarios": scenarios, "runs": runs,
        "arms": [{"arm_id": a, "ppo_training_seed": s} for a, s in SMOKE_ARMS],
        "yard_profiles": {"primary_development": "protocol_v1_first_fit",
                          "labelled_diagnostic": "am01_balanced_diagnostic (itp_medium only)"},
        "crane_fleet": "scenario fleet (4 quay cranes, approved v1 reference)", "efficiency_basis": "assigned",
        "budgets": {"per_decision_timeout": None, "fallback_action": None,
                    "max_decisions_per_run": None,
                    "note": "no engineering cap is applied; a run that cannot finish is reported, not shortened"},
        "comparison_note": "Only the berth policy differs between arms of one scenario and yard profile. "
                           "Training seeds 11/23/37 are separate checkpoints, never pooled, and are not "
                           "independent scenario samples.",
    }


def plan_digest(plan: dict[str, Any]) -> str:
    return sha256_of(plan)


# ------------------------------------------------------------------------------------------- provenance

def git_state() -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True,
                                  check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    status = run("status", "--porcelain", "--untracked-files=no")
    return {"head": run("rev-parse", "HEAD"), "tracked_dirty": bool(status),
            "tracked_changes": status.splitlines()}


def package_versions() -> dict[str, str]:
    from importlib import metadata

    out = {"python": platform.python_version(), "platform": platform.platform()}
    for name in ("numpy", "torch", "stable-baselines3", "sb3-contrib", "gymnasium", "berth-allocation-lab",
                 "integrated-terminal-pilot"):
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "not installed"
    return out


def _write_exclusive(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=1, sort_keys=True, allow_nan=False, default=str)
    with open(path, "x", encoding="utf-8") as stream:
        stream.write(text)


def _load_doc(scenario: dict[str, Any]) -> dict[str, Any]:
    from integrated_terminal_pilot.scenarios.serialization import file_sha256, load_scenario

    path = PROJECT_ROOT / scenario["file"]
    if file_sha256(path) != scenario["file_sha256"]:
        raise Step5Error(f"{path.name}: SHA-256 differs from the source index")
    doc = load_scenario(path)
    if doc["identity"]["split"] != "development":
        raise Step5Error("Step 5 development runs accept development scenarios only")
    if doc["fingerprints"]["physical_fingerprint"] != scenario["physical_fingerprint"]:
        raise Step5Error(f"{path.name}: physical fingerprint differs from the index")
    return doc


# ------------------------------------------------------------------------------------------- compatibility

def source_audit() -> dict[str, Any]:
    """Project 03 symbols and contracts the adapters rely on (read-only)."""
    import inspect

    from berth_allocation_lab.envs import dynamic_bap_env, dynamic_observation
    from berth_allocation_lab.policies import dynamic_fcfs, dynamic_online_rollout
    from berth_allocation_lab.rl import dynamic_checkpoint, dynamic_config

    def src(module) -> dict[str, str]:
        path = Path(inspect.getsourcefile(module))
        return {"path": str(path.relative_to(PROJECT_ROOT.parent)).replace("\\", "/"),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    env_cls = dynamic_bap_env.DynamicBAPEnv
    checks = {
        "observation_version": dynamic_observation.OBSERVATION_VERSION == "dynamic_obs_v1",
        "environment_version": dynamic_bap_env.ENVIRONMENT_VERSION == "dynamic_bap_env_v1",
        "event_priority_completion_arrival_horizon": dynamic_bap_env._EVENT_PRIORITY == {
            "SERVICE_COMPLETION": 0, "VESSEL_ARRIVAL": 1, "HORIZON_ENTRY": 2},
        "observation_keys": set(dynamic_observation.build_dynamic_observation_space(24, 1153).spaces) == {
            "current_time", "horizon", "terminal_features", "vessel_features", "visible_mask",
            "status_features", "placement_features", "candidate_features", "action_mask"},
        "rollout_policy_id": dynamic_online_rollout.POLICY_ID == "dynamic_online_rollout_v1",
        "rollout_reads_only_visible_state": "env" not in inspect.signature(
            dynamic_online_rollout.online_rollout_choice).parameters,
        "fcfs_key_arrival_vessel_position": "(item[4], item[1], item[3])" in inspect.getsource(
            dynamic_fcfs.online_fcfs_action),
        "ppo_policy_id": dynamic_config.POLICY_ID == "dynamic_maskable_ppo_v1",
        "ppo_time_scale_length_scale": (
            dynamic_config.DynamicPPOConfig.__dataclass_fields__["time_scale_min"].default == 1440.0
            and dynamic_config.DynamicPPOConfig.__dataclass_fields__["length_scale_m"].default == 1000.0),
        "env_candidate_capacity_2M": "self.candidate_capacity = 2 * self.max_vessels" in inspect.getsource(env_cls),
        "loader_forbids_cross_horizon_by_default": inspect.signature(
            dynamic_checkpoint.load_dynamic_checkpoint).parameters["allow_cross_horizon"].default is False,
    }
    return {"modules": {name: src(module) for name, module in (
                ("dynamic_bap_env", dynamic_bap_env), ("dynamic_observation", dynamic_observation),
                ("dynamic_fcfs", dynamic_fcfs), ("dynamic_online_rollout", dynamic_online_rollout),
                ("dynamic_checkpoint", dynamic_checkpoint), ("dynamic_config", dynamic_config))},
            "checks": checks, "pass": all(checks.values())}


def family_matrix() -> list[dict[str, Any]]:
    """Per family x arm x checkpoint PASS/BLOCK from the generator family definitions (exogenous support)."""
    from integrated_terminal_pilot.benchmark.checkpoints import all_checkpoints
    from integrated_terminal_pilot.scenarios import load_generator_config
    from integrated_terminal_pilot.scenarios.berth_projection import PPO_SUPPORT

    config = load_generator_config()
    rows = []
    for family in SMOKE_FAMILIES:
        fam = config.family(family)
        traffic, terminal = fam["traffic"], fam["terminal"]
        horizon = config.physics_profile("standard_v1")["visibility"]["future_horizon_min"]
        for arm in ("A1", "A2"):
            rows.append({"family": family, "arm": arm, "checkpoint": None, "status": "PASS",
                         "reasons": ["Project 03 policy code unchanged; adapter gates G08/G09/G10/G17 per epoch"]})
        for ref in all_checkpoints():
            env = PPO_SUPPORT[ref.regime]
            reasons = []
            if terminal["berth_length_m"] != env["berth_length_m"]:
                reasons.append(f"G12 quay {terminal['berth_length_m']} m != trained {env['berth_length_m']} m")
            if terminal["min_clearance_m"] != env["min_clearance_m"]:
                reasons.append(f"G12 clearance {terminal['min_clearance_m']} != {env['min_clearance_m']}")
            if traffic["vessel_count"] > env["max_vessels"]:
                reasons.append(f"G11 {traffic['vessel_count']} vessels > M = {env['max_vessels']}")
            if not (env["length_m"][0] <= traffic["min_vessel_length_m"] and
                    traffic["max_vessel_length_m"] <= env["length_m"][1]):
                reasons.append("G16 vessel length range outside training support")
            if not (env["workload_moves"][0] <= traffic["min_workload_moves"] and
                    traffic["max_workload_moves"] <= env["workload_moves"][1]):
                reasons.append("G16 workload range outside training support")
            if horizon != env["future_horizon_min"]:
                reasons.append(f"G14 H {horizon} != 240")
            rows.append({"family": family, "arm": "A3", "checkpoint": f"{ref.regime}/seed_{ref.training_seed}",
                         "regime": ref.regime, "training_seed": ref.training_seed,
                         "status": "BLOCK" if reasons else "PASS (family support; per-scenario and per-epoch "
                                                           "gates still apply)",
                         "reasons": reasons})
    return rows


def check_compatibility(*, exact_scenarios: int = 1) -> dict[str, Any]:
    """Read-only: source audit, checkpoint static gates, family matrix, G04 loads, G18 determinism, PASS-EXACT."""
    import numpy as np

    from integrated_terminal_pilot.benchmark.adapter import adapt_berth_view, dynamic_observation
    from integrated_terminal_pilot.benchmark.checkpoints import (
        CheckpointRef, all_checkpoints, load_checkpoint, static_checkpoint_gates, verify_all_hashes,
    )
    from integrated_terminal_pilot.benchmark.exact_gate import _ViewRecorder, exact_gate
    from integrated_terminal_pilot.benchmark.policies import NON_PPO_CANDIDATE_CAPACITY, create_berth_policy
    from integrated_terminal_pilot.scenarios import generate_scenario, load_generator_config
    from integrated_terminal_pilot.scenarios.berth_projection import build_berth_projection

    started = time.perf_counter()
    hashes_before = verify_all_hashes()
    report: dict[str, Any] = {"flags": FLAGS, "source_audit": source_audit(),
                              "checkpoint_static_gates": [static_checkpoint_gates(r) for r in all_checkpoints()],
                              "family_matrix": family_matrix()}
    config = load_generator_config()
    doc = generate_scenario(config, "itp_medium", "development", SMOKE_SEED, "degenerate_equivalence_v1")
    projection = build_berth_projection(doc)
    # Fixed inference fixture: the A1 views of one degenerate development scenario.
    recorder = _ViewRecorder(create_berth_policy("A1"))
    from integrated_terminal_pilot.policies import FirstFitYardPolicy, GreedyBerthOrderCranePolicy
    from integrated_terminal_pilot.simulator.drivers import run_episode
    from integrated_terminal_pilot.simulator.kernel import TerminalKernel

    run_episode(TerminalKernel.from_scenario(doc), berth_policy=recorder,
                crane_policy=GreedyBerthOrderCranePolicy(), yard_policy=FirstFitYardPolicy())
    fixtures = [dynamic_observation(adapt_berth_view(v, candidate_capacity=NON_PPO_CANDIDATE_CAPACITY),
                                    max_vessels=24) for v in recorder.views]
    loads = []
    for seed in (11, 23, 37):
        ref = CheckpointRef("medium_heavy", seed)
        try:
            loaded = load_checkpoint(ref, projection)
            first = [loaded.predict(o, m) for o, m in fixtures]
            second = [loaded.predict(o, m) for o, m in fixtures]
            legal = all(bool(m[a]) for (o, m), a in zip(fixtures, first))
            loads.append({"training_seed": seed, "G04": "PASS", "load_seconds": loaded.load_seconds,
                          "torch_threads": loaded.torch_threads,
                          "G18_repeat_identical": first == second, "G19_all_actions_in_mask": legal,
                          "fixture_epochs": len(fixtures),
                          "fixture_actions_sha256": hashlib.sha256(json.dumps(first).encode()).hexdigest()})
        except Exception as error:  # noqa: BLE001 - recorded as a gate failure, never hidden
            loads.append({"training_seed": seed, "G04": f"FAIL: {type(error).__name__}: {error}"})
    for ref in all_checkpoints():
        if ref.regime == "tiny":
            loads.append({"regime": "tiny", "training_seed": ref.training_seed, "G04": "NOT_ATTEMPTED",
                          "reason": "G12/G11: every Project I family uses a 1200 m quay (tiny trained on 600 m) "
                                    "and the tiny checkpoints support M = 8; no Project I scenario is eligible"})
    report["checkpoint_loads"] = loads
    exact = []
    for family in SMOKE_FAMILIES[:max(1, exact_scenarios)] if exact_scenarios else ():
        gate_doc = doc if family == "itp_medium" else generate_scenario(config, family, "development", SMOKE_SEED,
                                                                        "degenerate_equivalence_v1")
        for arm, seed in SMOKE_ARMS:
            row = exact_gate(gate_doc, arm, seed)
            exact.append({k: row[k] for k in ("scenario_id", "arm_id", "ppo_training_seed", "pass", "checks",
                                               "decisions", "wait_decisions")})
    report["pass_exact_sample"] = exact
    report["checkpoint_hashes_before"] = hashes_before
    report["checkpoint_hashes_after"] = verify_all_hashes()
    arms = {}
    arms["A1"] = "PASS" if report["source_audit"]["pass"] and all(
        r["pass"] for r in exact if r["arm_id"] == "A1") else "BLOCK"
    arms["A2"] = "PASS" if report["source_audit"]["pass"] and all(
        r["pass"] for r in exact if r["arm_id"] == "A2") else "BLOCK"
    for seed in (11, 23, 37):
        static = next(g for g in report["checkpoint_static_gates"]
                      if g["regime"] == "medium_heavy" and g["training_seed"] == seed)
        load = next(r for r in loads if r.get("training_seed") == seed and "regime" not in r)
        ok = (report["source_audit"]["pass"] and static["pass"] and load["G04"] == "PASS" and load.get("G18_repeat_identical")
              and load.get("G19_all_actions_in_mask")
              and all(r["pass"] for r in exact if r["arm_id"] == "A3" and r["ppo_training_seed"] == seed))
        arms[f"A3-train{seed}"] = "PASS" if ok else "BLOCK"
    for seed in (11, 23, 37):
        arms[f"tiny-train{seed}"] = "BLOCK (G12/G11: no eligible Project I family)"
    report["arm_status"] = arms
    report["pass"] = (all(v == "PASS" for k, v in arms.items() if not k.startswith("tiny"))
                      and report["checkpoint_hashes_after"]["ok"])
    report["wall_seconds"] = time.perf_counter() - started
    return report


# ------------------------------------------------------------------------------------------- smoke

def _run_path(run_dir: Path, item: dict[str, Any]) -> Path:
    from integrated_terminal_pilot.benchmark.runner import arm_label

    label = arm_label(item["arm_id"], item["ppo_training_seed"])
    if item["kind"] == "run":
        return run_dir / "runs" / item["yard_profile"] / label / f"{item['scenario_id']}.json"
    if item["kind"] == "repeat":
        return run_dir / "repeats" / label / f"{item['scenario_id']}.json"
    return run_dir / "s1_reference" / label / f"{item['scenario_id']}.json"


def select_runs(plan: dict[str, Any], *, policy: str | None, checkpoint_seed: int | None,
                yard_policy: str | None, max_runs: int | None) -> list[dict[str, Any]]:
    from integrated_terminal_pilot.benchmark.profiles import yard_profile

    runs = plan["runs"]
    if policy is not None:
        runs = [r for r in runs if r["arm_id"] == policy]
    if checkpoint_seed is not None:
        if policy not in (None, "A3"):
            raise Step5Error("--checkpoint-seed applies to A3 only")
        runs = [r for r in runs if r["ppo_training_seed"] == checkpoint_seed]
    if yard_policy is not None:
        name, _ = yard_profile(yard_policy)
        runs = [r for r in runs if r["yard_profile"] in (name, None)]
    if max_runs is not None:
        runs = runs[:max_runs]
    return runs


def _s1_reference(doc: dict[str, Any], arm_id: str, seed: int | None) -> dict[str, Any]:
    """Project 03 berth-only reference on the projection (unchanged ``run_dynamic_episode``)."""
    from berth_allocation_lab.policies.dynamic_online_rollout import POLICY_ID as ROLLOUT_ID
    from berth_allocation_lab.rl.dynamic_evaluation import FCFS_ID, run_dynamic_episode

    from integrated_terminal_pilot.benchmark.checkpoints import CheckpointRef, load_checkpoint
    from integrated_terminal_pilot.scenarios.berth_projection import build_berth_projection

    projection = build_berth_projection(doc)
    method = {"A1": FCFS_ID, "A2": ROLLOUT_ID, "A3": "dynamic_maskable_ppo_v1"}[arm_id]
    model = load_checkpoint(CheckpointRef("medium_heavy", seed), projection).model if arm_id == "A3" else None
    out = run_dynamic_episode(projection, horizon_min=projection.future_horizon_min, max_vessels=24,
                              method=method, model=model)
    keep = ("status", "failure", "vessel_count", "vessel_count_completed", "total_waiting_time_min",
            "mean_waiting_time_min", "p95_waiting_time_min", "mean_turnaround_time_min", "intentional_waits",
            "legal_wait_opportunities", "decision_count", "runtime_seconds", "inference_seconds",
            "physical_fingerprint", "method")
    return {"label": "Project 03 DynamicBAPEnv berth-only reference on the berth projection (nominal service; "
                     "no cranes or yard) - S1 context, not an integrated result",
            "scenario_id": doc["identity"]["scenario_id"], "arm_id": arm_id, "ppo_training_seed": seed,
            "reference": {k: out.get(k) for k in keep}}


def smoke(args: argparse.Namespace) -> int:
    from integrated_terminal_pilot.benchmark.profiles import approval_state
    from integrated_terminal_pilot.benchmark.runner import run_arm

    plan = build_plan()
    digest = plan_digest(plan)
    runs = select_runs(plan, policy=args.policy, checkpoint_seed=args.checkpoint_seed,
                       yard_policy=args.yard_policy, max_runs=args.max_runs)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("s5dev_%Y%m%dT%H%M%SZ")
    run_dir = STEP5_ROOT / run_id
    manifest_path = run_dir / "manifest.json"
    if args.resume:
        if not manifest_path.exists():
            raise Step5Error(f"--resume: {manifest_path} does not exist")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["plan_sha256"] != digest:
            raise Step5Error("--resume: the stored plan hash differs from the current plan; refusing")
        if manifest["selection"] != _selection(args):
            raise Step5Error("--resume: run selection differs from the stored manifest; refusing")
    else:
        if run_dir.exists():
            raise Step5Error(f"{run_dir} exists; choose a new --run-id or pass --resume (no overwrite)")
        manifest = {
            "manifest_version": "itp_step5_manifest_v1", "run_id": run_id, **FLAGS,
            "created_utc": datetime.now(timezone.utc).isoformat(), "git": git_state(),
            "packages": package_versions(), "plan_sha256": digest, "plan": plan, "selection": _selection(args),
            "planned_runs": len(runs), "trace_mode": args.trace_mode,
            "approval_state": approval_state(),
        }
        manifest["scientific_protocol_lock"] = manifest["approval_state"]["scientific_protocol_lock"]
        _write_exclusive(manifest_path, manifest)
        sidecar = manifest_path.with_name("manifest.json.sha256")
        with open(sidecar, "x", encoding="utf-8") as stream:
            stream.write(hashlib.sha256(manifest_path.read_bytes()).hexdigest() + "  manifest.json\n")
    scenarios = {s["scenario_id"]: s for s in plan["scenarios"]}
    docs: dict[str, dict[str, Any]] = {}
    done = skipped = 0
    for index, item in enumerate(runs, start=1):
        path = _run_path(run_dir, item)
        if path.exists():
            skipped += 1
            continue
        scenario_id = item["scenario_id"]
        if scenario_id not in docs:
            docs.clear()  # one scenario document in memory at a time
            docs[scenario_id] = _load_doc(scenarios[scenario_id])
        doc = docs[scenario_id]
        started = time.perf_counter()
        if item["kind"] == "s1_reference":
            record = _s1_reference(doc, item["arm_id"], item["ppo_training_seed"])
        else:
            trace_dir = None
            if args.trace_mode == "full":
                trace_dir = run_dir / "traces" / path.relative_to(run_dir).with_suffix("")
            record = run_arm(doc, arm_id=item["arm_id"], training_seed=item["ppo_training_seed"],
                             yard_profile_name=item["yard_profile"], trace_mode=args.trace_mode, trace_dir=trace_dir)
        record = {"run_id": run_id, "plan_sha256": digest, "item": item, **FLAGS,
                  "scenario_file_sha256": scenarios[scenario_id]["file_sha256"], **record}
        _write_exclusive(path, record)
        done += 1
        if args.progress:
            sc = record.get("service_compliance", {})
            print(f"[{index}/{len(runs)}] {item['kind']} {item.get('yard_profile')} "
                  f"{item['arm_id']}{'' if item['ppo_training_seed'] is None else '-' + str(item['ppo_training_seed'])} "
                  f"{scenario_id} {record.get('status', record.get('reference', {}).get('status'))} "
                  f"departed={sc.get('vessels_departed')} fulfilled={sc.get('vessels_cargo_fulfilled')} "
                  f"{time.perf_counter() - started:.1f}s", flush=True)
    print(json.dumps({"run_dir": str(run_dir), "executed": done, "already_present": skipped,
                      "planned": len(runs)}, indent=1))
    return 0


def _selection(args: argparse.Namespace) -> dict[str, Any]:
    return {"policy": args.policy, "checkpoint_seed": args.checkpoint_seed, "yard_policy": args.yard_policy,
            "max_runs": args.max_runs, "trace_mode": args.trace_mode}


# ------------------------------------------------------------------------------------------- report

def _latest_run_dir() -> Path:
    candidates = sorted(p for p in STEP5_ROOT.glob("s5dev_*") if (p / "manifest.json").exists()) \
        if STEP5_ROOT.exists() else []
    if not candidates:
        raise Step5Error(f"no Step 5 development runs under {STEP5_ROOT}")
    return candidates[-1]


def build_report(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    recorded = hashlib.sha256((run_dir / "manifest.json").read_bytes()).hexdigest()
    sidecar = (run_dir / "manifest.json.sha256").read_text(encoding="utf-8").split()[0]
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(run_dir.rglob("*.json"))
               if p.name not in ("manifest.json",) and "reports" not in p.parts]
    runs = [r for r in records if r.get("item", {}).get("kind") == "run"]
    repeats = [r for r in records if r.get("item", {}).get("kind") == "repeat"]
    references = [r for r in records if r.get("item", {}).get("kind") == "s1_reference"]
    rows = []
    for r in runs:
        sc = r.get("service_compliance", {})
        d = r.get("decisions", {})
        rows.append({
            "yard_profile": r["item"]["yard_profile"], "arm": r["arm"]["arm_label"],
            "ppo_training_seed": r["arm"]["ppo_training_seed"], "scenario_id": r["scenario"]["scenario_id"],
            "family": r["scenario"]["family"], "scenario_seed": r["scenario"]["scenario_seed"],
            "status": r["status"], "status_reason": r.get("status_reason"),
            **{k: sc.get(k) for k in SUMMARY_METRICS},
            "vessels_total": sc.get("vessels_total"),
            "T_end_censored_total_turnaround_min": r.get("kpi", {}).get("total_turnaround_min"),
            "mean_berth_waiting_min": r.get("kpi", {}).get("mean_berth_waiting_min"),
            "p95_berth_waiting_min": r.get("kpi", {}).get("p95_berth_waiting_min"),
            "makespan_min": r.get("kpi", {}).get("makespan_min"),
            "realized_to_nominal_max": r.get("realized_to_nominal_occupancy", {}).get("max"),
            "berth_decisions": d.get("berth_decisions"), "wait_selected": d.get("wait_selected"),
            "forecast_epochs": d.get("forecast_epoch_modes", {}).get("FORECAST"),
            "policy_seconds_mean": d.get("seconds", {}).get("policy", {}).get("mean"),
            "policy_seconds_p95": d.get("seconds", {}).get("policy", {}).get("p95"),
            "policy_seconds_max": d.get("seconds", {}).get("policy", {}).get("max"),
            "rejections": len(r.get("rejections", [])), "audits_ok": r.get("audits", {}).get("ok"),
            "move_reconciliation_ok": r.get("per_vessel_move_reconciliation_ok"),
            "trace_sha256": r.get("digests", {}).get("trace_sha256"),
            "comparison_fingerprint": r.get("comparison_fingerprint"),
            "run_wall_seconds": r.get("engineering", {}).get("run_wall_seconds"),
            "blocked_reasons": r.get("blocked_reasons"),
        })
    fairness = {}
    for r in runs:
        key = f"{r['item']['yard_profile']}|{r['scenario']['scenario_id']}"
        fairness.setdefault(key, set()).add(r["comparison_fingerprint"])
    fairness_ok = {k: len(v) == 1 for k, v in fairness.items()}
    determinism = []
    for rep in repeats:
        twin = next((r for r in runs if r["item"]["yard_profile"] == rep["item"]["yard_profile"]
                     and r["arm"]["arm_label"] == rep["arm"]["arm_label"]
                     and r["scenario"]["scenario_id"] == rep["scenario"]["scenario_id"]), None)
        determinism.append({"arm": rep["arm"]["arm_label"], "scenario_id": rep["scenario"]["scenario_id"],
                            "identical_trace_digest": twin is not None and
                            twin.get("digests", {}).get("trace_sha256") == rep.get("digests", {}).get("trace_sha256")})
    return {
        "report_version": "itp_step5_report_v1", "run_id": manifest["run_id"], **FLAGS,
        "manifest_sha256": recorded, "manifest_sidecar_matches": recorded == sidecar,
        "plan_sha256": manifest["plan_sha256"], "git": manifest["git"],
        "scientific_protocol_lock": manifest["scientific_protocol_lock"],
        "approval_state_at_run": {k: manifest["approval_state"][k] for k in
                                  ("frozen", "proposed_pending_review", "am01", "scientific_protocol_lock")},
        "planned_runs": manifest["planned_runs"], "records": len(records),
        "rows": rows, "fairness_comparison_fingerprint_identical": fairness_ok,
        "determinism_repeats": determinism,
        "s1_reference": [{"arm": r["arm_id"] + ("" if r["ppo_training_seed"] is None else
                                                f"-train{r['ppo_training_seed']}"),
                          "scenario_id": r["scenario_id"], **r["reference"]} for r in references],
        "interpretation": "Development diagnostics only. No arm is ranked, selected or declared better; "
                          "departure counts are never read without cargo fulfillment, rollover and "
                          "unfinished work next to them.",
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [f"# Step 5 development smoke report `{report['run_id']}`", "",
             "Development diagnostics only (development split, seed 10,000,000). Not validation, not a "
             "ranking; scientific protocol lock: **" + report["scientific_protocol_lock"] + "**.", "",
             "| yard profile | arm | family | status | departed | cargo fulfilled | rolled over | unfinished moves | "
             "T_end-censored total turnaround | restricted observed turnaround | mean / P95 wait | decisions (WAIT) "
             "| FORECAST epochs | policy s mean / max | rejections | audits | trace sha |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]

    def f(x, nd=1):
        return "—" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))

    for r in report["rows"]:
        lines.append(
            f"| {r['yard_profile']} | {r['arm']} | {r['family']} | {r['status']} | "
            f"{f(r['vessels_departed'])}/{f(r['vessels_total'])} | {f(r['vessels_cargo_fulfilled'])} | "
            f"{f(r['rolled_over_containers'])} | {f(r['unfinished_ship_moves_at_stop'])} | "
            f"{f(r['T_end_censored_total_turnaround_min'])} | {f(r['restricted_observed_turnaround_total_min'])} | "
            f"{f(r['mean_berth_waiting_min'])} / {f(r['p95_berth_waiting_min'])} | "
            f"{f(r['berth_decisions'])} ({f(r['wait_selected'])}) | {f(r['forecast_epochs'])} | "
            f"{f(r['policy_seconds_mean'], 4)} / {f(r['policy_seconds_max'], 4)} | {f(r['rejections'])} | "
            f"{f(r['audits_ok'])} | `{(r['trace_sha256'] or '')[:12]}` |")
    lines += ["", "Fairness (one comparison fingerprint per scenario and yard profile): "
              + ("all identical" if all(report["fairness_comparison_fingerprint_identical"].values()) else
                 json.dumps(report["fairness_comparison_fingerprint_identical"])),
              "", "Determinism repeats: " + ", ".join(
                  f"{d['arm']} {'identical' if d['identical_trace_digest'] else 'DIFFERENT'}"
                  for d in report["determinism_repeats"]), ""]
    if report["s1_reference"]:
        lines += ["## Project 03 berth-only reference (nominal service, no cranes/yard; S1 context)", "",
                  "| arm | scenario | status | total waiting (min) | WAITs | decisions |", "| --- | --- | --- | --- | --- | --- |"]
        for r in report["s1_reference"]:
            lines.append(f"| {r['arm']} | {r['scenario_id']} | {r['status']} | {f(r['total_waiting_time_min'])} | "
                         f"{f(r['intentional_waits'])} | {f(r['decision_count'])} |")
    return "\n".join(lines) + "\n"


def report(args: argparse.Namespace) -> int:
    run_dir = STEP5_ROOT / args.run_id if args.run_id else _latest_run_dir()
    data = build_report(run_dir)
    text = json.dumps(data, indent=1, sort_keys=True, allow_nan=False, default=str)
    sha = hashlib.sha256(text.encode()).hexdigest()[:12]
    out = run_dir / "reports"
    out.mkdir(exist_ok=True)
    json_path, md_path = out / f"report_{sha}.json", out / f"report_{sha}.md"
    if not json_path.exists():
        json_path.write_text(text, encoding="utf-8")
        md_path.write_text(_markdown(data), encoding="utf-8")
    print(_markdown(data))
    print(json.dumps({"report": str(json_path), "markdown": str(md_path)}, indent=1))
    return 0


# ------------------------------------------------------------------------------------------- exact gate

def exact_gate_command(args: argparse.Namespace) -> int:
    from integrated_terminal_pilot.benchmark.exact_gate import exact_gate
    from integrated_terminal_pilot.scenarios import generate_scenario, load_generator_config

    config = load_generator_config()
    plan = dict(item.split("=") for item in (args.family or ["itp_medium=30", "itp_heavy=30", "itp_low=10",
                                                             "itp_yard_bottleneck=10"]))
    arms = [(a, s) for a, s in SMOKE_ARMS if args.policy in (None, a)
            and (args.checkpoint_seed is None or s == args.checkpoint_seed)]
    rows = []
    started = time.perf_counter()
    for family, count in plan.items():
        for seed in range(SMOKE_SEED, SMOKE_SEED + int(count)):
            doc = generate_scenario(config, family, "development", seed, "degenerate_equivalence_v1")
            for arm, training_seed in arms:
                row = exact_gate(doc, arm, training_seed)
                rows.append(row)
                if args.progress:
                    print(f"{family} {seed} {arm}{'' if training_seed is None else '-' + str(training_seed)} "
                          f"pass={row['pass']} decisions={row['decisions']} waits={row['wait_decisions']}",
                          flush=True)
    summary = {"label": "Step 5 PASS-EXACT gate (degenerate profile): integrated arm vs Project 03 DynamicBAPEnv, "
                        "decision by decision, observations bit-equal", **FLAGS,
               "plan": plan, "first_seed": SMOKE_SEED, "arms": [f"{a}{'' if s is None else '-' + str(s)}"
                                                                for a, s in arms],
               "by_arm": {}, "wall_seconds": time.perf_counter() - started}
    for arm, training_seed in arms:
        mine = [r for r in rows if r["arm_id"] == arm and r["ppo_training_seed"] == training_seed]
        summary["by_arm"][f"{arm}{'' if training_seed is None else '-train' + str(training_seed)}"] = {
            "scenarios": len(mine), "passed": sum(r["pass"] for r in mine),
            "failed": [r["scenario_id"] for r in mine if not r["pass"]],
            "decisions": sum(r["decisions"] for r in mine), "wait_decisions": sum(r["wait_decisions"] for r in mine)}
    summary["pass"] = all(v["passed"] == v["scenarios"] for v in summary["by_arm"].values())
    if not args.no_write:
        out = STEP5_ROOT / datetime.now(timezone.utc).strftime("exact_gate_%Y%m%dT%H%M%SZ")
        _write_exclusive(out / "report.json", {"summary": summary, "rows": rows})
        summary["report"] = str(out / "report.json")
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0 if summary["pass"] else 1


# ------------------------------------------------------------------------------------------- CLI

def dry_run(args: argparse.Namespace) -> int:
    from integrated_terminal_pilot.benchmark.profiles import YARD_PROFILES, approval_state

    plan = build_plan()
    runs = select_runs(plan, policy=args.policy, checkpoint_seed=args.checkpoint_seed,
                       yard_policy=args.yard_policy, max_runs=args.max_runs)
    print(json.dumps({**FLAGS, "writes": "nothing (dry run)", "plan_sha256": plan_digest(plan),
                      "scenarios": plan["scenarios"], "selected_runs": runs, "selected_count": len(runs),
                      "yard_profiles": YARD_PROFILES, "approval_state": approval_state(),
                      "development_checks": ["--check-compatibility (read-only gates G01-G21, PASS-EXACT sample)",
                                             "--exact-gate (degenerate profile, 80 development scenarios)",
                                             "--smoke (this plan)", "--report"]},
                     indent=1, sort_keys=True, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_step5_independent_benchmark",
        description="Project I Step 5 independent berth-policy benchmark - development-only tools.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-compatibility", action="store_true", help="read-only gates G01-G21 + PASS-EXACT sample")
    mode.add_argument("--dry-run", action="store_true", help="list planned checks and all pending approvals")
    mode.add_argument("--smoke", action="store_true", help="bounded predeclared development smoke runs")
    mode.add_argument("--report", action="store_true", help="summarize existing outputs; runs nothing")
    mode.add_argument("--exact-gate", action="store_true", help="PASS-EXACT gate on degenerate development scenarios")
    parser.add_argument("--policy", choices=("A1", "A2", "A3"))
    parser.add_argument("--checkpoint-seed", type=int, choices=(11, 23, 37))
    parser.add_argument("--yard-policy", help="yard profile or policy id (default: plan, protocol_v1_first_fit)")
    parser.add_argument("--trace-mode", choices=("summary", "full"), default="summary")
    parser.add_argument("--max-runs", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--family", action="append", help="--exact-gate only: family=count (repeatable)")
    parser.add_argument("--exact-scenarios", type=int, default=1,
                        help="--check-compatibility: families sampled for the PASS-EXACT check (0 to skip)")
    parser.add_argument("--no-write", action="store_true", help="--exact-gate: print only")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_runs is not None and args.max_runs <= 0:
        raise SystemExit("--max-runs must be positive")
    if args.resume and not (args.smoke and args.run_id):
        raise SystemExit("--resume needs --smoke and --run-id")
    if args.run_id and not all(c.isalnum() or c in "_-" for c in args.run_id):
        raise SystemExit("--run-id may contain letters, digits, '_' and '-' only")
    try:
        if args.check_compatibility:
            report_data = check_compatibility(exact_scenarios=args.exact_scenarios)
            print(json.dumps(report_data, indent=1, sort_keys=True, default=str))
            return 0 if report_data["pass"] else 1
        if args.dry_run:
            return dry_run(args)
        if args.smoke:
            return smoke(args)
        if args.report:
            return report(args)
        return exact_gate_command(args)
    except Step5Error as error:
        print(f"step5: {error}", file=sys.stderr)
        return 2


__all__ = ["FLAGS", "STEP5_ROOT", "build_plan", "build_report", "check_compatibility", "main", "plan_digest"]
