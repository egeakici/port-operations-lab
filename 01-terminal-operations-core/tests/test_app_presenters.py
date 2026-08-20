from __future__ import annotations

from datetime import datetime

from app import presenters
from app.models import CommandRecord, canonical_json
from terminal_core.berth import Berth
from terminal_core.integration import (
    IntegrationCheckpoint,
    build_reference_terminal,
    run_reference_scenario,
)
from terminal_core.quay_crane import QuayCrane
from terminal_core.terminal import Terminal
from terminal_core.vessel import Vessel
from terminal_core.yard_block import YardBlock


def _vessel(vessel_id: str = "V001") -> Vessel:
    return Vessel(
        vessel_id=vessel_id,
        length_m=120.0,
        eta=datetime(2026, 1, 1, 8, 0),
        workload_moves=40,
        priority=2,
        max_cranes=1,
    )


def test_empty_terminal_presenters() -> None:
    state = Terminal(datetime(2026, 1, 1, 8, 0)).snapshot()

    assert presenters.build_overview_metrics(state)[1]["value"] == 0
    assert presenters.build_vessel_rows(state) == []
    assert presenters.build_berth_rows(state) == []


def test_populated_terminal_presenters() -> None:
    terminal = Terminal(datetime(2026, 1, 1, 8, 0))
    terminal.register_berth(Berth("B01", 300.0))
    terminal.register_vessel(_vessel())
    terminal.register_quay_crane(QuayCrane("QC01", 10.0, 30.0))
    terminal.register_yard_block(YardBlock("Y01", 100.0))
    state = terminal.snapshot()

    assert presenters.build_vessel_rows(state)[0]["vessel_id"] == "V001"
    assert presenters.build_crane_rows(state)[0]["crane_id"] == "QC01"
    assert presenters.build_yard_rows(state)[0]["block_id"] == "Y01"


def test_multiple_berth_occupancies() -> None:
    terminal = Terminal(datetime(2026, 1, 1, 8, 0))
    terminal.register_berth(Berth("B01", 400.0, 10.0))
    terminal.register_vessel(_vessel("V001"))
    terminal.register_vessel(_vessel("V002"))
    terminal.arrive_vessel("V001")
    terminal.arrive_vessel("V002")
    terminal.berth_vessel("V001", "B01", 0.0)
    terminal.berth_vessel("V002", "B01", 150.0)

    rows = presenters.build_berth_rows(terminal.snapshot())

    assert {row["vessel_id"] for row in rows} == {"V001", "V002"}


def test_reference_checkpoint_presentation_and_task_progress() -> None:
    result = run_reference_scenario()
    state = result.get_checkpoint(IntegrationCheckpoint.CRANE_FAILED)

    task_rows = presenters.build_task_rows(state)
    crane_rows = presenters.build_crane_rows(state)

    assert any(row["task_id"] == "T-DISCHARGE" for row in task_rows)
    assert any(row["progress_pct"] == 40.0 for row in task_rows)
    assert any(row["crane_id"] == "QC01" and row["status"] == "failed" for row in crane_rows)
    assert presenters.build_scenario_summary(result)["scenario_id"] == "two-vessel-transshipment-v1"


def test_cargo_location_totals_and_event_order() -> None:
    result = run_reference_scenario()
    final = result.final_state

    cargo_rows = presenters.build_cargo_location_rows(final)
    event_rows = presenters.build_event_rows(result.events)

    assert cargo_rows == [
        {
            "group_id": "G-TRANS",
            "location_type": "vessel",
            "location_id": "V-OUT",
            "teu": 100.0,
        }
    ]
    assert [row["sequence"] for row in event_rows] == sorted(
        row["sequence"] for row in event_rows
    )


def test_command_history_order_and_no_mutation() -> None:
    terminal = build_reference_terminal()
    state = terminal.snapshot()
    before = state.to_dict()
    commands = [
        CommandRecord(
            sequence=2,
            command_name="B",
            attempted_at=datetime(2026, 1, 1, 8, 0),
            parameters={},
            success=True,
            new_event_ids=(),
            new_event_types=(),
            error_type=None,
            error_message=None,
            before_terminal_json=canonical_json(terminal.to_dict()),
            after_terminal_json=canonical_json(terminal.to_dict()),
        ),
        CommandRecord(
            sequence=1,
            command_name="A",
            attempted_at=datetime(2026, 1, 1, 8, 0),
            parameters={},
            success=False,
            new_event_ids=(),
            new_event_types=(),
            error_type="Error",
            error_message="failed",
            before_terminal_json=canonical_json(terminal.to_dict()),
            after_terminal_json=None,
        ),
    ]

    rows = presenters.build_command_rows(commands)
    presenters.build_yard_rows(state)

    assert [row["sequence"] for row in rows] == [2, 1]
    assert state.to_dict() == before

