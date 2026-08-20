from __future__ import annotations

from collections import defaultdict

from app.visual import layout
from app.visual.models import (
    BerthVisual,
    CargoBadgeVisual,
    CraneVisual,
    GateVisual,
    TaskFlowVisual,
    TerminalVisualScene,
    VesselVisual,
    VisualPoint,
    VisualRect,
    YardBlockVisual,
)
from terminal_core.operation_task import OperationTaskStatus, TaskLocationType
from terminal_core.terminal_state import TerminalState
from terminal_core.vessel import VesselStatus


ACTIVE_TASK_STATUSES = {
    OperationTaskStatus.ASSIGNED,
    OperationTaskStatus.IN_PROGRESS,
    OperationTaskStatus.BLOCKED,
}


def build_terminal_visual_scene(state: TerminalState) -> TerminalVisualScene:
    cargo_by_location = _cargo_by_location(state)
    berths, berth_rects = _build_berths(state)
    vessels, anchorage_vessels, departed_vessels = _build_vessels(
        state,
        berth_rects,
        cargo_by_location,
    )
    cranes = _build_cranes(state, berth_rects)
    yard_blocks = _build_yard_blocks(state, cargo_by_location)
    gates = _build_gates(state, cargo_by_location)
    task_flows = _build_task_flows(
        state,
        vessels + anchorage_vessels + departed_vessels,
        yard_blocks,
        gates,
    )

    return TerminalVisualScene(
        width=layout.SCENE_WIDTH,
        height=layout.SCENE_HEIGHT,
        berths=berths,
        vessels=vessels,
        anchorage_vessels=anchorage_vessels,
        departed_vessels=departed_vessels,
        cranes=cranes,
        yard_blocks=yard_blocks,
        gates=gates,
        task_flows=task_flows,
    )


def _cargo_by_location(
    state: TerminalState,
) -> dict[tuple[str, str], tuple[CargoBadgeVisual, ...]]:
    grouped: dict[tuple[str, str], list[CargoBadgeVisual]] = defaultdict(list)
    for location in state.group_locations:
        grouped[
            (
                location.location.location_type.value,
                location.location.location_id,
            )
        ].append(
            CargoBadgeVisual(
                group_id=location.group_id,
                teu=location.teu,
            )
        )
    return {
        key: tuple(sorted(items, key=lambda item: item.group_id))
        for key, items in grouped.items()
    }


def _build_berths(
    state: TerminalState,
) -> tuple[tuple[BerthVisual, ...], dict[str, BerthVisual]]:
    if not state.berth_ids:
        return (), {}

    berths = [state.get_berth(berth_id) for berth_id in state.berth_ids]
    total_length = sum(berth.length_m for berth in berths)
    gap = 12.0
    available_width = layout.QUAY_WIDTH - gap * (len(berths) - 1)
    current_x = layout.QUAY_X
    visuals: list[BerthVisual] = []

    for berth in berths:
        normalized_width = layout.ratio(berth.length_m, total_length)
        width = available_width * normalized_width
        visual = BerthVisual(
            berth_id=berth.berth_id,
            rect=VisualRect(
                x=current_x,
                y=layout.QUAY_Y - 16.0,
                width=width,
                height=34.0,
            ),
            length_m=berth.length_m,
            min_clearance_m=berth.min_clearance_m,
            normalized_start=layout.ratio(current_x - layout.QUAY_X, layout.QUAY_WIDTH),
            normalized_width=normalized_width,
        )
        visuals.append(visual)
        current_x += width + gap

    return tuple(visuals), {visual.berth_id: visual for visual in visuals}


