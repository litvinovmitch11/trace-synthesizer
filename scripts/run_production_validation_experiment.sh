#!/usr/bin/env bash
# Production validation: multi-run PGO profile merge, PGO+CFG build, N_DR× DynamoRIO+compress,
# reference intra export, RandomPGO + LSTM rollouts (10 episodes) + metrics, manifest + FINDINGS.
# LSTM: JSONL dataset from all dr_runs compressed traces → supervised MaskedLSTM (BB history +
# existing BlockFeatures from CFG only; no extra embeddings) → rollout-lstm trace generation.
#
# Prerequisites: from repo root after `make configure && make build`, `poetry install`.
#
# Usage:
#   ./scripts/run_production_validation_experiment.sh
# Environment (optional):
#   OUT_DIR              — default: output/production_validation
#   BENCHMARK_CPP        — default: benchmarks/local/benchmark_complex.cpp
#   FUNC                 — default: main
#   SEED                 — default: 42
#   LLVM_DIR             — default: LLVM_INSTALL_DIR or Makefile-style path
#   ROLL_MAX_STEPS       — default: 8000
#   REFERENCE_RUN        — which dr_runs/NN compressed trace is reference (default: 0)
#   N_PGO N_DR           — default: 10 each
#   LSTM_EPOCHS          — default: 200 (global feature-window LSTM)
#   LSTM_WINDOW_BACK     — default: 8 (past block-feature window)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BENCHMARK_CPP="${BENCHMARK_CPP:-$ROOT/benchmarks/local/benchmark_complex.cpp}"
OUT_DIR="${OUT_DIR:-$ROOT/output/production_validation}"
FUNC="${FUNC:-main}"
SEED="${SEED:-42}"
REFERENCE_RUN="${REFERENCE_RUN:-0}"
ROLL_MAX_STEPS="${ROLL_MAX_STEPS:-8000}"
N_PGO="${N_PGO:-10}"
N_DR="${N_DR:-10}"

LLVM_DIR="${LLVM_DIR:-${LLVM_INSTALL_DIR:-/home/mitchell/dev/llvm/llvm-project/build-install}}"
CLANG="$LLVM_DIR/bin/clang++"
LLVM_PROFDATA="$LLVM_DIR/bin/llvm-profdata"
LLVM_LINK="$LLVM_DIR/bin/llvm-link"
LLC="$LLVM_DIR/bin/llc"
LLVM_READOBJ="$LLVM_DIR/bin/llvm-readobj"

PLUGIN_SO="$ROOT/build/src/CFGDumper/CFGDumper.so"
DRRUN="$ROOT/build/_deps/dynamorio_pkg-src/bin64/drrun"
TRACER_SO="$ROOT/build/src/InstrTracer/libInstrTracer.so"

if [[ ! -f "$BENCHMARK_CPP" ]]; then
  echo "Error: BENCHMARK_CPP not found: $BENCHMARK_CPP" >&2
  exit 1
fi
if [[ ! -f "$PLUGIN_SO" || ! -f "$TRACER_SO" ]]; then
  echo "Error: build plugins first (make build): $PLUGIN_SO $TRACER_SO" >&2
  exit 1
fi

BASENAME=$(basename "$BENCHMARK_CPP" | cut -d. -f1)
mkdir -p "$OUT_DIR/profile" "$OUT_DIR/results" "$OUT_DIR/dr_runs"

echo "========================================="
echo "Production validation experiment"
echo "  BENCHMARK_CPP=$BENCHMARK_CPP"
echo "  OUT_DIR=$OUT_DIR  FUNC=$FUNC  SEED=$SEED"
echo "========================================="

# --- [1] Profile instrumented binary ---
echo "[1/8] Profile-generation build (_prof)"
"$CLANG" -O3 -fprofile-instr-generate -fcoverage-mapping "$BENCHMARK_CPP" -o "$OUT_DIR/${BASENAME}_prof"

