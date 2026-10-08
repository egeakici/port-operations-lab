"""Warehouse contracts without inference or training."""

import re
import sqlite3
from pathlib import Path

import pytest

from berth_allocation_lab.benchmark.config import BenchmarkError
from berth_allocation_lab.results.ingest import ingest, verify_sources
from berth_allocation_lab.results.queries import QUERY_GUIDE, run_documented_queries
from berth_allocation_lab.results.release import _check_database
from berth_allocation_lab.results.schema import create_schema, row_counts

ROOT = Path(__file__).resolve().parents[2]


def test_schema_duplicate_rejection_and_nullable_measurement():
    connection = sqlite3.connect(":memory:")
    create_schema(connection)
    values = ("s", "static", "test", "tiny", "tiny_n6", "fingerprint", None, None)
    connection.execute("INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?)", values)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?)", values)
    assert connection.execute("SELECT vessel_count, future_horizon_min FROM scenarios").fetchone() == (None, None)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?)",
                           ("d", "dynamic", "validation", "tiny", "tiny_n6", "another", 6, 240))


def test_frozen_ingest_coverage_and_reconciliation():
    bundle = verify_sources(ROOT)
    connection = sqlite3.connect(":memory:")
    counts = ingest(connection, bundle)
    assert counts == row_counts(connection)
    assert counts["scenario_results"] == 4800
    assert counts["uncertainty_intervals"] == 56
    assert counts["diagnostic_metrics"] == 1590
    assert counts["latency_metrics"] == 6
    assert _check_database(connection, bundle)["source_reconciliation"] == "passed"
    assert dict(connection.execute("SELECT branch, COUNT(*) FROM scenarios GROUP BY branch")) == {"dynamic": 250, "static": 250}
    assert connection.execute("SELECT DISTINCT split FROM scenarios").fetchall() == [("test",)]
    assert set(row[0] for row in connection.execute("SELECT DISTINCT training_seed FROM experiments WHERE branch='dynamic'")) == {11, 23, 37}
    assert connection.execute("SELECT COUNT(*) FROM scenario_results WHERE p95_waiting_time_min IS NULL").fetchone()[0] > 0
    assert connection.execute("SELECT COUNT(*) FROM aggregate_metrics WHERE family <> 'WEIGHTED'").fetchone()[0] > 0


def test_query_guide_sql_runs_as_written():
    connection = sqlite3.connect(":memory:")
    ingest(connection, verify_sources(ROOT))
    guide = (ROOT / "docs/project03_results_queries.md").read_text(encoding="utf-8")
    code_blocks = re.findall(r"```sql\s*(.*?)```", guide, re.DOTALL)
    assert len(code_blocks) == len(QUERY_GUIDE) == 10
    for (_, (_, sql)), block in zip(QUERY_GUIDE.items(), code_blocks):
        assert block.strip() == sql.strip()
        assert connection.execute(block).fetchall()
    assert all(run_documented_queries(connection).values())


def test_source_hash_failure_is_blocking(monkeypatch):
    import berth_allocation_lab.results.ingest as source
    original = source.sha256_file
    monkeypatch.setattr(source, "sha256_file", lambda path: "0" * 64 if Path(path).name == "manifest.json" else original(path))
    with pytest.raises(BenchmarkError):
        verify_sources(ROOT)
