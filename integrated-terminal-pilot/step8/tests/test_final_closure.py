"""Bounded Final Closure contract gates: contrived fixtures, no13M generation."""
import copy
from dataclasses import replace
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_step8 import fixture_directory
from evidence import publish, read, sha, s, PROJECT, REPO
from statistical import ContractError, interval
from multiplicity import holm, simultaneous_interval
from closure_matrix import matrix, physical_document, YARD, scenario_key
from model_coupling import (CouplingEvaluator, SWITCHES, transform_fork, transformed_view,
                            NominalCapacityKernel)
from closure_probe import helpers, view_of, counterexample
from closure_runtime import (worker_lock, inventory, verify_cell, campaign_status,
                             resource_check, run_campaign, gzip_json, load_scenario)
from closure_reporting import final_gate, diagnostic_analysis


def doc_ready(*, vessels=1, cranes=1, max_cranes=1, arrival=0., quiet=True):
    h=helpers()
    vs=[h.vessel(f'V{i+1:03d}',arrival if i else 0,300,max_cranes=max_cranes) for i in range(vessels)]
    return h.build_doc(vessels=vs,
        containers=[h.container(i*10+j,'export',dest=v['vessel_id'],block='B01') for i,v in enumerate(vs) for j in range(1,11)],
        cranes=[h.crane(f'QC{i+1:02d}',30) for i in range(cranes)],
        physics_doc=h.physics(**(h.QUIET if quiet else {})))


def mock_cell():
    return dict(cell_id='FIXTURE',fingerprint='fixture',status='RUNNABLE',family='itp_medium',
        arm='A1',condition='base',model_variant='both',training_seed=None,
        changed_values={},scenario_seed=13000000)


def mock_plan():
    return dict(matrix=dict(cells=[mock_cell()],counts=dict(requirements=1,sensitivity=1,coupling=0,
        aliases=0,unique=1,runnable=1,unsupported=0,optional=0)))


class MultipleComparisonTests(unittest.TestCase):
    def test_holm_known_independent_numerical_answer(self):
        # Standard stepdown manual arithmetic: .01*4, .02*3, .03*2, .9*1.
        self.assertEqual(holm(dict(a=.01,b=.02,c=.03,d=.9)),dict(a=.04,b=.06,c=.06,d=.9))

    def test_holm_monotone_and_bounded(self):
        self.assertEqual(holm(dict(x=.04,y=.041)),dict(x=.08,y=.08))
        self.assertEqual(holm(dict(x=.8,y=.9)),dict(x=1.,y=1.))

    def test_holm_order_independent_ties(self):
        self.assertEqual(holm(dict(b=.01,a=.01)),holm(dict(a=.01,b=.01)))

    def test_invalid_holm(self):
        for p in ({},{'a':-1},{'a':float('nan')},{'a':2}):
            with self.assertRaises(ContractError):holm(p)

    def test_family_adjustment_widens_interval(self):
        values={'itp_medium':list(range(-20,30))}
        raw=interval(values);adj=simultaneous_interval(values)
        self.assertLess(adj['lower'],raw['lower']);self.assertGreater(adj['upper'],raw['upper'])
        self.assertEqual(adj['m'],2);self.assertEqual(adj['marginal_confidence'],.975)

    def test_fixed_bootstrap_parity_and_no_switch(self):
        a=simultaneous_interval({'f':[1.,2.,3.,4.]})
        self.assertEqual(a,simultaneous_interval({'f':[1.,2.,3.,4.]}))
        with self.assertRaises(ContractError):simultaneous_interval({'f':[1.]},m=1)

    def test_constant_effect_and_direction(self):
        self.assertEqual(simultaneous_interval({'f':[-2.]*5})['verdict'],'LOWER_TIME')
        self.assertEqual(simultaneous_interval({'f':[0.]*5})['p_raw_centered_bootstrap'],1.)


class MatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=matrix()

    def test_exact_requirement_accounting(self):
        self.assertEqual(self.plan['counts'],dict(requirements=4480,sensitivity=4320,coupling=160,
            aliases=40,unique=4440,runnable=4320,unsupported=120,optional=0))

    def test_unique_cell_and_fingerprints(self):
        self.assertEqual(len({r['cell_id'] for r in self.plan['cells']}),4480)
        self.assertEqual(len({r['fingerprint'] for r in self.plan['cells']}),4480)

    def test_all_seeds_roles_and_policy_identities(self):
        self.assertEqual({r['scenario_seed'] for r in self.plan['cells']},set(range(13000000,13000020)))
        self.assertEqual({r['family'] for r in self.plan['cells']},{'itp_medium','itp_heavy'})
        self.assertTrue(all(r['split']=='diagnostic' for r in self.plan['cells']))
        self.assertEqual({r['training_seed'] for r in self.plan['cells'] if r['arm']=='A3'},{11,23,37})

    def test_no_generation_from_planning(self):
        with patch('integrated_terminal_pilot.scenarios.generator.generate_scenario_with_diagnostics',side_effect=AssertionError('No generation')):
            self.assertEqual(matrix(),self.plan)

    def test_unsupported_preserved_not_success(self):
        unsupported=[r for r in self.plan['cells'] if r['status']=='UNSUPPORTED']
        self.assertEqual(len(unsupported),120)
        self.assertTrue(all(r['family']=='itp_heavy' and r['changed_values']=={'initial_occupancy':.3} for r in unsupported))
        with self.assertRaises(ContractError):physical_document(None,unsupported[0])

    def test_alias_exact_base_identity(self):
        lookup={r['cell_id']:r for r in self.plan['cells']}
        for alias in (r for r in lookup.values() if r['status']=='ALIAS'):
            base=lookup[alias['alias_of']]
            self.assertEqual(scenario_key(alias),scenario_key(base))
            self.assertEqual(base['arm'],'B2');self.assertEqual(alias['model_variant'],'both')

    def test_all_factors_validate_on_mocked_micro_scenario(self):
        # Generator is mocked, so no13M traffic is generated. Real validator
        # checks every physically transformed hand-written document.
        from integrated_terminal_pilot.scenarios.config import load_generator_config
        from integrated_terminal_pilot.scenarios.generator import GenerationResult
        from integrated_terminal_pilot.simulator.catalog import ScenarioCatalog
        cfg=load_generator_config(); before=copy.deepcopy(cfg.parameters)
        source=doc_ready(max_cranes=2,cranes=4)
        for condition in self.plan['conditions']:
            cell=next(c for c in self.plan['cells'] if c['condition']==condition['id'] and c['family']=='itp_medium')
            with self.subTest(condition=condition['id']),patch('integrated_terminal_pilot.scenarios.generator.generate_scenario_with_diagnostics',return_value=GenerationResult(source,{})):
                result=physical_document(cfg,cell)
                cat=ScenarioCatalog.from_document(result['document'])
                self.assertEqual(len(cat.cranes),cell['changed_values'].get('cranes',8))
                self.assertEqual(cat.physics.batch_size_containers,10)
                self.assertEqual(cat.physics.max_load_wait_min,cell['changed_values'].get('D17_wait_min',240))
        self.assertEqual(cfg.parameters,before)

    def test_out_of_band_refused_before_generator(self):
        from integrated_terminal_pilot.scenarios.config import load_generator_config
        for seed in (10000000,12000000,14000000):
            cell=dict(mock_cell(),scenario_seed=seed)
            with self.assertRaises(ContractError):physical_document(load_generator_config(),cell)


