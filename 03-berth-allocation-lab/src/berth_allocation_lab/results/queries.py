"""Executable, documented questions against the final SQLite schema."""

from __future__ import annotations

import sqlite3

STATIC_SUMMARY = """
SELECT regime, source_version,
  MAX(CASE WHEN method='fcfs' THEN value END) AS fcfs_min,
  MAX(CASE WHEN method='rollout' THEN value END) AS rollout_min,
  MAX(CASE WHEN method='ppo_seed_mean' THEN value END) AS ppo_seed_mean_min,
  MAX(CASE WHEN method='candidate_space_exact' THEN value END) AS candidate_space_exact_min,
  MAX(selected_by_frozen_rule) AS selected_by_frozen_rule,
  MAX(n_physical_scenarios) AS n_physical_scenarios
FROM aggregate_metrics
WHERE branch='static' AND split='test' AND family='WEIGHTED'
  AND metric_name='mean_total_waiting_time_min'
GROUP BY regime, source_version
ORDER BY CASE regime WHEN 'tiny' THEN 0 ELSE 1 END, source_version;
"""

DYNAMIC_SUMMARY = """
WITH totals AS (
 SELECT regime,
  MAX(CASE WHEN method='fcfs' AND metric_name='mean_total_waiting_time_min' THEN value END) AS fcfs_min,
  MAX(CASE WHEN method='rollout' AND metric_name='mean_total_waiting_time_min' THEN value END) AS rollout_min,
  MAX(CASE WHEN method='ppo_seed_mean' AND metric_name='mean_total_waiting_time_min' THEN value END) AS ppo_seed_mean_min,
  MAX(CASE WHEN method='ppo_seed_mean' AND metric_name='gap_closed' THEN value END) AS gap_closed,
  MAX(n_physical_scenarios) AS n_physical_scenarios
 FROM aggregate_metrics WHERE branch='dynamic' AND split='test' AND family='WEIGHTED'
 GROUP BY regime
)
SELECT t.regime, t.fcfs_min, t.ppo_seed_mean_min, t.rollout_min,
 t.fcfs_min-t.ppo_seed_mean_min AS improvement_vs_fcfs_min,
 t.ppo_seed_mean_min-t.rollout_min AS delta_vs_rollout_min,
 t.gap_closed, i.lower_bound AS ci_lower_min, i.upper_bound AS ci_upper_min,
 t.n_physical_scenarios
FROM totals t JOIN uncertainty_intervals i ON i.branch='dynamic' AND i.regime=t.regime
 AND i.family='WEIGHTED' AND i.candidate_method='ppo_seed_mean'
 AND i.reference_method='fcfs' AND i.training_seed_rule='seed_mean'
ORDER BY CASE t.regime WHEN 'tiny' THEN 0 ELSE 1 END;
"""

DYNAMIC_BY_SEED = """
WITH ppo AS (
 SELECT regime, seed_label,
 MAX(CASE WHEN metric_name='mean_total_waiting_time_min' THEN value END) AS ppo_min,
 MAX(CASE WHEN metric_name='gap_closed' THEN value END) AS gap_closed
 FROM aggregate_metrics WHERE branch='dynamic' AND family='WEIGHTED'
 AND method='ppo' AND seed_label IN ('11','23','37') GROUP BY regime, seed_label
), refs AS (
 SELECT regime,
 MAX(CASE WHEN method='fcfs' THEN value END) AS fcfs_min,
 MAX(CASE WHEN method='rollout' THEN value END) AS rollout_min
 FROM aggregate_metrics WHERE branch='dynamic' AND family='WEIGHTED'
 AND metric_name='mean_total_waiting_time_min' GROUP BY regime
)
SELECT p.regime, CAST(p.seed_label AS INTEGER) AS training_seed, p.ppo_min,
 r.fcfs_min-p.ppo_min AS improvement_vs_fcfs_min,
 p.ppo_min-r.rollout_min AS delta_vs_rollout_min, p.gap_closed
FROM ppo p JOIN refs r ON r.regime=p.regime
ORDER BY CASE p.regime WHEN 'tiny' THEN 0 ELSE 1 END, training_seed;
"""

WAIT_DIAGNOSTICS = """
SELECT regime, family, method, CAST(seed_label AS INTEGER) AS training_seed,
 MAX(CASE WHEN metric_name='intentional_waits' THEN value END) AS intentional_waits,
 MAX(CASE WHEN metric_name='legal_wait_opportunities' THEN value END) AS legal_wait_opportunities,
 MAX(CASE WHEN metric_name='wait_rate_per_opportunity' THEN value END) AS wait_rate,
 MAX(CASE WHEN metric_name='episodes_with_wait' THEN value END) AS episodes_with_wait,
 MAX(CASE WHEN metric_name='forced_advances' THEN value END) AS forced_advances
FROM diagnostic_metrics WHERE method IN ('fcfs','rollout','ppo')
GROUP BY regime, family, method, seed_label
ORDER BY regime, family, method, training_seed;
"""

