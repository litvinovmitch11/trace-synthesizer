import subprocess
import sys
import json
from pathlib import Path

ROOT = Path(".")
CFG = ROOT / "benchmarks/local/cpp_diamond/build/diamond.cfg.json"
REF = ROOT / "benchmarks/local/cpp_diamond/build/diamond.compressed_trace.json"
REF_INTRA = ROOT / "benchmarks/local/cpp_diamond/build/reference_intra.json"
OUT = ROOT / "benchmarks/local/cpp_diamond/out"
OUT.mkdir(parents=True, exist_ok=True)

def train_and_eval(name, extra_args):
    print(f"--- Training {name} ---")
    stem = OUT / f"{name}_ckpt"
    cmd = [
        sys.executable, "-m", "trace_synthesizer", "train-hrl-ppo",
        "--cfg", str(CFG),
        "--func", "main",
        "--out-stem", str(stem),
        "--device", "cpu",
        "--seed", "42",
        "--iterations", "10",
        "--steps-per-iter", "1024",
        "--epochs", "4",
        "--minibatch-size", "128",
        "--reference", str(REF),
        "--reference-compressed",
        "--terminal-kl-scale", "100.0",
        "--pgo-log-scale", "0.0",
        "--loop-profile", "benchmarks/local/cpp_diamond/build/loop_profile.json",
        "--loop-timing-scale", "20.0",
        "--ref-edge-log-scale", "1.0",
        "--short-path-penalty-scale", "100.0",
        "--max-steps", "1500",
        "--window-back", "8",
        "--bc-epochs", "10"
    ] + extra_args
    subprocess.run(cmd, check=True)
    
    print(f"--- Rollout {name} ---")
    roll_dir = OUT / f"{name}_rollout"
    cmd_roll = [
        sys.executable, "-m", "trace_synthesizer", "rollout-hrl",
        "--cfg", str(CFG),
        "--func", "main",
        "--episodes", "10",
        "--seed", "1",
        "--out-dir", str(roll_dir),
        "--checkpoint", str(stem),
        "--action-select", "sample",
        "--max-steps", "1500",
        "--window-back", "8"
    ]
    subprocess.run(cmd_roll, check=True)
    
    print(f"--- Metrics {name} ---")
    met = OUT / f"{name}_metrics.json"
    cmd_met = [
        sys.executable, "-m", "trace_synthesizer", "metrics-compare",
        "--reference", str(REF_INTRA),
        "--candidate", str(roll_dir / "intra_traces.jsonl"),
        "--func", "main",
        "--out", str(met)
    ]
    subprocess.run(cmd_met, check=True)
    
    report = json.loads(met.read_text())
    for m in report["metrics"]:
        print(f"  {m['name']}: {m['value']}")

train_and_eval("flat", [])
train_and_eval("hierarchical", ["--hierarchical", "--num-modes", "4", "--manager-every", "4"])
