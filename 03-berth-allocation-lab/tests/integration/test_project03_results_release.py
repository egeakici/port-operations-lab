"""Frozen Step 12 records to an immutable, verifiable Step 13 release."""

import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from berth_allocation_lab.benchmark.config import BenchmarkError
from berth_allocation_lab.benchmark.inputs import sha256_file
from berth_allocation_lab.results.ingest import verify_sources
from berth_allocation_lab.results.release import build_release, dry_run, verify_release
from berth_allocation_lab.results.reporting import EXPORTS, FIGURE_SOURCES, verify_tables

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def release_area():
    base = (ROOT / "experiments" / f"_step13_pytest_{uuid4().hex}").resolve()
    assert base.is_relative_to(ROOT.resolve()) and not base.exists()
    try:
        yield base
    finally:
        if base.exists():
            assert base.is_relative_to(ROOT.resolve()) and base.name.startswith("_step13_pytest_")
            shutil.rmtree(base)


def test_release_build_verify_immutability_and_determinism(release_area):
    source_before = verify_sources(ROOT).artifact_hashes.copy()
    assert dry_run(ROOT)["expected_row_counts"]["scenarios"] == 500
    assert not release_area.exists()
    first = build_release(ROOT, "integration_a", output_root=release_area)
    second = build_release(ROOT, "integration_b", output_root=release_area)
    assert verify_release(first)["status"] == "passed"
    assert verify_release(second)["status"] == "passed"
    assert sha256_file(first / "project03_results.sqlite") == sha256_file(second / "project03_results.sqlite")
    for name in [*EXPORTS, "limitations.csv"]:
        assert sha256_file(first / "tables" / name) == sha256_file(second / "tables" / name)
    with closing(sqlite3.connect(first / "project03_results.sqlite")) as connection:
        verify_tables(connection, first / "tables")
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["figure_source_tables"]) == set(FIGURE_SOURCES)
    assert manifest["training_performed"] is False
    assert manifest["test_inference_performed"] is False
    assert manifest["new_diagnostic_scenarios_generated"] is False
    assert all((first / "figures" / name).stat().st_size > 1000 for name in FIGURE_SOURCES)
    assert verify_sources(ROOT).artifact_hashes == source_before
    with pytest.raises(BenchmarkError, match="never overwrite"):
        build_release(ROOT, "integration_a", output_root=release_area)
    (second / "tables/dynamic_summary.csv").write_text("altered", encoding="utf-8")
    with pytest.raises(BenchmarkError, match="hash mismatch"):
        verify_release(second)
