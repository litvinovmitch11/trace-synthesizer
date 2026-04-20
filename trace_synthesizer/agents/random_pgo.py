"""Random walk agent using PGO-normalized successor weights."""

from __future__ import annotations

from typing import Any

import numpy as np

from trace_synthesizer.core.grammar import CfgProgram, normalized_successor_weights


class RandomPGOAgent:
    """Sample a valid successor index proportional to CFG PGO weights."""

    def __init__(
        self,
        grammar: CfgProgram,
        function_name: str,
        *,
        seed: int | None = None,
    ) -> None:
        self._grammar = grammar
        self._fn = function_name
        self._rng = np.random.default_rng(seed)
        self._by_id = grammar.function(function_name).block_by_id()

    def act(self, observation: dict[str, Any], info: dict[str, Any]) -> int:
        bb_id = int(observation["bb_id"][0])
        mask = np.asarray(info["action_mask"], dtype=bool)
        block = self._by_id[bb_id]
        w = normalized_successor_weights(block)
        n = int(mask.shape[0])
        p = np.zeros(n, dtype=np.float64)
        for i in range(min(len(w), n)):
            if mask[i]:
                p[i] = w[i]
        total = p.sum()
        if total <= 0:
            valid = np.flatnonzero(mask)
            if valid.size == 0:
                return 0
            return int(self._rng.choice(valid))
        p /= total
        return int(self._rng.choice(n, p=p))
