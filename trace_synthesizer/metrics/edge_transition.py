"""KL over empirical distributions of consecutive (BB_i, BB_{i+1}) transitions."""

from __future__ import annotations

from collections import Counter
from typing import Tuple

from trace_synthesizer.metrics.discrete import counts_to_probabilities, kl_divergence
from trace_synthesizer.metrics.types import MetricContext, MetricResult, TracePath

Edge = Tuple[int, int]


def _edge_counts(paths: list[TracePath], func: str) -> Counter[Edge]:
    c: Counter[Edge] = Counter()
    for path in paths:
        bbs = [bb for f, bb in path if f == func]
        for a, b in zip(bbs, bbs[1:], strict=False):
            c[(a, b)] += 1
    return c


def compute_edge_transition_kl(
    reference_paths: list[TracePath],
    candidate_paths: list[TracePath],
    ctx: MetricContext,
) -> MetricResult:
    er = _edge_counts(reference_paths, ctx.function_name)
    ec = _edge_counts(candidate_paths, ctx.function_name)
    if sum(er.values()) == 0 or sum(ec.values()) == 0:
        return MetricResult(
            name="edge_transition_kl",
            value=None,
            details={
                "reason": "no_transitions_in_reference_or_candidate",
                "reference_edges": int(sum(er.values())),
                "candidate_edges": int(sum(ec.values())),
            },
        )
    support = set(er.keys()) | set(ec.keys())
    p = counts_to_probabilities(er, support, ctx.epsilon)
    q = counts_to_probabilities(ec, support, ctx.epsilon)
    kl = kl_divergence(p, q, support)
    kl_rev = kl_divergence(q, p, support)
    return MetricResult(
        name="edge_transition_kl",
        value=float(kl),
        details={
            "kl_reference_given_candidate": float(kl_rev),
            "symmetrized_kl": float(0.5 * (kl + kl_rev)),
            "support_size": len(support),
            "reference_edges": int(sum(er.values())),
            "candidate_edges": int(sum(ec.values())),
        },
    )
