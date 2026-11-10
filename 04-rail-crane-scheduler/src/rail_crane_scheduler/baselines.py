"""Four deterministic strategies sharing the kernel and independent verifier."""
from dataclasses import dataclass
import time
from .contracts import *
from .kernel import CraneSchedulingKernel
from .validator import verify

POLICIES = ("ordered_sweep_v1", "nearest_feasible_v1", "longest_work_v1", "balanced_finish_v1")


def choose(kernel, policy):
    require(policy in POLICIES, "POLICY", "policy_id", "unknown policy")
    pairs = kernel.legal_pairs()
    if not pairs: return SchedulingDecision("WAIT",None,None) if kernel.can_wait() else None
    def key(pair):
        cid,jid = pair
        c,t = kernel._cranes[cid],kernel._jobs[jid]
        x = kernel._bayx[t.bay_id]
        distance = abs(x-kernel.position(cid))
        canonical_tie = (c.rail_rank,x,jid)
        if policy == POLICIES[0]: return (x,)+canonical_tie
        if policy == POLICIES[1]: return (distance,)+canonical_tie
        if policy == POLICIES[2]: return (-t.workload_moves,distance)+canonical_tie
        load = sum(kernel._jobs[r.task_id].workload_moves for r in kernel.records if r.crane_id==cid)
        finish = kernel.time+distance/c.travel_speed_m_per_min+c.setup_min+60*t.workload_moves/c.effective_moves_per_hour
        return (load,finish)+canonical_tie
    cid,jid = min(pairs,key=key)
    return SchedulingDecision("ASSIGN_TASK",cid,jid)


def metrics(problem,schedule,latencies=(),permit=None):
    verdict = verify(problem,schedule,permit=permit)
    window_stop=problem.vessel.planning_start_min+verdict.makespan_min if verdict.valid_complete else schedule.stop_min
    elapsed = window_stop-problem.vessel.planning_start_min
    totals={mode:0. for mode in ("PROCESS","SETUP","TRAVEL")}; distance=0.
    for s in schedule.segments:
        actual = max(0.,min(s.end_min,window_stop)-max(s.start_min,problem.vessel.planning_start_min))
        if s.mode in totals: totals[s.mode] += actual
        if s.mode=="TRAVEL" and s.end_min>s.start_min:
            distance += abs(s.end_m-s.start_m)*actual/(s.end_min-s.start_min)
    completed = sum(t.workload_moves for t in problem.tasks if t.task_id in verdict.completed_task_ids)
    return MetricRecord(problem.fingerprint,verdict.valid_complete,verdict.makespan_min,problem.declared_workload_moves,completed,totals["TRAVEL"],distance,totals["PROCESS"],totals["PROCESS"]/(2*elapsed) if elapsed else None,max(0.,2*elapsed-sum(totals.values())),tuple(latencies))


@dataclass(frozen=True)
class RunRecord(Wire):
    schema_version: str
    problem_hash: str
    physical_hash: str
    role: str
    policy_id: str
    status: str
    action_count: int
    episode_wall_s: float
    schedule: CraneSchedule
    metrics: MetricRecord


def run(problem,policy,permit=None):
    if permit is None:
        require(problem.metadata.role in {"development","diagnostic"}, "SPLIT_GUARD", "problem.role", "bounded development runner never reads held-out or validation scenarios")
    else: problem.require_fixture_execution(permit)
    start=time.perf_counter(); kernel=CraneSchedulingKernel(problem,permit); latencies=[]; actions=0
    # At most n assignments + 3n motion/setup/process ends + two availability events.
    budget=4*len(problem.tasks)+3
    while kernel.status=="RUNNING":
        t=time.perf_counter(); action=choose(kernel,policy); latencies.append(time.perf_counter()-t)
        if action is None: kernel.mark_deadlock(); break
        require(actions<budget,"PROGRESS_BOUND","runner","event/assignment bound exceeded")
        kernel.step(action); actions+=1
    schedule=kernel.schedule(policy)
    values=metrics(problem,schedule,latencies,permit)
    status='INVALID_PLAN' if kernel.status=='COMPLETED' and not values.valid_complete else kernel.status
    return RunRecord(SCHEMA,problem.fingerprint,problem.physical_fingerprint,problem.metadata.role,policy,status,actions,time.perf_counter()-start,schedule,values)


def paired_development(problem):
    results=tuple(run(problem,policy) for policy in POLICIES)
    require(len({r.problem_hash for r in results})==1,"PAIRING","results","different inputs")
    return results
