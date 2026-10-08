"""Small SQLite schema for immutable, synthetic Project 03 evidence."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

DDL = """
PRAGMA foreign_keys = ON;
CREATE TABLE schema_info(version INTEGER PRIMARY KEY);
INSERT INTO schema_info(version) VALUES (1);

CREATE TABLE experiments (
    experiment_id TEXT NOT NULL,
    branch TEXT NOT NULL CHECK (branch IN ('static','dynamic')),
    regime TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    environment_version TEXT,
    observation_version TEXT,
    training_seed INTEGER NOT NULL,
    training_device TEXT,
    evaluation_device TEXT,
    source_commit TEXT,
    source_manifest_path TEXT NOT NULL,
    source_manifest_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status = 'completed'),
    PRIMARY KEY (experiment_id, training_seed)
);

CREATE TABLE scenarios (
    scenario_id TEXT NOT NULL,
    branch TEXT NOT NULL CHECK (branch IN ('static','dynamic')),
    split TEXT NOT NULL CHECK (split = 'test'),
    regime TEXT NOT NULL,
    family TEXT NOT NULL,
    physical_fingerprint TEXT NOT NULL,
    vessel_count INTEGER,
    future_horizon_min REAL,
    PRIMARY KEY (branch, scenario_id),
    UNIQUE (branch, physical_fingerprint)
);

CREATE TABLE scenario_results (
    branch TEXT NOT NULL CHECK (branch IN ('static','dynamic')),
    regime TEXT NOT NULL,
    source_version TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    experiment_id TEXT,
    method TEXT NOT NULL,
    seed_label TEXT NOT NULL,
    training_seed INTEGER,
    total_waiting_time_min REAL NOT NULL,
    mean_waiting_time_min REAL,
    p95_waiting_time_min REAL,
    mean_turnaround_time_min REAL,
    p95_turnaround_time_min REAL,
    schedule_valid INTEGER NOT NULL CHECK (schedule_valid = 1),
    truncated INTEGER NOT NULL CHECK (truncated = 0),
    source_path TEXT NOT NULL,
    PRIMARY KEY (branch, regime, source_version, scenario_id, method, seed_label),
    FOREIGN KEY (branch, scenario_id) REFERENCES scenarios(branch, scenario_id)
);

CREATE TABLE aggregate_metrics (
    branch TEXT NOT NULL CHECK (branch IN ('static','dynamic')),
    split TEXT NOT NULL CHECK (split = 'test'),
    regime TEXT NOT NULL,
    source_version TEXT NOT NULL,
    family TEXT NOT NULL,
    method TEXT NOT NULL,
    seed_label TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL,
    n_physical_scenarios INTEGER NOT NULL,
    selected_by_frozen_rule INTEGER,
    source_artifact TEXT NOT NULL,
    PRIMARY KEY (branch, regime, source_version, family, method, seed_label, metric_name)
);

CREATE TABLE scenario_differences (
    branch TEXT NOT NULL CHECK (branch IN ('static','dynamic')),
    regime TEXT NOT NULL,
    source_version TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    family TEXT NOT NULL,
    candidate_method TEXT NOT NULL,
    reference_method TEXT NOT NULL,
    seed_label TEXT NOT NULL,
    paired_delta_min REAL NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('win','tie','loss')),
    source_artifact TEXT NOT NULL,
    PRIMARY KEY (branch, regime, source_version, scenario_id,
                 candidate_method, reference_method, seed_label),
    FOREIGN KEY (branch, scenario_id) REFERENCES scenarios(branch, scenario_id)
);

CREATE TABLE paired_comparisons (
    branch TEXT NOT NULL CHECK (branch IN ('static','dynamic')),
    split TEXT NOT NULL CHECK (split = 'test'),
    regime TEXT NOT NULL,
    source_version TEXT NOT NULL,
    family TEXT NOT NULL,
    candidate_method TEXT NOT NULL,
    reference_method TEXT NOT NULL,
    seed_label TEXT NOT NULL,
    mean_delta_min REAL NOT NULL,
    median_delta_min REAL NOT NULL,
    wins INTEGER NOT NULL,
    ties INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    win_fraction REAL NOT NULL,
    n_physical_scenarios INTEGER NOT NULL,
    source_artifact TEXT NOT NULL,
    PRIMARY KEY (branch, regime, source_version, family,
                 candidate_method, reference_method, seed_label)
);

CREATE TABLE uncertainty_intervals (
    branch TEXT NOT NULL CHECK (branch IN ('static','dynamic')),
    split TEXT NOT NULL CHECK (split = 'test'),
    regime TEXT NOT NULL,
    source_version TEXT NOT NULL,
    family TEXT NOT NULL,
    candidate_method TEXT NOT NULL,
    reference_method TEXT NOT NULL,
    training_seed_rule TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    estimate REAL NOT NULL,
    lower_bound REAL NOT NULL,
    upper_bound REAL NOT NULL,
    confidence_level REAL NOT NULL,
    bootstrap_resamples INTEGER NOT NULL,
    bootstrap_seed INTEGER NOT NULL,
    n_physical_scenarios INTEGER NOT NULL,
    source_artifact TEXT NOT NULL,
    PRIMARY KEY (branch, regime, source_version, family,
                 candidate_method, reference_method, training_seed_rule, metric_name)
);

CREATE TABLE diagnostic_metrics (
    regime TEXT NOT NULL,
    family TEXT NOT NULL,
    method TEXT NOT NULL,
    seed_label TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL,
    source_artifact TEXT NOT NULL,
    PRIMARY KEY (regime, family, method, seed_label, metric_name)
);

CREATE TABLE latency_metrics (
    regime TEXT NOT NULL,
    method TEXT NOT NULL,
    device TEXT NOT NULL,
    fixture_count INTEGER NOT NULL,
    decision_count INTEGER NOT NULL,
    mean_decision_ms REAL NOT NULL,
    median_decision_ms REAL NOT NULL,
    p95_decision_ms REAL NOT NULL,
    max_decision_ms REAL NOT NULL,
    total_policy_ms REAL NOT NULL,
    source_artifact TEXT NOT NULL,
    PRIMARY KEY (regime, method, device)
);

CREATE TABLE artifacts (
    artifact_type TEXT NOT NULL,
    artifact_path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    source_or_derived TEXT NOT NULL CHECK (source_or_derived IN ('source','derived')),
    producer_step TEXT NOT NULL,
    git_commit TEXT
);
"""


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(DDL)
    connection.execute("PRAGMA foreign_keys = ON")


def row_counts(connection: sqlite3.Connection) -> dict[str, int]:
    names = ("experiments", "scenarios", "scenario_results", "aggregate_metrics",
             "scenario_differences", "paired_comparisons", "uncertainty_intervals",
             "diagnostic_metrics", "latency_metrics", "artifacts")
    return {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in names}
