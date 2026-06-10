"""cpp_trigger state-machine, in-domain.

Trains and evaluates all four generator families on the same trigger CFG
(Random PGO, LSTM-BC, Flat PPO, Hierarchical PPO) and reports
block_visit_kl + hot_path_ngram_overlap against the DynamoRIO reference.

This is the context-dependency counterpart to run_diamond_exp.py; the trigger
program tracks an internal `state` variable that controls branching, so a
memoryless PGO walk cannot reproduce the phase logic.
"""

import json
import sys
from pathlib import Path

from exp_common import build_artifacts, run_cmd

ROOT = Path(".")
SRC = ROOT / "benchmarks/local/cpp_trigger/trigger.cpp"
BUILD = ROOT / "benchmarks/local/cpp_trigger/build"
OUT = ROOT / "benchmarks/local/cpp_trigger/out"
FUNC = "main"

OUT.mkdir(parents=True, exist_ok=True)


def create_lstm_dataset(cfg, comp, name):
    ds_path = OUT / f"dataset_{name}.jsonl"
    record = {
        "cfg": str(cfg.resolve()),
        "func": FUNC,
        "sequence": json.loads(comp.read_text()),
        "program_id": name,
    }
    ds_path.write_text(json.dumps(record) + "\n")
    return ds_path


def eval_rollout(name, cmd_rollout, ref_intra):
    print(f"\n=== Rollout: {name} ===")
    roll_dir = OUT / f"rollouts_{name}"
    cmd_rollout.extend(["--out-dir", str(roll_dir)])
    run_cmd(cmd_rollout)

    print(f"--- Metrics {name} ---")
    met = OUT / f"metrics_{name}.json"
    run_cmd(
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "metrics-compare",
            "--reference",
            str(ref_intra),
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
        print(f"  [{name}] {m['name']}: {m['value']}")


def train_ppo(name, comp, loop_profile, extra_args):
    print(f"\n--- Training {name} ---")
    ckpt = OUT / f"{name}_ckpt"
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
        str(ckpt),
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
        str(comp),
        "--reference-compressed",
        "--terminal-kl-scale",
        "100.0",
        "--pgo-log-scale",
        "0.0",
        "--loop-profile",
        str(loop_profile),
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
    return ckpt


def main():
    global CFG
    print("=== 1. Building CFG + trace artifacts ===")
    CFG, COMP, REF_INTRA, LOOP_PROFILE = build_artifacts(
        SRC, BUILD, FUNC, compute_loop_profile=True
    )

    print("\n=== 2. Random PGO baseline ===")
    eval_rollout(
        "pgo",
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "rollout-random",
            "--cfg",
            str(CFG),
            "--func",
            FUNC,
            "--episodes",
            "10",
            "--seed",
            "42",
            "--max-steps",
            "1500",
        ],
        REF_INTRA,
    )

    print("\n=== 3. LSTM behavioral cloning ===")
    ds = create_lstm_dataset(CFG, COMP, "trigger")
    lstm_ckpt = OUT / "lstm_ckpt"
    run_cmd(
        [
            sys.executable,
            "scripts/train_feature_window_lstm.py",
            "--dataset-jsonl",
            str(ds),
            "--func-filter",
            FUNC,
            "--out-stem",
            str(lstm_ckpt),
            "--epochs",
            "20",
            "--seed",
            "42",
        ]
    )
    eval_rollout(
        "lstm",
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "rollout-lstm",
            "--cfg",
            str(CFG),
            "--func",
            FUNC,
            "--episodes",
            "10",
            "--seed",
            "42",
            "--max-steps",
            "1500",
            "--checkpoint",
            str(lstm_ckpt),
        ],
        REF_INTRA,
    )

    print("\n=== 4. Flat PPO ===")
    flat_ckpt = train_ppo("flat", COMP, LOOP_PROFILE, [])
    eval_rollout(
        "flat_ppo",
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
            "--max-steps",
            "1500",
            "--checkpoint",
            str(flat_ckpt),
            "--action-select",
            "sample",
            "--window-back",
            "8",
        ],
        REF_INTRA,
    )

    print("\n=== 5. Hierarchical PPO ===")
    hrl_ckpt = train_ppo(
        "hierarchical",
        COMP,
        LOOP_PROFILE,
        ["--hierarchical", "--num-modes", "4", "--manager-every", "4"],
    )
    eval_rollout(
        "hrl_ppo",
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
            "--max-steps",
            "1500",
            "--checkpoint",
            str(hrl_ckpt),
            "--action-select",
            "sample",
            "--window-back",
            "8",
        ],
        REF_INTRA,
    )


if __name__ == "__main__":
    main()
