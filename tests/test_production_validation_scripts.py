"""Smoke tests for production validation scripts (no full LLVM pipeline)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_production_validation_bash_syntax() -> None:
    root = Path(__file__).resolve().parents[1]
    sh = root / "scripts" / "run_production_validation_experiment.sh"
    r = subprocess.run(["bash", "-n", str(sh)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_train_feature_window_writes_checkpoint(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = root / "tests" / "fixtures" / "test" / "main.cfg.json"
    intra = {
        "cfg": str(cfg.resolve()),
        "func": "main",
        "sequence": [
            {"func": "main", "bb": 0},
            {"func": "main", "bb": 1},
            {"func": "main", "bb": 3},
        ],
    }
    ds = tmp_path / "cross.jsonl"
    ds.write_text(json.dumps(intra) + "\n", encoding="utf-8")
    stem = tmp_path / "ckpt" / "fw"
    report = tmp_path / "train.json"
    r = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "train_feature_window_lstm.py"),
            "--dataset-jsonl",
            str(ds),
            "--func-filter",
            "main",
            "--out-stem",
            str(stem),
            "--window-back",
            "4",
            "--epochs",
            "35",
            "--seed",
            "0",
            "--no-global-summary",
            "--succ-slots",
            "0",
            "--train-report",
            str(report),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert stem.with_suffix(".pt").is_file()
    assert stem.with_suffix(".json").is_file()
    assert report.is_file()
