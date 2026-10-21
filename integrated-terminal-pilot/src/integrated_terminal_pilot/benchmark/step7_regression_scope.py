"""Pre-lock Project03 regression eligibility. Reads test source only, never results.

Archive consumers are outside the authorized pre-lock fast scope. Synthetic replay
unit tests and the safe nodes of mixed modules remain eligible. New modules require
classification before they can be collected or executed by the Step7 runner.
"""
import ast
import hashlib

UNSAFE_MODULES = {
    'tests/integration/test_dynamic_ppo_integration.py': 'real PPO training',
    'tests/integration/test_static_ppo_integration.py': 'training fixtures or direct training in every fast test',
    'tests/integration/test_project03_results_release.py': 'reads historical held-out warehouse and writes Project03 experiment directories',
    'tests/integration/test_scientific_benchmark_integration.py': 'reads real historical held-out campaign records in all fixtures',
    'tests/integration/test_replay_records.py': 'loads original Step12A held-out replay catalog and scenario result records',
    'tests/integration/test_replay_frontend.py': 'opens the real Streamlit replay app backed by the original held-out catalog',
}
MIXED = {
    'tests/integration/test_static_ppo_v2_integration.py': ['test_v2_short_training_and_adapter'],
    'tests/unit/test_project03_results.py': ['test_frozen_ingest_coverage_and_reconciliation',
        'test_query_guide_sql_runs_as_written', 'test_source_hash_failure_is_blocking'],
    'tests/integration/test_benchmark_diagnostics_integration.py': ['test_step12a_outputs_complete_and_hashed',
        'test_wait_and_agreement_from_locked_records', 'test_tails_traces_and_static_separation',
        'test_fixture_plan_fixed_and_disjoint_from_test', 'test_completed_outputs_are_immutable_and_sources_unchanged',
        'test_tiny_bounded_latency_smoke'],
}
SAFE_MODULES = (
    'tests/integration/test_candidate_reference.py',
    'tests/integration/test_dynamic_bap_integration.py',
    'tests/integration/test_rollout_dominance_slow.py',
    'tests/integration/test_static_bap_env_integration.py',
    'tests/integration/test_static_runner.py',
    'tests/integration/test_synthetic_core_integration.py',
    'tests/integration/test_synthetic_upstream_compatibility.py',
    'tests/integration/test_upstream_imports.py',
    'tests/unit/test_benchmark_diagnostics.py',
    'tests/unit/test_candidate_enumeration.py',
    'tests/unit/test_candidate_scoring.py',
    'tests/unit/test_candidates.py',
    'tests/unit/test_config_loader.py',
    'tests/unit/test_dynamic_bap_env.py',
    'tests/unit/test_dynamic_joint_scoring.py',
    'tests/unit/test_dynamic_online_rollout.py',
    'tests/unit/test_dynamic_step11_contract.py',
    'tests/unit/test_feasibility.py',
    'tests/unit/test_geometry.py',
    'tests/unit/test_git_metadata.py',
    'tests/unit/test_objectives.py',
    'tests/unit/test_package_metadata.py',
    'tests/unit/test_placement.py',
    'tests/unit/test_ppo_progress.py',
    'tests/unit/test_ppo_v2_contract.py',
    'tests/unit/test_ppo_v2_tools.py',
    'tests/unit/test_replay.py',
    'tests/unit/test_scheduling.py',
    'tests/unit/test_scientific_benchmark.py',
    'tests/unit/test_static_bap_env.py',
    'tests/unit/test_static_metrics.py',
    'tests/unit/test_static_policies.py',
    'tests/unit/test_static_ppo_components.py',
    'tests/unit/test_static_ppo_policy.py',
    'tests/unit/test_synthetic_generator.py',
)


def audit(project03):
    """A deterministic source-only receipt; no import of upstream test modules."""
    known = set(SAFE_MODULES) | set(UNSAFE_MODULES) | set(MIXED)
    actual = {p.relative_to(project03).as_posix() for p in (project03/'tests').rglob('test_*.py')}
    if actual != known:
        raise ValueError(f'Project03 test scope needs source review: unclassified={sorted(actual-known)}, missing={sorted(known-actual)}')
    for name, nodes in MIXED.items():
        tree = ast.parse((project03/name).read_text(encoding='utf-8-sig'))
        functions = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        if set(nodes)-functions:
            raise ValueError(f'Excluded Project03 node no longer exists: {name}: {sorted(set(nodes)-functions)}')
    return dict(schema='step7_project03_eligible_scope_v1', marker='not slow',
        excluded_modules=UNSAFE_MODULES, excluded_nodes=MIXED,
        eligible_modules=sorted(set(SAFE_MODULES) | set(MIXED)),
        classified_test_source_sha256={name: hashlib.sha256((project03/name).read_bytes()).hexdigest() for name in sorted(known)},
        results_read=False, training_performed=False)


def pytest_arguments():
    return ['-m', 'not slow', *('--ignore='+name for name in UNSAFE_MODULES),
            *('--deselect='+name+'::'+node for name, nodes in MIXED.items() for node in nodes)]
