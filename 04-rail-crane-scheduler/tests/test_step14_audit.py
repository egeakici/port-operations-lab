from pathlib import Path
from dataclasses import replace
import json
import hashlib
import subprocess
import pytest
from test_step02_contracts import fixture
from test_step03_generator import config as generator_config
from test_step10_training import config as training_config
from rail_crane_scheduler.contracts import *
from rail_crane_scheduler.cli import main
from rail_crane_scheduler.research import source_snapshot


def test_preserved_all_protected_sources():
    project=Path(__file__).resolve().parents[1]; repo=project.parent
    baseline=json.loads((project/'docs/development_run/PREFLIGHT.json').read_text(encoding='utf-8'))
    for path,expected in baseline['protected_sha256'].items():
        assert hashlib.sha256((repo/path).read_bytes()).hexdigest()==expected,path
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()==baseline['head']
    assert not subprocess.check_output(['git','diff','--cached','--name-only'],cwd=repo,text=True).strip()


def test_cli_plan_status_and_bounded_fixture_run(tmp_path,capsys):
    problem=tmp_path/'problem.json'; problem.write_text(fixture().to_json(),encoding='utf-8')
    config=tmp_path/'generator.json'; config.write_text(generator_config().to_json(),encoding='utf-8')
    assert main(['generator','--config',str(config),'--mode','validate'])==0
    assert main(['benchmark','--mode','plan'])==0
    assert main(['benchmark','--mode','validate','--problem',str(problem)])==0
    out=tmp_path/'development'
    assert main(['benchmark','--mode','run-development-small','--problem',str(problem),'--output',str(out)])==0
    assert (out/'summary.csv').exists() and (out/'manifest.json').exists()
    assert main(['replay','--mode','render','--problem',str(problem),'--schedule',str(out/'ordered_sweep_v1.json'),'--output',str(tmp_path/'plot.png')])==0
    assert (tmp_path/'plot.png').read_bytes().startswith(b'\x89PNG')
    assert main(['solver','--mode','check'])==0
    assert main(['training','--mode','check'])==0
    assert main(['evaluation','--mode','status'])==0
    assert main(['evaluation','--mode','render-existing'])==0
    c=tmp_path/'training.json'; c.write_text(json.dumps({'training_config':training_config().to_dict(),'train_inputs':[],'validation_inputs':[],'source_sha256':{}}),encoding='utf-8')
    assert main(['training','--mode','plan','--config',str(c)])==0
    assert main(['training','--mode','train','--config',str(c),'--output',str(tmp_path/'forbidden')])==2
    assert not (tmp_path/'forbidden').exists()


def test_primary_execution_is_not_unlocked_by_metadata():
    p=fixture(); p=replace(p,metadata=replace(p.metadata,origin='PROPOSED_SYNTHETIC',role='train'))
    with pytest.raises(ContractError): p.require_fixture_execution()
    with pytest.raises(ContractError): p.require_fixture_execution(ExecutionPermit('TEST_ONLY',('wrong_hash',),('train',)))
    # Permission wiring test only, not an actual owner approval artifact.
    p.require_fixture_execution(ExecutionPermit('TEST_ONLY_NOT_OWNER_APPROVAL',(p.fingerprint,),('train',)))


def test_numeric_extremes_and_failure_status():
    with pytest.raises(ContractError): replace(fixture().vessel,length_m=10**500)
    with pytest.raises(ContractError): replace(fixture().tasks[0],workload_moves=2**54)
    from rail_crane_scheduler.evaluation import certified_gap
    with pytest.raises(ContractError): certified_gap({}, {'solver_status':'FEASIBLE'})
