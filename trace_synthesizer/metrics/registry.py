"""Registry of built-in metrics; extend by adding a ``TraceMetric`` implementation."""

from __future__ import annotations

from typing import Callable

from trace_synthesizer.metrics.block_frequency import compute_block_visit_kl
from trace_synthesizer.metrics.edge_transition import compute_edge_transition_kl
from trace_synthesizer.metrics.hot_path import compute_hot_path_overlap
from trace_synthesizer.metrics.protocol import TraceMetric
from trace_synthesizer.metrics.types import MetricContext, MetricResult, TracePath

MetricComputeFn = Callable[
    [list[TracePath], list[TracePath], MetricContext],
    MetricResult,
]


class CallableTraceMetric:
    """Wraps a plain function as a ``TraceMetric`` (structural implementation)."""

    __slots__ = ("name", "_compute")

    def __init__(self, name: str, compute_fn: MetricComputeFn) -> None:
        self.name = name
        self._compute = compute_fn

    def compute(
        self,
        reference_paths: list[TracePath],
        candidate_paths: list[TracePath],
        ctx: MetricContext,
    ) -> MetricResult:
        return self._compute(reference_paths, candidate_paths, ctx)


def _builtins() -> dict[str, TraceMetric]:
    ms: tuple[CallableTraceMetric, ...] = (
        CallableTraceMetric("block_visit_kl", compute_block_visit_kl),
        CallableTraceMetric("edge_transition_kl", compute_edge_transition_kl),
        CallableTraceMetric("hot_path_ngram_overlap", compute_hot_path_overlap),
    )
    return {m.name: m for m in ms}


METRIC_REGISTRY: dict[str, TraceMetric] = _builtins()

DEFAULT_METRIC_ORDER: tuple[str, ...] = (
    "block_visit_kl",
    "edge_transition_kl",
    "hot_path_ngram_overlap",
)


def register_metric(metric: TraceMetric) -> None:
    """Register or replace a metric under ``metric.name`` (plugins, experiments)."""
    METRIC_REGISTRY[metric.name] = metric


def list_registered_metrics() -> tuple[str, ...]:
    """Deterministic order: built-in order first, then any extras alphabetically."""
    known = [n for n in DEFAULT_METRIC_ORDER if n in METRIC_REGISTRY]
    rest = sorted(n for n in METRIC_REGISTRY if n not in known)
    return tuple(known + rest)


def get_metric(name: str) -> TraceMetric:
    if name not in METRIC_REGISTRY:
        raise KeyError(f"Unknown metric {name!r}; known: {list_registered_metrics()}")
    return METRIC_REGISTRY[name]
