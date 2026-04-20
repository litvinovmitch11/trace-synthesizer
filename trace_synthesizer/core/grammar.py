"""Strict CFG grammar: validated graph + successor ordering + PGO normalization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from trace_synthesizer.domain.cfg_loader import load_program_from_cfg_json
from trace_synthesizer.domain.program import (
    BasicBlock,
    FunctionCFG,
    Program,
    SuccessorEdge,
)


def normalized_successor_weights(block: BasicBlock) -> list[float]:
    """Return sampling weights aligned to ordered_successors(block)."""
    ordered = ordered_successors(block)
    n = len(ordered)
    if n == 0:
        return []
    raw = [e.prob for e in ordered]
    if all(p is None for p in raw):
        return [1.0 / n] * n
    weights = [0.0 if p is None else float(p) for p in raw]
    s = sum(weights)
    missing_n = sum(1 for p in raw if p is None)
    if missing_n > 0:
        remainder = max(0.0, 1.0 - s)
        add = remainder / missing_n if remainder > 0 else 0.0
        weights = [add if raw[i] is None else float(raw[i] or 0.0) for i in range(n)]
    s2 = sum(weights)
    if s2 <= 0:
        return [1.0 / n] * n
    return [w / s2 for w in weights]


def ordered_successors(block: BasicBlock) -> list[SuccessorEdge]:
    """Deterministic successor order: by target_id ascending."""
    return sorted(block.successors, key=lambda e: e.target_id)


def max_out_degree_for_function(fn: FunctionCFG) -> int:
    return max((len(b.successors) for b in fn.blocks), default=0)


@dataclass
class TransitionIndex:
    """Adjacency and metadata for trace validation (incl. recursive call/return)."""

    edges: dict[str, dict[int, set[int]]]
    entry_blocks: dict[str, set[int]]
    exit_blocks: dict[str, set[int]]
    calls: dict[str, dict[int, str]]


def build_transition_index(program: Program) -> TransitionIndex:
    edges: dict[str, dict[int, set[int]]] = {}
    entry_blocks: dict[str, set[int]] = {}
    exit_blocks: dict[str, set[int]] = {}
    calls: dict[str, dict[int, str]] = {}

    for fn in program.functions:
        name = fn.function_name
        edges[name] = {}
        entry_blocks[name] = set()
        exit_blocks[name] = set()
        calls[name] = {}
        for block in fn.blocks:
            bid = block.id
            edges[name][bid] = set()
            if block.is_entry:
                entry_blocks[name].add(bid)
            if block.has_call and block.call_target:
                calls[name][bid] = block.call_target
            succs = block.successors
            if not succs:
                exit_blocks[name].add(bid)
            for s in succs:
                edges[name][bid].add(s.target_id)
    return TransitionIndex(
        edges=edges,
        entry_blocks=entry_blocks,
        exit_blocks=exit_blocks,
        calls=calls,
    )


class CfgProgram:
    """
    Core grammar view over a loaded Program: validation, successor ordering,
    normalized PGO weights, and transition metadata for trace validation.
    """

    def __init__(self, program: Program) -> None:
        self._program = program
        self._index = build_transition_index(program)

    @classmethod
    def from_cfg_json(cls, path: str | Path) -> CfgProgram:
        return cls(load_program_from_cfg_json(path))

    @property
    def program(self) -> Program:
        return self._program

    @property
    def transition_index(self) -> TransitionIndex:
        return self._index

    def function(self, name: str) -> FunctionCFG:
        return self._program.get_function(name)

    def successor_targets(self, func_name: str, bb_id: int) -> list[int]:
        block = self.function(func_name).block_by_id()[bb_id]
        return [e.target_id for e in ordered_successors(block)]

    def successor_weights(self, func_name: str, bb_id: int) -> list[float]:
        block = self.function(func_name).block_by_id()[bb_id]
        return normalized_successor_weights(block)

    def step(self, func_name: str, bb_id: int, action_index: int) -> Optional[int]:
        """
        Apply action_index in ordered successor list.
        Returns target BB id or None if action invalid / terminal.
        """
        targets = self.successor_targets(func_name, bb_id)
        if action_index < 0 or action_index >= len(targets):
            return None
        return targets[action_index]

    def entry_bb_id(self, func_name: str) -> int:
        fn = self.function(func_name)
        entries = [b.id for b in fn.blocks if b.is_entry]
        if not entries:
            raise ValueError(f"No entry block for {func_name}")
        if len(entries) > 1:
            # Prefer lowest id for determinism
            return min(entries)
        return entries[0]
