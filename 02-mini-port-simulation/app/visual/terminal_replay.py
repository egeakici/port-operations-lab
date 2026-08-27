from __future__ import annotations

from app.visual import layout
from app.visual.models import (
    BerthReplayVisual,
    CraneReplayVisual,
    TerminalReplayScene,
    VesselReplayVisual,
    VisualRect,
    YardReplayVisual,
)


BERThed_STATUSES = {"berthed", "operating", "ready_to_depart"}


def build_terminal_replay_scene(bundle, frame_index: int) -> TerminalReplayScene:
    frames = bundle.result.replay_frames
    if not frames:
        return TerminalReplayScene(
            width=layout.SCENE_WIDTH,
            height=layout.SCENE_HEIGHT,
            elapsed_minutes=0.0,
            event_id=None,
            event_type=None,
            warnings=("No replay frames are available.",),
        )

    frame_index = max(0, min(frame_index, len(frames) - 1))
    frame = frames[frame_index]
    state = frame.state
    scenario = bundle.result.scenario
    terminal = bundle.result.simulation.terminal
    berth_length = scenario.terminal.berth_length_m
    berth_rect = VisualRect(
        x=layout.QUAY_X,
        y=layout.QUAY_Y - 16.0,
        width=layout.QUAY_WIDTH,
        height=34.0,
    )
    berths = (
        BerthReplayVisual(
            berth_id="B01",
            rect=berth_rect,
            length_m=berth_length,
            min_clearance_m=scenario.terminal.min_clearance_m,
        ),
    )

    workload_by_vessel = {
        plan.vessel.vessel_id: plan.vessel.workload_moves
        for plan in bundle.result.simulation.arrival_plans
    }
    vessels = state.vessels if state is not None else {}
    waiting_items = sorted(
        (
            (vessel_id, data)
            for vessel_id, data in vessels.items()
            if data.get("status") in {"arrived", "waiting"}
        ),
        key=lambda item: item[0],
    )
    waiting_rects = layout.anchorage_rects(len(waiting_items))
    visible_waiting_items = waiting_items[: len(waiting_rects)]
    waiting = tuple(
        VesselReplayVisual(
            vessel_id=vessel_id,
            status=str(data.get("status", "waiting")),
            rect=waiting_rects[index],
            length_m=_float_or_none(data.get("length_m")),
            workload_moves=workload_by_vessel.get(vessel_id),
        )
        for index, (vessel_id, data) in enumerate(visible_waiting_items)
    )
    waiting_overflow_count = max(0, len(waiting_items) - len(waiting))

    berthed: list[VesselReplayVisual] = []
    departed: list[VesselReplayVisual] = []
    for vessel_id, data in sorted(vessels.items()):
        status = str(data.get("status", "unknown"))
        length_m = _float_or_none(data.get("length_m"))
        if status == "departed":
            departed.append(
                VesselReplayVisual(
                    vessel_id=vessel_id,
                    status=status,
                    rect=VisualRect(layout.QUAY_X, layout.SCENE_HEIGHT - 70, 1, 1),
                    length_m=length_m,
                    workload_moves=workload_by_vessel.get(vessel_id),
                )
            )
            continue
        if status not in BERThed_STATUSES:
            continue
        start_position = _float_or_none(data.get("start_position_m")) or 0.0
        visual_width = max(
            72.0,
            layout.ratio(length_m or 0.0, berth_length) * berth_rect.width,
        )
        x = berth_rect.x + layout.ratio(start_position, berth_length) * berth_rect.width
        x = min(x, berth_rect.x + berth_rect.width - visual_width)
        berthed.append(
            VesselReplayVisual(
                vessel_id=vessel_id,
                status=status,
                rect=VisualRect(
                    x=x,
                    y=layout.QUAY_Y - 116.0,
                    width=visual_width,
                    height=76.0,
                ),
                length_m=length_m,
                workload_moves=workload_by_vessel.get(vessel_id),
                berth_id=data.get("berth_id"),
                start_position_m=start_position,
            )
        )

    cranes = []
    crane_states = state.cranes if state is not None else {}
    for crane_id in terminal.quay_crane_ids:
        crane = terminal.get_quay_crane(crane_id)
        crane_state = crane_states.get(crane_id, {})
        normalized = layout.ratio(crane.position_m, berth_length)
        x = layout.QUAY_X + normalized * layout.QUAY_WIDTH
        cranes.append(
            CraneReplayVisual(
                crane_id=crane_id,
                status=str(crane_state.get("status", crane.status.value)),
                rect=VisualRect(x - 34.0, layout.APRON_Y, 68.0, 58.0),
                position_m=crane.position_m,
                assigned_vessel_id=crane_state.get("assigned_vessel_id"),
                task_id=crane_state.get("task_id"),
                moves_per_hour=crane.moves_per_hour,
            )
        )

    yard_states = state.yards if state is not None else {}
    yard_rectangles = layout.yard_rects(len(terminal.yard_block_ids))
    yards = []
    for index, yard_id in enumerate(terminal.yard_block_ids):
        block = terminal.get_yard_block(yard_id)
        yard_state = yard_states.get(yard_id, {})
        yards.append(
            YardReplayVisual(
                yard_id=yard_id,
                rect=yard_rectangles[index],
                occupied_teu=float(yard_state.get("occupied_teu", 0.0)),
                capacity_teu=float(
                    yard_state.get("capacity_teu", block.capacity_teu)
                ),
                status=block.status.value,
            )
        )

    return TerminalReplayScene(
        width=layout.SCENE_WIDTH,
        height=layout.SCENE_HEIGHT,
        elapsed_minutes=frame.elapsed_minutes,
        event_id=frame.event_id,
        event_type=frame.event_type,
        berths=berths,
        berthed_vessels=tuple(berthed),
        waiting_vessels=waiting,
        waiting_overflow_count=waiting_overflow_count,
        departed_vessels=tuple(departed),
        cranes=tuple(cranes),
        yards=tuple(yards),
    )


def current_waiting_queue(bundle, frame_index: int) -> tuple[dict[str, object], ...]:
    frames = bundle.result.replay_frames
    if not frames:
        return ()

    frame_index = max(0, min(frame_index, len(frames) - 1))
    frame = frames[frame_index]
    state = frame.state
    if state is None:
        return ()

    arrival_by_vessel = {
        plan.vessel.vessel_id: plan.arrival_time_minutes
        for plan in bundle.result.simulation.arrival_plans
    }
    workload_by_vessel = {
        plan.vessel.vessel_id: plan.vessel.workload_moves
        for plan in bundle.result.simulation.arrival_plans
    }
    rows = []
    for vessel_id, data in state.vessels.items():
        if data.get("status") not in {"arrived", "waiting"}:
            continue
        arrival = arrival_by_vessel.get(vessel_id, frame.elapsed_minutes)
        rows.append(
            {
                "vessel_id": vessel_id,
                "status": str(data.get("status", "waiting")),
                "waiting_minutes": max(0.0, frame.elapsed_minutes - arrival),
                "workload_moves": workload_by_vessel.get(vessel_id),
            }
        )
    return tuple(sorted(rows, key=lambda row: row["waiting_minutes"], reverse=True))


def _float_or_none(value) -> float | None:
    if value is None:
        return None
    return float(value)
