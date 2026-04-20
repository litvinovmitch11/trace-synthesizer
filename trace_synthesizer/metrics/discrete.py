"""Discrete distributions from counts and KL(P || Q)."""

from __future__ import annotations

import math
from collections import Counter
from typing import Hashable, TypeVar

T = TypeVar("T", bound=Hashable)


def counts_to_probabilities(
    counts: Counter[T], support: set[T], epsilon: float
) -> dict[T, float]:
    """Laplace-style smoothing on a fixed support: p_i ∝ c_i + ε."""
    if not support:
        return {}
    total = sum(float(counts.get(k, 0)) + epsilon for k in support)
    return {k: (float(counts.get(k, 0)) + epsilon) / total for k in support}


def kl_divergence(p: dict[T, float], q: dict[T, float], support: set[T]) -> float:
    """KL(P || Q) = Σ p log(p/q) over support (p,q must be positive on support)."""
    acc = 0.0
    for k in support:
        pi = p[k]
        qi = q[k]
        if pi <= 0.0:
            continue
        if qi <= 0.0:
            return math.inf
        acc += pi * math.log(pi / qi)
    return acc
