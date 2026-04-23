#!/usr/bin/env bash
# Single entry point: full C++ pipeline (PGO, CFGDumper, DynamoRIO InstrTracer)
# plus intra export, rollout-random, metrics-compare, metrics-bench-speed.
#
# Usage:
#   ./scripts/run_benchmark_complex.sh [args passed to the benchmark binary...]
# Environment:
#   BENCHMARK_CPP  — path to .cpp (default: benchmarks/local/benchmark_complex.cpp)
#   OUT_DIR        — artifact directory (default: output)
#   FUNC           — function name for viz/metrics (default: main)
#   SKIP_ANALYSIS  — if 1, run only full_pipeline.sh (no Python steps)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CPP="${BENCHMARK_CPP:-$ROOT/benchmarks/local/benchmark_complex.cpp}"
export OUT_DIR="${OUT_DIR:-output}"
FUNC="${FUNC:-main}"
SKIP_ANALYSIS="${SKIP_ANALYSIS:-0}"

if [[ ! -f "$CPP" ]]; then
  echo "Error: C++ source not found: $CPP" >&2
  exit 1
fi

BASE=$(basename "$CPP" | cut -d. -f1)
mkdir -p "$OUT_DIR"

LLVM_DIR="${LLVM_DIR:-${LLVM_INSTALL_DIR:-/home/mitchell/dev/llvm/llvm-project/build-install}}"
CLANG="$LLVM_DIR/bin/clang++"
LLVM_PROFDATA="$LLVM_DIR/bin/llvm-profdata"
LLVM_LINK="$LLVM_DIR/bin/llvm-link"
LLC="$LLVM_DIR/bin/llc"
LLVM_READOBJ="$LLVM_DIR/bin/llvm-readobj"

PLUGIN_SO="build/src/CFGDumper/CFGDumper.so"
DRRUN="build/_deps/dynamorio_pkg-src/bin64/drrun"
TRACER_SO="build/src/InstrTracer/libInstrTracer.so"

if [[ ! -f "$PLUGIN_SO" || ! -f "$TRACER_SO" ]]; then
  echo "Error: Plugins not found. Please run 'make build'." >&2
  exit 1
fi

echo "========================================="
echo "benchmark_complex — source: $CPP"
echo "OUT_DIR=$OUT_DIR  FUNC=$FUNC"
echo "========================================="

echo "[1/6] Profile Generation Build"
"$CLANG" -O3 -fprofile-instr-generate -fcoverage-mapping "$CPP" -o "$OUT_DIR/${BASE}_prof"

echo "[2/6] Profile Collection & Merge"
LLVM_PROFILE_FILE="$OUT_DIR/default.profraw" "$OUT_DIR/${BASE}_prof" "$@" >/dev/null
"$LLVM_PROFDATA" merge -output="$OUT_DIR/${BASE}.profdata" "$OUT_DIR/default.profraw"

echo "[3/6] CFG Generation Build (with PGO)"
"$CLANG" -O3 -fPIC -fbasic-block-address-map -flto -fprofile-instr-use="$OUT_DIR/${BASE}.profdata" -c "$CPP" -o "$OUT_DIR/${BASE}.bc"
"$LLVM_LINK" "$OUT_DIR/${BASE}.bc" -o "$OUT_DIR/${BASE}_whole.bc"
"$LLC" --basic-block-address-map -relocation-model=pic -load="$PLUGIN_SO" -cfg-pretty=false -cfg-out-file="$OUT_DIR/${BASE}.cfg.json" "$OUT_DIR/${BASE}_whole.bc" -o "$OUT_DIR/${BASE}.s"
"$CLANG" "$OUT_DIR/${BASE}.s" -o "$OUT_DIR/${BASE}.bin"
"$LLVM_READOBJ" --bb-addr-map "$OUT_DIR/${BASE}.bin" >"$OUT_DIR/${BASE}_bb_map.txt"

echo "[4/6] DynamoRIO Trace Collection"
"$DRRUN" -c "$TRACER_SO" -o "$OUT_DIR/${BASE}.trace.bin" "${BASE}.bin" -- "$OUT_DIR/${BASE}.bin" "$@" >/dev/null

echo "[5/6] Trace Compression & Validation"
poetry run python3 -m trace_synthesizer compress \
  --cfg "$OUT_DIR/${BASE}.cfg.json" \
  --map "$OUT_DIR/${BASE}_bb_map.txt" \
  --trace "$OUT_DIR/${BASE}.trace.bin" \
  --out "$OUT_DIR/${BASE}.compressed_trace.json"

echo "[6/6] Visualization"
poetry run python3 -m trace_synthesizer visualize \
  --cfg "$OUT_DIR/${BASE}.cfg.json" \
  --func "main" \
  --out "$OUT_DIR/${BASE}_main_cfg_pgo"

poetry run python3 -m trace_synthesizer visualize \
  --cfg "$OUT_DIR/${BASE}.cfg.json" \
  --func "main" \
  --trace "$OUT_DIR/${BASE}.compressed_trace.json" \
  --out "$OUT_DIR/${BASE}_main_cfg_pgo_trace"

if [[ "$SKIP_ANALYSIS" == "1" ]]; then
  echo "SKIP_ANALYSIS=1 — stopping after full_pipeline."
  exit 0
fi

CFG="$OUT_DIR/${BASE}.cfg.json"
COMP="$OUT_DIR/${BASE}.compressed_trace.json"

if [[ ! -f "$CFG" || ! -f "$COMP" ]]; then
  echo "Error: expected $CFG and $COMP after pipeline." >&2
  exit 1
fi

ROLL_DIR="$OUT_DIR/${BASE}_rollouts"

echo "========================================="
echo "Python: export intra-trace (real / DynamoRIO)"
echo "========================================="
poetry run python3 -m trace_synthesizer export-intra-trace \
  --compressed "$COMP" \
  --func "$FUNC" \
  --out "$OUT_DIR/${BASE}_real_intra.json"

echo "========================================="
echo "Python: rollout-random (PGO baseline)"
echo "========================================="
poetry run python3 -m trace_synthesizer rollout-random \
  --cfg "$CFG" \
  --func "$FUNC" \
  --episodes "${ROLL_EPISODES:-120}" \
  --seed "${ROLL_SEED:-42}" \
  --max-steps "${ROLL_MAX_STEPS:-8000}" \
  --out-dir "$ROLL_DIR"

echo "========================================="
echo "Python: metrics-compare"
echo "========================================="
poetry run python3 -m trace_synthesizer metrics-compare \
  --reference "$OUT_DIR/${BASE}_real_intra.json" \
  --candidate "$ROLL_DIR/intra_traces.jsonl" \
  --func "$FUNC" \
  --out "$OUT_DIR/${BASE}_metrics.json"

echo "========================================="
echo "Python: metrics-bench-speed"
echo "========================================="
poetry run python3 -m trace_synthesizer metrics-bench-speed \
  --cfg "$CFG" \
  --func "$FUNC" \
  --n-episodes "${BENCH_EPISODES:-200}" \
  --max-steps "${BENCH_MAX_STEPS:-4000}" \
  --seed "${BENCH_SEED:-0}" \
  --out "$OUT_DIR/${BASE}_bench_speed.json"

echo "========================================="
echo "Done. Key outputs:"
echo "  $CFG"
echo "  $COMP"
echo "  $OUT_DIR/${BASE}_real_intra.json"
echo "  $ROLL_DIR/intra_traces.jsonl"
echo "  $OUT_DIR/${BASE}_metrics.json"
echo "  $OUT_DIR/${BASE}_bench_speed.json"
echo "========================================="
