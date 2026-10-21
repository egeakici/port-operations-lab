"""Owner-run bootstrap integrity checks using tiny synthetic ZIPs; never run Python installers."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

import pytest


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell bootstrap')
HELPER = Path(__file__).resolve().parents[2] / 'scripts/Step7PythonBootstrap.ps1'


def powershell_path(path):
    return "'" + str(path).replace("'", "''") + "'"


def archive_fixture(tmp_path, members):
    archive = tmp_path / 'synthetic.nupkg'
    with zipfile.ZipFile(archive, 'w') as stream:
        for name, contents in members.items():
            stream.writestr(name, contents)
    raw = archive.read_bytes()
    spec = {
        'bytes': len(raw),
        'sha512_base64': base64.b64encode(hashlib.sha512(raw).digest()).decode('ascii'),
        'required_members': ['tools/python.exe'],
    }
    spec_path = tmp_path / 'spec.json'
    spec_path.write_text(json.dumps(spec), encoding='utf-8')
    return archive, spec_path


def expand(archive, spec, destination):
    command = (
        "$ErrorActionPreference='Stop'; "
        f'. {powershell_path(HELPER)}; '
        f'$spec=Get-Content -LiteralPath {powershell_path(spec)} -Raw | ConvertFrom-Json; '
        f'Expand-Step7RuntimeArchive -Archive {powershell_path(archive)} '
        f'-Destination {powershell_path(destination)} -Specification $spec'
    )
    return subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
        capture_output=True, encoding='utf-8', errors='replace', timeout=30,
    )


def test_corrupt_runtime_is_rejected_before_extraction(tmp_path):
    archive, spec = archive_fixture(tmp_path, {'tools/python.exe': b'not executable'})
    raw = archive.read_bytes()
    archive.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])  # Same size, wrong checksum.
    result = expand(archive, spec, tmp_path / 'destination')
    assert result.returncode != 0
    assert 'checksum mismatch' in result.stderr
    assert not (tmp_path / 'destination').exists()
    assert archive.exists()  # Bad evidence is retained.


def test_verified_archive_cannot_escape_destination(tmp_path):
    archive, spec = archive_fixture(tmp_path, {
        'tools/python.exe': b'not executable', '../escaped.txt': b'blocked',
    })
    result = expand(archive, spec, tmp_path / 'destination')
    assert result.returncode != 0
    assert 'Unsafe path' in result.stderr
    assert not (tmp_path / 'escaped.txt').exists()
    assert not (tmp_path / 'destination').exists()


def test_valid_fixture_extracts_but_existing_destination_is_never_overwritten(tmp_path):
    archive, spec = archive_fixture(tmp_path, {'tools/python.exe': b'not executable'})
    destination = tmp_path / 'destination with spaces'
    first = expand(archive, spec, destination)
    assert first.returncode == 0, first.stderr
    retained = destination / 'tools/python.exe'
    retained.write_bytes(b'retained interruption evidence')
    second = expand(archive, spec, destination)
    assert second.returncode != 0
    assert 'already exists' in second.stderr
    assert retained.read_bytes() == b'retained interruption evidence'
