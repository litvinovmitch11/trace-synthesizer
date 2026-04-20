"""Load trace paths from intra_trace JSON, JSONL, or compressed_trace JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trace_synthesizer.io.compress_pipeline import load_compressed_trace_json
from trace_synthesizer.io.intra_trace import intra_sequence_from_compressed
from trace_synthesizer.metrics.types import TracePath


def _events_to_path(events: list[dict[str, Any]]) -> TracePath:
    return [(str(e["func"]), int(e["bb"])) for e in events]


def load_path_from_intra_trace_json(path: str | Path) -> TracePath:
    """Single object with ``sequence``: list of {func, bb}."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "sequence" not in raw:
        raise ValueError(f"{path}: expected intra_trace JSON object with 'sequence'")
    seq = raw["sequence"]
    if not isinstance(seq, list):
        raise ValueError(f"{path}: 'sequence' must be a list")
    return _events_to_path(seq)


def load_paths_from_intra_traces_jsonl(path: str | Path) -> list[TracePath]:
    """One JSON object per line (rollout export)."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    out: list[TracePath] = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict) or "sequence" not in raw:
            raise ValueError(f"{path}:{i+1}: expected object with 'sequence'")
        out.append(_events_to_path(raw["sequence"]))
    return out


def load_path_from_compressed_trace(path: str | Path, function_name: str) -> TracePath:
    """Filter one function from global compressed trace and dedupe like compress."""
    compressed = load_compressed_trace_json(path)
    seq = intra_sequence_from_compressed(compressed, function_name)
    return _events_to_path(seq)
