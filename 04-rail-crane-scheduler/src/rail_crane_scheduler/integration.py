"""Versioned, one-way synthetic compatibility adapter; no legacy imports/writes."""
from dataclasses import dataclass,replace
from .contracts import *
from .kernel import CraneSchedulingKernel
from .validator import verify

ADAPTER_VERSION="p04_isolated_crane_proposal_v1"


@dataclass(frozen=True)
class AdapterRequest(Wire):
    schema_version: str
    source_state_hash: str
    decision_id: str
    observed_time_min: float
    problem: QCSPProblem
    fidelity: str


@dataclass(frozen=True)
class OperationProposal(Wire):
    task_id: str
    source_task_ids: tuple[str, ...]
    crane_id: str
    bay_id: str
    workload_moves: int
    forecast_start_min: float
    forecast_completion_min: float


@dataclass(frozen=True)
class IntegratedProposal(Wire):
    schema_version: str
    source_state_hash: str
    decision_id: str
    observed_time_min: float
    problem_hash: str
    schedule: CraneSchedule
    operations: tuple[OperationProposal, ...]
    authority: str


def from_primitive(observation,enrichment=None,*,expected_axis,expected_clearance_m):
    require(enrichment is not None,"MISSING_DATA","observation","native CraneView has no ship bays/current rail positions/speed")
    require(enrichment.metadata.origin=='TEST_FIXTURE_SYNTHETIC',"LIVE_INTEGRATION_PENDING","enrichment","only separately labelled synthetic mapping is supported")
    require(observation.get('schema_version')=='itp_crane_observation_v1',"SOURCE_VERSION","observation","unknown primitive schema")
    vessels=observation.get('vessels',[]); cranes=observation.get('cranes',[])
    require(len(vessels)==1 and len(cranes)==2,"UNSUPPORTED_QCAP","observation","single-vessel fixed-two-crane adapter only")
    vessel=vessels[0]; p=enrichment
    require(vessel['vessel_id']==p.vessel.vessel_id and vessel['max_cranes']==2 and vessel['remaining_moves']==p.declared_workload_moves,"SOURCE_IDENTITY_WORK","observation","vessel/cap/work mismatch")
    require(vessel['phase'] in {'HANDLING','BERTHING_PREP'} and vessel['berth_position_m']==p.vessel.berth_origin_m and vessel['length_m']==p.vessel.length_m,"SOURCE_FRAME","vessel","fixed berth/frame mismatch")
    ids=[c['crane_id'] for c in cranes]
    require(len(set(ids))==2 and set(ids)=={c.crane_id for c in p.cranes},"SOURCE_CRANES","observation","fleet identity mismatch")
    require(observation['time_min']==p.vessel.planning_start_min and bool(observation.get('decision_id')),"SOURCE_CLOCK","observation","missing decision or inconsistent clock")
    require(expected_axis==p.rail.axis and expected_clearance_m==p.rail.min_clearance_m,"PHYSICS_CONFLICT","geometry","axis/clearance differs")
    require(all(t.source_task_ids for t in p.tasks),"MISSING_PROVENANCE","tasks","explicit original task mapping required; no invented real IDs")
    require(all(not t.source_container_ids for t in p.tasks),"AGGREGATE_ONLY","tasks","this synthetic adapter has no authoritative container-to-bay ledger")
    state_hash=digest(observation)
    metadata=replace(p.metadata,source_project='PROJECT_I_SYNTHETIC_ADAPTER_FIXTURE',source_snapshot=state_hash,scenario_id='adapter_'+state_hash[:20])
    problem=replace(p,metadata=metadata)
    return AdapterRequest(ADAPTER_VERSION,state_hash,observation['decision_id'],float(observation['time_min']),problem,'EXPLICIT_SYNTHETIC_ENRICHMENT_NOT_NATIVE_BAY_DATA')


def to_proposal(request,schedule):
    require(request.schema_version==ADAPTER_VERSION,"ADAPTER_VERSION","request","unsupported")
    verdict=verify(request.problem,schedule)
    require(verdict.valid_complete,"INCOMPLETE_OR_INVALID_PLAN","schedule",str(verdict.errors))
    jobs={t.task_id:t for t in request.problem.tasks}
    operations=tuple(OperationProposal(r.task_id,jobs[r.task_id].source_task_ids,r.crane_id,jobs[r.task_id].bay_id,jobs[r.task_id].workload_moves,r.process_start_min,r.completion_min) for r in schedule.tasks)
    return IntegratedProposal(ADAPTER_VERSION,request.source_state_hash,request.decision_id,request.observed_time_min,request.problem.fingerprint,schedule,operations,'FORECAST_PROPOSAL_ONLY_NO_CARGO_COMPLETION_AUTHORITY')


def isolated_smoke(request,proposal,*,current_state_hash,current_decision_id,current_time_min):
    require(proposal.schema_version==ADAPTER_VERSION and proposal.problem_hash==request.problem.fingerprint,"PROPOSAL_IDENTITY","proposal","wrong version/input")
    require(current_state_hash==proposal.source_state_hash==request.source_state_hash and current_decision_id==proposal.decision_id==request.decision_id and current_time_min==proposal.observed_time_min==request.observed_time_min,"STALE_PROPOSAL","proposal","state/decision/clock changed; reject atomically")
    expected=to_proposal(request,proposal.schedule)
    require(expected==proposal,"PROPOSAL_CONSERVATION","operations","identity/work/times altered")
    kernel=CraneSchedulingKernel(request.problem)
    for r in proposal.schedule.tasks:
        while kernel.time<r.departure_min:
            require(kernel.can_wait() and min(kernel.future_events())<=r.departure_min,"UNSUPPORTED_REPOSITION","schedule","not representable by isolated dispatch harness")
            kernel.step(SchedulingDecision('WAIT',None,None))
        require(kernel.time==r.departure_min,"PLAN_TIME_ORDER","schedule","out-of-order departure")
        kernel.step(SchedulingDecision('ASSIGN_TASK',r.crane_id,r.task_id))
    while kernel.can_wait(): kernel.step(SchedulingDecision('WAIT',None,None))
    verdict=verify(request.problem,kernel.schedule())
    require(verdict.valid_complete and tuple(kernel.records)==proposal.schedule.tasks,"EXECUTION_DRIFT","harness","forecast and isolated execution differ")
    return {'status':'ISOLATED_SMOKE_PASS','adapter_status':'ADAPTER_READY_FOR_SYNTHETIC_FIXTURES','live_integration':'LIVE_INTEGRATION_PENDING','full_terminal_integration':'FULL_TERMINAL_INTEGRATION_NOT_PERFORMED','clock_owner':'ISOLATED_PROJECT04_KERNEL_ONLY','original_moves':request.problem.declared_workload_moves,'executed_moves':sum(t.workload_moves for t in request.problem.tasks if t.task_id in kernel.completed),'cargo_ledger_mutated':False,'makespan_min':verdict.makespan_min}


def legacy_crane_action(proposal):
    raise ContractError('INCOMPATIBLE_PHYSICS','CraneAction','legacy vessel assignment cannot carry bay paths; separately versioned successor required')
