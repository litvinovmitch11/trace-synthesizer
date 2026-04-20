"""JSON / JSONL writers for rollout artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from trace_synthesizer.io.intra_trace import (
    canonical_intra_trace_record,
    intra_sequence_from_bb_path,
)
from trace_synthesizer.runner.rollout import EpisodeRollout
from trace_synthesizer.runner.stats import RolloutSummary


def write_episodes_jsonl(
    path: str | Path, episodes: list[EpisodeRollout], *, seed: int
) -> None:
    p = Path(path)
    lines = []
    for i, ep in enumerate(episodes):
        lines.append(
            json.dumps(
                {
                    "episode": i,
                    "seed": seed,
                    "entry_bb_id": ep.entry_bb_id,
                    "termination": ep.termination,
                    "length": ep.length,
                    "steps": [asdict(s) for s in ep.steps],
                }
            )
        )
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_json(path: str | Path, summary: RolloutSummary) -> None:
    Path(path).write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")


def write_intra_traces_jsonl(
    path: str | Path,
    episodes: list[EpisodeRollout],
    function_name: str,
) -> None:
    """One JSON object per line: same `sequence` layout as compressed_trace.json."""
    lines = []
    for ep in episodes:
        seq = intra_sequence_from_bb_path(
            function_name, ep.entry_bb_id, [s.to_bb for s in ep.steps]
        )
        lines.append(
            json.dumps(
                canonical_intra_trace_record(
                    function_name=function_name,
                    sequence=seq,
                    episode=None,
                )
            )
        )
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
