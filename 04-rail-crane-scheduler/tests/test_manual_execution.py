"""Read-only/manual facade tests; no research action or PPO optimizer call."""
import importlib.util
from pathlib import Path
import pytest

from rail_crane_scheduler.contracts import ContractError
from rail_crane_scheduler.readiness import PROJECT, require_resources
from rail_crane_scheduler import readiness


def load_preflight():
    spec = importlib.util.spec_from_file_location('manual_preflight', PROJECT / 'scripts/manual/preflight.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('ram,disk,error', [
    (2147483647, 10737418240, 'INSUFFICIENT_FREE_RAM'),
    (2147483648, 10737418239, 'INSUFFICIENT_FREE_DISK'),
])
def test_resource_thresholds_fail_closed(monkeypatch, ram, disk, error):
    monkeypatch.setattr(readiness, 'environment', lambda: {
        'memory_available_bytes': ram, 'disk_free_bytes': disk})
    profile = {'compute': {'minimum_available_ram_bytes': 2147483648,
                           'minimum_free_disk_bytes': 10737418240}}
    with pytest.raises(ContractError, match=error):
        require_resources(profile)


def test_exact_resource_boundaries_pass(monkeypatch):
    measured = {'memory_available_bytes': 2147483648, 'disk_free_bytes': 10737418240}
    monkeypatch.setattr(readiness, 'environment', lambda: measured)
    assert require_resources({'compute': {'minimum_available_ram_bytes': 2147483648,
                                         'minimum_free_disk_bytes': 10737418240}}) == measured


def test_preflight_wrong_profile_cannot_dispatch(monkeypatch):
    module = load_preflight()
    class WrongProfile:
        profile_hash = '0' * 64
    monkeypatch.setattr(module, 'Campaign', WrongProfile)
    with pytest.raises(ContractError, match='PROFILE_CHANGED'):
        module.verify()


def test_preflight_resources_cannot_dispatch(monkeypatch):
    module = load_preflight()
    class Candidate:
        profile_hash = module.APPROVED
        profile = {'approval_scope': {}, 'compute': {}}
        profile_path = Path('candidate.json')
        approval = Path('approval.json')
    monkeypatch.setattr(module, 'Campaign', Candidate)
    monkeypatch.setattr(module, 'validate_profile', lambda _: None)
    monkeypatch.setattr(module, 'file_hash', lambda _: 'fixture_hash')
    monkeypatch.setattr(module, 'manual_gate', lambda *_: None)
    # In-memory schema fixtures only: no owner receipt is created or overwritten.
    def fixture_read(path):
        if path.name == 'APPROVAL_PACKAGE.json':
            return {'canonical_profile_sha256': module.APPROVED,
                    'profile_file_sha256': 'fixture_hash', 'candidate_views_sha256': {}}
        return {'owner_declaration': module.approval_text(module.APPROVED), 'scope': {}}
    monkeypatch.setattr(module, 'read', fixture_read)
    def insufficient(_):
        raise ContractError('INSUFFICIENT_FREE_RAM', 'compute', 'fixture only')
    monkeypatch.setattr(module, 'require_resources', insufficient)
    with pytest.raises(ContractError, match='INSUFFICIENT_FREE_RAM'):
        module.verify()


def test_launcher_is_additive_and_preserves_approved_tool_bytes():
    from rail_crane_scheduler.readiness import validate_profile
    from rail_crane_scheduler.campaign import Campaign
    c = Campaign()
    assert validate_profile(c.profile)['profile_sha256'] == load_preflight().APPROVED
    launcher = (PROJECT / 'scripts/manual/Project04.ps1').read_text()
    assert launcher.index('$preflightOutput = & $pythonPath') < launcher.index('& $originalInterface @forward')
    assert 'Start-Process' not in launcher and 'Start-Job' not in launcher
    assert "[string]$Action = 'Help'" in launcher
    assert '2>&1' not in launcher
