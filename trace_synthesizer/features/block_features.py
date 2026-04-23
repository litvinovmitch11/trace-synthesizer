"""Unified per-block feature vector for observations (extensible)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import torch

from trace_synthesizer.domain.program import BasicBlock

if TYPE_CHECKING:
    pass


@dataclass
class BlockFeatures:
    """
    Scalar CFG features plus optional future embedding (IR2Vec, etc.).
    Extend by adding optional fields rather than parallel class hierarchies.
    """

    instr_count: float
    has_call: float
    out_degree: float
    max_out_prob: float
    mean_out_prob: float
    branch_instr_count: float
    conditional_branch_count: float
    unconditional_branch_count: float
    load_count: float
    store_count: float
    phi_count: float
    has_return: float
    has_indirect_branch: float
    loop_depth: float
    dom_tree_depth: float
    terminator_conditional: float
    terminator_unconditional: float
    terminator_return: float
    terminator_indirect: float
    terminator_other: float
    embedding: Optional[torch.Tensor] = None

    @classmethod
    def from_block(cls, block: BasicBlock) -> BlockFeatures:
        probs = [s.prob for s in block.successors if s.prob is not None]
        deg = len(block.successors)
        max_p = max(probs) if probs else 0.0
        mean_p = sum(probs) / len(probs) if probs else 0.0
        return cls(
            instr_count=float(block.instr_count),
            has_call=1.0 if block.has_call else 0.0,
            out_degree=float(deg),
            max_out_prob=float(max_p),
            mean_out_prob=float(mean_p),
            branch_instr_count=float(block.branch_instr_count),
            conditional_branch_count=float(block.conditional_branch_count),
            unconditional_branch_count=float(block.unconditional_branch_count),
            load_count=float(block.load_count),
            store_count=float(block.store_count),
            phi_count=float(block.phi_count),
            has_return=1.0 if block.has_return else 0.0,
            has_indirect_branch=1.0 if block.has_indirect_branch else 0.0,
            loop_depth=float(block.loop_depth),
            dom_tree_depth=float(block.dom_tree_depth),
            terminator_conditional=1.0
            if block.terminator_kind == "conditional_branch"
            else 0.0,
            terminator_unconditional=1.0
            if block.terminator_kind == "unconditional_branch"
            else 0.0,
            terminator_return=1.0 if block.terminator_kind == "return" else 0.0,
            terminator_indirect=1.0
            if block.terminator_kind == "indirect_branch"
            else 0.0,
            terminator_other=1.0
            if block.terminator_kind in {"other", "branch", "call"}
            else 0.0,
            embedding=(
                torch.tensor(list(block.ir2vec_embedding), dtype=torch.float32)
                if block.ir2vec_embedding is not None
                else None
            ),
        )

    def as_tensor(
        self,
        device: torch.device | str | None = None,
        dtype: torch.dtype = torch.float32,
    ) -> torch.Tensor:
        """Fixed-size base vector; appends flattened embedding if present."""
        parts = [
            self.instr_count,
            self.has_call,
            self.out_degree,
            self.max_out_prob,
            self.mean_out_prob,
            self.branch_instr_count,
            self.conditional_branch_count,
            self.unconditional_branch_count,
            self.load_count,
            self.store_count,
            self.phi_count,
            self.has_return,
            self.has_indirect_branch,
            self.loop_depth,
            self.dom_tree_depth,
            self.terminator_conditional,
            self.terminator_unconditional,
            self.terminator_return,
            self.terminator_indirect,
            self.terminator_other,
        ]
        base = torch.tensor(parts, device=device, dtype=dtype)
        if self.embedding is None:
            return base
        emb = self.embedding.to(device=device, dtype=dtype).flatten()
        return torch.cat([base, emb], dim=0)

    @property
    def base_dim(self) -> int:
        return 20
