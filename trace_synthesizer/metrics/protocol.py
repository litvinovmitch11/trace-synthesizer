"""Protocol for pluggable trace comparison metrics (proposal III.D)."""

from __future__ import annotations

from typing import Protocol

from trace_synthesizer.metrics.types import MetricContext, MetricResult, TracePath


class TraceMetric(Protocol):
    """Compare pooled reference traces vs pooled candidate traces."""

    @property
    def name(self) -> str:
        """Stable identifier (CLI ``--metrics`` / registry key)."""
        ...

    def compute(
        self,
        reference_paths: list[TracePath],
        candidate_paths: list[TracePath],
        ctx: MetricContext,
    ) -> MetricResult: ...
