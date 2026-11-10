"""Independent full-plan verifier. Does not import/call the execution kernel."""
from dataclasses import dataclass
import math
from .contracts import *


@dataclass(frozen=True)
class ValidationReport:
    valid_complete: bool
    errors: tuple[str, ...]
    makespan_min: float | None
    completed_task_ids: tuple[str, ...]


def verify(problem, schedule, require_complete=True, permit=None):
    problem.require_fixture_execution(permit)
    errors = []
    def check(ok, code):
        if not ok: errors.append(code)
    check(schedule.problem_hash == problem.fingerprint, "PROBLEM_HASH")
    t0 = problem.vessel.planning_start_min
    et, ex = problem.rail.time_tolerance_min, problem.rail.position_tolerance_m
    close = lambda a, b: abs(a-b) <= et
    check(t0 <= schedule.stop_min <= t0 + problem.rail.horizon_min, "STOP_TIME")
    cranes = {c.crane_id: c for c in problem.cranes}
    jobs = {t.task_id: t for t in problem.tasks}
    bayx = {b.bay_id: local_to_global(problem.vessel, b.local_m) for b in problem.bays}
    records = {t.task_id: t for t in schedule.tasks}
    check(len(records) == len(schedule.tasks) and set(records) <= set(jobs), "TASK_IDENTITY")
    check(all(s.crane_id in cranes for s in schedule.segments), "UNKNOWN_CRANE")
    paths = {}
    end = max([schedule.stop_min, t0] + [s.end_min for s in schedule.segments])
    for cid, crane in cranes.items():
        segments = sorted((s for s in schedule.segments if s.crane_id == cid), key=lambda s: (s.start_min, s.end_min))
        previous_end, position = t0, crane.initial_position_m
        expanded = []
        for s in segments:
            check(s.start_min >= previous_end - et and s.start_min >= t0, "CRANE_OVERLAP")
            check(abs(s.start_m-position) <= ex, "TELEPORT_OR_DISCONTINUITY")
            check(problem.rail.lower_m <= min(s.start_m,s.end_m) and max(s.start_m,s.end_m) <= problem.rail.upper_m, "RAIL_BOUNDARY")
            if s.mode == "TRAVEL":
                check(close(s.end_min-s.start_min, abs(s.end_m-s.start_m)/crane.travel_speed_m_per_min), "TRAVEL_SPEED")
            else:
                check(abs(s.end_m-s.start_m) <= ex, "MOTION_DURING_STATIONARY_WORK")
            check(s.task_id is None or s.task_id in jobs, "PHANTOM_SEGMENT_TASK")
            if s.start_min > previous_end:
                expanded.append(MotionSegment(cid,"IDLE",previous_end,s.start_min,position,position,None))
            expanded.append(s)
            previous_end, position = s.end_min, s.end_m
        if end > previous_end: expanded.append(MotionSegment(cid,"IDLE",previous_end,end,position,position,None))
        paths[cid] = expanded
    for jid, record in records.items():
        if jid not in jobs or record.crane_id not in cranes:
            check(False, "TASK_REFERENCE"); continue
        job, crane = jobs[jid], cranes[record.crane_id]
        x = bayx[job.bay_id]
        check(crane.reach_lower_m <= x <= crane.reach_upper_m, "TASK_REACH")
        check(record.departure_min >= max(t0,crane.available_at_min,job.release_min), "READINESS")
        check(close(record.process_start_min-record.setup_start_min, crane.setup_min), "SETUP_DURATION")
        check(close(record.completion_min-record.process_start_min, 60*job.workload_moves/crane.effective_moves_per_hour), "PROCESS_DURATION")
        expected = (("TRAVEL", record.departure_min, record.setup_start_min), ("SETUP",record.setup_start_min,record.process_start_min),("PROCESS",record.process_start_min,record.completion_min))
        for mode, start, stop in expected:
            matches = [s for s in schedule.segments if s.task_id == jid and s.mode == mode]
            check(len(matches) == 1, "ATOMIC_TASK_INTERVALS")
            if len(matches) == 1:
                s = matches[0]
                check(s.crane_id == record.crane_id and close(s.start_min,start) and close(s.end_min,stop), "TASK_PATH_TIMES")
                check(abs(s.end_m-x) <= ex and (mode == "TRAVEL" or abs(s.start_m-x)<=ex), "TASK_BAY_POSITION")
    # Segments for a job need a matching unique task record, never phantom work.
    check(all(s.task_id is None or s.task_id in records for s in schedule.segments), "ORPHAN_WORK")
    def position(cid, time):
        crane = cranes[cid]
        value = crane.initial_position_m
        for s in paths[cid]:
            if time < s.start_min: return value
            if s.start_min <= time <= s.end_min:
                if s.end_min == s.start_min: return s.end_m
                return s.start_m+(s.end_m-s.start_m)*(time-s.start_min)/(s.end_min-s.start_min)
            value = s.end_m
        return value
    knots = {t0,end}
    for path in paths.values():
        for s in path: knots.update((s.start_min,s.end_min))
    left,right = problem.cranes
    # On each union interval relative position is affine, hence extrema are knots.
    for t in sorted(knots):
        check(position(right.crane_id,t)-position(left.crane_id,t) >= problem.rail.min_clearance_m, "SWEPT_RAIL_CLEARANCE")
    completed = tuple(sorted(jid for jid,r in records.items() if jid in jobs and r.completion_min <= schedule.stop_min))
    all_done = set(completed) == set(jobs) and len(records) == len(jobs)
    if require_complete: check(all_done, "INCOMPLETE_ORIGINAL_WORK")
    valid = not errors and all_done
    makespan = (max((r.completion_min for r in records.values()),default=t0)-t0) if valid else None
    return ValidationReport(valid, tuple(sorted(set(errors))), makespan, completed)
