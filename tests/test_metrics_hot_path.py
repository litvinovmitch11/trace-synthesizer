"""Hot-path n-gram overlap metric."""

from trace_synthesizer.metrics.hot_path import compute_hot_path_overlap
from trace_synthesizer.metrics.types import MetricContext, TracePath


def test_hot_path_perfect_overlap() -> None:
    seq: TracePath = [("main", 0), ("main", 1), ("main", 2), ("main", 3)]
    ctx = MetricContext(function_name="main", top_k=8, ngram_min=2, ngram_max=3)
    r = compute_hot_path_overlap([seq], [seq], ctx)
    assert r.value is not None
    assert r.value == 1.0
