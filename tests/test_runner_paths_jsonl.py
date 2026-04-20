"""Path-length summaries from runs.jsonl."""

import json
from pathlib import Path

from trace_synthesizer.runner.stats import summarize_paths_from_runs_jsonl


def test_summarize_paths_from_runs_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "runs.jsonl"
    rows = [
        {"episode": 0, "termination": "terminated", "length": 10},
        {"episode": 1, "termination": "terminated", "length": 20},
        {"episode": 2, "termination": "truncated", "length": 2000},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    s = summarize_paths_from_runs_jsonl(p)
    assert s["n_episodes"] == 3
    assert s["by_termination"]["terminated"]["mean"] == 15.0
    assert s["by_termination"]["terminated"]["min"] == 10
    assert s["by_termination"]["truncated"]["max"] == 2000
