#!/usr/bin/env python3
"""Multi-seed experiment runner

Runs each benchmark/method N times and records the three comparison metrics so
that means and confidence intervals can be reported instead of single-seed point
estimates. Two modes:

  --mode retrain      Full pipeline per seed: (re)build artifacts once, then for
                      every seed retrain LSTM/Flat/HRL with that seed, roll out
                      with that seed, and score. Captures TRUE run-to-run
                      variance (BC init + PPO + env + rollout).

  --mode rollout-only Reuse the committed seed-42 checkpoints and only re-roll
                      with N different sampling seeds. The
                      interval reflects rollout sampling noise of a *fixed*
                      policy, not training variance.

  --mode summarize    Read a results JSON produced by the two modes above and
                      print mean +/- 95% CI (Student t, small n) markdown tables.

Examples
--------
    # fast sampling-variance run (reuses committed checkpoints)
    PYTHONPATH=. poetry run python3 scripts/run_multiseed.py \
        --mode rollout-only --seeds 1 2 3 4 5 \
        --out benchmarks/local/multiseed_rollout.json

    # full training-variance run (do this on your own machine; ~2-3 h)
    PYTHONPATH=. poetry run python3 scripts/run_multiseed.py \
        --mode retrain --seeds 42 43 44 45 46 \
        --out benchmarks/local/multiseed_retrain.json

    # turn either JSON into mean +/- CI tables
    PYTHONPATH=. poetry run python3 scripts/run_multiseed.py \
        --mode summarize --in benchmarks/local/multiseed_retrain.json

The raw JSON is written incrementally after every (benchmark, seed) so a crash
or Ctrl-C still leaves usable partial results.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(".")
PY = sys.executable
METRIC_KEYS = ("block_visit_kl", "edge_transition_kl", "hot_path_ngram_overlap")

# --------------------------------------------------------------------------- #
# Benchmark declarations. One entry per thesis benchmark. Paths are relative to
# the repo root. `train` reward flags mirror scripts/run_*_exp.py exactly.
# --------------------------------------------------------------------------- #
B = "benchmarks/local"


def _bench(
    *,
    key,
    table,
    func,
    train_build,
    train_stem,  # base file stem inside the build dir (e.g. "trigger")
    iters,
    max_steps,
    use_loop_profile,
    models,
    eval_targets,  # list of (label, eval_build, eval_stem)
    committed,  # {model: committed checkpoint stem name in <out>}
    src=None,
    out=None,
):
    out = out or f"{B}/{key}/out"
    return {
        "key": key,
        "table": table,
        "func": func,
        "src": src,
        "train_build": f"{B}/{train_build}",
        "train_cfg": f"{B}/{train_build}/{train_stem}.cfg.json",
        "train_comp": f"{B}/{train_build}/{train_stem}.compressed_trace.json",
        "loop_profile": f"{B}/{train_build}/loop_profile.json" if use_loop_profile else None,
        "iters": iters,
        "max_steps": max_steps,
        "models": models,
        "out": out,
        "eval_targets": [
            {
                "label": lbl,
                "cfg": f"{B}/{eb}/{es}.cfg.json",
                "ref_intra": f"{B}/{eb}/{es}_reference_intra.json",
            }
            for (lbl, eb, es) in eval_targets
        ],
        "committed": committed,
    }


BENCHMARKS = {
    "trigger": _bench(
        key="cpp_trigger", table="7.3", func="main",
        src=f"{B}/cpp_trigger/trigger.cpp",
        train_build="cpp_trigger/build", train_stem="trigger",
        iters=10, max_steps=1500, use_loop_profile=True,
        models=["pgo", "lstm", "flat", "hrl"],
        eval_targets=[("", "cpp_trigger/build", "trigger")],
        committed={"lstm": "lstm_ckpt", "flat": "flat_ckpt", "hrl": "hierarchical_ckpt"},
    ),
    "diamond": _bench(
        key="cpp_diamond", table="7.4", func="main",
        src=f"{B}/cpp_diamond/diamond.cpp",
        train_build="cpp_diamond/build", train_stem="diamond",
        iters=10, max_steps=1500, use_loop_profile=True,
        models=["flat", "hrl"],
        eval_targets=[("", "cpp_diamond/build", "diamond")],
        committed={"flat": "flat_ckpt", "hrl": "hierarchical_ckpt"},
    ),
    "mutation": _bench(
        key="cpp_mutation", table="7.5", func="main",
        src=f"{B}/cpp_mutation/trigger_base.cpp",
        train_build="cpp_mutation/build_base", train_stem="trigger_base",
        iters=15, max_steps=2000, use_loop_profile=False,
        models=["pgo", "lstm", "flat", "hrl"],
        eval_targets=[("", "cpp_mutation/build_mutated", "trigger_mutated")],
        committed={"lstm": "lstm_ckpt", "flat": "flat_ckpt", "hrl": "hrl_ckpt"},
    ),
    "sorting": _bench(
        key="cpp_sorting_mutation", table="7.6", func="_Z10sort_arrayPii",
        src=f"{B}/cpp_sorting_mutation/sort_base.cpp",
        train_build="cpp_sorting_mutation/build_base", train_stem="sort_base",
        iters=15, max_steps=2000, use_loop_profile=False,
        models=["pgo", "lstm", "flat", "hrl"],
        eval_targets=[("", "cpp_sorting_mutation/build_mutated", "sort_mutated")],
        committed={"lstm": "lstm_ckpt", "flat": "flat_ckpt", "hrl": "hrl_ckpt"},
    ),
    "smart": _bench(
        key="cpp_smart_mutation", table="7.7-7.8", func="_Z7processi",
        src=f"{B}/cpp_smart_mutation/smart_base.cpp",
        train_build="cpp_smart_mutation/build_base", train_stem="smart_base",
        iters=15, max_steps=2000, use_loop_profile=False,
        models=["pgo", "lstm", "flat", "hrl"],
        eval_targets=[("", "cpp_smart_mutation/build_mutated", "smart_mutated")],
        committed={"lstm": "lstm_ckpt", "flat": "flat_ckpt", "hrl": "hrl_ckpt"},
    ),
    "opt": _bench(
        key="cpp_opt_levels", table="7.10", func="_Z17complex_algorithmi",
        src=f"{B}/cpp_opt_levels/complex_opt.cpp",
        train_build="cpp_opt_levels/build_O0", train_stem="complex_opt",
        iters=15, max_steps=2000, use_loop_profile=False,
        models=["pgo", "lstm", "flat", "hrl"],
        eval_targets=[
            ("O0", "cpp_opt_levels/build_O0", "complex_opt"),
            ("O1", "cpp_opt_levels/build_O1", "complex_opt"),
            ("O2", "cpp_opt_levels/build_O2", "complex_opt"),
            ("O3", "cpp_opt_levels/build_O3", "complex_opt"),
        ],
        committed={"lstm": "lstm_ckpt_O0", "flat": "flat_ckpt_O0", "hrl": "hrl_ckpt_O0"},
    ),
}


# --------------------------------------------------------------------------- #
# Subprocess helpers
# --------------------------------------------------------------------------- #
def run(cmd: list[str]) -> None:
    print(f"  [exec] {' '.join(str(c) for c in cmd)}", flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def cli(*args) -> list[str]:
    return [PY, "-m", "trace_synthesizer", *args]


def check_artifacts(bench: dict, mode: str) -> list[str]:
    """Return the list of REQUIRED input files that are missing.

    CFG / reference / loop-profile are all seed-independent, so both modes simply
    reuse whatever `make exp-<name>` already produced under benchmarks/local/...
    (the committed local build dirs). In rollout-only mode the committed seed-42
    checkpoints are required as well. If anything is missing we tell the user
    which `make` target regenerates it and skip the benchmark.
    """
    need = [bench["train_cfg"], bench["train_comp"]]
    if bench["loop_profile"]:
        need.append(bench["loop_profile"])
    for et in bench["eval_targets"]:
        need += [et["cfg"], et["ref_intra"]]
    if mode == "rollout-only":
        for m in bench["models"]:
            if m == "pgo":
                continue
            need.append(f"{bench['out']}/{bench['committed'][m]}.pt")
    return [p for p in need if not Path(p).exists()]


def train_one(bench: dict, model: str, seed: int, stem: Path) -> None:
    """Train a single model for one seed. model in {lstm, flat, hrl}."""
    func = bench["func"]
    cfg = bench["train_cfg"]
    comp = bench["train_comp"]

    if model == "lstm":
        ds = stem.parent / f"dataset_{bench['key']}.jsonl"
        ds.write_text(
            json.dumps(
                {
                    "cfg": str(Path(cfg).resolve()),
                    "func": func,
                    "sequence": json.loads(Path(comp).read_text()),
                    "program_id": bench["key"],
                }
            )
            + "\n"
        )
        run(
            [
                PY, "scripts/train_feature_window_lstm.py",
                "--dataset-jsonl", ds, "--func-filter", func,
                "--out-stem", stem, "--epochs", "20", "--seed", seed,
            ]
        )
        return

    cmd = cli(
        "train-hrl-ppo",
        "--cfg", cfg, "--func", func, "--out-stem", stem,
        "--device", "cpu", "--seed", seed,
        "--iterations", bench["iters"], "--steps-per-iter", "1024",
        "--epochs", "4", "--minibatch-size", "128",
        "--reference", comp, "--reference-compressed",
        "--terminal-kl-scale", "100.0", "--pgo-log-scale", "0.0",
        "--max-steps", bench["max_steps"], "--window-back", "8", "--bc-epochs", "10",
    )
    if bench["loop_profile"]:
        cmd += [
            "--loop-profile", bench["loop_profile"],
            "--loop-timing-scale", "20.0",
            "--ref-edge-log-scale", "1.0",
            "--short-path-penalty-scale", "100.0",
        ]
    if model == "hrl":
        cmd += ["--hierarchical", "--num-modes", "4", "--manager-every", "4"]
    run(cmd)


def rollout_and_score(bench, model, seed, stem, target, roll_dir) -> dict:
    """Roll out one model on one eval target and return the metric dict."""
    func = bench["func"]
    cfg = target["cfg"]
    ref = target["ref_intra"]
    ms = bench["max_steps"]
    roll_dir.mkdir(parents=True, exist_ok=True)

    if model == "pgo":
        cmd = cli("rollout-random", "--cfg", cfg, "--func", func,
                  "--episodes", "10", "--seed", seed, "--max-steps", ms,
                  "--out-dir", roll_dir)
    elif model == "lstm":
        cmd = cli("rollout-lstm", "--cfg", cfg, "--func", func,
                  "--episodes", "10", "--seed", seed, "--max-steps", ms,
                  "--checkpoint", stem, "--out-dir", roll_dir)
    else:  # flat / hrl
        cmd = cli("rollout-hrl", "--cfg", cfg, "--func", func,
                  "--episodes", "10", "--seed", seed, "--max-steps", ms,
                  "--checkpoint", stem, "--action-select", "sample",
                  "--window-back", "8", "--out-dir", roll_dir)
    run(cmd)

    met_path = roll_dir / "metrics.json"
    run(cli("metrics-compare", "--reference", ref,
            "--candidate", roll_dir / "intra_traces.jsonl",
            "--func", func, "--out", met_path))

    report = json.loads(met_path.read_text())
    rec = {m["name"]: m["value"] for m in report["metrics"]}
    summ = roll_dir / "summary.json"
    if summ.exists():
        rec["mean_length"] = json.loads(summ.read_text()).get("mean_length")
    return rec


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def stem_for(bench, model, mode, seed, seed_dir):
    if model == "pgo":
        return None  # Random-PGO has no checkpoint
    if mode == "rollout-only":
        return Path(bench["out"]) / bench["committed"][model]
    return seed_dir / f"{model}_ckpt"


def run_sweep(args) -> None:
    selected = args.benchmarks or list(BENCHMARKS)
    seeds = args.seeds
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = {}
    if out_path.exists():  # resume / append
        results = json.loads(out_path.read_text())
    results.setdefault("_meta", {})
    results["_meta"].update(
        {"mode": args.mode, "seeds": seeds, "episodes_per_rollout": 10,
         "metric_keys": list(METRIC_KEYS), "generated": time.strftime("%Y-%m-%d %H:%M:%S")}
    )

    for bkey in selected:
        bench = BENCHMARKS[bkey]
        print(f"\n{'='*70}\n{bkey}  (thesis Table {bench['table']})  mode={args.mode}\n{'='*70}", flush=True)
        results.setdefault(bkey, {})

        missing = check_artifacts(bench, args.mode)
        if missing:
            print(f"  !! SKIP {bkey}: missing inputs (run `make exp-{bkey}` first):", flush=True)
            for p in missing:
                print(f"       {p}", flush=True)
            continue

        for seed in seeds:
            seed_dir = Path(bench["out"]) / "multiseed" / args.mode / f"seed{seed}"
            seed_dir.mkdir(parents=True, exist_ok=True)

            # Train (retrain mode only; pgo never trains).
            if args.mode == "retrain":
                for model in bench["models"]:
                    if model == "pgo":
                        continue
                    try:
                        train_one(bench, model, seed, stem_for(bench, model, args.mode, seed, seed_dir))
                    except subprocess.CalledProcessError as e:
                        print(f"  !! train {bkey}/{model}/seed{seed} failed: {e}", flush=True)

            # Roll out + score every (model, eval target).
            for model in bench["models"]:
                stem = stem_for(bench, model, args.mode, seed, seed_dir)
                for target in bench["eval_targets"]:
                    cell = f"{model}@{target['label']}" if target["label"] else model
                    rd = seed_dir / f"roll_{model}_{target['label'] or 'main'}"
                    try:
                        rec = rollout_and_score(bench, model, seed, stem, target, rd)
                    except subprocess.CalledProcessError as e:
                        print(f"  !! rollout {bkey}/{cell}/seed{seed} failed: {e}", flush=True)
                        rec = {"error": str(e)}
                    results[bkey].setdefault(cell, {})[str(seed)] = rec
                    if "error" not in rec:
                        print(f"  >> {cell} seed{seed}: "
                              f"KL={rec.get('block_visit_kl'):.3f} "
                              f"overlap={rec.get('hot_path_ngram_overlap'):.3f} "
                              f"len={rec.get('mean_length')}", flush=True)

            out_path.write_text(json.dumps(results, indent=2))  # incremental save
            print(f"  (saved partial results to {out_path})", flush=True)

    print(f"\nDone. Raw results in {out_path}\nSummarize with:  "
          f"python3 scripts/run_multiseed.py --mode summarize --in {out_path}", flush=True)


# --------------------------------------------------------------------------- #
# Summary statistics
# --------------------------------------------------------------------------- #
# Two-sided 95% Student-t critical values by degrees of freedom (n-1).
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
        7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 14: 2.145, 19: 2.093, 29: 2.045}


def _ci95(values: list[float]) -> dict:
    vals = [v for v in values if isinstance(v, (int, float))]
    n = len(vals)
    if n == 0:
        return {"n": 0}
    mean = statistics.fmean(vals)
    if n == 1:
        return {"n": 1, "mean": mean, "std": 0.0, "ci95": 0.0, "min": vals[0], "max": vals[0]}
    sd = statistics.stdev(vals)
    t = _T95.get(n - 1, 1.96)
    half = t * sd / math.sqrt(n)
    return {"n": n, "mean": mean, "std": sd, "ci95": half, "min": min(vals), "max": max(vals)}


def summarize(in_path: str) -> None:
    data = json.loads(Path(in_path).read_text())
    meta = data.get("_meta", {})
    print(f"# Multi-seed summary  (mode={meta.get('mode')}, seeds={meta.get('seeds')})\n")
    for bkey, cells in data.items():
        if bkey == "_meta":
            continue
        print(f"\n## {bkey}\n")
        print("| cell | n | block_visit_kl (mean ± 95% CI) | edge_kl | hot_path_overlap | mean_len |")
        print("|---|---|---|---|---|---|")
        for cell, by_seed in cells.items():
            runs = list(by_seed.values())
            stats = {k: _ci95([r.get(k) for r in runs if "error" not in r]) for k in METRIC_KEYS}
            lens = _ci95([r.get("mean_length") for r in runs if "error" not in r])

            def fmt(s, dec=3):
                if not s or s.get("n", 0) == 0:
                    return "—"
                return f"{s['mean']:.{dec}f} ± {s['ci95']:.{dec}f}"

            n = stats["block_visit_kl"].get("n", 0)
            print(f"| {cell} | {n} | {fmt(stats['block_visit_kl'])} | "
                  f"{fmt(stats['edge_transition_kl'])} | {fmt(stats['hot_path_ngram_overlap'])} | "
                  f"{fmt(lens, 1)} |")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["retrain", "rollout-only", "summarize"], required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44, 45, 46])
    ap.add_argument("--benchmarks", nargs="*", choices=list(BENCHMARKS),
                    help="subset to run (default: all)")
    ap.add_argument("--out", default="benchmarks/local/multiseed_results.json",
                    help="raw results JSON (retrain / rollout-only)")
    ap.add_argument("--in", dest="in_path", help="results JSON to summarize")
    args = ap.parse_args()

    if args.mode == "summarize":
        if not args.in_path:
            ap.error("--mode summarize requires --in <results.json>")
        summarize(args.in_path)
        return
    run_sweep(args)


if __name__ == "__main__":
    main()