TAIL_RISK = """
SELECT regime, family, method, CAST(seed_label AS INTEGER) AS training_seed,
 MAX(CASE WHEN metric_name='p95_scenario_total_min' THEN value END) AS p95_scenario_total_min,
 MAX(CASE WHEN metric_name='max_scenario_total_min' THEN value END) AS max_scenario_total_min,
 MAX(CASE WHEN metric_name='p95_vessel_waiting_min' THEN value END) AS p95_vessel_waiting_min,
 MAX(CASE WHEN metric_name='max_vessel_waiting_min' THEN value END) AS max_vessel_waiting_min,
 MAX(CASE WHEN metric_name='p95_paired_delta_min' THEN value END) AS p95_paired_delta_min,
 MAX(CASE WHEN metric_name='max_paired_delta_min' THEN value END) AS max_paired_delta_min,
 MAX(CASE WHEN metric_name='fraction_ppo_worse' THEN value END) AS fraction_ppo_worse
FROM diagnostic_metrics WHERE method IN ('fcfs','rollout','ppo','ppo_minus_fcfs','ppo_minus_rollout')
GROUP BY regime, family, method, seed_label
ORDER BY regime, family, method, training_seed;
"""

LATENCY = """
SELECT regime, method, device, fixture_count, decision_count,
 mean_decision_ms, median_decision_ms, p95_decision_ms, max_decision_ms,
 total_policy_ms, source_artifact
FROM latency_metrics ORDER BY regime, method;
"""

QUERY_GUIDE: dict[str, tuple[str, str]] = {
    "Dynamic held-out weighted methods": (
        "Methods are separate rows; no cross-branch ranking.",
        "SELECT regime, method, seed_label, value AS waiting_min FROM aggregate_metrics "
        "WHERE branch='dynamic' AND split='test' AND family='WEIGHTED' "
        "AND metric_name='mean_total_waiting_time_min' ORDER BY regime, method, seed_label;"),
    "PPO seed mean versus online references": (
        "The seed mean is scenario-first, not a fourth trained model.", DYNAMIC_SUMMARY),
    "Individual PPO training seeds": (
        "Training seed is distinct from each physical scenario seed.", DYNAMIC_BY_SEED),
    "Paired bootstrap intervals": (
        "Intervals describe scenario sampling conditional on frozen models.",
        "SELECT regime, candidate_method, reference_method, training_seed_rule, "
        "estimate, lower_bound, upper_bound, n_physical_scenarios "
        "FROM uncertainty_intervals WHERE branch='dynamic' AND family='WEIGHTED' "
        "ORDER BY regime, candidate_method, reference_method, training_seed_rule;"),
    "Worst held-out PPO deterioration": (
        "Positive paired delta means PPO waited longer.",
        "SELECT d.regime, d.scenario_id, d.seed_label, d.paired_delta_min, "
        "s.physical_fingerprint FROM scenario_differences d JOIN scenarios s "
        "ON s.branch=d.branch AND s.scenario_id=d.scenario_id "
        "WHERE d.branch='dynamic' AND d.candidate_method='ppo' "
        "AND d.reference_method='fcfs' ORDER BY d.paired_delta_min DESC, d.scenario_id LIMIT 10;"),
    "WAIT by family and seed": (
        "Automatic advances are a separate field.", WAIT_DIAGNOSTICS),
    "CPU decision latency": (
        "Validation-fixture engineering timing, not training runtime.", LATENCY),
    "Static v1 versus v2": (
        "Candidate-space Exact is not an unrestricted continuous optimum.", STATIC_SUMMARY),
    "Source provenance for a reported metric": (
        "Follow a weighted dynamic metric back to its hashed source artifact.",
        "SELECT a.regime, a.method, a.seed_label, a.value, a.source_artifact, "
        "p.sha256 FROM aggregate_metrics a JOIN artifacts p ON p.artifact_path=a.source_artifact "
        "WHERE a.branch='dynamic' AND a.regime='tiny' AND a.family='WEIGHTED' "
        "AND a.method='ppo_seed_mean' AND a.metric_name='mean_total_waiting_time_min';"),
    "Artifacts from a Git commit": (
        "The commit is source/analysis provenance, not a release timestamp.",
        "SELECT artifact_path, artifact_type, sha256 FROM artifacts "
        "WHERE git_commit='b87af8408940d2720c553bea88ee86090d1ec7b8' "
        "ORDER BY artifact_path;"),
}


def run_documented_queries(connection: sqlite3.Connection) -> dict[str, int]:
    return {title: len(connection.execute(sql).fetchall())
            for title, (_, sql) in QUERY_GUIDE.items()}


def write_query_guide(path: str) -> None:
    lines = ["# Project 03 Results: SQLite Queries", "",
             "Open the generated `project03_results.sqlite` with any SQLite client.",
             "All waiting values are raw vessel-minutes; lower is better.", ""]
    for index, (title, (note, sql)) in enumerate(QUERY_GUIDE.items(), 1):
        lines.extend([f"## {index}. {title}", "", note, "", "```sql", sql.strip(), "```", ""])
    from pathlib import Path
    Path(path).write_text("\n".join(lines), encoding="utf-8")
