import json
import pytest

from integrated_terminal_pilot.benchmark import step6_closure as ctl
from integrated_terminal_pilot.benchmark.closure_gate import run_gate


@pytest.fixture(scope='module')
def gate():
    return run_gate()


def test_independent_fixed_service_gate_and_negative_controls(gate):
    assert gate['gate'] == 'PASS_WITH_SCOPED_CLAIMS'
    assert (gate['full'], gate['prefix'], gate['noneligible'], gate['eligible_decisions']) == (12, 0, 5, 20)
    assert all(all(d['checks'].values()) for f in gate['fixtures'] for d in f['decisions'] if d['result'] == 'PASS')


@pytest.mark.parametrize('moves', (2, 4))
def test_hand_derived_oracle_is_not_a_copy_of_either_rollout(gate, moves):
    # One vessel: no waiting, duration=50+moves/2, both end positions tied.
    single = next(f for f in gate['fixtures'] if f['fixture_id'] == f'single_m{moves}')['decisions'][0]
    assert len(single['table']) == 2
    assert {r['p03_future_wait'] for r in single['table']} == {0}
    assert {r['b2t_turnaround'] for r in single['table']} == {50 + moves / 2}
    # Two 700m vessels cannot coexist on 1200m quay: one waits exactly one service.
    two = next(f for f in gate['fixtures'] if f['fixture_id'] == f'competing_m{moves}')['decisions'][0]
    assert {r['p03_future_wait'] for r in two['table']} == {50 + moves / 2}
    assert {r['b2t_turnaround'] for r in two['table']} == {3 * (50 + moves / 2)}


def test_censoring_and_distance_break_the_constant(gate):
    for name in ('censoring', 'distance_dependency'):
        d = next(f for f in gate['fixtures'] if f['fixture_id'] == name)['decisions'][0]
        assert d['result'] == 'NOT_EXACT_ELIGIBLE'
        assert not d['checks']['constant']


@pytest.mark.parametrize('mode', ('--run', '--resume'))
def test_no_approval_cannot_execute(mode, tmp_path, monkeypatch):
    monkeypatch.setattr(ctl, 'APPROVAL', tmp_path / 'absent.json')
    monkeypatch.setattr(ctl, 'run_plan', lambda *a, **k: pytest.fail('execution reached'))
    assert ctl.main([mode]) == 2


def test_incomplete_or_wrong_plan_approval_rejected(tmp_path):
    path = tmp_path / 'approval.json'
    path.write_text(json.dumps({'approval_status': 'APPROVED'}))
    with pytest.raises(ctl.ClosureError, match='exact plan'):
        ctl.require_approval({'items': []}, path)


def test_immutable_atomic_idempotent_publish(tmp_path):
    path = tmp_path / 'result.json'
    ctl.publish(path, {'x': 1})
    before = path.read_bytes()
    ctl.publish(path, {'x': 1})
    with pytest.raises(ctl.ClosureError, match='mismatch'):
        ctl.publish(path, {'x': 2})
    assert path.read_bytes() == before
    assert list(tmp_path.glob('*.tmp')) == []


