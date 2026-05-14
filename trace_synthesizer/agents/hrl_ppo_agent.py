"""Rollout agent for PPO flat/hierarchical actor-critic checkpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch

from trace_synthesizer.agents.checkpoint import (
    POLICY_TYPE_PPO_FLAT,
    POLICY_TYPE_PPO_HIERARCHICAL,
    load_policy_checkpoint,
)
from trace_synthesizer.agents.ppo_policies import FlatActorCritic, HierarchicalActorCritic

ActionSelect = Literal["argmax", "sample"]


class HRLPPOCfgAgent:
    """Inference agent for ``FlatActorCritic`` and ``HierarchicalActorCritic``."""

    def __init__(
        self,
        *,
        checkpoint_stem: Path | str,
        device: torch.device | str = "cpu",
        action_select: ActionSelect = "argmax",
        sample_temperature: float = 1.0,
        top_p: float = 1.0,
        seed: int | None = None,
        policy: FlatActorCritic | HierarchicalActorCritic | None = None,
    ) -> None:
        self._device = torch.device(device)
        self._action_select = action_select
        self._sample_temperature = max(1e-6, float(sample_temperature))
        self._top_p = float(top_p)
        self._rng = torch.Generator(device=self._device)
        if seed is not None:
            self._rng.manual_seed(seed)

        if policy is not None:
            self._policy = policy.to(self._device)
            self._meta: dict[str, Any] = {}
        else:
            self._policy, self._meta = load_policy_checkpoint(
                Path(checkpoint_stem), device=self._device
            )

        ptype = self._meta.get("policy_type") if self._meta else None
        if isinstance(self._policy, FlatActorCritic):
            self._kind = POLICY_TYPE_PPO_FLAT
        elif isinstance(self._policy, HierarchicalActorCritic):
            self._kind = POLICY_TYPE_PPO_HIERARCHICAL
        else:
            raise TypeError(f"Unsupported PPO policy type: {type(self._policy)}")
        if ptype is not None and ptype != self._kind:
            raise ValueError(f"Checkpoint policy_type {ptype!r} != model {self._kind!r}")

        self._t = 0
        self._z: torch.Tensor | None = None
        self._policy.eval()

    def _sample_from_logits(self, logits: torch.Tensor) -> torch.Tensor:
        x = logits / self._sample_temperature
        probs = torch.softmax(x, dim=-1)
        if self._top_p < 1.0:
            sp, idx = torch.sort(probs, descending=True, dim=-1)
            cdf = torch.cumsum(sp, dim=-1)
            keep = cdf <= self._top_p
            keep[..., 0] = True
            filt = torch.zeros_like(probs)
            filt.scatter_(-1, idx, sp * keep.float())
            denom = filt.sum(dim=-1, keepdim=True).clamp(min=1e-12)
            probs = filt / denom
        return torch.multinomial(probs, num_samples=1, generator=self._rng).squeeze(-1)

    def on_episode_start(self) -> None:
        self._t = 0
        self._z = None

    def act(self, observation: dict[str, Any], info: dict[str, Any]) -> int:
        obs = np.asarray(observation["features"], dtype=np.float32).reshape(1, -1)
        raw_mask = np.asarray(info["action_mask"], dtype=bool).reshape(-1)
        if self._kind == POLICY_TYPE_PPO_FLAT:
            pol0 = self._policy
            assert isinstance(pol0, FlatActorCritic)
            max_a = int(pol0.max_actions)
        else:
            pol0 = self._policy
            assert isinstance(pol0, HierarchicalActorCritic)
            max_a = int(pol0.max_actions)
        mask_row = np.zeros(max_a, dtype=bool)
        n = min(raw_mask.size, max_a)
        mask_row[:n] = raw_mask[:n]
        mask = mask_row.reshape(1, -1)
        obs_t = torch.tensor(obs, dtype=torch.float32, device=self._device)
        mask_t = torch.tensor(mask, dtype=torch.bool, device=self._device)

        if self._kind == POLICY_TYPE_PPO_FLAT:
            pol = self._policy
            assert isinstance(pol, FlatActorCritic)
            if self._action_select == "argmax":
                a = pol.act_argmax(obs_t, mask_t)
            else:
                logits, _vals = pol.forward(obs_t)
                logits = logits.masked_fill(~mask_t, -1e9)
                a = self._sample_from_logits(logits)
            self._t += 1
            return int(a.item())

        pol = self._policy
        assert isinstance(pol, HierarchicalActorCritic)
        fire = self._z is None or (self._t % pol.manager_every == 0)
        if fire:
            z, _lp_m = pol.sample_manager(obs_t)
            self._z = z
        assert self._z is not None
        if self._action_select == "argmax":
            a = pol.act_worker_argmax(obs_t, mask_t, self._z)
        else:
            logits, _vals = pol.forward_worker_critic(obs_t, self._z)
            logits = logits.masked_fill(~mask_t, -1e9)
            a = self._sample_from_logits(logits)
        self._t += 1
        return int(a.item())
