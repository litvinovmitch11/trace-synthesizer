"""Smoke test: multi-program dataset build + global LSTM train on cross JSONL."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def test_build_multi_program_and_train_global(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = root / "tests" / "fixtures" / "test" / "main.cfg.json"
    comp = root / "tests" / "fixtures" / "test" / "main.compressed_trace.json"
    spec_dir = tmp_path / "spec_here"
    spec_dir.mkdir()
    a = spec_dir / "a.compressed_trace.json"
    b = spec_dir / "b.compressed_trace.json"
    shutil.copyfile(comp, a)
    shutil.copyfile(comp, b)
    spec = {
        "schema_version": 1,
        "entries": [
            {
                "id": "prog_a",
                "cfg": str(cfg.resolve()),
                "func": "main",
                "compressed_paths": [str(a.resolve())],
            },
            {
                "id": "prog_b",
                "cfg": str(cfg.resolve()),
                "func": "main",
                "compressed_paths": [str(b.resolve())],
            },
        ],
    }
    spec_path = spec_dir / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    out_dir = tmp_path / "dataset"

    r1 = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "build_multi_program_intra_dataset.py"),
            "--spec",
            str(spec_path),
            "--out-dir",
            str(out_dir),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert r1.returncode == 0, r1.stdout + r1.stderr
    index_path = out_dir / "dataset_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["schema_version"] == 2
    assert len(index["programs"]) == 2
    assert "cross_program_jsonl" in index
    cross_path = Path(index["cross_program_jsonl"])
    assert cross_path.is_file()
    cross = json.loads(cross_path.read_text(encoding="utf-8").splitlines()[0])
    assert cross["func"] == "main"
    assert "cfg" in cross and "sequence" in cross

    stem = tmp_path / "fw" / "global"
    r2 = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "train_feature_window_lstm.py"),
            "--dataset-jsonl",
            str(cross_path),
            "--func-filter",
            "main",
            "--out-stem",
            str(stem),
            "--window-back",
            "4",
            "--epochs",
            "30",
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
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert stem.with_suffix(".pt").is_file()
