"""Canonical intra-trace JSON: identical schema for Dynamo export and rollouts."""

import json
from pathlib import Path

from trace_synthesizer.io.intra_trace import (
    CANONICAL_INTRA_TRACE_SOURCE,
    SCHEMA_VERSION,
    canonical_intra_trace_record,
    export_intra_trace_from_compressed_file,
    intra_sequence_from_bb_path,
)


def test_canonical_keys_and_source_match(tmp_path: Path) -> None:
    seq = [{"func": "f", "bb": 0}, {"func": "f", "bb": 1}]
    a = canonical_intra_trace_record(function_name="f", sequence=seq, episode=None)
    b = canonical_intra_trace_record(function_name="f", sequence=seq, episode=None)
    assert list(a.keys()) == list(b.keys())
    assert a["source"] == CANONICAL_INTRA_TRACE_SOURCE == "bb_trace"
    assert a["schema_version"] == SCHEMA_VERSION
    assert a["episode"] is None
    assert a["sequence"] == seq


def test_export_intra_matches_rollout_line_schema(tmp_path: Path) -> None:
    """Synthetic writer and export-intra must emit the same top-level keys."""
    from trace_synthesizer.runner.rollout import EpisodeRollout, StepRecord
    from trace_synthesizer.runner.writers import write_intra_traces_jsonl

    ep = EpisodeRollout(
        entry_bb_id=0,
        steps=(StepRecord(0, 0, 1, 0, 0.0, True, False),),
        termination="terminated",
    )
    jl = tmp_path / "a.jsonl"
    write_intra_traces_jsonl(jl, [ep], "f")
    line = jl.read_text(encoding="utf-8").strip()
    roll = json.loads(line)

    comp = tmp_path / "c.json"
    comp.write_text(
        json.dumps([{"func": "f", "bb": 0}, {"func": "f", "bb": 1}]), encoding="utf-8"
    )
    out = tmp_path / "b.json"
    export_intra_trace_from_compressed_file(comp, "f", out)
    ref = json.loads(Path(out).read_text(encoding="utf-8"))

    assert set(roll.keys()) == set(ref.keys())
    assert roll["source"] == ref["source"] == "bb_trace"


def test_intra_sequence_from_bb_path_preserves_repeats_when_requested() -> None:
    seq = intra_sequence_from_bb_path(
        "f", 0, [1, 1, 1, 2], dedupe_consecutive=False
    )
    assert [e["bb"] for e in seq] == [0, 1, 1, 1, 2]
    seq_d = intra_sequence_from_bb_path("f", 0, [1, 1, 1, 2], dedupe_consecutive=True)
    assert [e["bb"] for e in seq_d] == [0, 1, 2]
