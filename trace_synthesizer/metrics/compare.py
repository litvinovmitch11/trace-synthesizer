"""Run a named set of distribution / hot-path metrics on loaded paths."""

from __future__ import annotations

from trace_synthesizer.metrics.registry import DEFAULT_METRIC_ORDER, get_metric
from trace_synthesizer.metrics.types import MetricContext, MetricResult, TracePath


def run_metrics(
    reference_paths: list[TracePath],
    candidate_paths: list[TracePath],
    ctx: MetricContext,
    *,
    names: tuple[str, ...] = DEFAULT_METRIC_ORDER,
) -> list[MetricResult]:
    """``reference_paths`` / ``candidate_paths`` are lists of traces (one path each)."""
    out: list[MetricResult] = []
    for name in names:
        out.append(get_metric(name).compute(reference_paths, candidate_paths, ctx))
    return out


def results_to_jsonable(results: list[MetricResult]) -> list[dict[str, object]]:
    return [{"name": r.name, "value": r.value, "details": r.details} for r in results]
