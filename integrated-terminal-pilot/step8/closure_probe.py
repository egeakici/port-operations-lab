"""Small hand-constructed engineering probes, never 13M scientific episodes."""
import importlib.util
from pathlib import Path
import time
import uuid
from dataclasses import asdict
from evidence import PROJECT, REPO, s, sha, read, publish, code_inventory
from statistical import ContractError


def helpers():
    p=PROJECT/'tests/step4_support.py'
    spec=importlib.util.spec_from_file_location('closure_hand_fixtures',p)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def view_of(doc):
    from integrated_terminal_pilot.simulator.kernel import TerminalKernel
    from integrated_terminal_pilot.benchmark.coordination_view import build_coordination_view
    k=TerminalKernel.from_scenario(doc)
    request=k.advance()
    if request.kind!='BERTH': raise ContractError('Engineering fixture must begin at berth decision')
    return k,build_coordination_view(k,include_projection=True)


def counterexample():
    h=helpers()
    # One berth slot, ready cargo, short censoring horizon. A2 prefers the
    # short vessel; retained AM07 prioritizes loading more original containers.
    doc=h.build_doc(quay=800,vessels=[h.vessel('V001',0,700),h.vessel('V002',0,700)],
        containers=[h.container(1,'export',dest='V001',block='B01')]+
          [h.container(i,'export',dest='V002',block='B01') for i in range(2,6)],
        cranes=[h.crane('QC01',30)],physics_doc=h.physics(**dict(h.QUIET,**{'episode.max_drain_extension_min':70})))
    from integrated_terminal_pilot.benchmark.policies import create_berth_policy
    from integrated_terminal_pilot.benchmark.coordination_policies import select
    from model_coupling import CouplingEvaluator
    from closure_matrix import YARD
    kernel,view=view_of(doc)
    a2=create_berth_policy('A2').decide(view.berth)
    prediction=CouplingEvaluator(YARD,'none').evaluate(view)
    chosen=select(prediction,'B2')
    return dict(kind='ENGINEERING_ONLY_NOT_SCIENTIFIC',a2_vessel=a2.vessel_id,
        none_vessel=chosen.vessel_id,disagrees=a2.vessel_id!=chosen.vessel_id,
        predictions=[asdict(c) for c in prediction.candidates],
        reason='Censoring and retained AM07 invalidate uncensored candidate-independent service constant; nominal capacity alone cannot force A2 identity',
        outer_document=doc)


def execute():
    from model_coupling import CouplingEvaluator, SWITCHES
    from integrated_terminal_pilot.benchmark.coordination_policies import SharedRolloutEvaluator
    from diagnostic_episode import run_cell_episode
    from closure_matrix import YARD
    h=helpers()
    doc=h.build_doc(vessels=[h.vessel('V001',0,300)],
        containers=[h.container(i,'export',dest='V001',block='B01') for i in range(1,11)],
        cranes=[h.crane('QC01',30)],blocks=[h.block('B01',100,y=900,handling=20)],
        physics_doc=h.physics(**{'transport.speed_m_per_min':150.,'transport.units_per_crane':3}))
    k,view=view_of(doc)
    before=k.snapshot(); projections=[]; timings=[]
    for variant in SWITCHES:
        start=time.perf_counter(); cpu=time.process_time()
        result=CouplingEvaluator(YARD,variant).evaluate(view)
        timings.append(dict(variant=variant,wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,
            candidates=len(result.candidates),selected_predictions=[asdict(c) for c in result.candidates]))
        projections.append(result.prediction_digest)
    if k.snapshot()!=before or len(set(projections))<2:
        raise ContractError('Intervention no-op or outer mutation')
    full=SharedRolloutEvaluator(YARD).evaluate(view)
    both=CouplingEvaluator(YARD,'both').evaluate(view)
    if full.prediction_digest!=both.prediction_digest: raise ContractError('Both alias not byte-identical')
    example=counterexample()
    if not example['disagrees']: raise ContractError('Counterexample did not demonstrate claimed divergence')
    root=PROJECT/'experiments/step8_analysis/engineering'/uuid.uuid4().hex
    root.mkdir(parents=True)
    cell=dict(cell_id='ENGINEERING_HAND_FIXTURE',fingerprint='engineering_not_scientific',arm='B2',
              training_seed=None,model_variant='both')
    result=run_cell_episode(doc,cell,root/'trace')
    size=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    value=dict(schema='step8_engineering_probe_v1',scientific_episodes=0,handwritten_micro_episodes=1,
        outer_source_scenario='CONTRIVED_10_CONTAINERS_ONE_VESSEL',matrix_seeds_generated=0,
        outer_unchanged=True,both_identity=True,adapter_file_sha256=sha(Path(__file__).with_name('model_coupling.py')),
        timings=timings,counterexample=example,full_episode_compute=result['compute'],
        compressed_trace_bytes=size,fixture_containers=10,
        cargo_ledger_audit=result['diagnostics']['ledger_U']==result['cargo']['U_not_loaded'],
        benchmark_limit='Tiny engineering cost validates plumbing, not a scalable congestion runtime forecast')
    publish(root/'probe.json',value)
    return dict(path=(root/'probe.json').relative_to(REPO).as_posix(),sha256=sha(root/'probe.json'),evidence=value)


def latest_probe():
    paths=sorted((PROJECT/'experiments/step8_analysis/engineering').glob('*/probe.json'),key=lambda p:p.stat().st_mtime)
    for p in reversed(paths):
        value=read(p)
        if value['adapter_file_sha256']==sha(Path(__file__).with_name('model_coupling.py')):
            return dict(path=p.relative_to(REPO).as_posix(),sha256=sha(p),evidence=value)
    raise ContractError('Current adapter engineering probe required')