# --- [2] N_PGO profile runs (distinct argv) + merge ---
echo "[2/8] PGO collection ($N_PGO runs) + merge"
: >"$OUT_DIR/results/pgo_runs.jsonl"
PROFRAW_LIST=()
for ((i=0; i<N_PGO; i++)); do
  tag="run-$i"
  prof="$OUT_DIR/profile/run_$(printf '%02d' "$i").profraw"
  t0=$(date +%s.%N)
  LLVM_PROFILE_FILE="$prof" "$OUT_DIR/${BASENAME}_prof" "$tag" >/dev/null
  t1=$(date +%s.%N)
  wall=$(python3 -c "print(float('$t1') - float('$t0'))")
  sz=$(stat -c%s "$prof" 2>/dev/null || stat -f%z "$prof")
  PROFRAW_LIST+=("$prof")
  export PGO_JSON_RUN="$i" PGO_JSON_TAG="$tag" PGO_JSON_WALL="$wall" PGO_JSON_SZ="$sz" PGO_JSON_PROF="$prof" PGO_JSONL="$OUT_DIR/results/pgo_runs.jsonl"
  python3 <<'PY'
import json, os, pathlib
p = pathlib.Path(os.environ["PGO_JSONL"])
rec = {
    "run_index": int(os.environ["PGO_JSON_RUN"]),
    "argv_tag": os.environ["PGO_JSON_TAG"],
    "wall_seconds": float(os.environ["PGO_JSON_WALL"]),
    "profraw_bytes": int(os.environ["PGO_JSON_SZ"]),
    "profraw": os.environ["PGO_JSON_PROF"],
}
p.open("a", encoding="utf-8").write(json.dumps(rec) + "\n")
PY
done
"$LLVM_PROFDATA" merge -output="$OUT_DIR/${BASENAME}.profdata" "${PROFRAW_LIST[@]}"

# --- [3] PGO + CFG build (same as full_pipeline [3]) ---
echo "[3/8] PGO LTO build + CFGDumper + binary"
"$CLANG" -O3 -fPIC -fbasic-block-address-map -flto -fprofile-instr-use="$OUT_DIR/${BASENAME}.profdata" -c "$BENCHMARK_CPP" -o "$OUT_DIR/${BASENAME}.bc"
"$LLVM_LINK" "$OUT_DIR/${BASENAME}.bc" -o "$OUT_DIR/${BASENAME}_whole.bc"
"$LLC" --basic-block-address-map -relocation-model=pic -load="$PLUGIN_SO" -cfg-pretty=false -cfg-out-file="$OUT_DIR/${BASENAME}.cfg.json" "$OUT_DIR/${BASENAME}_whole.bc" -o "$OUT_DIR/${BASENAME}.s"
"$CLANG" "$OUT_DIR/${BASENAME}.s" -o "$OUT_DIR/${BASENAME}.bin"
"$LLVM_READOBJ" --bb-addr-map "$OUT_DIR/${BASENAME}.bin" >"$OUT_DIR/${BASENAME}_bb_map.txt"

# --- [4] N_DR full DynamoRIO + compress cycles ---
echo "[4/8] DynamoRIO + compress ($N_DR cycles)"
: >"$OUT_DIR/results/dr_compress_runs.jsonl"
for ((i=0; i<N_DR; i++)); do
  d="$OUT_DIR/dr_runs/$(printf '%02d' "$i")"
  mkdir -p "$d"
  tag="run-$i"
  t0=$(date +%s.%N)
  "$DRRUN" -c "$TRACER_SO" -o "$d/${BASENAME}.trace.bin" "${BASENAME}.bin" -- "$OUT_DIR/${BASENAME}.bin" "$tag" >/dev/null
  poetry run python3 -m trace_synthesizer compress \
    --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
    --map "$OUT_DIR/${BASENAME}_bb_map.txt" \
    --trace "$d/${BASENAME}.trace.bin" \
    --out "$d/${BASENAME}.compressed_trace.json"
  t1=$(date +%s.%N)
  wall=$(python3 -c "print(float('$t1') - float('$t0'))")
  tr_sz=$(stat -c%s "$d/${BASENAME}.trace.bin" 2>/dev/null || stat -f%z "$d/${BASENAME}.trace.bin")
  js_sz=$(stat -c%s "$d/${BASENAME}.compressed_trace.json" 2>/dev/null || stat -f%z "$d/${BASENAME}.compressed_trace.json")
  comp_path="$d/${BASENAME}.compressed_trace.json"
  export DR_JSON_RUN="$i" DR_JSON_TAG="$tag" DR_JSON_WALL="$wall" DR_JSON_TR="$tr_sz" DR_JSON_JS="$js_sz" DR_JSON_COMP="$comp_path" DR_JSONL="$OUT_DIR/results/dr_compress_runs.jsonl"
  python3 <<'PY'