class CouplingContractTests(unittest.TestCase):
    def test_reject_truth_and_unknown_variant(self):
        k,v=view_of(doc_ready())
        with self.assertRaises(ContractError):transform_fork(k,'none')
        with self.assertRaises(ContractError):CouplingEvaluator(YARD,'invented')

    def test_none_nominal_hand_calculation(self):
        k,v=view_of(doc_ready())
        r=CouplingEvaluator(YARD,'none').evaluate(v)
        for c in r.candidates:
            # 30min prep +10*.5min +20min departure =55min.
            self.assertAlmostEqual(c.leaf.predicted_turnaround_min,55.)

    def test_crane_on_hand_calculation(self):
        k,v=view_of(doc_ready())
        r=CouplingEvaluator(YARD,'crane-aware').evaluate(v)
        self.assertAlmostEqual(r.candidates[0].leaf.predicted_turnaround_min,70.)

    def test_virtual_capacity_not_a_shared_fleet(self):
        k,v=view_of(doc_ready(vessels=2,cranes=1))
        r=CouplingEvaluator(YARD,'none').evaluate(v)
        self.assertAlmostEqual(r.candidates[0].leaf.predicted_turnaround_min,110.)

    def test_multiple_cranes_keep_nominal_per_vessel_total(self):
        k,v=view_of(doc_ready(cranes=2,max_cranes=2))
        # One10-container batch; inactive second crane must not halve nominal speed.
        r=CouplingEvaluator(YARD,'none').evaluate(v)
        self.assertAlmostEqual(r.candidates[0].leaf.predicted_turnaround_min,55.)

    def test_outer_and_source_projection_unchanged(self):
        import pickle
        k,v=view_of(doc_ready(quiet=False))
        before=copy.deepcopy(k.snapshot()); original=pickle.dumps(v)
        for variant in SWITCHES:CouplingEvaluator(YARD,variant).evaluate(v)
        self.assertEqual(k.snapshot(),before);self.assertEqual(pickle.dumps(v),original)

    def test_both_byte_identity(self):
        from integrated_terminal_pilot.benchmark.coordination_policies import SharedRolloutEvaluator
        k,v=view_of(doc_ready(quiet=False))
        self.assertIs(transformed_view(v,'both'),v)
        self.assertEqual(SharedRolloutEvaluator(YARD).evaluate(v).prediction_digest,
                         CouplingEvaluator(YARD,'both').evaluate(v).prediction_digest)

    def test_switches_really_propagate(self):
        k,v=view_of(doc_ready(quiet=False))
        for variant,(crane,transport,yard) in SWITCHES.items():
            fork=transformed_view(v,variant).projection.fork()
            self.assertEqual(fork.catalog.physics.transport_enabled,transport)
            self.assertEqual(fork.catalog.physics.yard_constraints_enabled,yard)
            self.assertEqual(isinstance(fork,NominalCapacityKernel),not crane)

    def test_wait_branches_and_order_invariance(self):
        k,v=view_of(doc_ready(vessels=2,arrival=60))
        for variant in SWITCHES:
            evaluator=CouplingEvaluator(YARD,variant)
            first=evaluator.evaluate(v); second=evaluator.evaluate(v,reverse_order=True)
            self.assertEqual(first.prediction_digest,second.prediction_digest)
            self.assertTrue(any(c.kind=='WAIT' for c in first.candidates))
            self.assertTrue(all(c.wait_terminal or c.wait_branches for c in first.candidates if c.kind=='WAIT'))

    def test_wait_clone_preserves_model_kernel(self):
        k,v=view_of(doc_ready())
        fork=transformed_view(v,'none').projection.fork()
        self.assertIsInstance(fork.clone(),NominalCapacityKernel)
        self.assertIsNot(fork.state,fork.clone().state)

    def test_variant_budget_identity_explicit(self):
        self.assertEqual(len({CouplingEvaluator(YARD,v).fingerprint for v in SWITCHES}),4)

    def test_already_active_batches_survive_private_intervention(self):
        from integrated_terminal_pilot.simulator.kernel import DecisionRequest
        from integrated_terminal_pilot.simulator.validator import BerthAction
        from integrated_terminal_pilot.benchmark.coordination_view import build_coordination_view
        from integrated_terminal_pilot.policies import GreedyBerthOrderCranePolicy,create_policy
        k,v=view_of(doc_ready(vessels=2,arrival=35,cranes=2,max_cranes=2))
        k.apply_berth_action(BerthAction.assign('fixture','V001',0.,decision_id=v.decision_id))
        for _ in range(100):
            req=k.advance()
            if req.kind=='BERTH':
                if k.current_time_min>=35:break
                k.apply_berth_action(BerthAction.wait('fixture',decision_id=req.decision_id));continue
            if req.kind=='CRANE':k.apply_crane_action(GreedyBerthOrderCranePolicy().decide(k.crane_observation()))
            else:k.apply_yard_action(create_policy(YARD).decide(k.yard_observation()))
        self.assertTrue(k._ship_work_orders())
        view=build_coordination_view(k,include_projection=True)
        before=k.snapshot()
        for variant in SWITCHES:CouplingEvaluator(YARD,variant).evaluate(view)
        self.assertEqual(k.snapshot(),before)

    def test_hidden_future_not_added(self):
        h=helpers()
        doc=h.build_doc(vessels=[h.vessel('V001',0,300),h.vessel('V002',1000,300)],
            containers=[h.container(1,'export',dest='V001',block='B01'),h.container(2,'export',dest='V002',gate_in=500)],
            cranes=[h.crane('QC01',30)])
        k,v=view_of(doc)
        for variant in SWITCHES:
            fork=transformed_view(v,variant).projection.fork()
            self.assertNotIn('V002',fork.catalog.vessel_by_id)
            self.assertTrue(all(c.gate_in_time_min is None for c in fork.catalog.containers))
            self.assertIsNone(fork.catalog.identity)

    def test_ready_uncensored_scoped_positive(self):
        from integrated_terminal_pilot.benchmark.policies import create_berth_policy
        from integrated_terminal_pilot.benchmark.coordination_policies import select
        k,v=view_of(doc_ready(vessels=2))
        a2=create_berth_policy('A2').decide(v.berth)
        self.assertEqual(a2.vessel_id,select(CouplingEvaluator(YARD,'none').evaluate(v),'B2').vessel_id)

    def test_censored_counterexample_refutes_universal_equality(self):
        result=counterexample()
        self.assertTrue(result['disagrees'])
        self.assertEqual(result['a2_vessel'],'V001');self.assertEqual(result['none_vessel'],'V002')


