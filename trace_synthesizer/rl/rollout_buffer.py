"""Vector rollout storage for PPO (optionally hierarchical with manager goals)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import torch


@dataclass
class RolloutBatch:
    """One chunk of on-policy data."""

    obs_features: torch.Tensor  # (T, feat_dim)
    action_mask: torch.Tensor  # (T, max_actions) bool
    actions: torch.Tensor  # (T,) int64
    rewards: torch.Tensor  # (T,) float32
    dones: torch.Tensor  # (T,) float32 1 at terminal step
    old_log_probs: torch.Tensor  # (T,) float32 joint or worker-only
    old_values: torch.Tensor  # (T,) float32
    manager_z: torch.Tensor | None = None  # (T,) int64, -1 if unused
    old_manager_log_probs: torch.Tensor | None = None  # legacy; joint in old_log_probs
    manager_fired: torch.Tensor | None = None  # (T,) bool
    aux_targets: torch.Tensor | None = None  # (T,) float32 in {0,1} for exit auxiliary
    advantages: torch.Tensor | None = None
    returns: torch.Tensor | None = None


@dataclass
class RolloutBuffer:
    """Append-only lists; call ``stack`` to build tensors."""

    obs_feats: list[np.ndarray] = field(default_factory=list)
    masks: list[np.ndarray] = field(default_factory=list)
    actions: list[int] = field(default_factory=list)
    rewards: list[float] = field(default_factory=list)
    dones: list[float] = field(default_factory=list)
    old_log_probs: list[float] = field(default_factory=list)
    old_values: list[float] = field(default_factory=list)
    manager_z: list[int] = field(default_factory=list)
    old_mgr_log_probs: list[float] = field(default_factory=list)
    manager_fired: list[bool] = field(default_factory=list)
    aux_targets: list[float] = field(default_factory=list)

    def clear(self) -> None:
        self.obs_feats.clear()
        self.masks.clear()
        self.actions.clear()
        self.rewards.clear()
        self.dones.clear()
        self.old_log_probs.clear()
        self.old_values.clear()
        self.manager_z.clear()
        self.old_mgr_log_probs.clear()
        self.manager_fired.clear()
        self.aux_targets.clear()

    def __len__(self) -> int:
        return len(self.actions)

    def append(
        self,
        *,
        obs_feat: np.ndarray,
        mask: np.ndarray,
        action: int,
        reward: float,
        done: float,
        old_log_prob: float,
        old_value: float,
        manager_z: int = -1,
        old_mgr_log_prob: float = 0.0,
        manager_fired: bool = False,
        aux_target: float = 0.0,
    ) -> None:
        self.obs_feats.append(np.asarray(obs_feat, dtype=np.float32).copy())
        self.masks.append(np.asarray(mask, dtype=np.bool_).copy())
        self.actions.append(int(action))
        self.rewards.append(float(reward))
        self.dones.append(float(done))
        self.old_log_probs.append(float(old_log_prob))
        self.old_values.append(float(old_value))
        self.manager_z.append(int(manager_z))
        self.old_mgr_log_probs.append(float(old_mgr_log_prob))
        self.manager_fired.append(bool(manager_fired))
        self.aux_targets.append(float(aux_target))

    def stack(self, device: torch.device) -> RolloutBatch:
        if not self.actions:
            raise ValueError("empty buffer")
        mask_t = torch.from_numpy(np.stack(self.masks, axis=0)).to(device)
        mgr_z = torch.tensor(self.manager_z, dtype=torch.long, device=device)
        mf = torch.tensor(self.manager_fired, dtype=torch.bool, device=device)
        aux_t = torch.tensor(self.aux_targets, dtype=torch.float32, device=device)
        return RolloutBatch(
            obs_features=torch.tensor(np.stack(self.obs_feats, axis=0), device=device),
            action_mask=mask_t,
            actions=torch.tensor(self.actions, dtype=torch.long, device=device),
            rewards=torch.tensor(self.rewards, dtype=torch.float32, device=device),
            dones=torch.tensor(self.dones, dtype=torch.float32, device=device),
            old_log_probs=torch.tensor(self.old_log_probs, dtype=torch.float32, device=device),
            old_values=torch.tensor(self.old_values, dtype=torch.float32, device=device),
            manager_z=mgr_z,
            old_manager_log_probs=None,
            manager_fired=mf,
            aux_targets=aux_t,
        )


def compute_gae(
    rewards: torch.Tensor,
    values: torch.Tensor,
    dones: torch.Tensor,
    *,
    gamma: float,
    lam: float,
    next_value: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Generalized advantage estimation.

    ``values`` and ``rewards`` length T; ``dones[t]=1`` means terminal after step t.
    Bootstrap with ``next_value`` after last step if not terminal.
    """
    T = rewards.shape[0]
    device = rewards.device
    adv = torch.zeros(T, device=device, dtype=torch.float32)
    last_gae = 0.0
    next_v = float(next_value)
    for t in reversed(range(T)):
        mask = 1.0 - dones[t]
        delta = rewards[t] + gamma * next_v * mask - values[t]
        last_gae = delta + gamma * lam * mask * last_gae
        adv[t] = last_gae
        next_v = float(values[t].item())
    returns = adv + values
    return adv, returns
