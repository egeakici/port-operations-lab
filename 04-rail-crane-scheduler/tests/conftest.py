"""Workspace-local temporary paths without pytest's Windows chmod(0700).

The managed Windows sandbox cannot reopen pytest9's restricted temporary dirs.
This preserves actual filesystem tests; it changes location/creation permissions,
not assertions. Unique test directories are retained under ignored experiments.
"""
from pathlib import Path
from uuid import uuid4
import pytest


@pytest.fixture
def tmp_path():
    path = Path(__file__).resolve().parents[1] / "experiments/fixture_tmp" / uuid4().hex
    path.mkdir(parents=True)
    return path
