"""Typed results and context for trace comparison metrics."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetricContext:
    """Hyperparameters shared by several metrics."""

    function_name: str
    epsilon: float = 1e-8
    ngram_min: int = 2
    ngram_max: int = 4
    top_k: int = 64


@dataclass(frozen=True)
class MetricResult:
    """One scalar (or undefined) metric plus diagnostic payload."""

    name: str
    value: float | None
    details: dict[str, object] = field(default_factory=dict)


TracePath = list[tuple[str, int]]
