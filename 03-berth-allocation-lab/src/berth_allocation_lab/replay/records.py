"""Hash-gated adapter for completed Step 11/12 Dynamic held-out records."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from berth_allocation_lab.core import BAPPlacement, find_schedule_violations, total_waiting_time
from berth_allocation_lab.data import BAPVesselInput
from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig
from berth_allocation_lab.scenarios import SyntheticScenarioConfig

BENCHMARK = Path("experiments/benchmark/step12/dynamic_h240_locked_v1")
CONFIGS = {"tiny": "configs/rl/dynamic_ppo_tiny_extended_cuda.yaml",
           "medium_heavy": "configs/rl/dynamic_ppo_medium_heavy_extended_cuda.yaml"}
METHODS = {"dynamic_online_fcfs_v1": "fcfs",
           "dynamic_maskable_ppo_v1": "ppo",
           "dynamic_online_rollout_v1": "rollout"}


class ReplayError(ValueError):
    """Missing, incompatible or scientifically invalid frozen replay evidence."""


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_hash(path: Path, expected: str) -> None:
    if not path.is_file():
        raise ReplayError(f"Required frozen replay file is missing: {path}")
    if _digest(path) != expected:
        raise ReplayError(f"Frozen replay file SHA-256 mismatch: {path}")


def _evaluation_path(root: Path, recorded: str) -> Path:
    path = Path(recorded)
    if path.is_absolute() and path.is_relative_to(root) and path.is_file():
        return path
    parts = path.parts
    if "experiments" not in parts:
        raise ReplayError(f"Evaluation path has no project-relative experiments segment: {recorded}")
    path = root.joinpath(*parts[parts.index("experiments"):]).resolve()
    if not path.is_relative_to(root):
        raise ReplayError("Evaluation path escapes Project 03.")
    return path


@dataclass(frozen=True)
class ScenarioOption:
    scenario_id: str
    family: str
    vessel_count: int
    fingerprint: str
    regime: str


@dataclass(frozen=True)
class ReplayCatalog:
    root: Path
    scenarios: tuple[ScenarioOption, ...]
    sources: dict[tuple[str, int], dict[str, Any]]
    benchmark_manifest_sha256: str


@dataclass(frozen=True)
class ReplayVessel:
    vessel_id: str
    arrival_time_min: float
    length_m: float
    service_time_min: float
    berth_position_m: float
    berth_start_time_min: float
    service_end_time_min: float
    waiting_time_min: float
    turnaround_time_min: float


@dataclass(frozen=True)
class ReplayRun:
    method: str
    policy_id: str
    training_seed: int | None
    scenario_id: str
    fingerprint: str
    source_split: str
    source_experiment: str
    evaluation_path: str
    evaluation_sha256: str
    total_waiting_time_min: float
    mean_waiting_time_min: float
    p95_waiting_time_min: float | None
    mean_turnaround_time_min: float | None
    intentional_waits: int | None
    schedule_valid: bool
    vessels: tuple[ReplayVessel, ...]
    decisions: tuple[dict[str, Any], ...] | None
    events: tuple[dict[str, Any], ...] | None


@dataclass(frozen=True)
class ReplayScenario:
    option: ScenarioOption
    scenario_seed: int
    berth_length_m: float
    min_clearance_m: float
    horizon_min: float
    runs: dict[str, ReplayRun]


def load_catalog(root: Path) -> ReplayCatalog:
    root = root.resolve()
    folder = root / BENCHMARK
    manifest_file = folder / "manifest.json"
    if not manifest_file.is_file():
        raise ReplayError(f"Frozen Step 12A Dynamic release is unavailable: {manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if (manifest.get("status") != "completed" or manifest.get("formulation") != "dynamic" or
            manifest.get("benchmark_id") != "dynamic_h240_locked_v1"):
        raise ReplayError("Step 12A Dynamic release is incomplete or incompatible.")
    for name in ("source_inventory.json", "paired_differences.csv"):
        expected = manifest.get("derived_output_sha256", {}).get(name)
        if not expected:
            raise ReplayError(f"Step 12A does not hash {name}.")
        _require_hash(folder / name, expected)
    sources: dict[tuple[str, int], dict[str, Any]] = {}
    inventory = json.loads((folder / "source_inventory.json").read_text(encoding="utf-8"))
    for item in inventory:
        if (item.get("formulation") != "dynamic" or item.get("version") != "v1" or
                item.get("scenario_split") != "test" or item.get("horizon_min") != 240):
            raise ReplayError("Unexpected Step 11 source inventory contract.")
        key = (item["regime"], int(item["training_seed"]))
        if key in sources:
            raise ReplayError(f"Duplicate evaluation source: {key}")
        sources[key] = item
    if set(sources) != {(regime, seed) for regime in CONFIGS for seed in (11, 23, 37)}:
        raise ReplayError("Six frozen Dynamic PPO evaluation sources are required.")
    configs = {regime: DynamicPPOConfig.load_yaml(root / file) for regime, file in CONFIGS.items()}
    for (regime, _), source in sources.items():
        if configs[regime].source_sha256 != source["config_sha256"]:
            raise ReplayError(f"Frozen evaluation/config SHA-256 mismatch: {regime}")
    options: dict[str, ScenarioOption] = {}
    with (folder / "paired_differences.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            regime, sid = row["regime"], row["scenario_id"]
            component = next((item for item in configs[regime].components
                              if sid.startswith(item.base_scenario_id + "_")), None)
            if component is None:
                raise ReplayError(f"Scenario does not match a frozen component: {sid}")
            count = component.vessel_count or SyntheticScenarioConfig.load_yaml(
                root / component.source_config).traffic.vessel_count
            option = ScenarioOption(sid, component.name, count,
                                    row["physical_fingerprint"], regime)
            if sid in options and options[sid] != option:
                raise ReplayError(f"Conflicting physical scenario identity: {sid}")
            options[sid] = option
    if len(options) != 250:
        raise ReplayError(f"Expected 250 frozen Dynamic scenarios, found {len(options)}.")
    return ReplayCatalog(root, tuple(sorted(options.values(),
                                            key=lambda o: (o.vessel_count, o.scenario_id))),
                         sources, _digest(manifest_file))


@lru_cache(maxsize=2)
def _read_evaluation(path: str, expected_hash: str, mtime_ns: int, size: int) -> dict:
    file = Path(path)
    _require_hash(file, expected_hash)
    return json.loads(file.read_text(encoding="utf-8"))


def _one_run(row: dict, source: dict, root: Path, split: str,
             berth_length_m: float, clearance_m: float) -> ReplayRun:
    if (row.get("status") != "completed_valid" or row.get("schedule_valid") is not True or
            row.get("truncated") is not False):
        raise ReplayError(f"Incomplete or invalid recorded schedule: {row.get('scenario_id')}")
    method = METHODS.get(row.get("method"))
    if method is None:
        raise ReplayError(f"Unsupported recorded policy: {row.get('method')}")
    raw_placements = row.get("placements")
    raw_vessels = row.get("vessel_results")
    if not isinstance(raw_placements, list) or not isinstance(raw_vessels, list):
        raise ReplayError("Recorded vessel placements/results are required for replay.")
    try:
        placements = tuple(BAPPlacement(**item) for item in raw_placements)
        by_placement = {p.vessel_id: p for p in placements}
        vessels = tuple(BAPVesselInput(
            vessel_id=item["vessel_id"], arrival_time_min=item["arrival_time_min"],
            length_m=by_placement[item["vessel_id"]].length_m,
            service_time_min=by_placement[item["vessel_id"]].service_time_min)
            for item in raw_vessels)
        if len(by_placement) != len(placements):
            raise ReplayError("Duplicate recorded placement ID.")
        violations = find_schedule_violations(vessels, placements, berth_length_m,
                                              clearance_m, require_complete=True)
        if violations:
            raise ReplayError("Invalid physical schedule: " + "; ".join(v.message for v in violations))
        total = total_waiting_time(vessels, placements)
        if not math.isclose(total, float(row["total_waiting_time_min"]), abs_tol=1e-6):
            raise ReplayError("Recorded total waiting differs from canonical objective.")
        replay_vessels = []
        for raw, vessel in zip(raw_vessels, vessels):
            placement = by_placement[vessel.vessel_id]
            expected = (placement.berth_start_time_min - vessel.arrival_time_min,
                        placement.service_end_time_min - vessel.arrival_time_min)
            actual = (raw["waiting_time_min"], raw["turnaround_time_min"])
            if not all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(expected, actual)):
                raise ReplayError(f"Recorded vessel KPI mismatch: {vessel.vessel_id}")
            if not all(math.isclose(a, b, abs_tol=1e-6) for a, b in (
                (raw["berth_start_time_min"], placement.berth_start_time_min),
                (raw["berth_position_m"], placement.berth_position_m),
                (raw["service_end_time_min"], placement.service_end_time_min))):
                raise ReplayError(f"Recorded vessel/placement mismatch: {vessel.vessel_id}")
            replay_vessels.append(ReplayVessel(vessel.vessel_id, vessel.arrival_time_min,
                vessel.length_m, vessel.service_time_min, placement.berth_position_m,
                placement.berth_start_time_min, placement.service_end_time_min,
                float(raw["waiting_time_min"]), float(raw["turnaround_time_min"])))
        if len(vessels) != row["vessel_count"] or len(vessels) != row["vessel_count_completed"]:
            raise ReplayError("Recorded vessel count is incomplete.")
        decisions = row.get("decision_history")
        events = row.get("event_records")
        if decisions is not None and not isinstance(decisions, list):
            raise ReplayError("Malformed decision history.")
        if events is not None and not isinstance(events, list):
            raise ReplayError("Malformed event history.")
        if decisions is not None:
            if len(decisions) != row["decision_count"]:
                raise ReplayError("Recorded decision count mismatch.")
            if [d["decision_index"] for d in decisions] != list(range(len(decisions))):
                raise ReplayError("Recorded decision order is not contiguous.")
        if events is not None:
            if [e["event_index"] for e in events] != list(range(len(events))):
                raise ReplayError("Recorded event order is not contiguous.")
            times = [float(e["simulation_time_min"]) for e in events]
            if any(a > b + 1e-6 for a, b in zip(times, times[1:])):
                raise ReplayError("Recorded event times are not chronological.")
        return ReplayRun(method, row["method"], int(source["training_seed"]) if method == "ppo" else None,
            row["scenario_id"], row["physical_fingerprint"], split,
            source["experiment_id"], str(_evaluation_path(root, source["evaluation_path"])),
            source["evaluation_sha256"], float(row["total_waiting_time_min"]),
            float(row["mean_waiting_time_min"]),
            float(row["p95_waiting_time_min"]) if row.get("p95_waiting_time_min") is not None else None,
            float(row["mean_turnaround_time_min"]) if row.get("mean_turnaround_time_min") is not None else None,
            int(row["intentional_waits"]) if row.get("intentional_waits") is not None else None,
            True, tuple(replay_vessels), tuple(decisions) if decisions is not None else None,
            tuple(events) if events is not None else None)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, ReplayError):
            raise
        raise ReplayError(f"Malformed recorded replay for {row.get('scenario_id')}: {error}") from error


def load_scenario(catalog: ReplayCatalog, scenario_id: str, training_seed: int) -> ReplayScenario:
    option = next((o for o in catalog.scenarios if o.scenario_id == scenario_id), None)
    if option is None:
        raise ReplayError(f"Scenario is absent from frozen Step 12A: {scenario_id}")
    source = catalog.sources.get((option.regime, training_seed))
    if source is None:
        raise ReplayError(f"No frozen policy record for seed {training_seed}.")
    config = DynamicPPOConfig.load_yaml(catalog.root / CONFIGS[option.regime])
    if config.source_sha256 != source["config_sha256"]:
        raise ReplayError("Frozen configuration hash changed.")
    component = next(c for c in config.components if c.name == option.family)
    physics = SyntheticScenarioConfig.load_yaml(catalog.root / component.source_config)
    path = _evaluation_path(catalog.root, source["evaluation_path"])
    stat = path.stat() if path.is_file() else None
    if stat is None:
        raise ReplayError(f"Frozen evaluation artifact is missing: {path}")
    payload = _read_evaluation(str(path), source["evaluation_sha256"],
                               stat.st_mtime_ns, stat.st_size)
    if (payload.get("suite") != "test" or payload.get("evaluation_horizon_min") != 240 or
            payload.get("training_seed") != training_seed or
            payload.get("config_sha256") != config.source_sha256):
        raise ReplayError("Evaluation header differs from frozen test/config contract.")
    selected = [r for r in payload["rows"] if r.get("scenario_id") == scenario_id]
    if len(selected) != 3 or {r.get("method") for r in selected} != set(METHODS):
        raise ReplayError("No complete FCFS/PPO/Rollout trio for this scenario.")
    if any(r.get("physical_fingerprint") != option.fingerprint or
           r.get("vessel_count") != option.vessel_count or
           r.get("horizon_min") != 240 for r in selected):
        raise ReplayError("Policy runs differ in physical fingerprint, vessel count or horizon.")
    runs = {run.method: run for run in (
        _one_run(row, source, catalog.root, "test", physics.terminal.berth_length_m,
                 physics.terminal.min_clearance_m) for row in selected)}
    originals = [tuple((v.vessel_id, v.arrival_time_min, v.length_m, v.service_time_min)
                       for v in sorted(run.vessels, key=lambda v: v.vessel_id))
                 for run in runs.values()]
    if not all(item == originals[0] for item in originals[1:]):
        raise ReplayError("Policy runs do not share identical vessel inputs.")
    if any(run.fingerprint != option.fingerprint for run in runs.values()):
        raise ReplayError("Policy comparison physical fingerprint mismatch.")
    seed = selected[0]["scenario_seed"]
    if any(row["scenario_seed"] != seed for row in selected):
        raise ReplayError("Policy comparison scenario-seed mismatch.")
    return ReplayScenario(option, seed, physics.terminal.berth_length_m,
                          physics.terminal.min_clearance_m, 240.0, runs)
