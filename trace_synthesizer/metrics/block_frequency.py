"""KL divergence between empirical basic-block visit distributions."""

from __future__ import annotations

from collections import Counter

from trace_synthesizer.metrics.discrete import counts_to_probabilities, kl_divergence
from trace_synthesizer.metrics.types import MetricContext, MetricResult, TracePath


def _visit_counts(paths: list[TracePath], func: str) -> Counter[int]:
    c: Counter[int] = Counter()
    for path in paths:
        for f, bb in path:
            if f == func:
                c[bb] += 1
    return c


def compute_block_visit_kl(
    reference_paths: list[TracePath],
    candidate_paths: list[TracePath],
    ctx: MetricContext,
) -> MetricResult:
    """
    Pool all visits in reference_paths vs candidate_paths, build P, Q on union BB ids.
    Reports KL(P_ref || Q_cand) and symmetric KL in details.
    """
    cr = _visit_counts(reference_paths, ctx.function_name)
    cc = _visit_counts(candidate_paths, ctx.function_name)
    total_r = sum(cr.values())
    total_c = sum(cc.values())
    if total_r == 0 or total_c == 0:
        return MetricResult(
            name="block_visit_kl",
            value=None,
            details={
                "reason": "empty_reference_or_candidate_visits",
                "reference_visits": total_r,
                "candidate_visits": total_c,
            },
        )
    support = set(cr.keys()) | set(cc.keys())
    p = counts_to_probabilities(cr, support, ctx.epsilon)
    q = counts_to_probabilities(cc, support, ctx.epsilon)
    kl = kl_divergence(p, q, support)
    kl_rev = kl_divergence(q, p, support)
    return MetricResult(
        name="block_visit_kl",
        value=float(kl),
        details={
            "kl_reference_given_candidate": float(kl_rev),
            "symmetrized_kl": float(0.5 * (kl + kl_rev)),
            "support_size": len(support),
            "reference_visits": total_r,
            "candidate_visits": total_c,
        },
    )
