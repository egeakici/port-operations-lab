"""Single event clock, committed constant-speed fixture motion and safe dispatch.

Action support is deliberately narrower than unrestricted offline repositioning:
an unassigned crane holds position. No hidden yielding, teleport or task splitting.
Research execution is locked pending the inherited material decisions.
"""
import copy
from .contracts import *


class CraneSchedulingKernel:
    def __init__(self, problem, permit=None):
        problem.require_fixture_execution(permit)
        self.permit=permit
        self.problem = problem
        self.time = problem.vessel.planning_start_min
        self.records = []
        self.segments = []
        self.events = []
        self.completed = set()
        self.status = "RUNNING" if problem.tasks else "COMPLETED"
        self._jobs = {t.task_id:t for t in problem.tasks}
        self._cranes = {c.crane_id:c for c in problem.cranes}
        self._bayx = {b.bay_id:local_to_global(problem.vessel,b.local_m) for b in problem.bays}

    def clone(self): return copy.deepcopy(self)

    def position(self, cid, time=None):
        time = self.time if time is None else time
        value = self._cranes[cid].initial_position_m
        for s in self.segments:
            if s.crane_id != cid: continue
            if time < s.start_min: return value
            if time < s.end_min:
                return s.start_m+(s.end_m-s.start_m)*(time-s.start_min)/(s.end_min-s.start_min)
            value = s.end_m
        return value

    def busy(self, cid):
        return any(r.crane_id == cid and r.completion_min > self.time for r in self.records)

    def _proposal(self, cid, jid):
        c, task = self._cranes[cid], self._jobs[jid]
        start, x, target = self.time, self.position(cid), self._bayx[task.bay_id]
        arrival = start + abs(target-x)/c.travel_speed_m_per_min
        process = arrival + c.setup_min
        finish = process + 60*task.workload_moves/c.effective_moves_per_hour
        record = ScheduledTask(jid,cid,start,arrival,process,finish)
        segments = [MotionSegment(cid,"TRAVEL",start,arrival,x,target,jid), MotionSegment(cid,"SETUP",arrival,process,target,target,jid), MotionSegment(cid,"PROCESS",process,finish,target,target,jid)]
        return record, segments

    def _safe_reservation(self, cid, candidate):
        other = next(c.crane_id for c in self.problem.cranes if c.crane_id != cid)
        stop = max([self.time] + [s.end_min for s in candidate] + [s.end_min for s in self.segments if s.crane_id == other])
        knots = {self.time,stop}
        for s in candidate + [s for s in self.segments if s.crane_id==other and s.end_min>=self.time]:
            knots.update(t for t in (s.start_min,s.end_min) if t>=self.time)
        def proposed(t):
            for s in candidate:
                if s.start_min <= t < s.end_min:
                    return s.start_m+(s.end_m-s.start_m)*(t-s.start_min)/(s.end_min-s.start_min)
            return candidate[-1].end_m
        rank = self._cranes[cid].rail_rank
        for t in knots:
            a, b = proposed(t), self.position(other,t)
            gap = b-a if rank == 0 else a-b
            if gap < self.problem.rail.min_clearance_m: return False
        return True

    def legal_pair(self, cid, jid):
        if self.status != "RUNNING" or cid not in self._cranes or jid not in self._jobs: return False
        if self.busy(cid) or any(r.task_id==jid for r in self.records): return False
        c, t = self._cranes[cid], self._jobs[jid]
        if self.time < max(c.available_at_min,t.release_min): return False
        if not c.reach_lower_m <= self._bayx[t.bay_id] <= c.reach_upper_m: return False
        return self._safe_reservation(cid,self._proposal(cid,jid)[1])

    def legal_pairs(self):
        return tuple((c.crane_id,t.task_id) for c in self.problem.cranes for t in sorted(self.problem.tasks,key=lambda t:t.task_id) if self.legal_pair(c.crane_id,t.task_id))

    def future_events(self):
        times = {s.end_min for s in self.segments if s.end_min > self.time}
        times.update(c.available_at_min for c in self.problem.cranes if c.available_at_min>self.time)
        return tuple(sorted(times))

    def can_wait(self): return self.status == "RUNNING" and bool(self.future_events())

    def _event(self, kind, cid=None, jid=None):
        n = len(self.events)
        self.events.append(CraneTraceEvent(SCHEMA,f"e{n:08d}",n,self.time,kind,cid,jid))

    def step(self, decision):
        require(self.status == "RUNNING", "EPISODE_ENDED", "kernel", self.status)
        if decision.tag == "ASSIGN_TASK":
            require(self.legal_pair(decision.crane_id,decision.task_id), "ILLEGAL_ACTION", "action", "reservation rejected without mutation")
            record, segments = self._proposal(decision.crane_id,decision.task_id)
            self.records.append(record); self.segments.extend(segments)
            self._event("ASSIGN_TASK",record.crane_id,record.task_id)
        else:
            require(self.can_wait(), "INVALID_WAIT", "action", "no strictly later relevant event")
            next_time = min(self.future_events())
            horizon = self.problem.vessel.planning_start_min+self.problem.rail.horizon_min
            self.time = min(next_time,horizon)
            self._event("WAIT_ADVANCED")
            for r in sorted(self.records,key=lambda r:(r.completion_min,self._cranes[r.crane_id].rail_rank,r.task_id)):
                if r.completion_min <= self.time and r.task_id not in self.completed:
                    self.completed.add(r.task_id); self._event("TASK_COMPLETED",r.crane_id,r.task_id)
            if len(self.completed) == len(self._jobs): self.status = "COMPLETED"
            elif self.time >= horizon: self.status = "TRUNCATED_HORIZON"
        return self.observation()

    def mark_deadlock(self):
        require(not self.legal_pairs() and not self.can_wait(), "NOT_DEADLOCK", "kernel", "legal progress exists")
        self.status = "DEADLOCK"

    def observation(self):
        return CraneObservation(SCHEMA,self.time,tuple(self.position(c.crane_id) for c in self.problem.cranes),tuple(not self.busy(c.crane_id) and c.available_at_min<=self.time for c in self.problem.cranes),tuple(sorted(self.completed)),tuple(sorted(r.task_id for r in self.records)),"CURRENT_VESSEL_KNOWN_WORKLOAD")

    def schedule(self, policy_id="candidate", solver_status=None):
        outcome = {"RUNNING":"PARTIAL","COMPLETED":"CANDIDATE_UNVERIFIED","DEADLOCK":"DEADLOCK","TRUNCATED_HORIZON":"TRUNCATED_HORIZON"}[self.status]
        return CraneSchedule(SCHEMA,self.problem.fingerprint,policy_id,outcome,solver_status,tuple(self.records),tuple(self.segments),self.time)
