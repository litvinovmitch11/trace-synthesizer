"""Flat and hierarchical actor-critic policies for CFG PPO."""

from __future__ import annotations

import torch
import torch.nn as nn


def masked_categorical_logprob(
    logits: torch.Tensor, mask: torch.Tensor, actions: torch.Tensor
) -> tuple[torch.Tensor, torch.Tensor]:
    """log pi(a), entropy for masked categorical. logits (B,A), mask (B,A) bool."""
    logits = logits.masked_fill(~mask, -1e9)
    log_z = torch.logsumexp(logits, dim=-1)
    logp_sel = logits.gather(-1, actions.unsqueeze(-1)).squeeze(-1) - log_z
    p = torch.exp(logits - log_z.unsqueeze(-1))
    ent = -(p * (logits - log_z.unsqueeze(-1))).masked_fill(~mask, 0.0).sum(dim=-1)
    return logp_sel, ent


class FlatActorCritic(nn.Module):
    """MLP actor-critic on concatenated observation features (incl. RL extras)."""

    def __init__(
        self,
        feat_dim: int,
        max_actions: int,
        *,
        hidden: int = 128,
        use_aux_exit: bool = False,
    ) -> None:
        super().__init__()
        self._max_actions = int(max_actions)
        self._use_aux_exit = bool(use_aux_exit)
        h = int(hidden)
        self.body = nn.Sequential(
            nn.Linear(int(feat_dim), h),
            nn.Tanh(),
            nn.Linear(h, h),
            nn.Tanh(),
        )
        self.pi = nn.Linear(h, self._max_actions)
        self.v = nn.Linear(h, 1)
        if use_aux_exit:
            self.aux_exit = nn.Linear(h, 1)

    @property
    def max_actions(self) -> int:
        return self._max_actions

    def aux_exit_logit(self, obs: torch.Tensor) -> torch.Tensor:
        if not self._use_aux_exit:
            raise RuntimeError("FlatActorCritic: aux exit head disabled")
        h = self.body(obs)
        return self.aux_exit(h).squeeze(-1)

    def forward(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """obs (B, F) -> logits (B, A), value (B,)"""
        h = self.body(obs)
        return self.pi(h), self.v(h).squeeze(-1)

    def evaluate_actions(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        actions: torch.Tensor,
        manager_z: torch.Tensor | None = None,
        manager_fired: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        del manager_z, manager_fired
        logits, vals = self.forward(obs)
        lp, ent = masked_categorical_logprob(logits, mask, actions)
        return lp, ent, vals

    @torch.no_grad()
    def act(self, obs: torch.Tensor, mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Sample one action per row.

        Returns ``(actions, log_probs, values)``.
        """
        logits, vals = self.forward(obs)
        logits = logits.masked_fill(~mask, -1e9)
        probs = torch.softmax(logits, dim=-1)
        actions = torch.multinomial(probs, num_samples=1).squeeze(-1)
        lp, _ent = masked_categorical_logprob(logits, mask, actions)
        return actions, lp, vals

    @torch.no_grad()
    def act_argmax(self, obs: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        logits, _vals = self.forward(obs)
        logits = logits.masked_fill(~mask, -1e9)
        return logits.argmax(dim=-1)


class HierarchicalActorCritic(nn.Module):
    """
    Manager chooses ``z in {0..num_modes-1}`` every ``manager_every`` env steps (and on t=0).
    Worker maps ``concat(obs, embed(z))`` to edge logits; critic uses the same concat.
    """

    def __init__(
        self,
        feat_dim: int,
        max_actions: int,
        *,
        num_modes: int = 4,
        z_embed_dim: int = 8,
        manager_every: int = 4,
        hidden: int = 128,
        use_aux_exit: bool = False,
    ) -> None:
        super().__init__()
        self._feat_dim = int(feat_dim)
        self._max_actions = int(max_actions)
        self._num_modes = int(num_modes)
        self._z_dim = int(z_embed_dim)
        self._mgr_every = max(1, int(manager_every))
        self._use_aux_exit = bool(use_aux_exit)
        h = int(hidden)
        self.z_embed = nn.Embedding(self._num_modes, self._z_dim)
        self.manager = nn.Sequential(
            nn.Linear(self._feat_dim, h),
            nn.Tanh(),
            nn.Linear(h, self._num_modes),
        )
        self.worker = nn.Sequential(
            nn.Linear(self._feat_dim + self._z_dim, h),
            nn.Tanh(),
            nn.Linear(h, self._max_actions),
        )
        self.critic = nn.Sequential(
            nn.Linear(self._feat_dim + self._z_dim, h),
            nn.Tanh(),
            nn.Linear(h, 1),
        )
        if use_aux_exit:
            self.aux_exit = nn.Linear(self._feat_dim + self._z_dim, 1)

    @property
    def max_actions(self) -> int:
        return self._max_actions

    @property
    def num_modes(self) -> int:
        return self._num_modes

    @property
    def manager_every(self) -> int:
        return self._mgr_every

    def aux_exit_logit(self, obs: torch.Tensor, z: torch.Tensor) -> torch.Tensor:
        if not self._use_aux_exit:
            raise RuntimeError("HierarchicalActorCritic: aux exit head disabled")
        zc = z.clamp(min=0, max=self._num_modes - 1)
        ez = self.z_embed(zc)
        x = torch.cat([obs, ez], dim=-1)
        return self.aux_exit(x).squeeze(-1)

    def forward_worker_critic(
        self, obs: torch.Tensor, z: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        zc = z.clamp(min=0, max=self._num_modes - 1)
        ez = self.z_embed(zc)
        x = torch.cat([obs, ez], dim=-1)
        return self.worker(x), self.critic(x).squeeze(-1)

    def manager_logits(self, obs: torch.Tensor) -> torch.Tensor:
        return self.manager(obs)

    def forward(self, obs: torch.Tensor, z: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return self.forward_worker_critic(obs, z)

    def evaluate_actions(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        actions: torch.Tensor,
        manager_z: torch.Tensor | None,
        manager_fired: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        if manager_z is None:
            raise ValueError("HierarchicalActorCritic requires manager_z (B,)")

        logits, vals = self.forward_worker_critic(obs, manager_z)
        lp_w, ent_w = masked_categorical_logprob(logits, mask, actions)

        mgr_logits = self.manager_logits(obs)
        logp_m = torch.log_softmax(mgr_logits, dim=-1)
        zc = manager_z.clamp(min=0, max=self._num_modes - 1)
        sel_m = logp_m.gather(-1, zc.unsqueeze(-1)).squeeze(-1)
        if manager_fired is not None:
            sel_m = sel_m * manager_fired.float()

        p_m = torch.softmax(mgr_logits, dim=-1)
        ent_m = -(p_m * logp_m).sum(dim=-1)

        logp = lp_w + sel_m
        B = obs.shape[0]
        wf = (
            manager_fired.float()
            if manager_fired is not None
            else torch.zeros(B, device=obs.device, dtype=torch.float32)
        )
        entropy = ent_w + 0.1 * wf * ent_m
        return logp, entropy, vals

    @torch.no_grad()
    def sample_manager(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Sample manager latent ``z`` and return ``(z, log_prob)``.
        """
        lg = self.manager_logits(obs)
        p = torch.softmax(lg, dim=-1)
        z = torch.multinomial(p, num_samples=1).squeeze(-1)
        lp = torch.log_softmax(lg, dim=-1).gather(-1, z.unsqueeze(-1)).squeeze(-1)
        return z, lp

    @torch.no_grad()
    def act_worker(
        self, obs: torch.Tensor, mask: torch.Tensor, z: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Sample worker action with fixed manager latent ``z``.

        Returns ``(actions, worker_log_probs, values)``.
        """
        logits, vals = self.forward_worker_critic(obs, z)
        logits = logits.masked_fill(~mask, -1e9)
        probs = torch.softmax(logits, dim=-1)
        actions = torch.multinomial(probs, num_samples=1).squeeze(-1)
        lp_w, _ = masked_categorical_logprob(logits, mask, actions)
        return actions, lp_w, vals

    @torch.no_grad()
    def act_worker_argmax(
        self, obs: torch.Tensor, mask: torch.Tensor, z: torch.Tensor
    ) -> torch.Tensor:
        logits, _vals = self.forward_worker_critic(obs, z)
        logits = logits.masked_fill(~mask, -1e9)
        return logits.argmax(dim=-1)
