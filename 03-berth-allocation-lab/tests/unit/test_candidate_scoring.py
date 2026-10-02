"""Architectural invariants of the shared candidate scorer."""

import pytest

pytest.importorskip("sb3_contrib", reason="requires the rl extra")
import torch  # noqa: E402

from berth_allocation_lab.rl.candidate_scoring import CandidateScoringNetwork  # noqa: E402


def observation(vessels=8, candidates=16):
    torch.manual_seed(7)
    return {"vessel_features": torch.randn(2, vessels, 3),
            "vessel_mask": torch.tensor([[1] * (vessels - 2) + [0, 0]] * 2),
            "scheduled_mask": torch.zeros(2, vessels),
            "placement_features": torch.randn(2, vessels, 3),
            "current_vessel_features": torch.randn(2, 3),
            "terminal_features": torch.randn(2, 2),
            "candidate_features": torch.randn(2, candidates, 3),
            "candidate_mask": torch.tensor([[1] * (candidates - 3) + [0] * 3] * 2)}


def test_candidate_permutation_equivariance():
    network = CandidateScoringNetwork()
    obs = observation()
    permutation = torch.randperm(16)
    shuffled = {**obs, "candidate_features": obs["candidate_features"][:, permutation],
                "candidate_mask": obs["candidate_mask"][:, permutation]}
    logits, value = network(obs)
    permuted, same_value = network(shuffled)
    torch.testing.assert_close(permuted, logits[:, permutation])
    torch.testing.assert_close(same_value, value)


def test_padded_values_do_not_change_valid_outputs():
    network = CandidateScoringNetwork()
    obs = observation()
    changed = {key: value.clone() for key, value in obs.items()}
    changed["vessel_features"][:, -2:] = 1e5
    changed["placement_features"][:, -2:] = -1e5
    changed["scheduled_mask"][:, -2:] = 1
    changed["candidate_features"][:, -3:] = 1e5
    logits, value = network(obs)
    altered, altered_value = network(changed)
    torch.testing.assert_close(altered[:, :-3], logits[:, :-3])
    torch.testing.assert_close(altered_value, value)


def test_parameter_count_does_not_depend_on_capacity():
    network = CandidateScoringNetwork()
    count = sum(parameter.numel() for parameter in network.parameters())
    network(observation(8, 16))
    assert count == sum(parameter.numel() for parameter in network.parameters())
    network(observation(24, 48))
    assert count == sum(parameter.numel() for parameter in network.parameters())


def test_zero_terminal_observation_is_finite():
    network = CandidateScoringNetwork()
    obs = {key: torch.zeros_like(value) for key, value in observation().items()}
    logits, value = network(obs)
    assert torch.isfinite(logits).all() and torch.isfinite(value).all()


def test_full_policy_parameter_count_is_capacity_independent(manual_static_scenario):
    from sb3_contrib import MaskablePPO
    from berth_allocation_lab.envs import StaticBAPEnv
    from berth_allocation_lab.rl.candidate_scoring import CandidateScoringMaskablePolicy

    counts = []
    for capacity in (8, 24):
        env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=capacity)
        model = MaskablePPO(CandidateScoringMaskablePolicy, env, n_steps=16, batch_size=8,
                            device="cpu", seed=3)
        counts.append(sum(parameter.numel() for parameter in model.policy.parameters()))
    assert counts[0] == counts[1]
