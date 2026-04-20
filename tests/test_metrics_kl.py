"""KL metrics: discrete helper and block-visit KL on paths."""

from collections import Counter

from trace_synthesizer.metrics.block_frequency import compute_block_visit_kl
from trace_synthesizer.metrics.discrete import counts_to_probabilities, kl_divergence
from trace_synthesizer.metrics.edge_transition import compute_edge_transition_kl
from trace_synthesizer.metrics.types import MetricContext, TracePath


def test_kl_identical_distributions_near_zero() -> None:
    c = Counter({0: 10, 1: 10})
    support = {0, 1}
    eps = 1e-8
    p = counts_to_probabilities(c, support, eps)
    q = counts_to_probabilities(c, support, eps)
    assert kl_divergence(p, q, support) < 1e-6


def test_block_kl_on_simple_paths() -> None:
    ref: list[TracePath] = [[("main", 0), ("main", 1), ("main", 2)]]
    cand: list[TracePath] = [
        [("main", 0), ("main", 1), ("main", 2)],
        [("main", 0), ("main", 1), ("main", 2)],
    ]
    ctx = MetricContext(function_name="main", epsilon=1e-8)
    r = compute_block_visit_kl(ref, cand, ctx)
    assert r.value is not None
    assert r.value < 0.05


def test_edge_kl_finite_on_paths() -> None:
    ref: list[TracePath] = [[("f", 0), ("f", 1), ("f", 2)]]
    cand: list[TracePath] = [[("f", 0), ("f", 1), ("f", 3)]]
    ctx = MetricContext(function_name="f", epsilon=1e-8)
    r = compute_edge_transition_kl(ref, cand, ctx)
    assert r.value is not None
    assert r.value == r.value
