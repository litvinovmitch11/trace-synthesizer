"""Immutable CFG structures loaded from CFGDumper JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    branch_instr_count: int = 0
    conditional_branch_count: int = 0
    unconditional_branch_count: int = 0
    load_count: int = 0
    store_count: int = 0
    phi_count: int = 0
    has_return: bool = False
    has_indirect_branch: bool = False
    loop_depth: int = 0
    dom_tree_depth: int = 0
    pred_count: int = 0
    post_dom_tree_depth: int = 0
    is_loop_header: bool = False
    is_loop_latch: bool = False
    is_loop_exiting: bool = False
    back_edge_in_count: int = 0
    terminator_kind: str = "none"
    ir2vec_embedding: Optional[tuple[float, ...]] = None
    successors: tuple[SuccessorEdge, ...] = field(default_factory=tuple)


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
