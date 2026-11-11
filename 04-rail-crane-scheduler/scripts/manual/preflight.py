"""Read-only guards for the manual launcher; never dispatch an experiment.

Kept outside src and the top-level scripts glob so all approved execution bytes
and the canonical profile remain unchanged. This is an additional resource gate,
not a replacement for any existing plan/input/checkpoint approval gate.
"""
import json
from pathlib import Path

from rail_crane_scheduler.campaign import Campaign, read
from rail_crane_scheduler.campaign_cli import approval_text
from rail_crane_scheduler.contracts import require
from rail_crane_scheduler.readiness import PROJECT, file_hash, require_resources, validate_profile
from rail_crane_scheduler.research import manual_gate

APPROVED = 'd06b10d8e04fd0d3655c22267a4ed6cb48b9caa745fec12ac71a8a7bb19dddbc'


def verify():
    c = Campaign()
    require(c.profile_hash == APPROVED, 'PROFILE_CHANGED', 'profile', 'exact owner-approved profile required')
    validate_profile(c.profile)
    packet = read(PROJECT / 'docs/research_readiness/APPROVAL_PACKAGE.json')
    require(packet['canonical_profile_sha256'] == APPROVED and
            file_hash(c.profile_path) == packet['profile_file_sha256'],
            'PROFILE_FILE_CHANGED', 'profile', 'approved raw bytes must match')
    for name, expected in packet['candidate_views_sha256'].items():
        require(Path(name).name == name and file_hash(PROJECT / 'configs/research' / name) == expected,
                'CONFIGURATION_CHANGED', 'config', name)
    manual_gate(c.profile, c.approval, APPROVED)
    receipt = read(c.approval)
    require(receipt.get('owner_declaration') == approval_text(APPROVED) and
            receipt.get('scope') == c.profile['approval_scope'],
            'OWNER_DECLARATION_CHANGED', 'approval', 'exact declaration and scope required')
    info = require_resources(c.profile)
    return {'status': 'MANUAL_EXECUTION_PREFLIGHT_VERIFIED', 'profile_sha256': APPROVED,
            'owner_receipt_status': 'OWNER_APPROVED_ROOT_VERIFIED',
            'approval_path': str(c.approval), 'approval_file_sha256': file_hash(c.approval),
            'device': info['selected_device'], 'python': info['executable'],
            'available_ram_bytes': info['memory_available_bytes'],
            'minimum_available_ram_bytes': c.profile['compute']['minimum_available_ram_bytes'],
            'free_disk_bytes': info['disk_free_bytes'],
            'minimum_free_disk_bytes': c.profile['compute']['minimum_free_disk_bytes'],
            'scientific_commands_started': 0}


def main():
    try:
        print(json.dumps(verify(), allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, ImportError) as exc:
        print(json.dumps({'status': 'REJECTED', 'error': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
