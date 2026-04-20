#!/usr/bin/env bash
# Single entry point: full C++ pipeline (PGO, CFGDumper, DynamoRIO InstrTracer)
# plus intra export, rollout-random, metrics-compare, metrics-bench-speed.
#
# Usage:
#   ./scripts/run_benchmark_complex.sh [args passed to the benchmark binary...]
# Environment:
#   BENCHMARK_CPP  — path to .cpp (default: examples/benchmark_complex/benchmark_complex.cpp)
#   OUT_DIR        — artifact directory (default: output)
#   FUNC           — function name for viz/metrics (default: main)
#   SKIP_ANALYSIS  — if 1, run only full_pipeline.sh (no Python steps)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CPP="${BENCHMARK_CPP:-$ROOT/examples/benchmark_complex/benchmark_complex.cpp}"
export OUT_DIR="${OUT_DIR:-output}"
FUNC="${FUNC:-main}"
SKIP_ANALYSIS="${SKIP_ANALYSIS:-0}"

if [[ ! -f "$CPP" ]]; then
  echo "Error: C++ source not found: $CPP" >&2
  exit 1
fi

BASE=$(basename "$CPP" | cut -d. -f1)
mkdir -p "$OUT_DIR"

echo "========================================="
echo "benchmark_complex — source: $CPP"
echo "OUT_DIR=$OUT_DIR  FUNC=$FUNC"
echo "========================================="

./scripts/full_pipeline.sh "$CPP" "$@"

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
