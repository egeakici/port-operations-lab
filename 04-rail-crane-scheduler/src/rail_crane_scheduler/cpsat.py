"""Extensional CP-SAT reference over a fully enumerated finite dispatch tree.

Not unrestricted continuous QCSP. Incomplete enumeration never certifies a bound.
Every selectable path is independently verified, including all swept rail knots.
"""
from dataclasses import dataclass
import importlib.metadata
import math
import time
from .contracts import *
from .kernel import CraneSchedulingKernel
from .validator import verify

FORMULATION = "p04_exact_finite_event_dispatch_paths_v1"


def enumerate_paths(problem, max_nodes,permit=None,*,deadline=None):
    require(len(problem.tasks)<=5 and type(max_nodes) is int and 0<max_nodes<=100000,"UNSUPPORTED_FORMULATION","enumeration","at most five jobs; explicit finite node bound required")
    stack=[CraneSchedulingKernel(problem,permit)]; paths=[]; count=0
    while stack:
        require(deadline is None or time.perf_counter()<deadline,'ENUMERATION_TIMEOUT','wall_limit_s','complete domain unavailable; no bound or infeasibility claim')
        count+=1
        require(count<=max_nodes,"ENUMERATION_INCOMPLETE","max_nodes","no optimality claim from incomplete candidate set")
        k=stack.pop()
        if k.status=="COMPLETED":
            schedule=k.schedule("cpsat_finite_dispatch_v1")
            require(verify(problem,schedule,permit=permit).valid_complete,"REFERENCE_VERIFIER","candidate","invalid enumerated path")
            paths.append(schedule); continue
        if k.status!="RUNNING": continue
        actions=[SchedulingDecision("ASSIGN_TASK",c,j) for c,j in k.legal_pairs()]
        if k.can_wait(): actions.append(SchedulingDecision("WAIT",None,None))
        for action in reversed(actions):
            clone=k.clone(); clone.step(action); stack.append(clone)
    return tuple(paths),count


def exact_tick(value,tick,tolerance):
    require(type(tick) in (int,float) and math.isfinite(tick) and tick>0,"TICK","tick_min","finite positive tick required")
    ratio=value/tick
    require(math.isfinite(ratio) and abs(ratio)<2**50,"SCALING_OVERFLOW","time","scaled time outside safe domain")
    integer=round(ratio)
    require(abs(integer*tick-value)<=tolerance,"UNSUPPORTED_FORMULATION","grid","non-grid event; no silent duration rounding")
    return integer


@dataclass(frozen=True)
class SolverResult:
    status: str
    formulation: str
    schedule: CraneSchedule | None
    objective_min: float | None
    bound_min: float | None
    relative_gap: float | None
    wall_s: float
    tick_min: float
    solver_version: str | None
    detail: str


def solve(problem,*,tick_min,wall_limit_s,max_nodes,permit=None):
    started=time.perf_counter()
    require(type(wall_limit_s) in (int,float) and math.isfinite(wall_limit_s) and wall_limit_s>0,"SOLVER_BUDGET","wall_limit_s","explicit positive budget required")
    if permit is None:
        require(problem.metadata.role in {"development","diagnostic"},"SPLIT_GUARD","role","reference smoke is fixture-only")
    else: problem.require_fixture_execution(permit)
    try:
        # OR-Tools Windows DLL loader writes informational Python prints.
        # Keep machine-readable CLI stdout reserved for JSON.
        import contextlib
        import sys
        with contextlib.redirect_stdout(sys.stderr):
            from ortools.sat.python import cp_model
    except ImportError:
        return SolverResult("DEPENDENCY_PENDING",FORMULATION,None,None,None,None,time.perf_counter()-started,tick_min,None,"OR-Tools absent; not installed automatically")
    try:
        deadline=started+wall_limit_s
        paths,nodes=enumerate_paths(problem,max_nodes,permit,deadline=deadline)
        t0=problem.vessel.planning_start_min
        tol=problem.rail.time_tolerance_min
        model=cp_model.CpModel()
        selectors=[model.NewBoolVar(f"path_{i}") for i in range(len(paths))]
        model.Add(sum(selectors)==1)
        objectives=[]; crane_intervals={c.crane_id:[] for c in problem.cranes}
        for i,schedule in enumerate(paths):
            require(time.perf_counter()<deadline,'ENUMERATION_TIMEOUT','wall_limit_s','model construction exhausted total wall budget')
            objectives.append(exact_tick(schedule.stop_min-t0,tick_min,tol))
            for record in schedule.tasks:
                start=exact_tick(record.departure_min-t0,tick_min,tol)
                end=exact_tick(record.completion_min-t0,tick_min,tol)
                interval=model.NewOptionalIntervalVar(start,end-start,end,selectors[i],f"occupied_{i}_{record.task_id}")
                crane_intervals[record.crane_id].append(interval)
        for intervals in crane_intervals.values(): model.AddNoOverlap(intervals)
        for task in problem.tasks:
            assignments=[]
            for crane in problem.cranes:
                y=model.NewBoolVar(f"assign_{crane.crane_id}_{task.task_id}")
                matching=[selectors[i] for i,s in enumerate(paths) if any(r.task_id==task.task_id and r.crane_id==crane.crane_id for r in s.tasks)]
                model.Add(y==sum(matching)); assignments.append(y)
            model.Add(sum(assignments)==1)
        model.Minimize(sum(v*x for v,x in zip(objectives,selectors)))
        remaining=deadline-time.perf_counter()
        require(remaining>0,'ENUMERATION_TIMEOUT','wall_limit_s','total budget exhausted before solve')
        solver=cp_model.CpSolver(); solver.parameters.max_time_in_seconds=remaining
        solver.parameters.num_search_workers=1; solver.parameters.random_seed=0
        code=solver.Solve(model); status=solver.StatusName(code)
        version=importlib.metadata.version("ortools")
        if status not in {"OPTIMAL","FEASIBLE"}:
            exhausted=status=='UNKNOWN' and solver.WallTime()>=remaining*.95
            return SolverResult('TIMEOUT' if exhausted else status,FORMULATION,None,None,None,None,time.perf_counter()-started,tick_min,version,f"raw_status={status}; finite subclass only; complete enumeration nodes={nodes}; budget_exhausted={exhausted}")
        selected=next(i for i,x in enumerate(selectors) if solver.Value(x))
        from dataclasses import replace
        schedule=replace(paths[selected],solver_status=status)
        report=verify(problem,schedule,permit=permit)
        require(report.valid_complete,"SOLVER_PHYSICAL_REJECTION","schedule",str(report.errors))
        bound=float(solver.BestObjectiveBound())*tick_min
        objective=report.makespan_min
        return SolverResult(status,FORMULATION,schedule,objective,bound,(objective-bound)/objective if objective else None,time.perf_counter()-started,tick_min,version,f"complete finite event-action enumeration nodes={nodes}; no unrestricted continuous optimum claim")
    except ContractError as exc:
        return SolverResult("TIMEOUT" if exc.code=='ENUMERATION_TIMEOUT' else "UNSUPPORTED_FORMULATION",FORMULATION,None,None,None,None,time.perf_counter()-started,tick_min,importlib.metadata.version("ortools"),str(exc))