def test_failed_atomic_install_leaves_no_published_result(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError('controlled interruption')
    monkeypatch.setattr(ctl.os, 'link', fail)
    with pytest.raises(OSError):
        ctl.publish(tmp_path / 'result.json', {'x': 1})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('seed', (11_000_000, 12_000_000))
def test_forbidden_seed_rejected_before_source_access(seed, monkeypatch):
    from integrated_terminal_pilot.benchmark import pre_step6
    monkeypatch.setattr(pre_step6, '_source_rows', lambda: pytest.fail('forbidden source access'))
    with pytest.raises(ctl.step6.Step6Error, match='outside the development'):
        ctl.step6._scenario_row('itp_heavy', seed)


def test_pending_records_and_formal_lock_unchanged():
    s = ctl.approval_state()
    assert s['proposed_pending_review'] == 28
    assert not s['formal_step7_lock_present'] and not s['validation_authorized']


def test_plan_hash_tampering_rejected(tmp_path):
    path = tmp_path / 'plan.json'
    ctl.publish(path, {'split': 'validation'})
    ctl.publish(path.with_suffix('.sha256.json'), {'canonical_sha256': 'wrong'})
    with pytest.raises(ctl.ClosureError, match='hash mismatch'):
        ctl.load_plan(path)


@pytest.mark.parametrize('arm', ('A2', 'B2', 'B2-T'))
def test_optional_observation_capture_preserves_actions_and_trace(arm):
    from integrated_terminal_pilot.benchmark.runner import run_arm
    from tests.step6_support import leakage_doc
    kwargs = {'arm_id': arm, 'research_profile': ctl.step6.PRIMARY}
    plain = run_arm(leakage_doc(), **kwargs)
    captured = run_arm(leakage_doc(), **kwargs, capture_decision_snapshots=True, keep_kernel=True)
    assert plain['digests']['trace_sha256'] == captured['digests']['trace_sha256']
    assert len(captured['closure_observations']) == captured['decisions']['berth_decisions']
    assert 'closure_observations' not in plain
    assert all(v['projection'] is None for v in captured['closure_observations'])
    import base64
    import pickle
    from integrated_terminal_pilot.simulator.observations import BerthView
    from integrated_terminal_pilot.benchmark.coordination_view import CoordinationView
    inputs = [pickle.loads(base64.b64decode(v['policy_observation_pickle_base64']))
              for v in captured['closure_observations']]
    assert all(isinstance(v, BerthView if arm == 'A2' else CoordinationView) for v in inputs)
    if arm != 'A2':
        assert all(v.projection.catalog.identity is None and v.projection.catalog.fingerprints is None
                   and v.projection.fork().state.ledger is None and v.projection.fork().state.event_log is None
                   for v in inputs)
        assert [v.digest for v in inputs] == [r['evaluation']['view_digest'] for r in captured['_policy'].records]
    if arm != 'A2':
        assert plain['step6']['prediction_digests'] == captured['step6']['prediction_digests']


@pytest.mark.parametrize('status', ('COMPLETED', 'FAILED'))
def test_controller_resume_is_idempotent_and_failure_stops(status, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from integrated_terminal_pilot.benchmark import runner
    item = {'scenario_id': 'fixture', 'family': 'itp_heavy', 'seed': 10000000, 'arm': 'A2'}
    plan = {'items': [item], 'scenarios': [{'scenario_id': 'fixture', 'file_sha256': 'source',
            'comparison_fingerprint': 'paired', 'N_out': 0, 'T_end_min': 100}],
            'resources': {'rss_admission_limit_mb': 4096}}
    monkeypatch.setattr(ctl, 'load_plan', lambda p: plan)
    monkeypatch.setattr(ctl, 'require_approval', lambda p: {'max_wall_minutes': 10})
    monkeypatch.setattr(ctl.step6, '_load', lambda s: {})
    calls = []
    def execute(*a, **k):
        calls.append(1)
        return {'status': status, 'audits': {'ok': status == 'COMPLETED'}, 'comparison_fingerprint': 'paired',
                'outbound_obligations': {'N_out': 0}, 'T_end_min': 100,
                'scenario': {'scenario_id': 'fixture'}, 'arm': {'arm_id': 'A2'},
                '_kernel': SimpleNamespace(state=SimpleNamespace(ledger=[], event_log=[], block_episodes=[])),
                '_policy': SimpleNamespace(records=[])}
    monkeypatch.setattr(runner, 'run_arm', execute)
    path = tmp_path / 'plan.json'
    if status == 'FAILED':
        with pytest.raises(ctl.ClosureError, match='failed'):
            ctl.run_plan(path)
        with pytest.raises(ctl.ClosureError, match='previous failed'):
            ctl.run_plan(path)
    else:
        ctl.run_plan(path)
        ctl.run_plan(path)
    assert calls == [1]
    stored = ctl.item_path(tmp_path, item)
    stored.write_text(stored.read_text() + ' ')
    with pytest.raises(ctl.ClosureError, match='checksum'):
        ctl.run_plan(path)
    assert calls == [1]


def test_controller_refuses_stale_worker_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(ctl, 'load_plan', lambda p: {})
    monkeypatch.setattr(ctl, 'require_approval', lambda p: {})
    (tmp_path / 'worker.lock').write_text('controlled interruption')
    with pytest.raises(ctl.ClosureError, match='worker lock'):
        ctl.run_plan(tmp_path / 'plan.json')


def test_progress_has_no_invented_eta_and_marks_interruption(tmp_path, monkeypatch):
    monkeypatch.setattr(ctl, 'APPROVAL', tmp_path / 'absent.json')
    item = {'family': 'itp_heavy', 'seed': 10000000, 'arm': 'A2'}
    plan = {'items': [item]}
    report = ctl.campaign_progress(tmp_path, plan)
    assert report['blocked'] == 1 and report['done'] == 0
    assert report['estimated_remaining_seconds'] is None
    target = ctl.item_path(tmp_path, item).with_suffix('.started.json')
    ctl.publish(target, {'controlled': 'interruption'})
    report = ctl.campaign_progress(tmp_path, plan, recent_seconds=[10, 20])
    assert report['failed_or_interrupted'] == 1 and report['blocked'] == 0
    assert report['estimated_remaining_seconds'] == 15


def test_approval_requires_the_actual_reviewed_gate_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(ctl, 'ROOT', tmp_path)
    plan = {'fixture': 'approval linkage only'}
    gate = {'contract_defects': 0, 'gate': 'PASS_WITH_SCOPED_CLAIMS'}
    sha = ctl.digest(gate)
    a = {'plan_sha256': ctl.digest(plan), 'decisions': ctl.DECISIONS,
         'approval_status': 'APPROVED', 'owner_response_verbatim': 'TEST FIXTURE ONLY',
         'approval_date': 'TEST FIXTURE ONLY',
         'approval_source': 'explicit project-owner approval in this Step 6 Closure conversation',
         'gate_review': gate['gate'], 'degenerate_gate_sha256': sha,
         'workers': 1, 'max_wall_minutes': 1}
    path = tmp_path / 'fixture_approval.json'
    path.write_text(json.dumps(a))
    with pytest.raises(ctl.ClosureError, match='artifact missing'):
        ctl.require_approval(plan, path)
    artifact = tmp_path / 'gates' / (sha + '.json')
    ctl.publish(artifact, gate)
    assert ctl.require_approval(plan, path) == a
    artifact.write_text(json.dumps(dict(gate, contract_defects=1)))
    with pytest.raises(ctl.ClosureError, match='does not match'):
        ctl.require_approval(plan, path)


@pytest.mark.parametrize('arm', ('A2', 'B2-T', 'B2'))
def test_controller_archives_real_fixture_evidence_without_a_development_campaign(arm, tmp_path, monkeypatch):
    from integrated_terminal_pilot.benchmark import runner
    from tests.step6_support import leakage_doc
    doc = leakage_doc()
    baseline = runner.run_arm(doc, arm_id=arm, research_profile=ctl.step6.PRIMARY)
    item = {'scenario_id': baseline['scenario']['scenario_id'], 'family': baseline['scenario']['family'],
            'seed': baseline['scenario']['scenario_seed'], 'arm': arm}
    plan = {'items': [item], 'scenarios': [{'scenario_id': item['scenario_id'], 'file_sha256': 'TEST_FIXTURE_ONLY',
             'comparison_fingerprint': baseline['comparison_fingerprint'],
             'N_out': baseline['outbound_obligations']['N_out'], 'T_end_min': baseline['T_end_min']}],
            'resources': {'rss_admission_limit_mb': 4096}}
    monkeypatch.setattr(ctl, 'load_plan', lambda p: plan)
    monkeypatch.setattr(ctl, 'require_approval', lambda p: {'max_wall_minutes': 1, 'TEST_FIXTURE_ONLY': True})
    monkeypatch.setattr(ctl.step6, '_load', lambda s: doc)
    ctl.run_plan(tmp_path / 'fixture_plan.json')
    record = ctl.verify_record(ctl.item_path(tmp_path, item), plan, item)['record']
    assert record['digests']['trace_sha256'] == baseline['digests']['trace_sha256']
    assert record['closure_ledger'] and record['closure_events']
    assert len(record['closure_observations']) == len(record['closure_decisions'])
    if arm != 'A2':
        import base64
        import pickle
        view = pickle.loads(base64.b64decode(record['closure_observations'][0]['policy_observation_pickle_base64']))
        assert view.digest == record['closure_decisions'][0]['evaluation']['view_digest']