import json, os, pathlib
p = pathlib.Path(os.environ["DR_JSONL"])
rec = {
    "run_index": int(os.environ["DR_JSON_RUN"]),
    "argv_tag": os.environ["DR_JSON_TAG"],
    "wall_seconds": float(os.environ["DR_JSON_WALL"]),
    "trace_bytes": int(os.environ["DR_JSON_TR"]),
    "compressed_bytes": int(os.environ["DR_JSON_JS"]),
    "compressed": os.environ["DR_JSON_COMP"],
}
p.open("a", encoding="utf-8").write(json.dumps(rec) + "\n")
PY
done

# --- [5] Reference intra from chosen DR run ---
REF_DIR="$OUT_DIR/dr_runs/$(printf '%02d' "$REFERENCE_RUN")"
REF_COMP="$REF_DIR/${BASENAME}.compressed_trace.json"
if [[ ! -f "$REF_COMP" ]]; then
  echo "Error: reference compressed missing: $REF_COMP" >&2
  exit 1
fi
echo "[5/8] export-intra-trace (reference run $REFERENCE_RUN)"
poetry run python3 -m trace_synthesizer export-intra-trace \
  --compressed "$REF_COMP" \
  --func "$FUNC" \
  --out "$OUT_DIR/reference_real_intra.json"

# --- [6] RandomPGO rollouts + metrics ---
echo "[6/8] rollout-random (10) + metrics-compare"
ROLL_DIR="$OUT_DIR/rollouts_random"
poetry run python3 -m trace_synthesizer rollout-random \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
  --func "$FUNC" \
  --episodes 10 \
  --seed "$SEED" \
  --max-steps "$ROLL_MAX_STEPS" \
  --out-dir "$ROLL_DIR"
poetry run python3 -m trace_synthesizer metrics-compare \
  --reference "$OUT_DIR/reference_real_intra.json" \
  --candidate "$ROLL_DIR/intra_traces.jsonl" \
  --func "$FUNC" \
  --out "$OUT_DIR/results/metrics_random.json"

# --- [7] Global trace LSTM: cross-program JSONL (cfg on each line) + train + rollouts + metrics ---
echo "[7/8] Global trace LSTM: cross dataset + train + rollout-lstm (10) + metrics"
mkdir -p "$OUT_DIR/dataset"
cat <<EOF > "$OUT_DIR/dataset/spec.json"
{
  "schema_version": 1,
  "entries": [
    {
      "id": "${BASENAME}_val",
      "cfg": "$OUT_DIR/${BASENAME}.cfg.json",
      "func": "$FUNC",
      "compressed_glob": "$OUT_DIR/dr_runs/*/${BASENAME}.compressed_trace.json"
    }
  ]
}
EOF
poetry run python3 "$ROOT/scripts/build_multi_program_intra_dataset.py" \
  --spec "$OUT_DIR/dataset/spec.json" \
  --out-dir "$OUT_DIR/dataset"
CROSS_JSONL="$OUT_DIR/dataset/cross.train.jsonl"
N_LINES=$(wc -l <"$CROSS_JSONL" | tr -d ' \t\n\r')
if [[ "${N_LINES:-0}" -lt 1 ]]; then
  echo "Error: empty cross dataset (no compressed traces?): $CROSS_JSONL" >&2
  exit 1
