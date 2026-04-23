"""Cross-program feature-window LSTM: train + rollout-lstm dispatch."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def test_train_feature_window_and_rollout_cli(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = root / "tests" / "fixtures" / "test" / "main.cfg.json"
    comp = root / "tests" / "fixtures" / "test" / "main.compressed_trace.json"
    a = tmp_path / "t1.compressed_trace.json"
    b = tmp_path / "t2.compressed_trace.json"
    shutil.copyfile(comp, a)
    shutil.copyfile(comp, b)

    seq = json.loads(comp.read_text(encoding="utf-8"))
    assert isinstance(seq, list)
    lines = []
    for p in (a, b):
        lines.append(
            json.dumps(
                {
                    "cfg": str(cfg.resolve()),
                    "func": "main",
                    "sequence": seq,
                    "program_id": p.stem,
                }
            )
        )
    ds = tmp_path / "cross.jsonl"
    ds.write_text("\n".join(lines) + "\n", encoding="utf-8")
    stem = tmp_path / "fw" / "ckpt"
    r1 = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "train_feature_window_lstm.py"),
            "--dataset-jsonl",
            str(ds),
            "--func-filter",
            "main",
            "--window-back",
            "4",
            "--out-stem",
            str(stem),
            "--epochs",
            "40",
            "--seed",
            "0",
            "--no-global-summary",
            "--succ-slots",
            "0",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert stem.with_suffix(".pt").is_file()
    meta = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["policy_type"] == "feature_window_lstm"

    roll = tmp_path / "roll"
    r2 = subprocess.run(
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "rollout-lstm",
            "--cfg",
            str(cfg),
            "--func",
            "main",
            "--episodes",
            "2",
            "--seed",
            "1",
            "--max-steps",
            "500",
            "--out-dir",
            str(roll),
            "--checkpoint",
            str(stem),
            "--device",
            "cpu",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert (roll / "summary.json").is_file()
