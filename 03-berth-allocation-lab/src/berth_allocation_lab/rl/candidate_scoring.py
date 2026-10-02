"""Capacity-independent candidate-scoring policy for MaskablePPO 2.8."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from gymnasium import spaces
from sb3_contrib.common.maskable.policies import MaskableMultiInputActorCriticPolicy
from torch import nn


def _mlp(input_dim: int, widths: tuple[int, ...]) -> nn.Sequential:
    layers: list[nn.Module] = []
    for width in widths:
        layers.extend((nn.Linear(input_dim, width), nn.Tanh()))
        input_dim = width
    return nn.Sequential(*layers)


def _masked_mean(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    weights = mask.unsqueeze(-1).to(values.dtype)
    return (values * weights).sum(dim=1) / weights.sum(dim=1).clamp_min(1)


def _masked_max(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    masked = values.masked_fill(~mask.unsqueeze(-1), -torch.inf)
    return torch.where(mask.any(dim=1, keepdim=True), masked.max(dim=1).values,
                       torch.zeros_like(masked[:, 0]))


class CandidateScoringNetwork(nn.Module):
    """Shared row encoders and scorer; neither width depends on row capacity."""

    def __init__(self, vessel_embedding_dim: int = 64, context_dim: int = 128,
                 scorer_layers: tuple[int, ...] = (128, 128),
                 value_layers: tuple[int, ...] = (128, 128)) -> None:
        super().__init__()
        self.vessel_encoder = _mlp(7, (vessel_embedding_dim,))
        self.context_encoder = _mlp(2 * vessel_embedding_dim + 3 + 2, (context_dim,))
        self.candidate_encoder = _mlp(3 + 3 + context_dim, tuple(scorer_layers))
        self.candidate_score = nn.Linear(scorer_layers[-1], 1)
        self.value_encoder = _mlp(context_dim + scorer_layers[-1], tuple(value_layers))
        self.value_output = nn.Linear(value_layers[-1], 1)

    def forward(self, obs: dict[str, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
        vessel_mask = obs["vessel_mask"].bool()
        candidate_mask = obs["candidate_mask"].bool()
        vessel_rows = torch.cat((obs["vessel_features"],
                                 obs["scheduled_mask"].unsqueeze(-1).float(),
                                 obs["placement_features"]), dim=-1)
        vessels = self.vessel_encoder(vessel_rows)
        context = self.context_encoder(torch.cat((
            _masked_mean(vessels, vessel_mask), _masked_max(vessels, vessel_mask),
            obs["current_vessel_features"], obs["terminal_features"]), dim=-1))
        current = obs["current_vessel_features"].unsqueeze(1).expand(-1, obs["candidate_features"].shape[1], -1)
        broadcast_context = context.unsqueeze(1).expand(-1, current.shape[1], -1)
        rows = self.candidate_encoder(torch.cat((obs["candidate_features"], current,
                                                  broadcast_context), dim=-1))
        logits = self.candidate_score(rows).squeeze(-1)
        value = self.value_output(self.value_encoder(torch.cat((
            context, _masked_mean(rows, candidate_mask)), dim=-1)))
        return logits, value


class CandidateScoringMaskablePolicy(MaskableMultiInputActorCriticPolicy):
    """Maskable actor-critic with direct, shared per-candidate logits."""

    def __init__(self, observation_space: spaces.Dict, action_space: spaces.Space,
                 lr_schedule, *, vessel_embedding_dim: int = 64, context_dim: int = 128,
                 scorer_layers: tuple[int, ...] = (128, 128),
                 value_layers: tuple[int, ...] = (128, 128), **kwargs: Any) -> None:
        self.vessel_embedding_dim = vessel_embedding_dim
        self.context_dim = context_dim
        self.scorer_layers = tuple(scorer_layers)
        self.value_layers = tuple(value_layers)
        super().__init__(observation_space, action_space, lr_schedule, **kwargs)

    def _build(self, lr_schedule) -> None:
        self.scoring_network = CandidateScoringNetwork(
            self.vessel_embedding_dim, self.context_dim, self.scorer_layers, self.value_layers)
        self.optimizer = self.optimizer_class(
            self.parameters(), lr=lr_schedule(1), **self.optimizer_kwargs)

    def _scores(self, obs: dict[str, torch.Tensor], action_masks=None):
        logits, values = self.scoring_network(obs)
        distribution = self.action_dist.proba_distribution(action_logits=logits)
        if action_masks is not None:
            distribution.apply_masking(action_masks)
        return distribution, values

    def forward(self, obs: dict[str, torch.Tensor], deterministic: bool = False,
                action_masks: np.ndarray | None = None):
        distribution, values = self._scores(obs, action_masks)
        actions = distribution.get_actions(deterministic=deterministic)
        return actions.reshape((-1, *self.action_space.shape)), values, distribution.log_prob(actions)

    def evaluate_actions(self, obs: dict[str, torch.Tensor], actions: torch.Tensor,
                         action_masks: torch.Tensor | None = None):
        distribution, values = self._scores(obs, action_masks)
        return values, distribution.log_prob(actions), distribution.entropy()

    def get_distribution(self, obs: dict[str, torch.Tensor], action_masks: np.ndarray | None = None):
        return self._scores(obs, action_masks)[0]

    def predict_values(self, obs: dict[str, torch.Tensor]) -> torch.Tensor:
        return self.scoring_network(obs)[1]

    def _get_constructor_parameters(self) -> dict[str, Any]:
        return {**super()._get_constructor_parameters(),
                "vessel_embedding_dim": self.vessel_embedding_dim,
                "context_dim": self.context_dim,
                "scorer_layers": self.scorer_layers, "value_layers": self.value_layers}
