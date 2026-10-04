"""Adapters and fail-closed provenance checks for locked Step 9/11 evidence."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from berth_allocation_lab.benchmark.config import BenchmarkConfig, BenchmarkError, BenchmarkSource
from berth_allocation_lab.benchmark.stats import TRAINING_SEEDS, TIE_TOLERANCE
from berth_allocation_lab.core import BAPPlacement, find_schedule_violations, total_waiting_time
from berth_allocation_lab.rl.suites import (
    build_config_suites, physical_fingerprint, scenario_identity,
)

STATIC_POLICY_IDS = {
    "fcfs": "static_fcfs_v1",
    "rollout": "static_greedy_rollout_v1",
    "exact": "static_candidate_enumeration_v1",
}
DYNAMIC_POLICY_IDS = {
    "fcfs": "dynamic_online_fcfs_v1",
    "rollout": "dynamic_online_rollout_v1",
    "ppo": "dynamic_maskable_ppo_v1",
}


@dataclass
class LockedDataset:
    source: BenchmarkSource
    weights: dict[str, float]
    scenarios: dict[str, dict[str, Any]]
    costs: dict[tuple[str, int | None, str], float]
    inventory: list[dict[str, Any]]
    audit: dict[str, Any]
    reconciliation: dict[str, Any]

    def series(self, method: str, seed: int | None = None) -> dict[str, float]:
        return {sid: value for (name, row_seed, sid), value in self.costs.items()
                if name == method and row_seed == seed}

    def methods(self) -> list[str]:
        return sorted({method for method, _, _ in self.costs})


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BenchmarkError(f"Required locked artifact missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise BenchmarkError(f"Required locked artifact missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_decision(path: Path) -> tuple[dict[str, Any], str]:
    digest = sha256_file(path)
    sidecar = path.with_name(path.name + ".sha256")
    sidecar_tokens = sidecar.read_text(encoding="utf-8").split() if sidecar.is_file() else []
    if not sidecar_tokens or sidecar_tokens[0] != digest:
        raise BenchmarkError(f"Decision SHA-256 sidecar mismatch: {path}")
    value = _read_json(path)
    if value.get("uses_test_results") is not False or value.get("source_git_dirty_at_decision") is not False:
        raise BenchmarkError(f"Decision is not clean validation-only evidence: {path}")
    if value.get("final_testing_permitted") is not True:
        raise BenchmarkError(f"Frozen decision did not authorize testing: {path}")
    return value, digest


def _same(actual: float, expected: float, label: str) -> None:
    if not math.isfinite(actual) or not math.isclose(actual, expected, abs_tol=TIE_TOLERANCE, rel_tol=0):
        raise BenchmarkError(f"Locked metric mismatch for {label}: {actual!r} != {expected!r}")


def _check_weights(config: BenchmarkConfig, regime: str, components: Any) -> dict[str, float]:
    declared = config.normalized_weights(regime)
    actual = {component.base_scenario_id: component.weight for component in components}
    total = sum(actual.values())
    actual = {name: value / total for name, value in actual.items()}
    if declared != actual:
        raise BenchmarkError(f"Benchmark family weights differ from frozen {regime} config.")
    return declared


def _suite_scenarios(identities: list[dict[str, Any]], generated: Any) -> dict[str, Any]:
    frozen = {row["scenario_id"]: row for row in identities}
    if len(frozen) != len(identities) or len(frozen) != len(generated):
        raise BenchmarkError("Frozen suite has duplicate or missing scenario identities.")
    scenarios = {scenario.scenario_id: scenario for scenario in generated}
    if set(frozen) != set(scenarios):
        raise BenchmarkError("Frozen test identities differ from the configured suite.")
    for sid, scenario in scenarios.items():
        if scenario_identity(scenario) != frozen[sid]:
            raise BenchmarkError(f"Scenario fingerprint/input mismatch: {sid}")
    return scenarios


def _training_overlap(paths: list[Path], locked: set[str], *, static: bool) -> int:
    seen: set[str] = set()
    for path in paths:
        if not path.is_file():
            raise BenchmarkError(f"Training episode evidence missing: {path}")
        if static:
            with path.open(newline="", encoding="utf-8") as stream:
                for row in csv.DictReader(stream):
                    if row["scenario_split"] != "train":
                        raise BenchmarkError(f"Nontraining episode in {path}")
                    seen.add(row["physical_fingerprint"])
        else:
            for row in json.loads(path.read_text(encoding="utf-8")):
                seen.add(row["physical_fingerprint"])
    overlap = seen & locked
    if overlap:
        raise BenchmarkError(f"Training/test physical leakage: {sorted(overlap)[:3]}")
    return len(seen)


def _checkpoint(path: Path, *, experiment: str, seed: int, selected_step: int,
                expected_sha: str, config_sha: str) -> dict[str, Any]:
    digest = sha256_file(path)
    if digest != expected_sha:
        raise BenchmarkError(f"Selected checkpoint hash mismatch: {path}")
    sidecar = _read_json(path.with_name(path.stem + ".metadata.json"))
    if (sidecar.get("experiment_id", experiment) != experiment or
            sidecar.get("training_seed") != seed or
            sidecar.get("timesteps") != selected_step or
            sidecar.get("checkpoint_kind") != "best_validation" or
            sidecar.get("config_sha256", config_sha) != config_sha or
            sidecar.get("git_dirty") is not False):
        raise BenchmarkError(f"Selected checkpoint sidecar mismatch: {path}")
    return sidecar


def load_static(config: BenchmarkConfig, source: BenchmarkSource,
                decisions: dict[str, tuple[dict[str, Any], str]]) -> LockedDataset:
    from berth_allocation_lab.rl.config import StaticPPOExperimentConfig

    frozen = StaticPPOExperimentConfig.load_yaml(config.resolve(source.config_path))
    if frozen.experiment_id != source.experiment_id or frozen.training.training_seeds != TRAINING_SEEDS:
        raise BenchmarkError(f"Static config/seed mismatch: {source.config_path}")
    weights = _check_weights(config, source.regime, frozen.components)
    suite = build_config_suites(frozen)["test"]
    evaluation = config.resolve(source.evaluation_path)
    manifest = _read_json(evaluation / "evaluation_manifest.json")
    if (manifest.get("experiment_id") != source.experiment_id or
            manifest.get("config_sha256") != frozen.source_sha256 or
            manifest.get("checkpoint_kind") != "best_validation" or
            manifest.get("git_dirty") is not False or
            manifest.get("objective_units") != "vessel-minutes (raw, unscaled)"):
        raise BenchmarkError(f"Static evaluation provenance mismatch: {evaluation}")
    scenarios = _suite_scenarios(manifest["suites"]["test"]["identities"], suite.scenarios)
    decision_kind = "v1" if source.version == "v1" else "v2"
    decision, decision_sha = decisions[decision_kind]
    if (manifest["validation_decision"]["sha256"] != decision_sha or
            manifest["validation_decision"]["path"] != config.decisions[decision_kind]):
        raise BenchmarkError(f"Static evaluation decision mismatch: {evaluation}")
    v2_decision = decisions["v2"][0]
    if v2_decision.get("decision_rule_version") != "v2_rule_1":
        raise BenchmarkError("Static v2 decision version changed.")
    if source.version == "v1":
        original_rows = {r["training_seed"]: r for r in
                         decisions["v1"][0]["regimes"][source.regime]["seeds"]}
        copied_rows = {r["training_seed"]: r for r in
                       v2_decision["regimes"][source.regime]["v1_seeds"]}
        if set(original_rows) != set(TRAINING_SEEDS) or set(copied_rows) != set(original_rows):
            raise BenchmarkError("Static v1/v2 decision seed coverage mismatch.")
        for seed in TRAINING_SEEDS:
            for field in ("checkpoint_id", "checkpoint_sha256", "selected_timesteps",
                          "ppo_validation_mean_min"):
                if original_rows[seed][field] != copied_rows[seed][field]:
                    raise BenchmarkError(f"Static v1 decision changed in v2: {seed}/{field}")
    expected_decision_rows = v2_decision["regimes"][source.regime][
        "v1_seeds" if source.version == "v1" else "seeds"]
    selected_by_seed = {row["training_seed"]: row for row in expected_decision_rows}
    if set(selected_by_seed) != set(TRAINING_SEEDS):
        raise BenchmarkError("Static decision lacks three training seeds.")
    checkpoint_refs = {row["training_seed"]: row for row in manifest["checkpoints"]}
    if set(checkpoint_refs) != set(TRAINING_SEEDS):
        raise BenchmarkError("Static evaluation lacks selected checkpoints.")
    inventory, training_paths = [], []
    evaluation_sha = sha256_file(evaluation / "per_instance.jsonl")
    for seed in TRAINING_SEEDS:
        row = selected_by_seed[seed]
        run = frozen.resolve(frozen.output_dir) / source.experiment_id / f"seed_{seed}"
        training = _read_json(run / "manifest.json")
        if (training.get("status") != "completed" or training.get("git_dirty") is not False or
                training.get("config_sha256") != frozen.source_sha256 or
                training.get("training_seed") != seed or
                training.get("git_commit_hash") != row["git_commit_hash"] or
                training["selection"]["selected_timesteps"] != row["selected_timesteps"]):
            raise BenchmarkError(f"Static training manifest mismatch: {run}")
        _same(training["selection"]["selected_mean_total_waiting_time_min"],
              row["ppo_validation_mean_min"], f"static_validation/{source.regime}/{seed}")
        if ({item["physical_fingerprint"] for item in training["validation_scenario_set"]} !=
                set(row["validation_physical_fingerprints"])):
            raise BenchmarkError(f"Static validation identity mismatch: {run}")
        reference = checkpoint_refs[seed]
        if (reference["checkpoint_id"] != row["checkpoint_id"] or
                manifest["checkpoint_sha256"].get(reference["checkpoint_id"]) != row["checkpoint_sha256"]):
            raise BenchmarkError(f"Static evaluation selected wrong checkpoint: {run}")
        checkpoint_path = config.resolve(reference["checkpoint_path"])
        metadata = _checkpoint(checkpoint_path, experiment=source.experiment_id, seed=seed,
                               selected_step=row["selected_timesteps"],
                               expected_sha=row["checkpoint_sha256"],
                               config_sha=frozen.source_sha256)
        if metadata.get("model_id") != row["checkpoint_id"] or metadata.get("policy_id") != frozen.policy_id:
            raise BenchmarkError(f"Static checkpoint policy mismatch: {checkpoint_path}")
        training_paths.append(run / "train_episodes.csv")
        inventory.append({
            "experiment_id": source.experiment_id, "formulation": "static",
            "regime": source.regime, "version": source.version,
            "source_git_commit": training["git_commit_hash"], "git_dirty": False,
            "config_sha256": frozen.source_sha256, "training_seed": seed,
            "checkpoint_id": row["checkpoint_id"],
            "checkpoint_sha256": row["checkpoint_sha256"],
            "checkpoint_path": reference["checkpoint_path"],
            "environment_version": metadata["environment_version"],
            "observation_version": metadata["observation_definition_version"],
            "policy_id": metadata["policy_id"], "horizon_min": None,
            "scenario_suite": "test", "scenario_split": "test",
            "physical_fingerprints": sorted(physical_fingerprint(s) for s in suite.scenarios),
            "evaluation_path": str(evaluation / "per_instance.jsonl"),
            "evaluation_sha256": evaluation_sha,
            "evaluation_device": "cpu_inferred_from_torch_cpu_build",
            "completion_status": training["status"],
        })
    test_fp = {physical_fingerprint(s) for s in suite.scenarios}
    validation_fp = {x["physical_fingerprint"] for x in
                     _read_json(frozen.resolve(frozen.output_dir) / source.experiment_id /
                                "seed_11" / "manifest.json")["validation_scenario_set"]}
    if test_fp & validation_fp:
        raise BenchmarkError("Static test/validation physical overlap.")
    train_count = _training_overlap(training_paths, test_fp | validation_fp, static=True)
    costs: dict[tuple[str, int | None, str], float] = {}
    expected_methods = {"fcfs", "rollout", "ppo"}
    if source.regime == "tiny":
        expected_methods.add("exact")
    row_count = 0
    with (evaluation / "per_instance.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if record["suite"] != "test":
                continue
            row_count += 1
            sid, method = record["scenario_id"], record["method"]
            if sid not in scenarios or method not in expected_methods:
                raise BenchmarkError(f"Unexpected static test row: {sid}/{method}")
            scenario = scenarios[sid]
            if (record["scenario_split"] != "test" or
                    record["physical_fingerprint"] != physical_fingerprint(scenario) or
                    record["scenario_fingerprint"] != scenario.content_fingerprint or
                    record["vessel_count"] != scenario.vessel_count or
                    record["component"] not in weights or
                    not sid.startswith(record["component"] + "_test_seed") or
                    record["is_valid"] is not True or record["run_status"] != "completed" or
                    record["validation_status"] != "valid" or
                    record["vessel_count_completed"] != scenario.vessel_count):
                raise BenchmarkError(f"Invalid static test row: {sid}/{method}")
            seed = record.get("training_seed") if method == "ppo" else None
            if method == "ppo":
                if seed not in TRAINING_SEEDS or record["policy_id"] != frozen.policy_id or (
                        record["checkpoint_id"] != checkpoint_refs[seed]["checkpoint_id"]):
                    raise BenchmarkError(f"Static PPO provenance mismatch: {sid}")
            elif record["policy_id"] != STATIC_POLICY_IDS[method]:
                raise BenchmarkError(f"Static baseline policy mismatch: {sid}/{method}")
            if method == "exact" and record.get("exact_certified") is not True:
                raise BenchmarkError(f"Uncertified candidate-space Exact: {sid}")
            value = record["total_waiting_time_min"]
            if value is None or value < -TIE_TOLERANCE:
                raise BenchmarkError(f"Invalid static waiting total: {sid}/{method}")
            _same(value, record["mean_waiting_time_min"] * scenario.vessel_count,
                  f"{sid}/{method}/raw_waiting")
            key = method, seed, sid
            if key in costs:
                raise BenchmarkError(f"Duplicate static method/seed/scenario row: {key}")
            costs[key] = value
    for sid in scenarios:
        for method in expected_methods:
            for seed in (TRAINING_SEEDS if method == "ppo" else (None,)):
                if (method, seed, sid) not in costs:
                    raise BenchmarkError(f"Missing static paired row: {method}/{seed}/{sid}")
    identities = {sid: {"physical_fingerprint": physical_fingerprint(s),
                        "family": next(name for name in weights if sid.startswith(name + "_test_seed")),
                        "vessel_count": s.vessel_count}
                  for sid, s in scenarios.items()}
    return LockedDataset(source, weights, identities, costs, inventory, {
        "source_rows": row_count, "source_test_scenarios": len(scenarios),
        "source_methods": sorted(expected_methods), "training_distinct_physical": train_count,
        "physical_pairing_complete": True, "missing_rows": 0,
        "invalid_rows": 0, "replay_status": "not_required",
    }, {"source_aggregate_path": str(evaluation / "aggregate.json"),
        "evaluation_sha256": evaluation_sha,
        "decision_sha256": decision_sha})


def load_dynamic(config: BenchmarkConfig, source: BenchmarkSource,
                 decisions: dict[str, tuple[dict[str, Any], str]]) -> LockedDataset:
    from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig
    from berth_allocation_lab.rl.dynamic_suites import dynamic_suites

    frozen = DynamicPPOConfig.load_yaml(config.resolve(source.config_path))
    if (frozen.experiment_id != source.experiment_id or frozen.horizon_min != 240 or
            frozen.training.training_seeds != TRAINING_SEEDS):
        raise BenchmarkError(f"Dynamic config/seed/horizon mismatch: {source.config_path}")
    weights = _check_weights(config, source.regime, frozen.components)
    suite = dynamic_suites(frozen)["test"]
    scenarios = {scenario.scenario_id: scenario for scenario in suite.scenarios}
    decision, decision_sha = decisions["dynamic_rule_1"]
    if decision.get("decision_rule_version") != "dynamic_rule_1":
        raise BenchmarkError("Dynamic decision rule version changed.")
    chosen = decision["regimes"][source.regime]
    if (chosen["config_sha256"] != frozen.source_sha256 or
            chosen["experiment_id"] != source.experiment_id or
            chosen["horizon_min"] != 240):
        raise BenchmarkError("Dynamic decision/config mismatch.")
    by_seed = {row["training_seed"]: row for row in chosen["seeds"]}
    if set(by_seed) != set(TRAINING_SEEDS):
        raise BenchmarkError("Dynamic decision lacks three training seeds.")
    fcfs_validation = chosen["fcfs_mean_waiting_min"]
    rollout_validation = chosen["rollout_mean_waiting_min"]
    validation_scores = [by_seed[seed]["ppo_validation_waiting_min"] for seed in TRAINING_SEEDS]
    _same(sum(validation_scores) / len(validation_scores), chosen["ppo_mean_waiting_min"],
          f"dynamic_rule_1/{source.regime}/ppo_mean")
    if (chosen["r1_seed_wins_vs_fcfs"] != sum(value < fcfs_validation for value in validation_scores) or
            chosen["r1_useful_learning"] is not
            (chosen["r1_seed_wins_vs_fcfs"] >= 2)):
        raise BenchmarkError(f"Dynamic R1 decision mismatch: {source.regime}")
    if fcfs_validation <= rollout_validation:
        raise BenchmarkError(f"Dynamic frozen R2 denominator undefined: {source.regime}")
    for seed, expected_gap in zip(TRAINING_SEEDS, chosen["r2_gap_closed_by_seed"]):
        _same((fcfs_validation - by_seed[seed]["ppo_validation_waiting_min"]) /
              (fcfs_validation - rollout_validation), expected_gap,
              f"dynamic_rule_1/{source.regime}/seed_{seed}_r2")
    _same(sum(chosen["r2_gap_closed_by_seed"]) / len(TRAINING_SEEDS),
          chosen["r2_gap_closed_mean"], f"dynamic_rule_1/{source.regime}/r2_mean")
    costs: dict[tuple[str, int | None, str], float] = {}
    inventory, training_paths, eval_hashes = [], [], {}
    baselines: dict[tuple[str, str], float] = {}
    expected_fp = {sid: physical_fingerprint(s) for sid, s in scenarios.items()}
    for seed in TRAINING_SEEDS:
        run = frozen.resolve(frozen.output_dir) / source.experiment_id / f"seed_{seed}"
        training = _read_json(run / "manifest.json")
        selected = by_seed[seed]
        if (training.get("status") != "completed" or training.get("git_dirty") is not False or
                training.get("config_sha256") != frozen.source_sha256 or
                training.get("training_seed") != seed or
                training.get("git_commit_hash") != selected["git_commit_hash"] or
                training["selection"]["selected_timesteps"] != selected["selected_timesteps"] or
                [r["physical_fingerprint"] for r in training["test_scenario_set_identities_only"]]
                != [expected_fp[s.scenario_id] for s in suite.scenarios]):
            raise BenchmarkError(f"Dynamic training/locked test identity mismatch: {run}")
        if ([r["physical_fingerprint"] for r in training["validation_scenario_set"]] !=
                selected["validation_physical_fingerprints"]):
            raise BenchmarkError(f"Dynamic validation identity mismatch: {run}")
        _same(training["selection"]["selected_mean_total_waiting_min"],
              selected["ppo_validation_waiting_min"],
              f"dynamic_validation/{source.regime}/{seed}")
        checkpoint = run / "best_validation_model.zip"
        metadata = _checkpoint(checkpoint, experiment=source.experiment_id, seed=seed,
                               selected_step=selected["selected_timesteps"],
                               expected_sha=selected["checkpoint_sha256"],
                               config_sha=frozen.source_sha256)
        if (metadata["policy_id"] != frozen.policy_id or
                metadata["environment_version"] != frozen.environment_version or
                metadata["observation_version"] != frozen.observation_version or
                metadata["device_actual"] != "cuda"):
            raise BenchmarkError(f"Dynamic checkpoint metadata mismatch: {checkpoint}")
        path = config.resolve(source.evaluation_path) / f"{source.regime}_seed_{seed}.json"
        record = _read_json(path)
        eval_hashes[str(path)] = sha256_file(path)
        if (record.get("suite") != "test" or record.get("config_sha256") != frozen.source_sha256 or
                record.get("training_seed") != seed or
                record.get("training_horizon_min") != 240 or
                record.get("evaluation_horizon_min") != 240 or
                record.get("comparison_label") != "matched_horizon" or
                record.get("device_inference") != "cpu" or
                record.get("test_gate", {}).get("decision_sha256") != decision_sha or
                record.get("external_schedule_violations") or
                record.get("checkpoint_metadata") != metadata):
            raise BenchmarkError(f"Dynamic held-out record provenance mismatch: {path}")
        if len(record["rows"]) != 3 * len(scenarios):
            raise BenchmarkError(f"Dynamic held-out row count mismatch: {path}")
        seen: set[tuple[str, str]] = set()
        for row in record["rows"]:
            sid = row["scenario_id"]
            method_id = row["method"]
            method = next((name for name, policy in DYNAMIC_POLICY_IDS.items()
                           if method_id == policy), None)
            if sid not in scenarios or method is None or (sid, method) in seen:
                raise BenchmarkError(f"Duplicate or unknown dynamic paired row: {sid}/{method_id}")
            seen.add((sid, method))
            scenario = scenarios[sid]
            if (row["physical_fingerprint"] != expected_fp[sid] or
                    row["scenario_seed"] != scenario.seed or
                    row["scenario_family"] != scenario.scenario_family or
                    row["horizon_min"] != 240 or
                    row["vessel_count"] != scenario.vessel_count or
                    row["vessel_count_completed"] != scenario.vessel_count or
                    row["status"] != "completed_valid" or
                    row["schedule_valid"] is not True or row["truncated"] is not False):
                raise BenchmarkError(f"Invalid dynamic held-out row: {sid}/{method_id}")
            placements = [BAPPlacement(**item) for item in row["placements"]]
            violations = find_schedule_violations(
                scenario.vessels, placements, scenario.berth_length_m, scenario.min_clearance_m)
            if violations:
                raise BenchmarkError(f"Dynamic physical schedule violation: {sid}/{method_id}: {violations}")
            value = total_waiting_time(scenario.vessels, placements)
            _same(value, row["total_waiting_time_min"], f"{sid}/{method_id}/canonical_waiting")
            _same(-sum(item["reward"] for item in row["decision_history"]), value,
                  f"{sid}/{method_id}/raw_return")
            _same(sum(item["waiting_time_min"] for item in row["vessel_results"]), value,
                  f"{sid}/{method_id}/vessel_waiting")
            if method != "ppo":
                baseline_key = method, sid
                if baseline_key in baselines:
                    _same(value, baselines[baseline_key], f"{sid}/{method}/shared_reference")
                else:
                    baselines[baseline_key] = value
            else:
                costs[(method, seed, sid)] = value
        if len(seen) != 3 * len(scenarios):
            raise BenchmarkError(f"Incomplete dynamic pairing matrix: {path}")
        training_paths.append(run / "train_episodes.json")
        inventory.append({
            "experiment_id": source.experiment_id, "formulation": "dynamic",
            "regime": source.regime, "version": source.version,
            "source_git_commit": training["git_commit_hash"], "git_dirty": False,
            "config_sha256": frozen.source_sha256, "training_seed": seed,
            "checkpoint_id": f"best_validation@{selected['selected_timesteps']}",
            "checkpoint_sha256": selected["checkpoint_sha256"],
            "checkpoint_path": str(checkpoint),
            "environment_version": metadata["environment_version"],
            "observation_version": metadata["observation_version"],
            "policy_id": metadata["policy_id"], "horizon_min": 240,
            "scenario_suite": "test", "scenario_split": "test",
            "physical_fingerprints": sorted(expected_fp.values()),
            "evaluation_path": str(path), "evaluation_sha256": eval_hashes[str(path)],
            "training_device": metadata["device_actual"],
            "evaluation_device": record["device_inference"],
            "completion_status": training["status"],
        })
    for (method, sid), value in baselines.items():
        costs[(method, None, sid)] = value
    validation_fp = {r["physical_fingerprint"] for r in
                     _read_json(frozen.resolve(frozen.output_dir) / source.experiment_id /
                                "seed_11" / "manifest.json")["validation_scenario_set"]}
    if set(expected_fp.values()) & validation_fp:
        raise BenchmarkError("Dynamic test/validation physical overlap.")
    train_count = _training_overlap(training_paths, set(expected_fp.values()) | validation_fp,
                                    static=False)
    identities = {sid: {"physical_fingerprint": expected_fp[sid],
                        "family": next(c.base_scenario_id for c in frozen.components
                                       if sid.startswith(c.base_scenario_id + "_test_seed")),
                        "vessel_count": scenario.vessel_count}
                  for sid, scenario in scenarios.items()}
    return LockedDataset(source, weights, identities, costs, inventory, {
        "source_rows": len(scenarios) * 3 * 3,
        "source_test_scenarios": len(scenarios), "source_methods": sorted(DYNAMIC_POLICY_IDS),
        "training_distinct_physical": train_count,
        "physical_pairing_complete": True, "missing_rows": 0,
        "invalid_rows": 0, "replay_status": "not_required",
    }, {"evaluation_sha256": eval_hashes, "decision_sha256": decision_sha})


def load_all(config: BenchmarkConfig) -> tuple[list[LockedDataset], dict[str, Any]]:
    decisions = {name: verify_decision(config.resolve(path))
                 for name, path in config.decisions.items()}
    datasets = [(load_static(config, source, decisions) if config.formulation == "static"
                 else load_dynamic(config, source, decisions)) for source in config.sources]
    by_regime: dict[str, list[LockedDataset]] = {}
    for dataset in datasets:
        by_regime.setdefault(dataset.source.regime, []).append(dataset)
    for regime, variants in by_regime.items():
        reference = variants[0]
        for other in variants[1:]:
            if other.scenarios != reference.scenarios:
                raise BenchmarkError(f"Static v1/v2 physical pairing mismatch: {regime}")
            for method in {"fcfs", "rollout"}:
                if other.series(method) != reference.series(method):
                    raise BenchmarkError(f"Static v1/v2 baseline mismatch: {regime}/{method}")
    decision_audit = {
        name: {"path": config.decisions[name], "sha256": sha,
               "rule_version": value["decision_rule_version"],
               "uses_test_results": value["uses_test_results"]}
        for name, (value, sha) in decisions.items()
    }
    if config.formulation == "static":
        decision_audit["previously_selected"] = {
            regime: decisions["v2"][0]["regimes"][regime]["winner"]
            for regime in ("tiny", "medium_heavy")}
    else:
        decision_audit["r1_r2"] = {
            regime: {key: decisions["dynamic_rule_1"][0]["regimes"][regime][key]
                     for key in ("r1_useful_learning", "r1_seed_wins_vs_fcfs",
                                 "r2_gap_closed_by_seed", "r2_gap_closed_mean")}
            for regime in ("tiny", "medium_heavy")}
    return datasets, decision_audit
