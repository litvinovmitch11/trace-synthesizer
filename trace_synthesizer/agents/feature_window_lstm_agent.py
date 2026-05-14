"""Rollout agent: FeatureWindowLstmPolicy + trace context (back window, CFG successors, summary)."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch

from trace_synthesizer.agents.cfg_supervision import (
    global_cfg_summary_vector,
    successor_features_flat,
)
from trace_synthesizer.agents.checkpoint import load_policy_checkpoint
from trace_synthesizer.agents.feature_window_lstm_policy import FeatureWindowLstmPolicy
from trace_synthesizer.core.grammar import CfgProgram
from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv

ActionSelect = Literal["argmax", "sample"]


class FeatureWindowLSTMCfgAgent:
    def __init__(
        self,
        grammar: CfgProgram,
        function_name: str,
        env: CFGWalkEnv,
        *,
        device: torch.device | str = "cpu",
        action_select: ActionSelect = "argmax",
        seed: int | None = None,
        checkpoint_stem: Path | str | None = None,
        policy: FeatureWindowLstmPolicy | None = None,
        sample_temperature: float = 1.0,
    ) -> None:
        self._grammar = grammar
        self._fn = function_name
        self._device = torch.device(device)
        self._action_select: ActionSelect = action_select
        self._rng = torch.Generator(device=self._device)
        if seed is not None:
            self._rng.manual_seed(seed)

        self._env_max_actions = int(env.action_space.n)
        self._feat_dim = int(env.observation_space["features"].shape[0])

        if policy is not None:
            self._policy = policy.to(self._device)
        elif checkpoint_stem is not None:
            stem = Path(checkpoint_stem)
            self._policy, _meta = load_policy_checkpoint(stem, device=self._device)
            if not isinstance(self._policy, FeatureWindowLstmPolicy):
                raise TypeError(
                    f"Expected FeatureWindowLstmPolicy at {stem}, got {type(self._policy)}"
                )
        else:
            raise ValueError(
                "FeatureWindowLSTMCfgAgent requires `policy` or `checkpoint_stem`"
            )

        if int(self._policy.feat_dim) != self._feat_dim:
            raise ValueError(
                f"Checkpoint feat_dim {self._policy.feat_dim} != env {self._feat_dim}"
            )
        if int(self._policy.max_actions) < self._env_max_actions:
            raise ValueError(
                f"Checkpoint max_actions {self._policy.max_actions} < env "
                f"{self._env_max_actions}; retrain with larger max_actions."
            )

        self._window_back = int(self._policy.window_back)
        self._succ_slots = int(self._policy.succ_feat_slots)
        self._global_dim = int(self._policy.global_summary_dim)
        self._max_actions_ckpt = int(self._policy.max_actions)
        self._sample_temperature = max(1e-6, float(sample_temperature))
        self._policy.eval()
        self._hx: tuple[torch.Tensor, torch.Tensor] | None = None
        self._feat_buf: deque[np.ndarray] = deque(maxlen=self._window_back)
        self._global_np: np.ndarray | None = None

    @property
    def policy(self) -> FeatureWindowLstmPolicy:
        return self._policy

    def on_episode_start(self) -> None:
        self._hx = None
        self._feat_buf.clear()
        if self._global_dim > 0:
            g = global_cfg_summary_vector(self._grammar, self._fn, target_dim=self._global_dim)
            if g.shape[0] != self._global_dim:
                raise ValueError(
                    f"global summary dim {g.shape[0]} != {self._global_dim}"
                )
            self._global_np = g.astype(np.float32)
        else:
            self._global_np = None

    def act(self, observation: dict[str, Any], info: dict[str, Any]) -> int:
        bb = int(observation["bb_id"][0])
        feats = np.asarray(observation["features"], dtype=np.float32).reshape(-1)
        if feats.shape[0] != self._feat_dim:
            raise ValueError(
                f"feature dim {feats.shape[0]} != expected {self._feat_dim}"
            )
        self._feat_buf.append(feats.copy())

        back = np.zeros(self._window_back * self._feat_dim, dtype=np.float32)
        stacked = np.stack(list(self._feat_buf), axis=0)
        flat_b = stacked.reshape(-1)
        back[-len(flat_b) :] = flat_b

        succ = successor_features_flat(
            self._grammar, self._fn, bb, self._succ_slots, self._feat_dim
        )
        parts = [back, succ]
        if self._global_dim > 0:
            assert self._global_np is not None
            parts.append(self._global_np)
        row = np.concatenate(parts, axis=0)
        if row.shape[0] != self._policy.input_dim:
            raise ValueError(
                f"built input dim {row.shape[0]} != policy {self._policy.input_dim}"
            )

        x = torch.tensor(row, dtype=torch.float32, device=self._device).view(1, 1, -1)

        mask = np.asarray(info["action_mask"], dtype=bool)
        am = np.zeros(self._max_actions_ckpt, dtype=bool)
        n = min(mask.size, self._env_max_actions, self._max_actions_ckpt)
        am[:n] = mask.reshape(-1)[:n]
        mask_t = torch.from_numpy(am).view(1, 1, -1).to(self._device)

        with torch.no_grad():
            logits, self._hx = self._policy(x, action_mask=mask_t, hx=self._hx)
        logit_vec = logits[0, -1, : self._env_max_actions]
        if self._action_select == "argmax":
            return int(logit_vec.argmax().item())
        probs = torch.softmax(logit_vec / self._sample_temperature, dim=0)
        return int(torch.multinomial(probs, num_samples=1, generator=self._rng).item())
