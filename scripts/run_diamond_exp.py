import json
import sys
from pathlib import Path

from exp_common import build_artifacts, run_cmd

ROOT = Path(".")
SRC = ROOT / "benchmarks/local/cpp_diamond/diamond.cpp"
BUILD = ROOT / "benchmarks/local/cpp_diamond/build"
OUT = ROOT / "benchmarks/local/cpp_diamond/out"
FUNC = "main"

OUT.mkdir(parents=True, exist_ok=True)

print("=== Building CFG + trace artifacts ===")
CFG, REF, REF_INTRA, LOOP_PROFILE = build_artifacts(
    SRC, BUILD, FUNC, compute_loop_profile=True
)


def train_and_eval(name, extra_args):
    print(f"--- Training {name} ---")
    stem = OUT / f"{name}_ckpt"
    cmd = [
        sys.executable,
        "-m",
        "trace_synthesizer",
        "train-hrl-ppo",
        "--cfg",
        str(CFG),
        "--func",
        FUNC,
        "--out-stem",
        str(stem),
        "--device",
        "cpu",
        "--seed",
        "42",
        "--iterations",
        "10",
        "--steps-per-iter",
        "1024",
        "--epochs",
        "4",
        "--minibatch-size",
        "128",
        "--reference",
        str(REF),
        "--reference-compressed",
        "--terminal-kl-scale",
        "100.0",
        "--pgo-log-scale",
        "0.0",
        "--loop-profile",
        str(LOOP_PROFILE),
        "--loop-timing-scale",
        "20.0",
        "--ref-edge-log-scale",
        "1.0",
        "--short-path-penalty-scale",
        "100.0",
        "--max-steps",
        "1500",
        "--window-back",
        "8",
        "--bc-epochs",
        "10",
    ] + extra_args
    run_cmd(cmd)

    print(f"--- Rollout {name} ---")
    roll_dir = OUT / f"{name}_rollout"
    run_cmd(
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "rollout-hrl",
            "--cfg",
            str(CFG),
            "--func",
            FUNC,
            "--episodes",
            "10",
            "--seed",
            "1",
            "--out-dir",
            str(roll_dir),
            "--checkpoint",
            str(stem),
            "--action-select",
            "sample",
            "--max-steps",
            "1500",
            "--window-back",
            "8",
        ]
    )

    print(f"--- Metrics {name} ---")
    met = OUT / f"{name}_metrics.json"
    run_cmd(
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "metrics-compare",
            "--reference",
            str(REF_INTRA),
            "--candidate",
            str(roll_dir / "intra_traces.jsonl"),
            "--func",
            FUNC,
            "--out",
            str(met),
        ]
    )

    report = json.loads(met.read_text())
    for m in report["metrics"]:
        print(f"  {m['name']}: {m['value']}")


train_and_eval("flat", [])
train_and_eval(
    "hierarchical", ["--hierarchical", "--num-modes", "4", "--manager-every", "4"]
)
