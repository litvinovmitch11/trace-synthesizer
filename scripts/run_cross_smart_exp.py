import json
import sys
from pathlib import Path

from exp_common import build_artifacts, run_cmd

ROOT = Path(".")
OUT = ROOT / "benchmarks/local/cpp_smart_mutation/out"
OUT.mkdir(parents=True, exist_ok=True)

PROG_BASE = ROOT / "benchmarks/local/cpp_smart_mutation/smart_base.cpp"
BUILD_BASE = ROOT / "benchmarks/local/cpp_smart_mutation/build_base"

PROG_MUTATED = ROOT / "benchmarks/local/cpp_smart_mutation/smart_mutated.cpp"
BUILD_MUTATED = ROOT / "benchmarks/local/cpp_smart_mutation/build_mutated"

FUNC = "_Z7processi"


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


def rollout_and_eval(name, cmd_rollout, cfg_mut, ref_mut, render=True):
    print(f"\n=== Zero-Shot Rollout: {name} ===")
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
            str(ref_mut),
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

    if render:
        print(f"--- Rendering {name} ---")
        run_cmd(
            [
                "make",
                "visualize-trace",
                f"CFG={cfg_mut}",
                f"FUNC={FUNC}",
                f"TRACE={roll_dir}/intra_traces.jsonl",
                f"OUT={OUT}/viz_{name}",
            ]
        )


def main():
    print("=== 1. Building Base and Mutated Artifacts ===")
    cfg_base, comp_base, ref_base, _ = build_artifacts(PROG_BASE, BUILD_BASE, FUNC)
    cfg_mut, comp_mut, ref_mut, _ = build_artifacts(PROG_MUTATED, BUILD_MUTATED, FUNC)

    print("\n=== 2. Rendering Ground Truth Traces ===")
    run_cmd(
        [
            "make",
            "visualize-trace",
            f"CFG={cfg_base}",
            f"FUNC={FUNC}",
            f"TRACE={ref_base}",
            f"OUT={OUT}/viz_true_base",
        ]
    )
    run_cmd(
        [
            "make",
            "visualize-trace",
            f"CFG={cfg_mut}",
            f"FUNC={FUNC}",
            f"TRACE={ref_mut}",
            f"OUT={OUT}/viz_true_mutated",
        ]
    )

    print("\n=== 3. Training Synthesizers on Base Program ===")
    tb_dir = OUT / "tensorboard"

    # LSTM
    ds_base = create_lstm_dataset(cfg_base, comp_base, "smart_base")
    lstm_ckpt = OUT / "lstm_ckpt"
    run_cmd(
        [
            sys.executable,
            "scripts/train_feature_window_lstm.py",
            "--dataset-jsonl",
            str(ds_base),
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

    # Flat PPO
    flat_ckpt = OUT / "flat_ckpt"
    run_cmd(
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "train-hrl-ppo",
            "--cfg",
            str(cfg_base),
            "--func",
            FUNC,
            "--out-stem",
            str(flat_ckpt),
            "--device",
            "cpu",
            "--seed",
            "42",
            "--iterations",
            "15",
            "--steps-per-iter",
            "1024",
            "--epochs",
            "4",
            "--minibatch-size",
            "128",
            "--reference",
            str(comp_base),
            "--reference-compressed",
            "--terminal-kl-scale",
            "100.0",
            "--pgo-log-scale",
            "0.0",
            "--max-steps",
            "2000",
            "--window-back",
            "8",
            "--bc-epochs",
            "10",
            "--tb-logdir",
            str(tb_dir),
            "--tb-run-name",
            "train_flat",
        ]
    )

    # HRL PPO
    hrl_ckpt = OUT / "hrl_ckpt"
    run_cmd(
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "train-hrl-ppo",
            "--cfg",
            str(cfg_base),
            "--func",
            FUNC,
            "--out-stem",
            str(hrl_ckpt),
            "--device",
            "cpu",
            "--seed",
            "42",
            "--iterations",
            "15",
            "--steps-per-iter",
            "1024",
            "--epochs",
            "4",
            "--minibatch-size",
            "128",
            "--reference",
            str(comp_base),
            "--reference-compressed",
            "--hierarchical",
            "--num-modes",
            "4",
            "--manager-every",
            "4",
            "--terminal-kl-scale",
            "100.0",
            "--pgo-log-scale",
            "0.0",
            "--max-steps",
            "2000",
            "--window-back",
            "8",
            "--bc-epochs",
            "10",
            "--tb-logdir",
            str(tb_dir),
            "--tb-run-name",
            "train_hrl",
        ]
    )

    print("\n=== 4. Zero-Shot Synthesis on Mutated CFG (No New Trace!) ===")

    # PGO
    rollout_and_eval(
        "pgo",
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "rollout-random",
            "--cfg",
            str(cfg_mut),
            "--func",
            FUNC,
            "--episodes",
            "10",
            "--seed",
            "42",
            "--max-steps",
            "2000",
        ],
        cfg_mut,
        ref_mut,
    )

    # LSTM
    rollout_and_eval(
        "lstm",
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "rollout-lstm",
            "--cfg",
            str(cfg_mut),
            "--func",
            FUNC,
            "--episodes",
            "10",
            "--seed",
            "42",
            "--max-steps",
            "2000",
            "--checkpoint",
            str(lstm_ckpt),
        ],
        cfg_mut,
        ref_mut,
    )

    # Flat PPO
    rollout_and_eval(
        "flat_ppo",
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "rollout-hrl",
            "--cfg",
            str(cfg_mut),
            "--func",
            FUNC,
            "--episodes",
            "10",
            "--seed",
            "42",
            "--max-steps",
            "2000",
            "--checkpoint",
            str(flat_ckpt),
            "--action-select",
            "sample",
            "--window-back",
            "8",
        ],
        cfg_mut,
        ref_mut,
    )

    # HRL PPO
    rollout_and_eval(
        "hrl_ppo",
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "rollout-hrl",
            "--cfg",
            str(cfg_mut),
            "--func",
            FUNC,
            "--episodes",
            "10",
            "--seed",
            "42",
            "--max-steps",
            "2000",
            "--checkpoint",
            str(hrl_ckpt),
            "--action-select",
            "sample",
            "--window-back",
            "8",
        ],
        cfg_mut,
        ref_mut,
    )


if __name__ == "__main__":
    main()