class DurableExecutionTests(unittest.TestCase):
    def test_worker_prevents_overlap_and_releases(self):
        with fixture_directory() as d:
            with worker_lock(Path(d)):
                with self.assertRaises(ContractError):
                    with worker_lock(Path(d)):pass
            with worker_lock(Path(d)):pass

    def test_resource_stop_before_admission(self):
        with fixture_directory() as d,patch('shutil.disk_usage',return_value=type('Disk',(),{'free':1})()):
            with self.assertRaises(ContractError):resource_check(Path(d))

    def test_cell_tamper_rejected(self):
        with fixture_directory() as d:
            root=Path(d);cell=mock_cell();out=root/'cells'/cell['fingerprint'];out.mkdir(parents=True)
            publish(out/'result.json',dict(cell_id=cell['cell_id'],status='VERIFIED',trace={}))
            publish(out/'COMMIT.json',dict(status='VERIFIED',cell_fingerprint=cell['fingerprint'],plan_sha256='p',files=inventory(out)))
            self.assertIsNotNone(verify_cell(root,cell,'p'))
            (out/'result.json').write_text('{}')
            with self.assertRaises(ContractError):verify_cell(root,cell,'p')

    def test_plan_drift_rejected(self):
        with fixture_directory() as d:
            out=Path(d)/'cells/fixture';out.mkdir(parents=True)
            publish(out/'result.json',dict(cell_id='FIXTURE',status='VERIFIED'))
            publish(out/'COMMIT.json',dict(status='VERIFIED',cell_fingerprint='fixture',plan_sha256='old',files=inventory(out)))
            with self.assertRaises(ContractError):verify_cell(Path(d),mock_cell(),'new')

    def test_incomplete_publication_never_skipped(self):
        with fixture_directory() as d:
            (Path(d)/'cells/fixture').mkdir(parents=True)
            with self.assertRaises(ContractError):verify_cell(Path(d),mock_cell(),'p')

    def test_run_resume_exactly_once_with_mock_episode(self):
        result=dict(status='VERIFIED',cell_id='FIXTURE',policy_records=[],trace={})
        with fixture_directory() as d,patch('diagnostic_episode.run_cell_episode',return_value=result) as episode,patch('closure_runtime.load_scenario',return_value={'document':{}}),patch('closure_runtime.resource_check',return_value={}):
            root=Path(d);plan=mock_plan()
            first=run_campaign(root,plan,None,lambda:None)
            second=run_campaign(root,plan,None,lambda:None)
            self.assertEqual(first['verified'],1);self.assertEqual(second['pending'],0)
            self.assertEqual(episode.call_count,1)

    def test_failure_preserved_and_not_auto_retried(self):
        with fixture_directory() as d,patch('diagnostic_episode.run_cell_episode',side_effect=ValueError('deliberate fixture failure')) as episode,patch('closure_runtime.load_scenario',return_value={'document':{}}),patch('closure_runtime.resource_check',return_value={}):
            root=Path(d);plan=mock_plan()
            with self.assertRaises(ValueError):run_campaign(root,plan,None,lambda:None)
            with self.assertRaises(ContractError):run_campaign(root,plan,None,lambda:None)
            self.assertEqual(episode.call_count,1)
            self.assertEqual(len(list(root.glob('attempts/*/*/FAILED.json'))),1)

    def test_no_episode_when_preflight_fails(self):
        with fixture_directory() as d,patch('diagnostic_episode.run_cell_episode') as episode:
            with self.assertRaises(ContractError):
                run_campaign(Path(d),mock_plan(),None,lambda:(_ for _ in ()).throw(ContractError('source drift')))
            episode.assert_not_called()

    def test_scenario_cache_tampering(self):
        cell=mock_cell()
        with fixture_directory() as d:
            root=Path(d);target=root/'scenarios'/scenario_key(cell)/'scenario.json'
            publish(target,{'document':{}});publish(target.with_suffix('.sha256.json'),dict(sha256='bad',key=scenario_key(cell)))
            with self.assertRaises(ContractError):load_scenario(root,None,cell)

    def test_gzip_deterministic(self):
        with fixture_directory() as d:
            a=Path(d)/'a.gz';b=Path(d)/'b.gz';gzip_json(a,{'a':1});gzip_json(b,{'a':1})
            self.assertEqual(a.read_bytes(),b.read_bytes())

    def test_generated_unsupported_input_is_retained_never_success(self):
        error=ContractError('unexpected support block');error.generated_input={'document':{'fixture':True}}
        with fixture_directory() as d,patch('closure_matrix.physical_document',side_effect=error):
            root=Path(d)
            with self.assertRaises(ContractError):load_scenario(root,None,mock_cell())
            self.assertTrue((root/'scenarios'/scenario_key(mock_cell())/'UNSUPPORTED_GENERATED_INPUT.json').exists())
            self.assertFalse((root/'cells').exists())

    def test_real_diagnostic_lineage_rejects_changed_scenario(self):
        cell=dict(mock_cell(),role='DIAGNOSTIC_13M_NOT_PRIMARY_TEST')
        with fixture_directory() as d:
            root=Path(d);folder=root/'cells/fixture';folder.mkdir(parents=True)
            source={'document':{'frozen':'fixture'}};key=scenario_key(cell)
            path=root/'scenarios'/key/'scenario.json';publish(path,source)
            publish(path.with_suffix('.sha256.json'),dict(key=key,sha256=sha(path)))
            result=dict(status='VERIFIED',cell_id='FIXTURE',cell_fingerprint='fixture',plan_sha256='p',
                scenario_cache_key=key,source_input_sha256=s.digest(source),physical_document_sha256=s.digest(source['document']),trace={})
            publish(folder/'result.json',result)
            publish(folder/'COMMIT.json',dict(status='VERIFIED',cell_fingerprint='fixture',plan_sha256='p',files=inventory(folder)))
            self.assertIsNotNone(verify_cell(root,cell,'p'))
            path.write_text('{"document":{"changed":true}}')
            with self.assertRaises(ContractError):verify_cell(root,cell,'p')

    def test_status_hashes_large_plan_once_not_per_cell(self):
        with fixture_directory() as d,patch.object(s,'digest',wraps=s.digest) as digest:
            campaign_status(Path(d),mock_plan())
            self.assertEqual(digest.call_count,2)  # plan and completed-commit inventory

    def test_safe_interrupt_commits_current_then_stops_next(self):
        import signal
        plan=mock_plan();second=dict(mock_cell(),cell_id='SECOND',fingerprint='second')
        plan['matrix']['cells'].append(second);plan['matrix']['counts'].update(requirements=2,unique=2,runnable=2)
        def finish_episode(*_):
            signal.getsignal(signal.SIGINT)(signal.SIGINT,None)
            return dict(status='VERIFIED',cell_id='FIXTURE',policy_records=[],trace={})
        with fixture_directory() as d,patch('diagnostic_episode.run_cell_episode',side_effect=finish_episode) as episode,patch('closure_runtime.load_scenario',return_value={'document':{}}),patch('closure_runtime.resource_check',return_value={}):
            state=run_campaign(Path(d),plan,None,lambda:None)
            self.assertEqual(state['verified'],1);self.assertEqual(state['pending'],1);self.assertEqual(episode.call_count,1)

    def test_canonical_new_trace_checks_decompressed_bytes(self):
        import hashlib
        with fixture_directory() as d:
            root=Path(d);folder=root/'cells/fixture';folder.mkdir(parents=True)
            (folder/'trace').mkdir()
            gzip_json(folder/'trace/x.json.gz',{'x':1})
            publish(folder/'result.json',dict(status='VERIFIED',cell_id='FIXTURE',
                trace={'x.json':dict(canonical_sha256='wrong',canonical_bytes=0)}))
            publish(folder/'COMMIT.json',dict(status='VERIFIED',cell_fingerprint='fixture',plan_sha256='p',files=inventory(folder)))
            self.assertIsNotNone(verify_cell(root,mock_cell(),'p'))
            with self.assertRaises(ContractError):verify_cell(root,mock_cell(),'p',canonical=True)

    def test_none_records_realistic_same_state_a2_comparison(self):
        from diagnostic_episode import run_cell_episode
        with fixture_directory() as d:
            result=run_cell_episode(doc_ready(),dict(mock_cell(),arm='B2',model_variant='none'),Path(d)/'trace')
            self.assertTrue(all('same_state_A2' in r for r in result['policy_records']))
            self.assertTrue(all('same_state_A2' in r for r in result['diagnostics']['decisions']))

    def test_tiny_full_episode_ledger_and_policy_variants(self):
        from diagnostic_episode import run_cell_episode
        for arm in ('A1','A2','B2'):
            with self.subTest(arm=arm),fixture_directory() as d:
                cell=dict(mock_cell(),arm=arm)
                r=run_cell_episode(doc_ready(),cell,Path(d)/'trace')
                self.assertEqual(r['status'],'VERIFIED');self.assertEqual(r['cargo']['U_not_loaded'],0)
                self.assertEqual(r['diagnostics']['ledger_N_out'],10)
                self.assertEqual(r['diagnostics']['ledger_U'],r['cargo']['U_not_loaded'])
                self.assertEqual(len(r['trace']),7)


