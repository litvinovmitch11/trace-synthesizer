import os
import subprocess
import sys
import json
from pathlib import Path

ROOT = Path(".")
OUT = ROOT / "benchmarks/local/cpp_opt_levels/out"
OUT.mkdir(parents=True, exist_ok=True)

PROG = ROOT / "benchmarks/local/cpp_opt_levels/complex_opt.cpp"
FUNC = "_Z17complex_algorithmi"  # mangled name for `int complex_algorithm(int)`

OPT_LEVELS = ["O0", "O1", "O2", "O3"]

def run_cmd(cmd, env=None, **kwargs):
    print(f"\n[EXEC] {' '.join(cmd)}")
    subprocess.run(cmd, check=True, env=env, **kwargs)

def build_artifacts(src, opt_level):
    name = f"complex_{opt_level}"
    build_dir = ROOT / f"benchmarks/local/cpp_opt_levels/build_{opt_level}"
    build_dir.mkdir(parents=True, exist_ok=True)
    
    env = os.environ.copy()
    env["OPT_LEVEL"] = f"-{opt_level}"
    
    run_cmd(["bash", "scripts/build_cpp_dataset_artifacts.sh", str(src), str(build_dir)], env=env)

    cfg = build_dir / "complex_opt.cfg.json"
    comp = build_dir / "complex_opt.compressed_trace.json"
    
    from trace_synthesizer.io.intra_trace import canonical_intra_trace_record, intra_sequence_from_compressed
    seq = intra_sequence_from_compressed(json.loads(comp.read_text()), FUNC)
    ref_record = canonical_intra_trace_record(function_name=FUNC, sequence=seq, episode=None)
    ref_path = build_dir / "complex_opt_reference_intra.json"
    ref_path.write_text(json.dumps(ref_record))
    
    return cfg, comp, ref_path

def create_lstm_dataset(cfg, comp, name):
    ds_path = OUT / f"dataset_{name}.jsonl"
    record = {
        "cfg": str(cfg.resolve()),
        "func": FUNC,
        "sequence": json.loads(comp.read_text()),
        "program_id": name
    }
    ds_path.write_text(json.dumps(record) + "\n")
    return ds_path

def train_models(opt_level, cfg, comp):
    print(f"\n=== 3. Training Synthesizers on {opt_level} ===")
    tb_dir = OUT / "tensorboard"
    name = f"complex_{opt_level}"
    
    # LSTM
    ds_base = create_lstm_dataset(cfg, comp, name)
    lstm_ckpt = OUT / f"lstm_ckpt_{opt_level}"
    run_cmd([
        sys.executable, "scripts/train_feature_window_lstm.py",
        "--dataset-jsonl", str(ds_base),
        "--func-filter", FUNC,
        "--out-stem", str(lstm_ckpt),
        "--epochs", "20",
        "--seed", "42"
    ])
    
    # Flat PPO
    flat_ckpt = OUT / f"flat_ckpt_{opt_level}"
    run_cmd([
        sys.executable, "-m", "trace_synthesizer", "train-hrl-ppo",
        "--cfg", str(cfg),
        "--func", FUNC,
        "--out-stem", str(flat_ckpt),
        "--device", "cpu",
        "--seed", "42",
        "--iterations", "15",
        "--steps-per-iter", "1024",
        "--epochs", "4",
        "--minibatch-size", "128",
        "--reference", str(comp),
        "--reference-compressed",
        "--terminal-kl-scale", "100.0",
        "--pgo-log-scale", "0.0",
        "--max-steps", "2000",
        "--window-back", "8",
        "--bc-epochs", "10",
        "--tb-logdir", str(tb_dir),
        "--tb-run-name", f"train_flat_{opt_level}"
    ])
    
    # HRL PPO
    hrl_ckpt = OUT / f"hrl_ckpt_{opt_level}"
    run_cmd([
        sys.executable, "-m", "trace_synthesizer", "train-hrl-ppo",
        "--cfg", str(cfg),
        "--func", FUNC,
        "--out-stem", str(hrl_ckpt),
        "--device", "cpu",
        "--seed", "42",
        "--iterations", "15",
        "--steps-per-iter", "1024",
        "--epochs", "4",
        "--minibatch-size", "128",
        "--reference", str(comp),
        "--reference-compressed",
        "--hierarchical", "--num-modes", "4", "--manager-every", "4",
        "--terminal-kl-scale", "100.0",
        "--pgo-log-scale", "0.0",
        "--max-steps", "2000",
        "--window-back", "8",
        "--bc-epochs", "10",
        "--tb-logdir", str(tb_dir),
        "--tb-run-name", f"train_hrl_{opt_level}"
    ])
    
    return lstm_ckpt, flat_ckpt, hrl_ckpt

