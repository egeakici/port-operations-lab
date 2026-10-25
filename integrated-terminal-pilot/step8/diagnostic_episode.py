"""Isolated Step8 runner: frozen policies on intentionally versioned conditions.

No imports or functions in this module launch a scenario except run_cell_episode.
"""
from dataclasses import asdict
import time
from evidence import s
from statistical import d24, ContractError, validate_cargo
from closure_matrix import YARD


def run_cell_episode(doc, cell, trace_dir):
    from integrated_terminal_pilot.simulator.catalog import ScenarioCatalog
    from integrated_terminal_pilot.simulator.kernel import TerminalKernel
    from integrated_terminal_pilot.simulator.drivers import run_episode
    from integrated_terminal_pilot.simulator.trace import canonical_streams
    from integrated_terminal_pilot.policies import GreedyBerthOrderCranePolicy, create_policy
    from integrated_terminal_pilot.benchmark.runner import a3_scenario_gate, _decision_summary
    from integrated_terminal_pilot.benchmark.policies import create_berth_policy
    from integrated_terminal_pilot.scenarios.berth_projection import build_berth_projection
    from integrated_terminal_pilot.benchmark.cargo import outbound_obligations
    from integrated_terminal_pilot.benchmark.coordination_view import coordination_observer
    from integrated_terminal_pilot.benchmark.coordination_policies import IntegratedRolloutPolicy
    from model_coupling import CouplingEvaluator
    start, cpu = time.perf_counter(), time.process_time()
    catalog = ScenarioCatalog.from_document(doc,validate=True)
    outer_fp = s.digest(doc)
    gate = a3_scenario_gate(doc) if cell['arm']=='A3' else dict(status='NOT_APPLICABLE')
    if gate['status']=='BLOCK':
        # New unsupportedness is never silently excluded from the closure gate.
        raise ContractError('UNEXPECTED_PPO_SUPPORT_BLOCK: '+str(gate))
    observer = None
    if cell['arm']=='B2':
        class DiagnosticB2Policy(IntegratedRolloutPolicy):
            def decide(self,view):
                chosen=super().decide(view)
                if cell['model_variant']=='none':
                    # Downstream engineering/scientific observation only. It
                    # cannot change the already selected AM07 action.
                    t=time.perf_counter()
                    a2=create_berth_policy('A2')
                    action=a2.decide(view.berth)
                    self.records[-1]['same_state_A2']=dict(
                        action=a2.records[-1]['p03_action'],vessel_id=action.vessel_id,
                        agrees=a2.records[-1]['p03_action']==self.records[-1]['p03_action'],
                        diagnostic_seconds=time.perf_counter()-t,
                        interpretation='EMPIRICAL_SHARED_STATE_COMPARISON_NOT_AN_EQUALITY_GATE')
                return chosen
        policy = DiagnosticB2Policy('B2',YARD)
        if cell['model_variant'] != 'both': policy.evaluator = CouplingEvaluator(YARD,cell['model_variant'])
        observer = coordination_observer(include_projection=True)
    else:
        policy = create_berth_policy(cell['arm'],training_seed=cell['training_seed'],
            host_projection=build_berth_projection(doc) if cell['arm']=='A3' else None)
    observations=[]
    base_observer=observer
    def observe(live):
        view=base_observer(live) if base_observer else live.berth_view()
        berth=view.berth if cell['arm']=='B2' else view
        cohort=[v for v in berth.vessels if v.status!='DEPARTED']
        visible={v.vessel_id for v in cohort}
        projected=view.projection.catalog if cell['arm']=='B2' else None
        observations.append(dict(time_min=berth.time_min,cohort=[v.vessel_id for v in cohort],
            arrivals={v.vessel_id:v.arrival_time_min for v in cohort},
            inner_horizon_min=projected.drain_limit_min if projected else
                max(v.arrival_time_min for v in berth.vessels)+catalog.physics.max_drain_extension_min,
            known_outbound_ids=[c.container_id for c in projected.containers if c.destination_vessel_id in visible]
                if projected else None,
            occupying_release_forecasts=[dict(vessel_id=v.vessel_id,predicted=v.estimated_release_time_min)
                for v in berth.vessels if v.status=='OCCUPYING']))
        return view
    observer=observe
    kernel = TerminalKernel.from_catalog(catalog,invariant_mode='cheap')
    setup = time.perf_counter()-start
    run = run_episode(kernel,berth_policy=policy,crane_policy=GreedyBerthOrderCranePolicy(),
                      yard_policy=create_policy(YARD),berth_observer=observer)
    result = kernel.result()
    kernel.validate_invariants(full=True)
    if run.status=='FAILED' or run.rejections or not result['audits']['ok']:
        raise ContractError(f"FAILED_DIAGNOSTIC: {run.failure}; {run.rejections}; audits={result['audits']}")
    cargo = outbound_obligations(kernel)
    validate_cargo(cargo,cargo['N_out'],result['T_end_min'])
    if s.digest(doc) != outer_fp:
        raise ContractError('Outer scenario mutated')
    # Exact canonical streams, compressed directly. No lossy summary or rerun
    # dependency; both compressed and decompressed SHA are retained.
    import gzip
    import hashlib
    from pathlib import Path
    trace_dir = Path(trace_dir)
    trace_dir.mkdir(parents=True,exist_ok=False)
    traces = {}
    for name, chunks in canonical_streams(kernel,rejections=run.rejections,result=result).items():
        h, count = hashlib.sha256(), 0
        target = trace_dir/(name+'.gz')
        with target.open('xb') as raw, gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as stream:
            for chunk in chunks:
                b = chunk.encode('utf-8'); h.update(b); count += len(b); stream.write(b)
        traces[name] = dict(canonical_sha256=h.hexdigest(),canonical_bytes=count)
    vessels = result['vessels']
    total = d24(vessels,result['T_end_min'])
    from evidence import close
    close(total,result['kpi']['total_turnaround_min'],'Independent diagnostic D24 reconciliation')
    from closure_diagnostics import post_run
    diagnostics=post_run(trace_dir,doc,policy.records,observations,result)
    if (diagnostics['ledger_N_out']!=cargo['N_out'] or diagnostics['ledger_U']!=cargo['U_not_loaded']
            or diagnostics['rollovers']!=cargo['classes']['NOT_LOADED_ROLLED_OVER']):
        raise ContractError('Independent ledger cargo/rollover reconciliation failed')
    return dict(status='VERIFIED', terminal_status=run.status, cell_id=cell['cell_id'],
        cell_fingerprint=cell['fingerprint'], scenario_fingerprints=doc['fingerprints'],
        physical_document_sha256=outer_fp, a3_support=gate, model_variant=cell['model_variant'],
        model_visibility='UNCALIBRATED_SYNTHETIC_FORECAST; future gate/pickup omitted, observed continue',
        TA=total, n_vessels=len(vessels), TA_per_vessel=total/len(vessels),
        T_end_min=result['T_end_min'], cargo=cargo, kpi=result['kpi'], vessels=vessels,
        time_decomposition=result['time_decomposition'], service_compliance=result['service_compliance'],
        audits=result['audits'], decisions=_decision_summary(policy.records,run.berth_timings),
        policy_records=policy.records, observations=observations, diagnostics=diagnostics,
        policy=policy.describe(), trace=traces,
        compute=dict(wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,setup_seconds=setup,
                     simulation_device='CPU', inference_device='CPU',outer_workers=1,torch_threads=1))
