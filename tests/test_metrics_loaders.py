"""Loaders and metric registry."""

import json
from pathlib import Path

from trace_synthesizer.metrics.loaders import (
    load_path_from_intra_trace_json,
    load_paths_from_intra_traces_jsonl,
)
from trace_synthesizer.metrics.registry import (
    METRIC_REGISTRY,
    get_metric,
    list_registered_metrics,
    register_metric,
)
from trace_synthesizer.metrics.types import MetricContext, MetricResult, TracePath


def test_load_intra_json_and_jsonl(tmp_path: Path) -> None:
    one = {
        "schema_version": 1,
        "function_name": "main",
        "source": "x",
        "sequence": [{"func": "main", "bb": 0}, {"func": "main", "bb": 1}],
    }
    p1 = tmp_path / "a.json"
    p1.write_text(json.dumps(one), encoding="utf-8")
    assert load_path_from_intra_trace_json(p1) == [("main", 0), ("main", 1)]

    lines = [json.dumps({**one, "episode": i}) for i in range(2)]
    p2 = tmp_path / "b.jsonl"
    p2.write_text("\n".join(lines) + "\n", encoding="utf-8")
    paths = load_paths_from_intra_traces_jsonl(p2)
    assert len(paths) == 2
    assert paths[0] == [("main", 0), ("main", 1)]


def test_registry_lists_and_get() -> None:
    names = list_registered_metrics()
    assert "block_visit_kl" in names
    m = get_metric("block_visit_kl")
    assert m.name == "block_visit_kl"


class _DummyMetric:
    __slots__ = ("_name",)

    def __init__(self) -> None:
        self._name = "dummy_test_metric"

    @property
    def name(self) -> str:
        return self._name

    def compute(
        self,
        reference_paths: list[TracePath],
        candidate_paths: list[TracePath],
        ctx: MetricContext,
    ) -> MetricResult:
        return MetricResult(name=self.name, value=3.14, details={})


def test_register_custom_metric() -> None:
    try:
        register_metric(_DummyMetric())
        m = get_metric("dummy_test_metric")
        r = m.compute([], [], MetricContext(function_name="main"))
        assert r.value == 3.14
    finally:
        METRIC_REGISTRY.pop("dummy_test_metric", None)