def _build_vessels(
    state: TerminalState,
    berth_rects: dict[str, BerthVisual],
    cargo_by_location: dict[tuple[str, str], tuple[CargoBadgeVisual, ...]],
) -> tuple[tuple[VesselVisual, ...], tuple[VesselVisual, ...], tuple[VesselVisual, ...]]:
    berthed: list[VesselVisual] = []
    berthed_ids: set[str] = set()

    for berth_id in state.berth_ids:
        berth = state.get_berth(berth_id)
        berth_visual = berth_rects.get(berth_id)
        if berth_visual is None:
            continue

        for occupancy in berth.occupancies:
            vessel = occupancy.vessel
            normalized_x = layout.ratio(occupancy.start_position_m, berth.length_m)
            normalized_width = layout.ratio(vessel.length_m, berth.length_m)
            rect = VisualRect(
                x=berth_visual.rect.x + normalized_x * berth_visual.rect.width,
                y=layout.WATER_TOP + 142.0,
                width=max(78.0, normalized_width * berth_visual.rect.width),
                height=74.0,
            )
            berthed.append(
                VesselVisual(
                    vessel_id=vessel.vessel_id,
                    status=vessel.status.value,
                    rect=rect,
                    length_m=vessel.length_m,
                    cargo=cargo_by_location.get(
                        (TaskLocationType.VESSEL.value, vessel.vessel_id),
                        (),
                    ),
                    berth_id=berth_id,
                    start_position_m=occupancy.start_position_m,
                    normalized_x=normalized_x,
                    normalized_width=normalized_width,
                )
            )
            berthed_ids.add(vessel.vessel_id)

    anchorage_source = [
        state.get_vessel(vessel_id)
        for vessel_id in state.vessel_ids
        if vessel_id not in berthed_ids
        and state.get_vessel(vessel_id).status != VesselStatus.DEPARTED
    ]
    anchorage_rects = layout.anchorage_rects(len(anchorage_source))
    anchorage = tuple(
        VesselVisual(
            vessel_id=vessel.vessel_id,
            status=vessel.status.value,
            rect=anchorage_rects[index],
            length_m=vessel.length_m,
            cargo=cargo_by_location.get(
                (TaskLocationType.VESSEL.value, vessel.vessel_id),
                (),
            ),
            eta=vessel.eta.isoformat(),
        )
        for index, vessel in enumerate(anchorage_source)
    )

    departed = tuple(
        VesselVisual(
            vessel_id=vessel.vessel_id,
            status=vessel.status.value,
            rect=VisualRect(layout.QUAY_X, layout.GATE_Y, 1.0, 1.0),
            length_m=vessel.length_m,
            cargo=cargo_by_location.get(
                (TaskLocationType.VESSEL.value, vessel.vessel_id),
                (),
            ),
            eta=vessel.eta.isoformat(),
            departed=True,
        )
        for vessel in (
            state.get_vessel(vessel_id)
            for vessel_id in state.vessel_ids
        )
        if vessel.status == VesselStatus.DEPARTED
    )

    return tuple(berthed), anchorage, departed


def _build_cranes(
    state: TerminalState,
    berth_rects: dict[str, BerthVisual],
) -> tuple[CraneVisual, ...]:
    total_quay_length = sum(berth.length_m for berth in berth_rects.values())
    if total_quay_length <= 0:
        max_position = max(
            (state.get_quay_crane(crane_id).position_m for crane_id in state.quay_crane_ids),
            default=700.0,
        )
        total_quay_length = max(max_position, 700.0)

    active_task_by_crane: dict[str, str] = {}
    for task_id in state.operation_task_ids:
        task = state.get_operation_task(task_id)
        if task.assigned_resource_id:
            active_task_by_crane[task.assigned_resource_id] = task.task_id

    visuals: list[CraneVisual] = []
    for crane_id in state.quay_crane_ids:
        crane = state.get_quay_crane(crane_id)
        normalized_x = layout.ratio(crane.position_m, total_quay_length)
        x = layout.QUAY_X + normalized_x * layout.QUAY_WIDTH
        visuals.append(
            CraneVisual(
                crane_id=crane.crane_id,
                status=crane.status.value,
                rect=VisualRect(x - 34.0, layout.APRON_Y, 68.0, 58.0),
                position_m=crane.position_m,
                normalized_x=normalized_x,
                assigned_vessel_id=crane.assigned_vessel_id,
                active_task_id=active_task_by_crane.get(crane.crane_id),
                failed=crane.status.value == "failed",
            )
        )
    return tuple(visuals)


