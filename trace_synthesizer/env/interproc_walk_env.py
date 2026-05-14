"""Inter-procedural CFG walk with explicit call/return actions and call stack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, SupportsFloat

import gymnasium as gym
import numpy as np
import torch
from gymnasium import spaces

from trace_synthesizer.core.grammar import CfgProgram, max_out_degree_for_function, ordered_successors
from trace_synthesizer.domain.program import BasicBlock, FunctionCFG
from trace_synthesizer.features.block_features import BlockFeatures

# Two special actions after successor slots.
SPECIAL_CALL = 1
SPECIAL_RETURN = 2


@dataclass(frozen=True)
class CallFrame:
    function_name: str
    return_bb: int
    caller_bb: int


class InterproceduralCFGWalkEnv(gym.Env):
    """
    Multi-function walk with a call stack.

    Action layout per step:
      - ``0..max_out-1``: successor index in deterministic order
      - ``max_out``: CALL action (if current block has known callee)
      - ``max_out+1``: RETURN action (if currently at callee exit with non-empty stack)
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        grammar: CfgProgram,
        entry_function: str,
        *,
        max_steps: int = 10_000,
        max_call_depth: int = 32,
        device: torch.device | str | None = None,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__()
        self._grammar = grammar
        self._entry_fn = entry_function
        self._max_steps = int(max_steps)
        self._max_call_depth = int(max_call_depth)
        self._device = device
        self._rng = np.random.default_rng(seed)

        by_name = grammar.program.by_name()
        self._functions: dict[str, FunctionCFG] = by_name
        self._fn_names = sorted(by_name.keys())
        self._fn_to_id = {f: i for i, f in enumerate(self._fn_names)}
        self._max_out = max((max_out_degree_for_function(fn) for fn in by_name.values()), default=0)
        self._padded_out = max(1, self._max_out)
        self._action_n = self._padded_out + 2

        feat_dim = (
            BlockFeatures.from_block(next(iter(self._functions[self._entry_fn].blocks)))
            .as_tensor(device=self._device)
            .shape[0]
        )
        self._feat_dim = int(feat_dim) * 2 + 1  # base + caller_base + call_depth scalar
        self.observation_space = spaces.Dict(
            {
                "func_id": spaces.Box(
                    low=0, high=max(1, len(self._fn_names)), shape=(1,), dtype=np.int32
                ),
                "bb_id": spaces.Box(low=0, high=1_000_000, shape=(1,), dtype=np.int32),
                "valid_mask": spaces.MultiBinary(self._action_n),
                "features": spaces.Box(
                    low=-np.inf, high=np.inf, shape=(self._feat_dim,), dtype=np.float32
                ),
            }
        )
        self.action_space = spaces.Discrete(self._action_n)

        self._fn: str = self._entry_fn
        self._bb: int = 0
        self._steps = 0
        self._stack: list[CallFrame] = []

    @property
    def current_function(self) -> str:
        return self._fn

    @property
    def call_depth(self) -> int:
        return len(self._stack)

    def _current_block(self) -> BasicBlock:
        return self._functions[self._fn].block_by_id()[self._bb]

    def _call_target(self, block: BasicBlock) -> str | None:
        tgt = block.call_target
        if tgt and tgt in self._functions:
            return tgt
        return None

    def _observation(self) -> dict[str, np.ndarray]:
        b = self._current_block()
        base = BlockFeatures.from_block(b).as_tensor(device=self._device).detach().cpu().numpy()
        cd = min(1.0, float(len(self._stack)) / max(1.0, float(self._max_call_depth)))
        
        # Add caller features
        if self._stack:
            caller_frame = self._stack[-1]
            caller_b = self._functions[caller_frame.function_name].block_by_id()[caller_frame.caller_bb]
            caller_feat = BlockFeatures.from_block(caller_b).as_tensor(device=self._device).detach().cpu().numpy()
        else:
            caller_feat = np.zeros_like(base)
            
        feat = np.concatenate([base.astype(np.float32), caller_feat.astype(np.float32), np.array([cd], dtype=np.float32)], axis=0)
        return {
            "func_id": np.array([self._fn_to_id[self._fn]], dtype=np.int32),
            "bb_id": np.array([self._bb], dtype=np.int32),
            "valid_mask": self._valid_mask_array(),
            "features": feat,
        }

    def _valid_mask_array(self) -> np.ndarray:
        mask = np.zeros(self._action_n, dtype=np.int8)
        block = self._current_block()
        succs = ordered_successors(block)
        n = min(len(succs), self._padded_out)
        mask[:n] = 1
        tgt = self._call_target(block)
        if tgt is not None and len(self._stack) < self._max_call_depth:
            mask[self._padded_out + (SPECIAL_CALL - 1)] = 1
        if len(succs) == 0 and self._stack:
            mask[self._padded_out + (SPECIAL_RETURN - 1)] = 1
        return mask

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        del options
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._fn = self._entry_fn
        self._bb = self._grammar.entry_bb_id(self._entry_fn)
        self._steps = 0
        self._stack.clear()
        obs = self._observation()
        return obs, {"action_mask": self._valid_mask_array()}

    def step(
        self, action: SupportsFloat | np.ndarray
    ) -> tuple[dict[str, np.ndarray], float, bool, bool, dict[str, Any]]:
        self._steps += 1
        a = int(action)
        mask = self._valid_mask_array()
        if a < 0 or a >= self._action_n or not bool(mask[a]):
            obs = self._observation()
            return obs, -1.0, True, False, {"action_mask": mask, "reason": "invalid_action"}

        b = self._current_block()
        succs = ordered_successors(b)
        info: dict[str, Any] = {"action_mask": mask, "from_function": self._fn, "from_bb": self._bb}

        if a < self._padded_out:
            if a >= len(succs):
                obs = self._observation()
                return obs, -1.0, True, False, {"action_mask": mask, "reason": "invalid_action"}
            self._bb = succs[a].target_id
            info["transition"] = "intra"
        elif a == self._padded_out:
            callee = self._call_target(b)
            if callee is None:
                obs = self._observation()
                return obs, -1.0, True, False, {"action_mask": mask, "reason": "invalid_action"}
            # Continuation after return: successor with highest PGO prob (or smallest id).
            if succs:
                nxt = sorted(
                    succs,
                    key=lambda e: (-(e.prob if e.prob is not None else -1.0), e.target_id),
                )[0].target_id
            else:
                nxt = self._bb
            self._stack.append(CallFrame(function_name=self._fn, return_bb=nxt, caller_bb=self._bb))
            self._fn = callee
            self._bb = self._grammar.entry_bb_id(callee)
            info["transition"] = "call"
            info["callee"] = callee
        else:
            if not self._stack:
                obs = self._observation()
                return obs, -1.0, True, False, {"action_mask": mask, "reason": "invalid_action"}
            fr = self._stack.pop()
            self._fn = fr.function_name
            self._bb = fr.return_bb
            info["transition"] = "return"

        truncated = self._max_steps > 0 and self._steps >= self._max_steps
        at_sink = len(ordered_successors(self._current_block())) == 0
        terminated = at_sink and len(self._stack) == 0
        obs = self._observation()
        info["action_mask"] = self._valid_mask_array()
        info["to_function"] = self._fn
        info["to_bb"] = self._bb
        info["call_depth"] = len(self._stack)
        return obs, 0.0, terminated, truncated, info
