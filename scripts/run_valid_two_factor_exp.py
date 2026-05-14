import os
import subprocess
import sys
import json
from pathlib import Path

ROOT = Path(".")
OUT = ROOT / "output/valid_two_factor"
OUT.mkdir(parents=True, exist_ok=True)

# Program A (Corpus / Foundation Training)
PROG_A = ROOT / "tests/fixtures/cpp_minimal/minimal.cpp"
BUILD_A = OUT / "build_a"

# Program B (Target / Zero-shot Adaptation)
PROG_B = ROOT / "tests/fixtures/cpp_trigger/trigger.cpp"
BUILD_B = OUT / "build_b"

def run_cmd(cmd, **kwargs):
    print(f"\n[EXEC] {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kwargs)

def build_artifacts(src, build_dir):
    build_dir.mkdir(parents=True, exist_ok=True)
    run_cmd(["bash", "scripts/build_cpp_dataset_artifacts.sh", str(src), str(build_dir)])

    base = src.stem
    cfg = build_dir / f"{base}.cfg.json"
    comp = build_dir / f"{base}.compressed_trace.json"
    
    # Extract reference intra trace for evaluation
    from trace_synthesizer.io.intra_trace import canonical_intra_trace_record, intra_sequence_from_compressed
    seq = intra_sequence_from_compressed(json.loads(comp.read_text()), "main")
    ref_record = canonical_intra_trace_record(function_name="main", sequence=seq, episode=None)
    ref_path = build_dir / f"{base}_reference_intra.json"
    ref_path.write_text(json.dumps(ref_record))
    
    # Compute loop profile (allowed ONLY for Program A)
    loop_prof = build_dir / "loop_profile.json"
    run_cmd([
        sys.executable, "scripts/compute_loop_profile.py",
        "--cfg", str(cfg),
        "--func", "main",
        "--reference", str(comp),
        "--reference-compressed",
        "--out", str(loop_prof)
    ])
    
    return cfg, comp, ref_path, loop_prof

def main():
    # 1. Build Artifacts
    print("=== 1. Building Artifacts ===")
    cfg_a, comp_a, ref_intra_a, loop_a = build_artifacts(PROG_A, BUILD_A)
    cfg_b, comp_b, ref_intra_b, loop_b = build_artifacts(PROG_B, BUILD_B)

    # 2. Stage A: Corpus Pretrain (Foundation Model)
    # We train on Program A USING its DynamoRIO trace as ground truth.
    print("\n=== 2. Stage A: Corpus Pretrain (Foundation Model on minimal.cpp) ===")
    foundation_ckpt = OUT / "foundation_ckpt"
    run_cmd([
        sys.executable, "-m", "trace_synthesizer", "train-hrl-ppo",
        "--cfg", str(cfg_a),
        "--func", "main",
        "--out-stem", str(foundation_ckpt),
        "--device", "cpu",
        "--seed", "42",
        "--iterations", "10",
        "--steps-per-iter", "512",
        "--epochs", "4",
        "--minibatch-size", "64",
        "--reference", str(comp_a),
        "--reference-compressed",
        "--hierarchical", "--num-modes", "4", "--manager-every", "4",
        # Use heavy supervised signals since this is the corpus stage
        "--terminal-kl-scale", "100.0",
        "--loop-profile", str(loop_a),
        "--loop-timing-scale", "20.0",
        "--ref-edge-log-scale", "1.0",
        "--pgo-log-scale", "0.0",
        "--bc-epochs", "2"
    ])

    # 3. Stage B: Fast Adaptation (Zero-Shot / Head-only on Target)
    # We adapt on Program B WITHOUT using its DynamoRIO trace for rewards!
    # (We must pass --reference to satisfy CLI, but we set all trace-dependent rewards to 0)
    print("\n=== 3. Stage B: Fast Adaptation (on trigger.cpp WITHOUT trace leakage) ===")
    adapted_ckpt = OUT / "adapted_ckpt"
    run_cmd([
        sys.executable, "scripts/adapt_hrl_ppo_graph.py",
        "--cfg", str(cfg_b),
        "--func", "main",
        "--foundation-checkpoint", str(foundation_ckpt),
        "--out-stem", str(adapted_ckpt),
        "--device", "cpu",
        "--seed", "42",
        "--adapt-iterations", "10",
        "--adapt-steps-per-iter", "512",
        "--epochs", "2",
        "--freeze-mode", "head-only", # Only adapt the final layers to the new graph
        "--hierarchical", "--num-modes", "4", "--manager-every", "4",
        # Pass dummy reference but DISABLE all trace-based rewards to prevent cheating
        "--reference", str(comp_b),
        "--reference-compressed",
        "--terminal-kl-scale", "0.0",
        "--loop-timing-scale", "0.0",
        "--ref-edge-log-scale", "0.0",
        "--bc-epochs", "0",
        # Rely entirely on static PGO profile
        "--pgo-log-scale", "0.1" 
    ])

    # 4. Rollout and Evaluation
    print("\n=== 4. Inference & Evaluation on Target ===")
    roll_dir = OUT / "rollouts_b"
    run_cmd([
        sys.executable, "-m", "trace_synthesizer", "rollout-hrl",
        "--cfg", str(cfg_b),
        "--func", "main",
        "--episodes", "10",
        "--checkpoint", str(adapted_ckpt),
        "--out-dir", str(roll_dir),
        "--action-select", "sample",
        "--max-steps", "1500"
    ])

    met_path = OUT / "metrics_b.json"
    run_cmd([
        sys.executable, "-m", "trace_synthesizer", "metrics-compare",
        "--reference", str(ref_intra_b),
        "--candidate", str(roll_dir / "intra_traces.jsonl"),
        "--func", "main",
        "--out", str(met_path)
    ])

    print("\n=== VALID METRICS (NO TRACE LEAKAGE) ===")
    report = json.loads(met_path.read_text())
    for m in report["metrics"]:
        print(f"  {m['name']}: {m['value']}")
        
    # 5. Render Graph
    print("\n=== 5. Rendering Final Graphs ===")
    run_cmd([
        sys.executable, "scripts/render_trigger.py",
        str(cfg_b), str(ref_intra_b), str(OUT / "valid_trigger_graph")
    ])

if __name__ == "__main__":
    main()
