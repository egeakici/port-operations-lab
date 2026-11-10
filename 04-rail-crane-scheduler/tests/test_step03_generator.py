from dataclasses import replace
import pytest
from test_step02_contracts import fixture
from rail_crane_scheduler.scenarios import *


def config():
    return GeneratorConfig(GENERATOR_VERSION, fixture(), 4, 1, 20, 0.2, 0, 0, 0, 'DISCHARGE')


def test_determinism_streams_and_seed():
    c = config(); a = generate(c); b = generate(c)
    assert a.to_json() == b.to_json()
    changed = generate(replace(c, workload_nonce=5))
    assert changed.bays == a.bays
    assert [t.bay_id for t in changed.tasks] == [t.bay_id for t in a.tasks]
    assert [t.workload_moves for t in changed.tasks] != [t.workload_moves for t in a.tasks]
    c2 = replace(c, template=replace(c.template, metadata=replace(c.template.metadata, seed=7)))
    assert generate(c2).physical_fingerprint != a.physical_fingerprint
    assert a.declared_workload_moves == sum(t.workload_moves for t in a.tasks)


def test_split_leakage_even_with_changed_metadata():
    p = generate(config())
    with pytest.raises(ContractError): no_leakage([p, replace(p, metadata=replace(p.metadata, role="test", scenario_id="other"))])
    c=replace(config(), template=replace(p, metadata=replace(p.metadata, role="test")))
    with pytest.raises(ContractError): generate(c)


def test_safe_writer(tmp_path):
    manifest = write_fixture(config(), tmp_path / "fixture")
    p = QCSPProblem.from_json((tmp_path / "fixture/problem.json").read_text())
    assert manifest["problem_hash"] == p.fingerprint
    with pytest.raises(ContractError): write_fixture(config(), tmp_path / "fixture")


@pytest.mark.parametrize("kwargs", [{"task_count": -1}, {"min_moves": 0}, {"bay_jitter_m": float("nan")}, {"task_count": 100}])
def test_bad_config(kwargs):
    with pytest.raises(ContractError): replace(config(), **kwargs)


def test_empty_and_reverse_frame():
    c = config(); assert generate(replace(c, task_count=0)).tasks == ()
    p = c.template
    reverse = replace(p, vessel=replace(p.vessel, orientation=-1), bays=tuple(replace(b, verified_global_m=None) for b in p.bays))
    assert generate(replace(c, template=reverse)).vessel.orientation == -1


def test_generator_cli(tmp_path, capsys):
    from rail_crane_scheduler.cli import main
    path = tmp_path / "config.json"; path.write_text(config().to_json(), encoding="utf-8")
    assert main(["generator", "--config", str(path), "--mode", "validate"]) == 0
    assert main(["generator", "--config", str(path), "--mode", "manifest"]) == 0
    assert not (tmp_path / "manifest.json").exists()


def test_manual_generation_cannot_unlock_from_config_alone(tmp_path):
    payload={'configs':[config().to_dict()]}
    with pytest.raises(ContractError): generate_manual(payload,tmp_path/'no_approval','wrong',tmp_path/'not_created')
    assert not (tmp_path/'not_created').exists()
