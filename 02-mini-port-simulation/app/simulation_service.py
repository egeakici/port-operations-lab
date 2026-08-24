from __future__ import annotations

import csv
import io
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from mini_port_sim import (
    DisruptionConfig,
    ScenarioConfig,
    ServiceConfig,
    TerminalConfig,
    TerminationMode,
    TrafficConfig,
    run_scenario_experiment,
)

from app.models import ScenarioOption, SimulationRunBundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = PROJECT_ROOT / "scenarios"
DEFAULT_SCENARIO_ID = "crane_failure"


def list_scenario_options() -> tuple[ScenarioOption, ...]:
    options: list[ScenarioOption] = []
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        scenario = ScenarioConfig.load_json(path)
        options.append(
            ScenarioOption(
                label=_label_for_scenario(path, scenario),
                path=path,
                scenario=scenario,
            )
        )
    return tuple(options)


def default_scenario_option(
    options: tuple[ScenarioOption, ...],
) -> ScenarioOption | None:
    for option in options:
        if option.scenario.scenario_id == DEFAULT_SCENARIO_ID:
            return option
    return options[0] if options else None


def load_preset_scenario(path: str | Path, *, seed: int) -> ScenarioConfig:
    scenario = ScenarioConfig.load_json(path)
    return replace(scenario, seed=int(seed))


def build_custom_scenario(
    *,
    scenario_id: str,
    duration_hours: float,
    seed: int,
    termination_mode: str,
    max_drain_extension_hours: float,
    terminal: dict[str, Any],
    traffic: dict[str, Any],
    service: dict[str, Any],
    disruptions: dict[str, Any],
) -> ScenarioConfig:
    return ScenarioConfig(
        scenario_id=scenario_id.strip(),
        duration_hours=float(duration_hours),
        seed=int(seed),
        termination_mode=TerminationMode(termination_mode),
        max_drain_extension_hours=float(max_drain_extension_hours),
        terminal=TerminalConfig(
            berth_length_m=float(terminal["berth_length_m"]),
            min_clearance_m=float(terminal["min_clearance_m"]),
            quay_crane_count=int(terminal["quay_crane_count"]),
            quay_crane_moves_per_hour=float(
                terminal["quay_crane_moves_per_hour"]
            ),
            yard_block_count=int(terminal["yard_block_count"]),
            yard_block_capacity_teu=float(
                terminal["yard_block_capacity_teu"]
            ),
        ),
        traffic=TrafficConfig(
            vessel_count=int(traffic["vessel_count"]),
            mean_interarrival_minutes=float(
                traffic["mean_interarrival_minutes"]
            ),
            min_vessel_length_m=float(traffic["min_vessel_length_m"]),
            max_vessel_length_m=float(traffic["max_vessel_length_m"]),
            min_workload_moves=int(traffic["min_workload_moves"]),
            max_workload_moves=int(traffic["max_workload_moves"]),
        ),
        service=ServiceConfig(
            berthing_preparation_minutes=float(
                service["berthing_preparation_minutes"]
            ),
            service_minutes_per_move=float(service["service_minutes_per_move"]),
            departure_preparation_minutes=float(
                service["departure_preparation_minutes"]
            ),
            two_crane_efficiency=float(service["two_crane_efficiency"]),
            three_crane_efficiency=float(service["three_crane_efficiency"]),
            four_plus_crane_efficiency=float(
                service["four_plus_crane_efficiency"]
            ),
        ),
        disruptions=DisruptionConfig(
            eta_delay_stddev_minutes=float(
                disruptions["eta_delay_stddev_minutes"]
            ),
            productivity_min_factor=float(
                disruptions["productivity_min_factor"]
            ),
            productivity_max_factor=float(
                disruptions["productivity_max_factor"]
            ),
            crane_failures_enabled=bool(
                disruptions["crane_failures_enabled"]
            ),
            mean_time_to_failure_minutes=float(
                disruptions["mean_time_to_failure_minutes"]
            ),
            mean_repair_minutes=float(disruptions["mean_repair_minutes"]),
        ),
    )


