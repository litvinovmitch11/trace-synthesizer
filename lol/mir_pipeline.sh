#!/bin/bash
set -e 

# Конфигурация
SRC_FILE="${1:-interesting.cpp}" 
BINARY_NAME="app_pgo"
PROFILE_DIR="./profile_data"
PROFILE_FILE="merged.profdata"
OUTPUT_MIR="output.mir"

# Укажи свои версии clang
CLANG_BIN="clang++-21"
LLVM_PROFDATA_BIN="llvm-profdata-21"

echo "--- [1/4] Compiling with Instrumentation ---"
rm -rf "$PROFILE_DIR"
mkdir -p "$PROFILE_DIR"
"$CLANG_BIN" -O2 -fprofile-generate="$PROFILE_DIR" "$SRC_FILE" -o "$BINARY_NAME"

echo "--- [2/4] Running Profile Loop (50 iterations) ---"
# Запускаем много раз, чтобы набить статистику
for i in {1..50}; do
    ./"$BINARY_NAME" > /dev/null 2>&1
done

echo "--- [3/4] Merging Profile ---"
"$LLVM_PROFDATA_BIN" merge -output="$PROFILE_DIR/$PROFILE_FILE" "$PROFILE_DIR"/*.profraw

echo "--- [4/4] Generating MIR ---"
"$CLANG_BIN" -O2 -fprofile-use="$PROFILE_DIR/$PROFILE_FILE" \
    -c "$SRC_FILE" \
    -mllvm -stop-after=machine-scheduler \
    -fno-discard-value-names \
    -o "$OUTPUT_MIR"

echo "✅ MIR saved: $OUTPUT_MIR"
echo "Run analyzer: ./mir_analyzer.py $OUTPUT_MIR --highlight-path"