fi
CKPT_STEM="$OUT_DIR/lstm_checkpoint/global_validation"
mkdir -p "$OUT_DIR/lstm_checkpoint"
poetry run python3 "$ROOT/scripts/train_feature_window_lstm.py" \
  --dataset-jsonl "$CROSS_JSONL" \
  --func-filter "$FUNC" \
  --out-stem "$CKPT_STEM" \
  --window-back "${LSTM_WINDOW_BACK:-8}" \
  --epochs "${LSTM_EPOCHS:-200}" \
  --seed "$SEED" \
  --train-report "$OUT_DIR/results/lstm_train.json"

LSTM_DIR="$OUT_DIR/rollouts_lstm"
poetry run python3 -m trace_synthesizer rollout-lstm \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
  --func "$FUNC" \
  --episodes 10 \
  --seed "$SEED" \
  --max-steps "$ROLL_MAX_STEPS" \
  --out-dir "$LSTM_DIR" \
  --checkpoint "$CKPT_STEM" \
  --action-select argmax \
  --device cpu
poetry run python3 -m trace_synthesizer metrics-compare \
  --reference "$OUT_DIR/reference_real_intra.json" \
  --candidate "$LSTM_DIR/intra_traces.jsonl" \
  --func "$FUNC" \
  --out "$OUT_DIR/results/metrics_lstm.json"

# --- [8] manifest + FINDINGS ---
echo "[8/8] manifest.json + FINDINGS.md"
export ROOT OUT_DIR BENCHMARK_CPP BASENAME FUNC SEED REFERENCE_RUN ROLL_MAX_STEPS N_PGO N_DR
export LLVM_DIR
python3 <<'PY'
import json, os, subprocess
from pathlib import Path
from datetime import datetime, timezone

root = Path(os.environ["ROOT"])
out = Path(os.environ["OUT_DIR"])
try:
    git_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(root), text=True
    ).strip()
except Exception:
    git_head = "unknown"
clang_v = subprocess.run(
    [os.environ["LLVM_DIR"] + "/bin/clang++", "--version"],
    capture_output=True,
    text=True,
    cwd=str(root),
).stdout.splitlines()[0]

manifest = {
    "schema_version": 1,
    "kind": "production_validation",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "git_head": git_head,
    "llvm_dir": os.environ.get("LLVM_DIR", ""),
    "clang_version_line": clang_v,
    "benchmark_cpp": os.environ["BENCHMARK_CPP"],
    "basename": os.environ["BASENAME"],
    "out_dir": str(out),
    "func": os.environ["FUNC"],
    "seed": int(os.environ["SEED"]),
    "reference_run_index": int(os.environ["REFERENCE_RUN"]),
    "roll_max_steps": int(os.environ["ROLL_MAX_STEPS"]),
    "n_pgo_runs": int(os.environ["N_PGO"]),
    "n_dr_compress_runs": int(os.environ["N_DR"]),
    "reference_compressed": str(
        out
        / "dr_runs"
        / f"{int(os.environ['REFERENCE_RUN']):02d}"
        / f"{os.environ['BASENAME']}.compressed_trace.json"
    ),
    "reference_intra": str(out / "reference_real_intra.json"),
    "lstm_cross_dataset_jsonl": str(
        out / "dataset" / f"cross_{os.environ['FUNC']}.jsonl"
    ),
    "rollouts_random": str(out / "rollouts_random"),
    "rollouts_lstm": str(out / "rollouts_lstm"),
    "lstm_checkpoint_stem": str(out / "lstm_checkpoint" / "global_validation"),
    "metrics_random": str(out / "results" / "metrics_random.json"),
    "metrics_lstm": str(out / "results" / "metrics_lstm.json"),
}
out.mkdir(parents=True, exist_ok=True)
(out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("Wrote", out / "manifest.json")
PY

poetry run python3 "$ROOT/scripts/summarize_production_validation.py" "$OUT_DIR"

echo "Done. Key outputs:"
echo "  $OUT_DIR/manifest.json"
echo "  $OUT_DIR/FINDINGS.md"
echo "  $OUT_DIR/results/"
echo "========================================="
