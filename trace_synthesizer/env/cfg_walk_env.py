"""Gymnasium environment: walk one function's CFG with masked discrete actions."""

from __future__ import annotations

from typing import Any, Optional, SupportsFloat

import gymnasium as gym
import numpy as np
import torch
from gymnasium import spaces

from trace_synthesizer.core.grammar import (
    CfgProgram,
    max_out_degree_for_function,
    ordered_successors,
)
from trace_synthesizer.domain.program import BasicBlock
from trace_synthesizer.features.block_features import BlockFeatures


class CFGWalkEnv(gym.Env):
    """
    Single-function random walk on the CFG.

    Action: index into padded successor list (deterministic order by target_id).
    Observation: bb_id, valid_mask, BlockFeatures as float32 vector.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        grammar: CfgProgram,
        function_name: str,
        *,
        max_steps: int = 10_000,
        device: torch.device | str | None = None,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__()
        self._grammar = grammar
        self._fn = function_name
        self._func = grammar.function(function_name)
        self._max_steps = max_steps
        self._device = device
        self._rng = np.random.default_rng(seed)

        self._max_out = max_out_degree_for_function(self._func)
        # Gymnasium MultiBinary / Discrete require n >= 1; trivial CFG has max_out 0.
        self._padded_out = max(1, self._max_out)
        self._bb_ids = [b.id for b in self._func.blocks]
        self._max_bb_id = max(self._bb_ids, default=0)
        self._by_id = self._func.block_by_id()

        feat_dim = (
            BlockFeatures.from_block(next(iter(self._func.blocks)))
            .as_tensor(device=self._device)
            .shape[0]
        )

        self.observation_space = spaces.Dict(
            {
                "bb_id": spaces.Box(
                    low=0, high=self._max_bb_id + 1, shape=(1,), dtype=np.int32
                ),
                "valid_mask": spaces.MultiBinary(self._padded_out),
                "features": spaces.Box(
                    low=-np.inf, high=np.inf, shape=(feat_dim,), dtype=np.float32
                ),
            }
        )
        self.action_space = spaces.Discrete(self._padded_out)

        self._bb: int = 0
        self._steps: int = 0

    def _current_block(self) -> BasicBlock:
        return self._by_id[self._bb]

    def _observation(self) -> dict[str, np.ndarray]:
        block = self._current_block()
        feat = BlockFeatures.from_block(block).as_tensor(device=self._device)
        mask = self._valid_mask_array()
        return {
            "bb_id": np.array([self._bb], dtype=np.int32),
            "valid_mask": mask,
            "features": feat.detach().cpu().numpy().astype(np.float32),
        }

    def _valid_mask_array(self) -> np.ndarray:
        n = len(ordered_successors(self._current_block()))
        mask = np.zeros(self._padded_out, dtype=np.int8)
        mask[:n] = 1
        return mask

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._bb = self._grammar.entry_bb_id(self._fn)
        self._steps = 0
        obs = self._observation()
        if len(ordered_successors(self._by_id[self._bb])) == 0:
            return obs, {"action_mask": self._valid_mask_array(), "terminal": True}
        return obs, {"action_mask": self._valid_mask_array()}

    def step(
        self, action: SupportsFloat | np.ndarray
    ) -> tuple[dict[str, np.ndarray], float, bool, bool, dict[str, Any]]:
        self._steps += 1
        a = int(action)
        block = self._current_block()
        succs = ordered_successors(block)
        mask = self._valid_mask_array()

        if a < 0 or a >= self._padded_out or not mask[a]:
            return (
                self._observation(),
                -1.0,
                True,
                False,
                {"action_mask": mask, "reason": "invalid_action"},
            )

        if a >= len(succs):
            return (
                self._observation(),
                -1.0,
                True,
                False,
                {"action_mask": mask, "reason": "invalid_action"},
            )

        next_bb = succs[a].target_id
        self._bb = next_bb
        next_block = self._by_id[self._bb]
        terminated = len(ordered_successors(next_block)) == 0
        # max_steps <= 0: do not truncate (walk until a CFG sink / function exit).
        truncated = self._max_steps > 0 and self._steps >= self._max_steps
        obs = self._observation()
        return (
            obs,
            0.0,
            terminated,
            truncated,
            {"action_mask": self._valid_mask_array()},
        )