def run_simulation_from_ui(
    scenario: ScenarioConfig,
    *,
    start_time: datetime,
) -> SimulationRunBundle:
    result = run_scenario_experiment(
        scenario,
        start_time=start_time,
    )
    return SimulationRunBundle(
        result=result,
        event_rows=build_event_log_rows(result),
    )


def nearest_replay_frame_index(frames: tuple[Any, ...], elapsed_minutes: float) -> int:
    if not frames:
        return 0
    best_index = 0
    best_delta = abs(frames[0].elapsed_minutes - elapsed_minutes)
    for index, frame in enumerate(frames[1:], start=1):
        delta = abs(frame.elapsed_minutes - elapsed_minutes)
        if delta < best_delta:
            best_index = index
            best_delta = delta
    return best_index


def build_event_log_rows(result) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for event in result.simulation.terminal.events:
        elapsed = (
            event.occurred_at - result.simulation.start_time
        ).total_seconds() / 60.0
        payload = dict(event.payload)
        rows.append(
            {
                "event_id": event.event_id,
                "simulation_time_minutes": elapsed,
                "datetime": event.occurred_at.isoformat(),
                "event_type": event.event_type.value,
                "entity_type": event.entity_type.value,
                "entity_id": event.entity_id,
                "related_vessel": _related_vessel(event, payload),
                "related_crane": _related_crane(event, payload),
                "related_task": _related_task(event, payload),
                "details": payload,
            }
        )
    return tuple(rows)


def filter_event_rows(
    rows: tuple[dict[str, Any], ...],
    *,
    event_types: tuple[str, ...] = (),
    vessel_id: str | None = None,
    crane_id: str | None = None,
    time_range: tuple[float, float] | None = None,
    search_text: str = "",
) -> tuple[dict[str, Any], ...]:
    query = search_text.strip().lower()
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if event_types and row["event_type"] not in event_types:
            continue
        if vessel_id and row["related_vessel"] != vessel_id:
            continue
        if crane_id and row["related_crane"] != crane_id:
            continue
        if time_range is not None:
            start, end = time_range
            if not start <= row["simulation_time_minutes"] <= end:
                continue
        haystack = " ".join(
            str(row.get(field, ""))
            for field in (
                "event_id",
                "event_type",
                "entity_type",
                "entity_id",
                "related_vessel",
                "related_crane",
                "related_task",
                "details",
            )
        ).lower()
        if query and query not in haystack:
            continue
        filtered.append(row)
    return tuple(filtered)


def event_rows_csv_bytes(rows: tuple[dict[str, Any], ...]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "event_id",
            "simulation_time_minutes",
            "datetime",
            "event_type",
            "entity_type",
            "entity_id",
            "related_vessel",
            "related_crane",
            "related_task",
            "details",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, "details": str(row["details"])})
    return output.getvalue().encode("utf-8")


def _label_for_scenario(path: Path, scenario: ScenarioConfig) -> str:
    return (
        f"{scenario.scenario_id.replace('_', ' ').title()} "
        f"({path.name})"
    )


def _related_vessel(event, payload: dict[str, Any]) -> str | None:
    if event.entity_type.value == "vessel":
        return event.correlation_id or event.entity_id
    return (
        event.correlation_id
        or payload.get("vessel_id")
        or payload.get("source_vessel_id")
        or payload.get("target_vessel_id")
    )


def _related_crane(event, payload: dict[str, Any]) -> str | None:
    if event.entity_type.value == "quay_crane":
        return event.entity_id
    return payload.get("crane_id") or payload.get("assigned_resource_id")


def _related_task(event, payload: dict[str, Any]) -> str | None:
    if event.entity_type.value == "operation_task":
        return event.entity_id
    return payload.get("task_id")

