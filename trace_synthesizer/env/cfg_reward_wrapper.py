"""Wrap ``CFGWalkEnv`` with PGO-shaped rewards, visit stats, optional loop profile tail."""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional, SupportsFloat

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from trace_synthesizer.core.grammar import CfgProgram
from trace_synthesizer.rl.loop_profile import (
    exit_aux_label,
    loop_context_features,
    loop_timing_reward,
    rl_base_extras,
)
from trace_synthesizer.rl.rewards import (
    RewardConfig,
    reference_edge_log_reward,
    terminal_bb_kl_reward,
    terminal_short_path_penalty,
    transition_pgo_log_reward,
)

# Base RL tail (visit / length / call / reserved) without loop-context extras.
RL_EXTRAS_DIM = 4
RL_LOOP_EXTRAS_DIM = 3


class CFGWalkRewardWrapper(gym.Wrapper):
    """
    Adds per-step PGO log-reward, optional terminal KL vs reference BB histogram,
    optional loop-timing reward, and ``rl_extras`` observation tail:

    - Base 4 dims: log1p(visit current BB), episode length / max_steps, call depth, 0
    - Optional +3 dims when ``loop_profile`` is set (see ``loop_context_features``)
    """

    def __init__(
        self,
        env: gym.Env,
        grammar: CfgProgram,
        function_name: str,
        *,
        reward_config: Optional[RewardConfig] = None,
        ref_bb_hist: Optional[Counter[int]] = None,
        call_depth: float = 0.0,
        loop_profile: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(env)
        self._grammar = grammar
        self._fn = function_name
        self._cfg = reward_config or RewardConfig()
        self._ref_bb_hist = ref_bb_hist
        self._call_depth = float(call_depth)
        self._loop_profile = loop_profile
        self._by_id = grammar.function(function_name).block_by_id()

        base = env.observation_space
        if not isinstance(base, spaces.Dict) or "features" not in base.spaces:
            raise TypeError("CFGWalkRewardWrapper expects Dict obs with 'features'")
        feat = base["features"]
        if not isinstance(feat, spaces.Box) or len(feat.shape) != 1:
            raise TypeError("features must be 1-D Box")
        self._loop_extra = RL_LOOP_EXTRAS_DIM if loop_profile is not None else 0
        new_dim = int(feat.shape[0]) + RL_EXTRAS_DIM + self._loop_extra
        self.observation_space = spaces.Dict(
            {
                **{k: base[k] for k in base.spaces},
                "features": spaces.Box(
                    low=-np.inf, high=np.inf, shape=(new_dim,), dtype=np.float32
                ),
            }
        )
        self._base_feat_dim = int(feat.shape[0])
        self._visit_bb: Counter[int] = Counter()
        self._prev_bb: int = 0
        self._episode_steps: int = 0
        self._last_loop_header: int | None = None

    def _extras(self, current_bb: int) -> np.ndarray:
        max_s = getattr(self.env, "_max_steps", 0)
        base = rl_base_extras(
            current_bb=int(current_bb),
            visit_bb=self._visit_bb,
            episode_steps=self._episode_steps,
            call_depth=self._call_depth,
            max_steps=int(max_s),
        )
        if self._loop_profile is None:
            return base
        rel, mn, ex = loop_context_features(
            from_bb=int(current_bb),
            visit_bb=dict(self._visit_bb),
            last_loop_header=self._last_loop_header,
            profile=self._loop_profile,
        )
        return np.concatenate([base, np.array([rel, mn, ex], dtype=np.float32)], axis=0)

    def _pad_features(
        self, obs: dict[str, Any], current_bb: int
    ) -> dict[str, np.ndarray]:
        base_f = np.asarray(obs["features"], dtype=np.float32).reshape(-1)
        if base_f.shape[0] != self._base_feat_dim:
            raise ValueError(
                f"base feature dim {base_f.shape[0]} != expected {self._base_feat_dim}"
            )
        ex = self._extras(current_bb)
        out = dict(obs)
        out["features"] = np.concatenate([base_f, ex], axis=0).astype(np.float32)
        return out

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        self._visit_bb.clear()
        self._episode_steps = 0
        self._last_loop_header = None
        obs, info = self.env.reset(seed=seed, options=options)
        bb = int(obs["bb_id"][0])
        self._prev_bb = bb
        self._visit_bb[bb] += 1
        blk = self._by_id.get(bb)
        if blk is not None and bool(blk.is_loop_header):
            self._last_loop_header = int(bb)
        obs2 = self._pad_features(obs, bb)
        return obs2, info

    def step(
        self, action: SupportsFloat | np.ndarray
    ) -> tuple[dict[str, np.ndarray], float, bool, bool, dict[str, Any]]:
        from_bb = self._prev_bb
        obs, base_r, terminated, truncated, info = self.env.step(action)
        to_bb = int(obs["bb_id"][0])
        invalid = info.get("reason") == "invalid_action"

        r = float(base_r)
        if invalid:
            r += self._cfg.invalid_action_penalty
            obs2 = self._pad_features(obs, to_bb)
            info = {
                **info,
                "from_bb": from_bb,
                "to_bb": to_bb,
                "visit_bb_counts": dict(self._visit_bb),
                "aux_exit_next": 0.0,
            }
            return obs2, r, terminated, truncated, info

        self._episode_steps += 1
        self._visit_bb[to_bb] += 1
        self._prev_bb = to_bb
        blk = self._by_id.get(to_bb)
        if blk is not None and bool(blk.is_loop_header):
            self._last_loop_header = int(to_bb)

        r += transition_pgo_log_reward(
            self._grammar,
            self._fn,
            from_bb,
            int(action),
            scale=self._cfg.pgo_log_scale,
        )
        if self._loop_profile is not None and self._cfg.ref_edge_log_scale > 0.0:
            r += reference_edge_log_reward(
                self._loop_profile,
                from_bb,
                int(action),
                scale=self._cfg.ref_edge_log_scale,
                epsilon=self._cfg.epsilon,
            )
        if self._cfg.repeat_bb_penalty_scale > 0.0:
            repeats = max(0, int(self._visit_bb[to_bb]) - 1)
            if repeats > 0:
                r -= float(self._cfg.repeat_bb_penalty_scale) * float(repeats)
        if truncated and not terminated and self._cfg.truncation_penalty != 0.0:
            r += float(self._cfg.truncation_penalty)

        if self._loop_profile is not None and self._cfg.loop_timing_scale > 0.0:
            r += loop_timing_reward(
                to_bb=to_bb,
                visit_bb=dict(self._visit_bb),
                profile=self._loop_profile,
                by_id=self._by_id,
                scale=float(self._cfg.loop_timing_scale),
            )

        if (
            (terminated or truncated)
            and self._cfg.terminal_kl_scale > 0
            and self._ref_bb_hist
        ):
            r += terminal_bb_kl_reward(
                self._visit_bb,
                self._ref_bb_hist,
                epsilon=self._cfg.epsilon,
                scale=self._cfg.terminal_kl_scale,
            )

        if (terminated or truncated) and self._loop_profile is not None:
            r -= terminal_short_path_penalty(
                self._loop_profile,
                self._episode_steps,
                scale=self._cfg.short_path_penalty_scale,
            )

        fn = self._grammar.function(self._fn)
        aux_exit = float(exit_aux_label(from_bb, to_bb, fn))

        obs2 = self._pad_features(obs, to_bb)
        info = {
            **info,
            "from_bb": from_bb,
            "to_bb": to_bb,
            "visit_bb_counts": dict(self._visit_bb),
            "aux_exit_next": aux_exit,
        }
        return obs2, r, terminated, truncated, info
