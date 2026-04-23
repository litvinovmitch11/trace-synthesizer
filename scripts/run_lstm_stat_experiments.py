#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

from trace_synthesizer.metrics.compare import results_to_jsonable, run_metrics
from trace_synthesizer.metrics.loaders import (
    load_path_from_compressed_trace,
    load_paths_from_intra_traces_jsonl,
)
from trace_synthesizer.metrics.types import MetricContext


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _ci95_half_width(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    # normal approximation (sufficient for quick experimental reporting)
    return 1.96 * _std(xs) / math.sqrt(len(xs))


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--cfg", type=Path, default=Path("output/lstm_eval/benchmark_complex.cfg.json"))
    p.add_argument("--func", default="main")
    p.add_argument("--checkpoint", type=Path, default=Path("output/train_lstm/model"))
    p.add_argument("--out-dir", type=Path, default=Path("output/stat_runs"))
    p.add_argument("--episodes", type=int, default=32)
    p.add_argument("--max-steps", type=int, default=8000)
    p.add_argument("--seeds", default="17,23,31,43,59")
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--ngram-min", type=int, default=2)
    p.add_argument("--ngram-max", type=int, default=4)
    p.add_argument("--top-k", type=int, default=64)
    args = p.parse_args()

    root = args.root.resolve()
    out_dir = (root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = (root / args.cfg).resolve()
    checkpoint = (root / args.checkpoint).resolve()
    func = str(args.func)
    seeds = [int(x.strip()) for x in str(args.seeds).split(",") if x.strip()]
    if not seeds:
        raise SystemExit("no seeds provided")

    # Reference pool: all DR runs instead of one trace.
    dr_root = (root / "output/lstm_eval/dr_runs").resolve()
    dr_paths = sorted(dr_root.glob("*/benchmark_complex.compressed_trace.json"))
    if not dr_paths:
        raise SystemExit(f"no reference DR traces found under {dr_root}")
    ref_paths = [load_path_from_compressed_trace(p, func) for p in dr_paths]

    per_seed: list[dict] = []
    by_metric: dict[str, list[float]] = {
        "block_visit_kl": [],
        "edge_transition_kl": [],
        "hot_path_ngram_overlap": [],
    }
    for seed in seeds:
        roll_dir = out_dir / f"seed_{seed}"
        roll_dir.mkdir(parents=True, exist_ok=True)
        _run(
            [
                "poetry",
                "run",
                "python3",
                "-m",
                "trace_synthesizer",
                "rollout-lstm",
                "--cfg",
                str(cfg),
                "--func",
                func,
                "--episodes",
                str(int(args.episodes)),
                "--seed",
                str(seed),
                "--max-steps",
                str(int(args.max_steps)),
                "--out-dir",
                str(roll_dir),
                "--checkpoint",
                str(checkpoint),
                "--action-select",
                "sample",
                "--temperature",
                str(float(args.temperature)),
                "--device",
                "cpu",
            ],
            cwd=root,
        )
        cand_paths = load_paths_from_intra_traces_jsonl(roll_dir / "intra_traces.jsonl")
        ctx = MetricContext(
            function_name=func,
            ngram_min=int(args.ngram_min),
            ngram_max=int(args.ngram_max),
            top_k=int(args.top_k),
        )
        rs = run_metrics(ref_paths, cand_paths, ctx)
        packed = results_to_jsonable(rs)
        row = {"seed": seed, "metrics": packed}
        per_seed.append(row)
        for m in packed:
            n = str(m["name"])
            if n in by_metric and m["value"] is not None:
                by_metric[n].append(float(m["value"]))

    agg = {}
    for name, vals in by_metric.items():
        agg[name] = {
            "n_runs": len(vals),
            "mean": _mean(vals),
            "std": _std(vals),
            "ci95_half_width": _ci95_half_width(vals),
            "ci95": [_mean(vals) - _ci95_half_width(vals), _mean(vals) + _ci95_half_width(vals)]
            if vals
            else [None, None],
            "values": vals,
        }

    report = {
        "cfg": str(cfg),
        "function": func,
        "checkpoint": str(checkpoint),
        "episodes_per_seed": int(args.episodes),
        "max_steps": int(args.max_steps),
        "action_select": "sample",
        "temperature": float(args.temperature),
        "seeds": seeds,
        "reference_pool_size": len(ref_paths),
        "per_seed": per_seed,
        "aggregate": agg,
    }
    out_path = out_dir / "stats_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out_path)}, indent=2))


if __name__ == "__main__":
    main()