class ClosureLifecycleTests(unittest.TestCase):
    def test_completed_diagnostics_nested_seeds_aliases_and_figures(self):
        from closure_reporting import plots
        rows=[];results={}
        identities=[('A1',None,10.),('A2',None,8.),('B2',None,6.),('A3',11,5.),('A3',23,8.),('A3',37,11.)]
        for arm,seed,ta in identities:
            c=dict(mock_cell(),cell_id=f'{arm}{seed}',fingerprint=f'{arm}{seed}',arm=arm,training_seed=seed,
                   requirement_kind='physical_sensitivity',alias_of=None,reason=None)
            rows.append(c)
            results[c['cell_id']]=dict(status='VERIFIED',cell_id=c['cell_id'],physical_document_sha256='same',
                terminal_status='TRUNCATED_DRAIN_LIMIT' if seed==23 else 'COMPLETED',TA=ta*2,TA_per_vessel=ta,
                cargo=dict(N_out=10,U_not_loaded=1,R_loss_rate=.1),
                compute=dict(wall_seconds=float({11:1,23:2,37:3}.get(seed,1)),cpu_seconds=1.),decisions=dict(wait_selected=0),
                diagnostics=dict(rollovers=1,decisions=[dict(policy_seconds=1.)]))
        base=next(c for c in rows if c['arm']=='B2')
        alias=dict(base,cell_id='alias',status='ALIAS',requirement_kind='model_coupling',alias_of=base['cell_id'])
        none=dict(base,cell_id='none',fingerprint='none',requirement_kind='model_coupling',model_variant='none')
        rows += [alias,none]
        results['none']=copy.deepcopy(results[base['cell_id']]);results['none']['cell_id']='none'
        results['none']['diagnostics']['decisions']=[dict(policy_seconds=1.,same_state_A2=dict(agrees=False)),dict(policy_seconds=2.,same_state_A2=dict(agrees=True))]
        plan=dict(matrix=dict(cells=rows))
        with fixture_directory() as d,patch('closure_reporting.verify_cell',side_effect=lambda root,c,h:copy.deepcopy(results[c['cell_id']])):
            output=Path(d);data=diagnostic_analysis(output,plan)
            avg=next(g for g in data['groups'] if g['arm']=='A3')
            self.assertEqual(avg['n'],1);self.assertEqual(avg['mean_TA_per_vessel'],8.)
            self.assertEqual(avg['mean_wall_seconds'],2.)
            self.assertEqual(avg['completion_denominator_episodes'],3)
            self.assertEqual(avg['terminal_status_counts']['COMPLETED'],2)
            groups=[g for g in data['groups'] if g['kind']=='model_coupling']
            self.assertEqual({g['variant'] for g in groups},{'both','none'})
            self.assertEqual(next(g for g in groups if g['variant']=='none')['same_state_A2']['disagree'],1)
            self.assertEqual(next(g for g in groups if g['variant']=='both')['source_run_ids'],[base['cell_id']])
            primary=dict(rows=[dict(metric='difference_per_vessel',population='itp_medium',hypothesis='B2-A2',estimate=-2.,lower=-3.,upper=-1.)])
            names=plots(output,primary,data)
            self.assertEqual(set(names),{'post_hoc_primary_intervals','physical_sensitivity','model_coupling','diagnostic_compute_cost'})
            before={p.name:sha(p) for p in (output/'figures').iterdir()}
            plots(output,primary,data)
            self.assertEqual(before,{p.name:sha(p) for p in (output/'figures').iterdir()})

    def test_gate_never_closes_from_good_primary_results_alone(self):
        ctx=dict(gate=dict(RETURN_VERIFY='VERIFIED_FULL_CANONICAL'))
        counts=dict(matrix()['counts'],verified=0,pending=4320,failed=0,verified_aliases=0)
        state=final_gate(ctx,counts,False,True,None)
        self.assertEqual(state['PROJECT_I_FINAL_CLOSED'],'NO')

    def test_gate_requires_actual_all_counts_and_approval(self):
        ctx=dict(gate=dict(RETURN_VERIFY='VERIFIED_FULL_CANONICAL'))
        counts=dict(matrix()['counts'],verified=4320,pending=0,failed=0,verified_aliases=40)
        self.assertEqual(final_gate(ctx,counts,True,True,True)['PROJECT_I_FINAL_CLOSED'],'YES')
        for arg in (0,1,2):
            flags=[True,True,True];flags[arg]=False
            self.assertEqual(final_gate(ctx,counts,*flags)['PROJECT_I_FINAL_CLOSED'],'NO')

    def test_gate_rejects_pseudo_empty_matrix(self):
        ctx=dict(gate=dict(RETURN_VERIFY='VERIFIED_FULL_CANONICAL'))
        counts=dict(runnable=0,unsupported=120,aliases=0,unique=120,verified=0,pending=0,failed=0,verified_aliases=0)
        self.assertEqual(final_gate(ctx,counts,True,True,True)['PROJECT_I_FINAL_CLOSED'],'NO')

    def test_non_run_verbs_never_simulate_even_on_failure(self):
        import final_closure as fc
        for action in ('plan','status','verify','analyze','finalize','approve'):
            with self.subTest(action=action),patch.object(fc,'original_inputs',side_effect=ContractError('fixture source mismatch')),patch('diagnostic_episode.run_cell_episode') as episode:
                self.assertEqual(fc.main([action]),2);episode.assert_not_called()

    def test_actual_cli_help_does_not_simulate(self):
        result=subprocess.run([sys.executable,'-B',str(PROJECT/'step8/final_closure.py'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0);self.assertIn('resume',result.stdout)

    @unittest.skipUnless(os.name=='nt','PowerShell launcher requires Windows')
    def test_actual_powershell_entrypoint_help(self):
        script=PROJECT/'scripts/Complete-ProjectIClosure.ps1'
        result=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-Action','Help','-Interpreter',sys.executable],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('engineering-probe',result.stdout)

    def test_approval_exact_hash_and_provenance_required(self):
        from final_closure import require_approval
        with fixture_directory() as d:
            root=Path(d);packet=dict(plan_sha256='p')
            with self.assertRaises(ContractError):require_approval(root,packet)
            publish(root/'approvals/x.json',dict(packet_sha256='wrong',plan_sha256='p',owner='Fixture',provenance='fixture'))
            with self.assertRaises(ContractError):require_approval(root,packet)

    @unittest.skipUnless(os.name=='nt','PowerShell pipeline contract requires Windows')
    def test_actual_manual_launcher_sequence_and_stop_on_resume_exit3(self):
        # Actual Windows entrypoint; a private CLI shim records orchestration.
        # It cannot import the simulator or generate scientific episodes.
        for resume_code in (0,3):
            with self.subTest(resume_code=resume_code),fixture_directory() as d:
                root=Path(d);log=root/'calls.txt';helper=root/'shim.py';shim=root/'python-shim.cmd'
                helper.write_text('import sys\nfrom pathlib import Path\n'+
                    "action='deps' if sys.argv[1]=='-c' else sys.argv[3]\n"+
                    f"with Path({str(log)!r}).open('a',encoding='utf-8') as f:f.write(action+'\\n')\n"+
                    f"sys.exit({resume_code} if action=='resume' else 0)\n",encoding='utf-8')
                shim.write_text(f'@"{sys.executable}" "{helper}" %*\n',encoding='utf-8')
                result=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',
                    str(PROJECT/'scripts/Complete-ProjectIClosure.ps1'),'-Action','Run',
                    '-Interpreter',str(shim),'-AcceptScientificPacket','a'*64],capture_output=True,text=True)
                calls=log.read_text(encoding='utf-8').splitlines()
                self.assertEqual(calls,['deps','approve','resume','verify','finalize'] if resume_code==0 else ['deps','approve','resume'])
                self.assertEqual(result.returncode,0 if resume_code==0 else 1,result.stderr)

    def test_non_run_verbs_never_simulate_after_successful_intake(self):
        import final_closure as fc
        for action in ('plan','status','verify','analyze','finalize'):
            with self.subTest(action=action),fixture_directory() as d:
                root=Path(d);plan=mock_plan();packet=dict(plan_sha256=s.digest(plan),code_sha256=s.digest({}))
                publish(root/'packet.json',packet)
                with patch.object(fc,'original_inputs',return_value={}),patch.object(fc,'predecessor',return_value={}),patch.object(fc,'plan_for',return_value=plan),patch.object(fc,'install_plan',return_value=root),patch.object(fc,'packet_path',return_value=root/'packet.json'),patch.object(fc,'code_inventory',return_value={}),patch.object(fc,'bounded_preflight'),patch('closure_reporting.release',return_value=dict(PROJECT_I_FINAL_CLOSED='NO')),patch('diagnostic_episode.run_cell_episode') as episode:
                    fc.main([action]);episode.assert_not_called()

    def test_portable_existing_return_receipt_is_authentic(self):
        import zipfile,hashlib
        from final_closure import DEFAULT_BUNDLE
        filename='09499de0840d7bdc7c152ee0bdf543c95716c86cf97b7273f418e1209b1dca3f.json'
        with zipfile.ZipFile(PROJECT/'step8/reference/closure_reference_v2.zip') as z:
            raw=z.read('verified_step7_return/'+filename)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'e903d0dc2f61c686fcdd4942dcfc813a6c05a5ba05f78b5e16dd2736b127e0cc')

    def test_git_preserves_portable_evidence_bytes(self):
        targets=['integrated-terminal-pilot/docs/step8/final_closure/fixture/focused_tests.log',
                 'integrated-terminal-pilot/docs/step8/final_closure/fixture/owner_amendment_packet.json',
                 'integrated-terminal-pilot/step8/reference/closure_reference_v2.zip']
        result=subprocess.run(['git','check-attr','text','--',*targets],cwd=REPO,capture_output=True,text=True,check=True)
        self.assertTrue(all(line.endswith(': text: unset') for line in result.stdout.splitlines()))

    def test_portable_predecessor_used_without_old_analysis_folder(self):
        import final_closure as fc
        with fixture_directory() as d,patch.object(fc,'PREVIOUS',Path(d)/'absent'):
            self.assertEqual(fc.predecessor()['provenance']['manifest_sha256'],fc.EXPECTED_MANIFEST)

    def test_runtime_os_metadata_not_an_environment_mismatch(self):
        from final_closure import execution_runtime
        actual=dict(python='3.13.2',platform='new windows build')
        ctx=dict(lock=dict(packages=dict(python='3.13.2',platform='old windows build')))
        with patch('integrated_terminal_pilot.benchmark.development.package_versions',return_value=actual):
            execution_runtime(ctx)


if __name__=='__main__':unittest.main()