def _build_yard_blocks(
    state: TerminalState,
    cargo_by_location: dict[tuple[str, str], tuple[CargoBadgeVisual, ...]],
) -> tuple[YardBlockVisual, ...]:
    rects = layout.yard_grid_rects(len(state.yard_block_ids))
    visuals: list[YardBlockVisual] = []
    for index, block_id in enumerate(state.yard_block_ids):
        block = state.get_yard_block(block_id)
        reservations = tuple(
            CargoBadgeVisual(group_id=group_id, teu=teu)
            for group_id, teu in sorted(block.reservations.items())
        )
        visuals.append(
            YardBlockVisual(
                block_id=block.block_id,
                status=block.status.value,
                rect=rects[index],
                capacity_teu=block.capacity_teu,
                stored_teu=block.occupied_teu,
                reserved_teu=block.reserved_teu,
                available_teu=block.available_teu,
                capabilities=tuple(
                    sorted(capability.value for capability in block.capabilities)
                ),
                stored_groups=cargo_by_location.get(
                    (TaskLocationType.YARD_BLOCK.value, block.block_id),
                    (),
                ),
                reservations=reservations,
            )
        )
    return tuple(visuals)


def _build_gates(
    state: TerminalState,
    cargo_by_location: dict[tuple[str, str], tuple[CargoBadgeVisual, ...]],
) -> tuple[GateVisual, ...]:
    gate_ids: set[str] = {
        location.location.location_id
        for location in state.group_locations
        if location.location.location_type == TaskLocationType.GATE
    }
    for task_id in state.operation_task_ids:
        task = state.get_operation_task(task_id)
        for location in (task.source, task.target):
            if location.location_type == TaskLocationType.GATE:
                gate_ids.add(location.location_id)

    rects = layout.gate_rects(len(gate_ids))
    return tuple(
        GateVisual(
            gate_id=gate_id,
            rect=rects[index],
            cargo=cargo_by_location.get((TaskLocationType.GATE.value, gate_id), ()),
        )
        for index, gate_id in enumerate(sorted(gate_ids))
    )


def _build_task_flows(
    state: TerminalState,
    vessels: tuple[VesselVisual, ...],
    yards: tuple[YardBlockVisual, ...],
    gates: tuple[GateVisual, ...],
) -> tuple[TaskFlowVisual, ...]:
    anchors = _entity_anchors(vessels, yards, gates)
    flows: list[TaskFlowVisual] = []
    for task_id in state.operation_task_ids:
        task = state.get_operation_task(task_id)
        if task.status not in ACTIVE_TASK_STATUSES:
            continue

        source_key = (task.source.location_type.value, task.source.location_id)
        target_key = (task.target.location_type.value, task.target.location_id)
        flows.append(
            TaskFlowVisual(
                task_id=task.task_id,
                task_type=task.task_type.value,
                status=task.status.value,
                source_type=task.source.location_type.value,
                source_id=task.source.location_id,
                target_type=task.target.location_type.value,
                target_id=task.target.location_id,
                source=anchors.get(source_key, _fallback_point("source")),
                target=anchors.get(target_key, _fallback_point("target")),
                planned_teu=task.planned_teu,
                completed_teu=task.completed_teu,
                progress_pct=round(task.progress_ratio * 100.0, 2),
                blocked=task.status == OperationTaskStatus.BLOCKED,
            )
        )
    return tuple(sorted(flows, key=lambda flow: flow.task_id))


def _entity_anchors(
    vessels: tuple[VesselVisual, ...],
    yards: tuple[YardBlockVisual, ...],
    gates: tuple[GateVisual, ...],
) -> dict[tuple[str, str], VisualPoint]:
    anchors: dict[tuple[str, str], VisualPoint] = {}
    for vessel in vessels:
        anchors[(TaskLocationType.VESSEL.value, vessel.vessel_id)] = vessel.rect.center
    for yard in yards:
        anchors[(TaskLocationType.YARD_BLOCK.value, yard.block_id)] = yard.rect.center
    for gate in gates:
        anchors[(TaskLocationType.GATE.value, gate.gate_id)] = gate.rect.center
    return anchors


def _fallback_point(endpoint: str) -> VisualPoint:
    if endpoint == "source":
        return VisualPoint(layout.QUAY_X + 40.0, layout.YARD_Y + 40.0)
    return VisualPoint(layout.QUAY_X + layout.QUAY_WIDTH - 40.0, layout.YARD_Y + 40.0)

