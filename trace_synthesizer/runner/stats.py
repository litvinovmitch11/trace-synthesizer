"""Aggregate statistics over rollouts."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trace_synthesizer.runner.rollout import EpisodeRollout


@dataclass(frozen=True)
class RolloutSummary:
    num_episodes: int
    mean_length: float
    termination_counts: dict[str, int]
    edge_counts: dict[tuple[int, int], int]

    def to_dict(self) -> dict:
        return {
            "num_episodes": self.num_episodes,
            "mean_length": self.mean_length,
            "termination_counts": dict(self.termination_counts),
            "edge_counts": {f"{a}->{b}": c for (a, b), c in self.edge_counts.items()},
        }


def summarize_rollouts(episodes: list[EpisodeRollout]) -> RolloutSummary:
    if not episodes:
        return RolloutSummary(
            num_episodes=0,
            mean_length=0.0,
            termination_counts={},
            edge_counts={},
        )
    lengths = [e.length for e in episodes]
    term = Counter(e.termination for e in episodes)
    edges: Counter[tuple[int, int]] = Counter()
    for ep in episodes:
        for rec in ep.steps:
            edges[(rec.from_bb, rec.to_bb)] += 1
    mean_len = sum(lengths) / len(lengths) if lengths else 0.0
    return RolloutSummary(
        num_episodes=len(episodes),
        mean_length=mean_len,
        termination_counts=dict(term),
        edge_counts=dict(edges),
    )


def _num_stats(xs: list[int]) -> dict[str, float | int]:
    if not xs:
        return {"count": 0, "min": 0, "max": 0, "mean": 0.0}
    return {
        "count": len(xs),
        "min": min(xs),
        "max": max(xs),
        "mean": float(sum(xs) / len(xs)),
    }


def summarize_paths_from_runs_jsonl(path: str | Path) -> dict[str, Any]:
    """
    Per-episode path lengths from ``runs.jsonl`` (``rollout-random``), grouped by
    termination kind (``terminated`` = reached CFG sink / exit from modeled function).
    """
    p = Path(path)
    if not p.is_file():
        return {}
    by_term: dict[str, list[int]] = {}
    n = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        n += 1
        term = str(raw.get("termination", "unknown"))
        length = int(raw.get("length", 0))
        by_term.setdefault(term, []).append(length)
    out: dict[str, Any] = {
        "n_episodes": n,
        "by_termination": {},
    }
    for k, lengths in by_term.items():
        if lengths:
            out["by_termination"][k] = {
                "lengths": lengths,
                **_num_stats(lengths),
            }
    all_lengths = [x for v in by_term.values() for x in v]
    out["all_episodes"] = _num_stats(all_lengths)
    return out
