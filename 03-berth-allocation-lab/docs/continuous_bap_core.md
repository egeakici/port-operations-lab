# Continuous BAP Core

Step 5 implements the shared physical and mathematical rules used by future
Project 03 policies, environments, and reference solvers. The module is pure
Python, deterministic, and independent of SimPy and solution methods.

## Schedule Representation

`BAPVesselInput` remains the canonical problem input. `BAPPlacement` is the
immutable scheduled outcome for one vessel:

```text
vessel_id
berth_position_m
berth_start_time_min
length_m
service_time_min
```

Its right berth edge and service completion time are derived properties, so
duplicate stored values cannot disagree.

## Interval Rules

Service uses half-open intervals:

```text
[berth_start_time_min, service_end_time_min)
```

Two services touching at an endpoint do not overlap. A vessel occupies the
closed hull footprint `[x, x + length_m]`. Simultaneous vessels are separated
when either vessel lies fully to one side of the other with one application of
`min_clearance_m`:

```text
right_a + min_clearance_m <= left_b
```

No clearance is added at either quay wall. Space-time conflict requires both
temporal overlap and insufficient spatial separation.

All comparisons use one absolute tolerance, `NUMERICAL_TOLERANCE = 1e-9`, to
absorb floating-point arithmetic noise. This does not discretize positions or
times.

## Feasibility And Scheduling

`is_placement_feasible` checks the quay boundary, arrival constraint, vessel
uniqueness, and conflicts with a partial schedule. It does not move the vessel
or choose another action.

`find_schedule_violations` provides compact diagnostic codes for complete or
partial schedule validation. `is_schedule_feasible` is its boolean wrapper.

`earliest_feasible_start` holds the berth position fixed. It begins at vessel
arrival and, on conflict, jumps directly to the earliest relevant service-end
event before checking again. It never scans minute by minute and retains
fractional times.

## Candidate Positions

`candidate_positions` returns a sorted, tolerance-deduplicated tuple made from:

- quay origin `0`,
- right alignment `Q - L`,
- each existing placement's right edge plus clearance,
- each existing placement's left edge minus clearance and the new vessel length.

Out-of-bounds positions are removed. These positions are a finite encoding for
future heuristics, RL, and candidate-space enumeration. They do not redefine
the physical problem: a future continuous mathematical solver may optimize any
real-valued berth position independently of this generator.

## Objective Helpers

The v1 objective remains total vessel waiting time:

```text
waiting_i = berth_start_i - arrival_i
turnaround_i = service_end_i - arrival_i
total_waiting = sum(waiting_i)
```

`total_waiting_time` requires a complete one-to-one vessel/placement mapping.
Missing, duplicate, unknown, mismatched, and pre-arrival placements raise an
error instead of being silently omitted.
