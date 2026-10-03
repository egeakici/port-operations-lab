"""Architecture invariants of the horizon-bounded joint-action network."""

import numpy as np
import pytest
import torch

from berth_allocation_lab.rl.dynamic_joint_scoring import DynamicJointScoringNetwork


def observation(m):
    n = 1 + 2 * m * m
    obs = {
        "current_time": torch.zeros((1, 1)),
        "horizon": torch.tensor([[240 / 1440]]),
        "terminal_features": torch.tensor([[0.1, 0.0]]),
        "vessel_features": torch.zeros((1, m, 3)),
        "visible_mask": torch.zeros((1, m)),
        "status_features": torch.zeros((1, m, 4)),
        "placement_features": torch.zeros((1, m, 3)),
        "candidate_features": torch.zeros((1, n, 2)),
        "action_mask": torch.zeros((1, n)),
    }
    obs["visible_mask"][0, :2] = 1
    obs["status_features"][0, 0, 1] = 1
    obs["status_features"][0, 1, 0] = 1
    obs["vessel_features"][0, 0] = torch.tensor((0, 0.6, 0.1))
    obs["vessel_features"][0, 1] = torch.tensor((0.01, 1.0, 0.02))
    obs["candidate_features"][0, 1] = torch.tensor((0, 0))
    obs["action_mask"][0, 0:2] = 1
    return obs


@pytest.mark.parametrize("m", [8, 16, 24])
def test_shapes_and_capacity_independent_parameters(m):
    model = DynamicJointScoringNetwork()
    logits, value = model(observation(m))
    assert logits.shape == (1, 1 + 2 * m * m)
    assert value.shape == (1, 1)
    assert torch.isfinite(logits).all() and torch.isfinite(value).all()
    assert sum(p.numel() for p in model.parameters()) == sum(
        p.numel() for p in DynamicJointScoringNetwork().parameters())


def test_padding_hidden_masked_candidate_and_absolute_time_invariance():
    model = DynamicJointScoringNetwork()
    obs = observation(8)
    logits, value = model(obs)
    altered = {k: v.clone() for k, v in obs.items()}
    altered["vessel_features"][0, 2:] = 999
    altered["status_features"][0, 2:, 0] = 1
    altered["placement_features"][0, 2:] = 99
    altered["candidate_features"][0, 2:] = 77
    altered["current_time"][0, 0] = 9999
    changed_logits, changed_value = model(altered)
    torch.testing.assert_close(logits[:, :2], changed_logits[:, :2])
    torch.testing.assert_close(value, changed_value)


def test_terminal_finiteness_and_gradient_flow():
    model = DynamicJointScoringNetwork()
    terminal = observation(8)
    terminal["visible_mask"].zero_()
    terminal["status_features"].zero_()
    terminal["action_mask"].zero_()
    logits, value = model(terminal)
    assert torch.isfinite(logits).all() and torch.isfinite(value).all()
    obs = observation(8)
    logits, value = model(obs)
    (logits[:, :2].sum() + value.sum()).backward()
    for name in ("vessel_encoder", "assignment_score", "wait_score", "value_output"):
        assert any(p.grad is not None and torch.isfinite(p.grad).all()
                   and p.grad.abs().sum() > 0 for p in getattr(model, name).parameters())


def test_slot_permutation_equivariance():
    m = 8
    p = 2 * m
    model = DynamicJointScoringNetwork()
    obs = observation(m)
    obs["status_features"][0, 1] = torch.tensor((0, 1, 0, 0))
    obs["candidate_features"][0, 1 + p] = torch.tensor((0.4, 0.02))
    obs["action_mask"][0, 1 + p] = 1
    original_logits, original_value = model(obs)
    altered = {k: v.clone() for k, v in obs.items()}
    for key in ("vessel_features", "visible_mask", "status_features", "placement_features"):
        altered[key][:, :2] = obs[key][:, [1, 0]]
    for key in ("candidate_features", "action_mask"):
        altered[key][:, 1:1+p] = obs[key][:, 1+p:1+2*p]
        altered[key][:, 1+p:1+2*p] = obs[key][:, 1:1+p]
    permuted_logits, permuted_value = model(altered)
    torch.testing.assert_close(permuted_logits[:, 0], original_logits[:, 0])
    torch.testing.assert_close(permuted_logits[:, 1:1+p], original_logits[:, 1+p:1+2*p])
    torch.testing.assert_close(permuted_logits[:, 1+p:1+2*p], original_logits[:, 1:1+p])
    torch.testing.assert_close(permuted_value, original_value)
