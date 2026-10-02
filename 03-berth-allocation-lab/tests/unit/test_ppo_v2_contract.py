"""Frozen v1/v2 suites and validation-only selection rule."""

from dataclasses import replace
from pathlib import Path

import pytest

from berth_allocation_lab.rl.config import StaticPPOExperimentConfig
from berth_allocation_lab.rl.decision import compare_validation_architectures
from berth_allocation_lab.rl.suites import build_config_suites


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("stem", ["tiny", "medium_heavy"])
def test_v2_changes_only_architecture_and_ids(stem):
    base = ROOT / "configs" / "rl"
    old = StaticPPOExperimentConfig.load_yaml(base / f"static_ppo_{stem}_extended.yaml")
    new = StaticPPOExperimentConfig.load_yaml(base / f"static_ppo_{stem}_v2.yaml")
    assert replace(new, experiment_id=old.experiment_id, policy_id=old.policy_id,
                   policy_architecture=old.policy_architecture, source_path=old.source_path,
                   source_sha256=old.source_sha256) == old
    first, second = build_config_suites(old), build_config_suites(new)
    for name in ("validation", "test", *(suite.name for suite in old.diagnostics)):
        assert [s["physical_fingerprint"] for s in first[name].identities()] == [
            s["physical_fingerprint"] for s in second[name].identities()]


@pytest.mark.parametrize("v1,v2,winner", [
    ([10, 10, 10], [9, 9, 11], "v2"),
    ([10, 10, 10], [11, 11, 9], "v1"),
    ([10, 10, 10], [10, 10, 10], "v1"),
    ([10, 10, 10], [8, 10, 10], "mixed"),
])
def test_v2_validation_rule(v1, v2, winner):
    result = compare_validation_architectures(v1, v2, 20, 5)
    assert result["winner"] == winner
    assert result["v2_better"] == (winner == "v2")
    assert result["v1_gap_closed"] == pytest.approx((20 - sum(v1) / 3) / 15)


def test_undefined_gap_fraction_when_rollout_not_better():
    result = compare_validation_architectures([10] * 3, [9] * 3, 10, 12)
    assert result["v1_gap_closed"] is None and result["v2_gap_closed"] is None
