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
            embedding=None,
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
        ]
        base = torch.tensor(parts, device=device, dtype=dtype)
        if self.embedding is None:
            return base
        emb = self.embedding.to(device=device, dtype=dtype).flatten()
        return torch.cat([base, emb], dim=0)

    @property
    def base_dim(self) -> int:
        return 5
