#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CPP="${1:-$ROOT/benchmarks/local/benchmark_complex.cpp}"
OUT_DIR="${OUT_DIR:-$ROOT/output/plugins_demo}"
FUNC="${FUNC:-main}"
N_PGO="${N_PGO:-10}"

if [[ ! -f "$CPP" ]]; then
  echo "Error: C++ source not found: $CPP" >&2
  exit 1
fi

BASE=$(basename "$CPP" | cut -d. -f1)
mkdir -p "$OUT_DIR/profile"

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
echo "Plugins Demo: $BASE"
echo "========================================="

echo "[1/6] Profile Generation Build"
"$CLANG" -O3 -fprofile-instr-generate -fcoverage-mapping "$CPP" -o "$OUT_DIR/${BASE}_prof"

echo "[2/6] Profile Collection & Merge (N=$N_PGO)"
PROFRAW_LIST=()
for ((i=0; i<N_PGO; i++)); do
  prof="$OUT_DIR/profile/run_$i.profraw"
  LLVM_PROFILE_FILE="$prof" "$OUT_DIR/${BASE}_prof" >/dev/null
  PROFRAW_LIST+=("$prof")
done
"$LLVM_PROFDATA" merge -output="$OUT_DIR/${BASE}.profdata" "${PROFRAW_LIST[@]}"

echo "[3/6] CFG Generation Build (with PGO)"
"$CLANG" -O3 -fPIC -fbasic-block-address-map -flto -fprofile-instr-use="$OUT_DIR/${BASE}.profdata" -c "$CPP" -o "$OUT_DIR/${BASE}.bc"
"$LLVM_LINK" "$OUT_DIR/${BASE}.bc" -o "$OUT_DIR/${BASE}_whole.bc"
"$LLC" --basic-block-address-map -relocation-model=pic -load="$PLUGIN_SO" -cfg-pretty=false -cfg-out-file="$OUT_DIR/${BASE}.cfg.json" "$OUT_DIR/${BASE}_whole.bc" -o "$OUT_DIR/${BASE}.s"
"$CLANG" "$OUT_DIR/${BASE}.s" -o "$OUT_DIR/${BASE}.bin"
"$LLVM_READOBJ" --bb-addr-map "$OUT_DIR/${BASE}.bin" >"$OUT_DIR/${BASE}_bb_map.txt"

echo "[4/6] DynamoRIO Trace Collection"
t0=$(date +%s.%N)
"$DRRUN" -c "$TRACER_SO" -o "$OUT_DIR/${BASE}.trace.bin" "${BASE}.bin" -- "$OUT_DIR/${BASE}.bin" >/dev/null
t1=$(date +%s.%N)
wall=$(python3 -c "print(float('$t1') - float('$t0'))")
echo "  Time: ${wall}s"

echo "[5/6] Trace Compression & Validation"
poetry run python3 -m trace_synthesizer compress \
  --cfg "$OUT_DIR/${BASE}.cfg.json" \
  --map "$OUT_DIR/${BASE}_bb_map.txt" \
  --trace "$OUT_DIR/${BASE}.trace.bin" \
  --out "$OUT_DIR/${BASE}.compressed_trace.json"

echo "[6/6] Visualization"
poetry run python3 -m trace_synthesizer visualize \
  --cfg "$OUT_DIR/${BASE}.cfg.json" \
  --func "$FUNC" \
  --out "$OUT_DIR/${BASE}_${FUNC}_cfg_pgo"

poetry run python3 -m trace_synthesizer visualize \
  --cfg "$OUT_DIR/${BASE}.cfg.json" \
  --func "$FUNC" \
  --trace "$OUT_DIR/${BASE}.compressed_trace.json" \
  --out "$OUT_DIR/${BASE}_${FUNC}_cfg_pgo_trace"

echo "Done. Outputs in $OUT_DIR"
