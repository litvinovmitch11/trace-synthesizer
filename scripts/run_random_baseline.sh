#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CPP="${1:-$ROOT/benchmarks/local/benchmark_complex.cpp}"
OUT_DIR="${OUT_DIR:-$ROOT/output/random_baseline}"
FUNC="${FUNC:-main}"
N_PGO="${N_PGO:-4}"
N_DR="${N_DR:-4}"
DR_TIMEOUT_SEC="${DR_TIMEOUT_SEC:-90}"

if [[ ! -f "$CPP" ]]; then
  echo "Error: C++ source not found: $CPP" >&2
  exit 1
fi

BASE=$(basename "$CPP" | cut -d. -f1)
mkdir -p "$OUT_DIR/profile" "$OUT_DIR/dr_runs" "$OUT_DIR/results"

LLVM_DIR="${LLVM_DIR:-${LLVM_INSTALL_DIR:-/home/mitchell/dev/llvm/llvm-project/build-install}}"
CLANG="$LLVM_DIR/bin/clang++"
LLVM_PROFDATA="$LLVM_DIR/bin/llvm-profdata"
LLVM_LINK="$LLVM_DIR/bin/llvm-link"
LLC="$LLVM_DIR/bin/llc"
LLVM_READOBJ="$LLVM_DIR/bin/llvm-readobj"
LLVM_IR2VEC="$LLVM_DIR/bin/llvm-ir2vec"
IR2VEC_VOCAB="${IR2VEC_VOCAB:-/home/mitchell/dev/llvm/llvm-project/llvm/lib/Analysis/models/seedEmbeddingVocab75D.json}"
ENABLE_IR2VEC="${ENABLE_IR2VEC:-1}"

PLUGIN_SO="build/src/CFGDumper/CFGDumper.so"
DRRUN="build/_deps/dynamorio_pkg-src/bin64/drrun"
TRACER_SO="build/src/InstrTracer/libInstrTracer.so"

if [[ ! -f "$PLUGIN_SO" || ! -f "$TRACER_SO" ]]; then
  echo "Error: Plugins not found. Please run 'make build'." >&2
  exit 1
fi

echo "========================================="
echo "Random Baseline: $BASE"
echo "========================================="

echo "[1/5] Profile Generation Build"
"$CLANG" -O3 -fprofile-instr-generate -fcoverage-mapping "$CPP" -o "$OUT_DIR/${BASE}_prof"

echo "[2/5] Profile Collection & Merge (N=$N_PGO)"
PROFRAW_LIST=()
for ((i=0; i<N_PGO; i++)); do
  prof="$OUT_DIR/profile/run_$i.profraw"
  LLVM_PROFILE_FILE="$prof" "$OUT_DIR/${BASE}_prof" >/dev/null
  PROFRAW_LIST+=("$prof")
done
"$LLVM_PROFDATA" merge -output="$OUT_DIR/${BASE}.profdata" "${PROFRAW_LIST[@]}"

echo "[3/5] CFG Generation Build (with PGO)"
"$CLANG" -O3 -fPIC -fbasic-block-address-map -flto -fprofile-instr-use="$OUT_DIR/${BASE}.profdata" -c "$CPP" -o "$OUT_DIR/${BASE}.bc"
"$LLVM_LINK" "$OUT_DIR/${BASE}.bc" -o "$OUT_DIR/${BASE}_whole.bc"
"$LLC" --basic-block-address-map -relocation-model=pic -load="$PLUGIN_SO" -cfg-pretty=false -cfg-out-file="$OUT_DIR/${BASE}.cfg.json" "$OUT_DIR/${BASE}_whole.bc" -o "$OUT_DIR/${BASE}.s"
if [[ "$ENABLE_IR2VEC" == "1" && -x "$LLVM_IR2VEC" && -f "$IR2VEC_VOCAB" ]]; then
  poetry run python3 scripts/augment_cfg_with_ir2vec.py \
    --cfg "$OUT_DIR/${BASE}.cfg.json" \
    --bc "$OUT_DIR/${BASE}_whole.bc" \
    --llvm-ir2vec "$LLVM_IR2VEC" \
    --vocab "$IR2VEC_VOCAB" > /dev/null
fi
"$CLANG" "$OUT_DIR/${BASE}.s" -o "$OUT_DIR/${BASE}.bin"
"$LLVM_READOBJ" --bb-addr-map "$OUT_DIR/${BASE}.bin" >"$OUT_DIR/${BASE}_bb_map.txt"

echo "[4/5] DynamoRIO Trace Collection (M=$N_DR)"
for ((i=0; i<N_DR; i++)); do
  d="$OUT_DIR/dr_runs/$(printf '%02d' "$i")"
  mkdir -p "$d"
  t0=$(date +%s.%N)
  timeout "$DR_TIMEOUT_SEC" "$DRRUN" -c "$TRACER_SO" -o "$d/${BASE}.trace.bin" "${BASE}.bin" -- "$OUT_DIR/${BASE}.bin" >/dev/null || true
  if [[ ! -s "$d/${BASE}.trace.bin" ]]; then
    echo "  Run $i skipped (timeout/empty trace)"
    continue
  fi
  t1=$(date +%s.%N)
  wall=$(python3 -c "print(float('$t1') - float('$t0'))")
  echo "  Run $i time: ${wall}s"
  
  poetry run python3 -m trace_synthesizer compress \
    --cfg "$OUT_DIR/${BASE}.cfg.json" \
    --map "$OUT_DIR/${BASE}_bb_map.txt" \
    --trace "$d/${BASE}.trace.bin" \
    --out "$d/${BASE}.compressed_trace.json" > /dev/null
done

echo "[5/5] Baseline Rollouts & Metrics"
REF_COMP="$(ls "$OUT_DIR"/dr_runs/*/"${BASE}.compressed_trace.json" 2>/dev/null | head -n 1 || true)"
if [[ -z "$REF_COMP" ]]; then
  echo "Error: no compressed DR traces were produced." >&2
  exit 1
fi
poetry run python3 -m trace_synthesizer export-intra-trace \
  --compressed "$REF_COMP" \
  --func "$FUNC" \
  --out "$OUT_DIR/reference_real_intra.json" > /dev/null

ROLL_DIR="$OUT_DIR/rollouts_random"
poetry run python3 -m trace_synthesizer rollout-random \
  --cfg "$OUT_DIR/${BASE}.cfg.json" \
  --func "$FUNC" \
  --episodes 10 \
  --seed 42 \
  --out-dir "$ROLL_DIR" > /dev/null

poetry run python3 -m trace_synthesizer metrics-compare \
  --reference "$OUT_DIR/reference_real_intra.json" \
  --candidate "$ROLL_DIR/intra_traces.jsonl" \
  --func "$FUNC" \
  --out "$OUT_DIR/results/metrics_random.json" > /dev/null

cat "$OUT_DIR/results/metrics_random.json"

echo "Generating Visualizations..."
make visualize-trace CFG="$OUT_DIR/${BASE}.cfg.json" FUNC="$FUNC" TRACE="$ROLL_DIR/intra_traces.jsonl" OUT="$OUT_DIR/rollouts_random/viz_random_trace" > /dev/null

echo "Done. Outputs in $OUT_DIR"