def rollout_and_eval(name, cmd_rollout, cfg_mut, ref_mut, report_dict):
    roll_dir = OUT / f"rollouts_{name}"
    cmd_rollout.extend(["--out-dir", str(roll_dir)])
    run_cmd(cmd_rollout)
    
    met = OUT / f"metrics_{name}.json"
    run_cmd([
        sys.executable, "-m", "trace_synthesizer", "metrics-compare",
        "--reference", str(ref_mut),
        "--candidate", str(roll_dir / "intra_traces.jsonl"),
        "--func", FUNC,
        "--out", str(met)
    ])
    
    report = json.loads(met.read_text())
    report_dict[name] = report["metrics"]

def main():
    print("=== 1. Building Artifacts for All Opt Levels ===")
    artifacts = {}
    for opt in OPT_LEVELS:
        cfg, comp, ref = build_artifacts(PROG, opt)
        artifacts[opt] = {"cfg": cfg, "comp": comp, "ref": ref}

    print("\n=== 2. Training Models on O0 ===")
    train_opt = "O0"
    lstm_ckpt, flat_ckpt, hrl_ckpt = train_models(
        train_opt, 
        artifacts[train_opt]["cfg"], 
        artifacts[train_opt]["comp"]
    )
    
    final_report = {}

    print(f"\n=== 4. Zero-Shot Evaluation (Trained on {train_opt}) ===")
    for eval_opt in OPT_LEVELS:
        print(f"\nEvaluating on {eval_opt}...")
        cfg_eval = artifacts[eval_opt]["cfg"]
        ref_eval = artifacts[eval_opt]["ref"]
        
        report_dict = {}
        
        # PGO
        rollout_and_eval("pgo", [
            sys.executable, "-m", "trace_synthesizer", "rollout-random",
            "--cfg", str(cfg_eval), "--func", FUNC, "--episodes", "10",
            "--seed", "42", "--max-steps", "2000"
        ], cfg_eval, ref_eval, report_dict)
        
        # LSTM
        rollout_and_eval("lstm", [
            sys.executable, "-m", "trace_synthesizer", "rollout-lstm",
            "--cfg", str(cfg_eval), "--func", FUNC, "--episodes", "10",
            "--seed", "42", "--max-steps", "2000", "--checkpoint", str(lstm_ckpt)
        ], cfg_eval, ref_eval, report_dict)
        
        # Flat PPO
        rollout_and_eval("flat_ppo", [
            sys.executable, "-m", "trace_synthesizer", "rollout-hrl",
            "--cfg", str(cfg_eval), "--func", FUNC, "--episodes", "10",
            "--seed", "42", "--max-steps", "2000", "--checkpoint", str(flat_ckpt),
            "--action-select", "sample", "--window-back", "8"
        ], cfg_eval, ref_eval, report_dict)
        
        # HRL PPO
        rollout_and_eval("hrl_ppo", [
            sys.executable, "-m", "trace_synthesizer", "rollout-hrl",
            "--cfg", str(cfg_eval), "--func", FUNC, "--episodes", "10",
            "--seed", "42", "--max-steps", "2000", "--checkpoint", str(hrl_ckpt),
            "--action-select", "sample", "--window-back", "8"
        ], cfg_eval, ref_eval, report_dict)
        
        final_report[f"train_{train_opt}_eval_{eval_opt}"] = report_dict
        
    report_path = OUT / "final_report_cross_opt.json"
    report_path.write_text(json.dumps(final_report, indent=2))
    print(f"\nFinal report written to {report_path}")

if __name__ == "__main__":
    main()