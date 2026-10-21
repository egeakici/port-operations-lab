"""Owner-run reference-environment and transport coverage checks; no simulations."""
import pytest
from integrated_terminal_pilot.benchmark import step7 as s


def test_environment_drift_is_blocked_before_any_experiment(monkeypatch):
    from integrated_terminal_pilot.benchmark import step7_environment as env
    spec={'python':'3.13.2','packages':{'numpy':'2.2.3','torch':'2.6.0'}}
    monkeypatch.setattr(s,'read_json',lambda p:spec)
    monkeypatch.setattr(env.platform,'python_implementation',lambda:'CPython')
    monkeypatch.setattr(env.platform,'python_version',lambda:'3.11.0')
    monkeypatch.setattr(env.metadata,'version',lambda name:spec['packages'][name])
    with pytest.raises(s.CampaignError,match='numerical reference environment differs'):env.verify()


def test_reference_versions_accept_cpu_build_suffix_but_no_numeric_upgrade(monkeypatch):
    from integrated_terminal_pilot.benchmark import step7_environment as env
    monkeypatch.setattr(s,'read_json',lambda p:{'python':'3.13.2','packages':{'torch':'2.6.0','numpy':'2.2.3'}})
    monkeypatch.setattr(env.platform,'python_implementation',lambda:'CPython')
    monkeypatch.setattr(env.platform,'python_version',lambda:'3.13.2')
    monkeypatch.setattr(env.metadata,'version',lambda name:'2.6.0+cpu' if name=='torch' else '2.2.3')
    assert env.verify()['status']=='PASS'
    monkeypatch.setattr(env.metadata,'version',lambda name:'2.14.1+cpu' if name=='torch' else '2.4.6')
    with pytest.raises(s.CampaignError):env.verify()


def test_remote_transport_covers_the_failed_legacy_manifest_consumers():
    from integrated_terminal_pilot.benchmark.step7_inputs import MANIFEST
    manifest=s.unseal(MANIFEST)
    prefix='restore/integrated-terminal-pilot/experiments/scenarios/development/dev_f5789d8c91_1ee66026/'
    assert prefix+'manifest.json' in manifest['files']
    assert prefix+'manifest.json.sha256' in manifest['files']
    assert manifest['numerical_reference']['python']=='3.13.2'
    original=s.unseal(s.PROJECT_ROOT/'configs/protocol/step7_remote_inputs.json')
    assert all(manifest['files'][name]==meta for name,meta in original['files'].items())
