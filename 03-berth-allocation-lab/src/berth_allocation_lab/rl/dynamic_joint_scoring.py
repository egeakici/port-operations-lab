"""Shared vessel/joint-action scorer for online MaskablePPO 2.8."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from gymnasium import spaces
from sb3_contrib.common.maskable.policies import MaskableMultiInputActorCriticPolicy
from torch import nn


def _mlp(input_width: int, widths: tuple[int, ...]) -> nn.Sequential:
    layers: list[nn.Module] = []
    for width in widths:
        layers.extend((nn.Linear(input_width, width), nn.Tanh()))
        input_width = width
    return nn.Sequential(*layers)


def _masked_mean(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    weights = mask.unsqueeze(-1).to(values.dtype)
    return (values * weights).sum(1) / weights.sum(1).clamp_min(1)


def _masked_max(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    masked = values.masked_fill(~mask.unsqueeze(-1), -torch.inf)
    return torch.where(mask.any(1, keepdim=True), masked.max(1).values,
                       torch.zeros_like(masked[:, 0]))


class DynamicJointScoringNetwork(nn.Module):
    """Capacity-independent shared scorer; action 0 has its own WAIT head."""

    def __init__(self, vessel_embedding_dim: int = 64, context_dim: int = 128,
                 scorer_layers: tuple[int, ...] = (128, 128),
                 value_layers: tuple[int, ...] = (128, 128)) -> None:
        super().__init__()
        self.vessel_encoder = _mlp(10, (vessel_embedding_dim,))
        self.context_encoder = _mlp(2 * vessel_embedding_dim + 1 + 2, (context_dim,))
        self.assignment_encoder = _mlp(vessel_embedding_dim + 10 + 2 + context_dim,
                                       scorer_layers)
        self.assignment_score = nn.Linear(scorer_layers[-1], 1)
        self.wait_encoder = _mlp(context_dim + 2 * vessel_embedding_dim, (context_dim,))
        self.wait_score = nn.Linear(context_dim, 1)
        self.value_encoder = _mlp(context_dim + scorer_layers[-1], value_layers)
        self.value_output = nn.Linear(value_layers[-1], 1)

    def forward(self, obs: dict[str, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
        visible = obs["visible_mask"].bool()
        status = obs["status_features"].float()
        vessel_raw = torch.cat((obs["vessel_features"], status,
                                obs["placement_features"]), dim=-1)
        embeddings = self.vessel_encoder(vessel_raw)
        context = self.context_encoder(torch.cat((
            _masked_mean(embeddings, visible), _masked_max(embeddings, visible),
            obs["horizon"], obs["terminal_features"]), dim=-1))
        announced = visible & obs["status_features"][:, :, 0].bool()
        wait_logit = self.wait_score(self.wait_encoder(torch.cat((
            context, _masked_mean(embeddings, announced),
            _masked_max(embeddings, announced)), dim=-1)))

        max_vessels = obs["vessel_features"].shape[1]
        action_count = obs["candidate_features"].shape[1]
        candidate_capacity = 2 * max_vessels
        if action_count != 1 + max_vessels * candidate_capacity:
            raise ValueError("Dynamic action capacity does not match max_vessels.")
        slots = torch.arange(action_count - 1, device=embeddings.device) // candidate_capacity
        action_embeddings = embeddings[:, slots]
        action_vessels = vessel_raw[:, slots]
        candidates = obs["candidate_features"][:, 1:]
        rows = self.assignment_encoder(torch.cat((
            action_embeddings, action_vessels, candidates,
            context.unsqueeze(1).expand(-1, action_count - 1, -1)), dim=-1))
        assignment_logits = self.assignment_score(rows).squeeze(-1)
        legal_assignments = obs["action_mask"][:, 1:].bool()
        value = self.value_output(self.value_encoder(torch.cat((
            context, _masked_mean(rows, legal_assignments)), dim=-1)))
        return torch.cat((wait_logit, assignment_logits), dim=-1), value


class DynamicJointMaskablePolicy(MaskableMultiInputActorCriticPolicy):
    """Direct shared logits; MaskablePPO applies the environment's legal mask."""

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
        self.scoring_network = DynamicJointScoringNetwork(
            self.vessel_embedding_dim, self.context_dim,
            self.scorer_layers, self.value_layers)
        self.optimizer = self.optimizer_class(self.parameters(), lr=lr_schedule(1),
                                               **self.optimizer_kwargs)

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
        return (actions.reshape((-1, *self.action_space.shape)), values,
                distribution.log_prob(actions))

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
                "scorer_layers": self.scorer_layers,
                "value_layers": self.value_layers}
