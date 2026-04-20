"""Compare real vs synthetic intra-function traces (proposal III.D metrics)."""

from trace_synthesizer.metrics.block_frequency import compute_block_visit_kl
from trace_synthesizer.metrics.compare import (
    DEFAULT_METRIC_ORDER,
    results_to_jsonable,
    run_metrics,
)
from trace_synthesizer.metrics.edge_transition import compute_edge_transition_kl
from trace_synthesizer.metrics.hot_path import compute_hot_path_overlap
from trace_synthesizer.metrics.loaders import (
    load_path_from_compressed_trace,
    load_path_from_intra_trace_json,
    load_paths_from_intra_traces_jsonl,
)
from trace_synthesizer.metrics.protocol import TraceMetric
from trace_synthesizer.metrics.registry import (
    METRIC_REGISTRY,
    get_metric,
    list_registered_metrics,
    register_metric,
)
from trace_synthesizer.metrics.speed import benchmark_random_rollouts, speedup_vs_dynamo
from trace_synthesizer.metrics.types import MetricContext, MetricResult, TracePath

__all__ = [
    "DEFAULT_METRIC_ORDER",
    "METRIC_REGISTRY",
    "MetricContext",
    "MetricResult",
    "TraceMetric",
    "TracePath",
    "benchmark_rollout_seconds",
    "benchmark_random_rollouts",
    "compute_block_visit_kl",
    "compute_edge_transition_kl",
    "compute_hot_path_overlap",
    "get_metric",
    "list_registered_metrics",
    "load_path_from_compressed_trace",
    "load_path_from_intra_trace_json",
    "load_paths_from_intra_traces_jsonl",
    "register_metric",
    "results_to_jsonable",
    "run_metrics",
    "speedup_vs_dynamo",
]
