"""Owner-run scope/isolation tests. All filesystem fixtures are synthetic."""
import copy
from types import SimpleNamespace

import pytest

from integrated_terminal_pilot.benchmark import step7 as s
from integrated_terminal_pilot.benchmark import step7_regression_scope as scope


def test_archive_consumers_are_excluded_but_synthetic_replay_stays_eligible():
    args=scope.pytest_arguments()
    for name in ('test_replay_records.py','test_replay_frontend.py'):
        assert '--ignore=tests/integration/'+name in args
        assert 'held-out' in scope.UNSAFE_MODULES['tests/integration/'+name]
    assert 'tests/unit/test_replay.py' in scope.SAFE_MODULES
    assert '--ignore=tests/unit/test_replay.py' not in args
    audit=scope.audit(s.REPO/'03-berth-allocation-lab')
    assert audit['results_read'] is False
    assert len(audit['classified_test_source_sha256']) == 44


def classified_fixture(root):
    for name in set(scope.SAFE_MODULES) | set(scope.UNSAFE_MODULES) | set(scope.MIXED):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        names=scope.MIXED.get(name,['test_fixture'])
        path.write_text('\n'.join('def '+node+'(): pass' for node in names),encoding='utf-8')


def test_unclassified_module_blocks_before_collection_or_import(tmp_path):
    classified_fixture(tmp_path)
    (tmp_path/'tests/unit/test_new.py').write_text("raise RuntimeError('must never import')",encoding='utf-8')
    with pytest.raises(ValueError,match='unclassified=.*test_new.py'):
        scope.audit(tmp_path)


def test_stale_mixed_node_exclusion_blocks(tmp_path):
    classified_fixture(tmp_path)
    path=tmp_path/'tests/integration/test_static_ppo_v2_integration.py'
    path.write_text('def renamed_training_test(): pass',encoding='utf-8')
    with pytest.raises(ValueError,match='no longer exists'):
        scope.audit(tmp_path)


@pytest.mark.parametrize('tamper',[False,True])
def test_regression_gate_binds_eligible_scope_receipt(monkeypatch,tamper):
    receipt={'fixture':'source-only audit'}
    monkeypatch.setattr(scope,'audit',lambda root:receipt)
    base=dict(exit_code=0,failed=0,errors=0,passed=1,skipped=0,deselected=0,
              stdout='fixture.stdout',stdout_sha256='fixture',junit='fixture.xml',junit_sha256='fixture')
    upstream=dict(base,scope_audit_sha256=s.digest(receipt),excluded_modules=copy.deepcopy(scope.UNSAFE_MODULES),
                  excluded_nodes=copy.deepcopy(scope.MIXED))
    if tamper:upstream['excluded_modules'].pop('tests/integration/test_replay_records.py')
    evidence=dict(implementation_digest='impl',parameter_values_sha256='parameters',
                  project_i_full=dict(base,slow_passed=9),project03_eligible_fast=upstream)
    monkeypatch.setattr(s,'unseal',lambda p:evidence)
    monkeypatch.setattr(s,'implementation_digest',lambda:'impl')
    monkeypatch.setattr(s,'load_generator_config',lambda:SimpleNamespace(parameters_fingerprint='parameters'))
    monkeypatch.setattr(s,'file_hash',lambda p:'fixture')
    if tamper:
        with pytest.raises(s.CampaignError,match='eligibility receipt'):s.verify_regressions('fixture')
    else:assert s.verify_regressions('fixture')==evidence


def test_prelock_failure_is_linked_without_changing_or_reusing_it(tmp_path,monkeypatch):
    from integrated_terminal_pilot.benchmark.step7_remote import retain_prelock_failure
    monkeypatch.setattr(s,'PROJECT_ROOT',tmp_path)
    old=tmp_path/'experiments/step7_remote/step7_cpu3132_v1'
    s.seal(old/'pipeline/FAILED.json',{'stage':'project03-fast','reason':'synthetic fixture'})
    result=old/'regressions/project-i-full_fixture/result.json'
    s.seal(result,{'passed':554,'fixture_only':True})
    s.seal(old/'regressions/project03-fast_fixture/result.json',dict(exit_code=1,collected=426,
        passed=420,failed=6,errors=0,failure_details=[{'classname':'tests.integration.test_replay_frontend'}]+
        [{'classname':'tests.integration.test_replay_records'} for _ in range(5)]))
    before={p.relative_to(old).as_posix():p.read_bytes() for p in old.rglob('*') if p.is_file()}
    new=tmp_path/'experiments/step7_remote/step7_cpu3132_v2'
    retain_prelock_failure(new);retain_prelock_failure(new)
    assert before=={p.relative_to(old).as_posix():p.read_bytes() for p in old.rglob('*') if p.is_file()}
    link=s.unseal(new/'prelock_repair/prior_step7_cpu3132_v1_link.json')
    assert any(row['path'].endswith('result.json') for row in link['files'])
    assert not (new/'regressions').exists()  # Archived PASS is not current-source authorization.


def test_prior_scientific_lock_blocks_fresh_repair_bundle(tmp_path,monkeypatch):
    from integrated_terminal_pilot.benchmark.step7_remote import retain_prelock_failure
    monkeypatch.setattr(s,'PROJECT_ROOT',tmp_path)
    old=tmp_path/'experiments/step7_remote/step7_cpu3132_v1'
    old.mkdir(parents=True);(old/'protocol_lock_v1.json').write_text('NOT TO BE OPENED')
    monkeypatch.setattr(s,'file_hash',lambda p:pytest.fail('must stop before opening old scientific files'))
    with pytest.raises(s.CampaignError,match='scientific lock'):
        retain_prelock_failure(tmp_path/'experiments/step7_remote/step7_cpu3132_v2')
