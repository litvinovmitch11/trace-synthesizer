#!/bin/bash

# End-to-End PGO Pipeline script
# 1. Profile Generation Build
# 2. Profile Collection & Merge
# 3. CFG Generation with PGO Build
# 4. DynamoRIO Trace Collection
# 5. Trace Compression
# 6. Visualization

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <input.cpp> [args_for_binary...]"
    echo "Example: $0 examples/complex.cpp arg1 arg2"
    exit 1
fi

INPUT_FILE=$1
shift
BIN_ARGS=("$@")

BASENAME=$(basename "$INPUT_FILE" | cut -d. -f1)
OUT_DIR="${OUT_DIR:-output}"
mkdir -p "$OUT_DIR"

LLVM_DIR="/home/mitchell/dev/llvm/llvm-project/build-install"
CLANG="$LLVM_DIR/bin/clang++"
LLVM_PROFDATA="$LLVM_DIR/bin/llvm-profdata"
LLVM_LINK="$LLVM_DIR/bin/llvm-link"
LLC="$LLVM_DIR/bin/llc"
LLVM_READOBJ="$LLVM_DIR/bin/llvm-readobj"

PLUGIN_SO="build/src/CFGDumper/CFGDumper.so"
DRRUN="build/_deps/dynamorio_pkg-src/bin64/drrun"
TRACER_SO="build/src/InstrTracer/libInstrTracer.so"

if [ ! -f "$PLUGIN_SO" ] || [ ! -f "$TRACER_SO" ]; then
    echo "Error: Plugins not found. Please run 'make build'."
    exit 1
fi

echo "========================================="
echo "[1/6] Profile Generation Build"
echo "========================================="
$CLANG -O3 -fprofile-instr-generate -fcoverage-mapping "$INPUT_FILE" -o "$OUT_DIR/${BASENAME}_prof"

echo "========================================="
echo "[2/6] Profile Collection & Merge"
echo "========================================="
LLVM_PROFILE_FILE="$OUT_DIR/default.profraw" "$OUT_DIR/${BASENAME}_prof" "${BIN_ARGS[@]}" > /dev/null
$LLVM_PROFDATA merge -output="$OUT_DIR/${BASENAME}.profdata" "$OUT_DIR/default.profraw"

echo "========================================="
echo "[3/6] CFG Generation Build (with PGO)"
echo "========================================="
$CLANG -O3 -fPIC -fbasic-block-address-map -flto -fprofile-instr-use="$OUT_DIR/${BASENAME}.profdata" -c "$INPUT_FILE" -o "$OUT_DIR/${BASENAME}.bc"

$LLVM_LINK "$OUT_DIR/${BASENAME}.bc" -o "$OUT_DIR/${BASENAME}_whole.bc"

$LLC --basic-block-address-map -relocation-model=pic -load="$PLUGIN_SO" -cfg-pretty=false -cfg-out-file="$OUT_DIR/${BASENAME}.cfg.json" "$OUT_DIR/${BASENAME}_whole.bc" -o "$OUT_DIR/${BASENAME}.s"

$CLANG "$OUT_DIR/${BASENAME}.s" -o "$OUT_DIR/${BASENAME}.bin"

$LLVM_READOBJ --bb-addr-map "$OUT_DIR/${BASENAME}.bin" > "$OUT_DIR/${BASENAME}_bb_map.txt"

echo "========================================="
echo "[4/6] DynamoRIO Trace Collection"
echo "========================================="
$DRRUN -c "$TRACER_SO" -o "$OUT_DIR/${BASENAME}.trace.bin" "${BASENAME}.bin" -- "$OUT_DIR/${BASENAME}.bin" "${BIN_ARGS[@]}" > /dev/null

echo "========================================="
echo "[5/6] Trace Compression & Validation"
echo "========================================="
poetry run python3 tools_py/trace_pipeline.py \
    --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
    --map "$OUT_DIR/${BASENAME}_bb_map.txt" \
    --trace "$OUT_DIR/${BASENAME}.trace.bin" \
    --out "$OUT_DIR/${BASENAME}.compressed_trace.json"

echo "========================================="
echo "[6/6] Visualization"
echo "========================================="
# Visualize without trace
poetry run python3 tools_py/visualize_cfg.py \
    --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
    --func "main" \
    --out "$OUT_DIR/${BASENAME}_main_cfg_pgo"

# Visualize with trace
poetry run python3 tools_py/visualize_cfg.py \
    --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
    --func "main" \
    --trace "$OUT_DIR/${BASENAME}.compressed_trace.json" \
    --out "$OUT_DIR/${BASENAME}_main_cfg_pgo_trace"

echo "========================================="
echo "End-to-End Pipeline Completed!"
echo "Check $OUT_DIR/ for SVG visualizations."