"""Canonical intra-function trace format: identical JSON for Dynamo and synthetic.

Every record uses the same top-level keys and the same ``source`` string so
reference and generated traces are byte-for-byte comparable in schema (only
``sequence`` content differs).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from trace_synthesizer.io.compress_pipeline import load_compressed_trace_json

SCHEMA_VERSION = 1

# Single literal for both Dynamo export and rollout output (indistinguishable schema).
CANONICAL_INTRA_TRACE_SOURCE: Literal["bb_trace"] = "bb_trace"


def dedupe_consecutive_func_bb(pairs: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Same rule as `compress_bb_sequence`: drop consecutive duplicate (func, bb)."""
    out: list[tuple[str, int]] = []
    for p in pairs:
        if not out or out[-1] != p:
            out.append(p)
    return out


def pairs_to_events(pairs: list[tuple[str, int]]) -> list[dict[str, str | int]]:
    return [{"func": f, "bb": b} for f, b in pairs]


def intra_sequence_from_compressed(
    compressed: list[dict[str, str | int]], function_name: str
) -> list[dict[str, str | int]]:
    """Filter global compressed trace to one function, then dedupe consecutive BBs."""
    raw = [
        (str(e["func"]), int(e["bb"]))
        for e in compressed
        if str(e["func"]) == function_name
    ]
    return pairs_to_events(dedupe_consecutive_func_bb(raw))


def intra_sequence_from_bb_path(
    function_name: str, entry_bb_id: int, step_to_bbs: Sequence[int]
) -> list[dict[str, str | int]]:
    """BB visit order: entry block then each step's destination (same dedupe as compress)."""
    raw = [(function_name, entry_bb_id)] + [
        (function_name, int(b)) for b in step_to_bbs
    ]
    return pairs_to_events(dedupe_consecutive_func_bb(raw))


def canonical_intra_trace_record(
    *,
    function_name: str,
    sequence: list[dict[str, str | int]],
    episode: int | None = None,
) -> dict[str, object]:
    """
    Fixed schema for reference and synthetic traces.

    Keys and ``source`` are always the same; only ``sequence`` (and optionally
    ``episode``) differ. For strict pairwise files use ``episode=None``.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "function_name": function_name,
        "source": CANONICAL_INTRA_TRACE_SOURCE,
        "episode": episode,
        "sequence": sequence,
    }


def build_intra_trace_record(
    *,
    function_name: str,
    source: str | None = None,
    sequence: list[dict[str, str | int]],
    episode: int | None = None,
) -> dict[str, object]:
    """Backward-compatible wrapper; ``source`` is ignored (always ``bb_trace``)."""
    _ = source
    return canonical_intra_trace_record(
        function_name=function_name, sequence=sequence, episode=episode
    )


def export_intra_trace_from_compressed_file(
    compressed_path: str | Path,
    function_name: str,
    out_path: str | Path,
) -> None:
    compressed = load_compressed_trace_json(compressed_path)
    seq = intra_sequence_from_compressed(compressed, function_name)
    rec = canonical_intra_trace_record(
        function_name=function_name,
        sequence=seq,
        episode=None,
    )
    Path(out_path).write_text(
        json.dumps(rec, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )


def dump_canonical_intra_json(
    out_path: str | Path,
    *,
    function_name: str,
    sequence: list[dict[str, str | int]],
    episode: int | None = None,
) -> None:
    """Write a single canonical intra-trace JSON file."""
    rec = canonical_intra_trace_record(
        function_name=function_name, sequence=sequence, episode=episode
    )
    Path(out_path).write_text(
        json.dumps(rec, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )


def load_intra_trace_bbs_for_visualize(
    intra_path: str | Path, function_name: str
) -> list[int]:
    """BB visit order for ``visualize`` overlay (same function filter as metrics)."""
    raw = json.loads(Path(intra_path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "sequence" not in raw:
        raise ValueError(f"{intra_path}: expected intra trace JSON with 'sequence'")
    seq = raw["sequence"]
    if not isinstance(seq, list):
        raise ValueError("'sequence' must be a list")
    out: list[int] = []
    for ev in seq:
        if not isinstance(ev, dict):
            continue
        if str(ev.get("func")) != function_name:
            continue
        out.append(int(ev["bb"]))
    return out
