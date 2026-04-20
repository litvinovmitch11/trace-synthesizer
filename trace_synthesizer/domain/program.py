"""Immutable CFG structures loaded from CFGDumper JSON."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class SuccessorEdge:
    """Single CFG edge with optional PGO probability."""

    target_id: int
    prob: Optional[float]
    is_fallthrough: bool


@dataclass(frozen=True)
class BasicBlock:
    """One machine basic block in a function."""

    id: int
    name: str
    is_entry: bool
    instr_count: int
    has_call: bool
    call_target: Optional[str]
    successors: tuple[SuccessorEdge, ...]


@dataclass(frozen=True)
class FunctionCFG:
    """CFG for one symbol (mangled or plain name)."""

    function_name: str
    blocks: tuple[BasicBlock, ...]

    def block_by_id(self) -> dict[int, BasicBlock]:
        return {b.id: b for b in self.blocks}


@dataclass(frozen=True)
class Program:
    """Whole-program CFG: function name -> CFG."""

    functions: tuple[FunctionCFG, ...]

    def by_name(self) -> dict[str, FunctionCFG]:
        return {f.function_name: f for f in self.functions}

    def get_function(self, name: str) -> FunctionCFG:
        m = self.by_name()
        if name not in m:
            from trace_synthesizer.domain.errors import UnknownFunctionError

            raise UnknownFunctionError(f"Unknown function: {name}")
        return m[name]
