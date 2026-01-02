#!/bin/bash
set -e

# Настройки
SRC_FILE="${1:-interesting.cpp}" 
BINARY_NAME="app_pgo"
PROFILE_DIR="./profile_data"
PROFILE_FILE="merged.profdata"
OUTPUT_MIR="output.mir"
CLANG_BIN="clang++-21"
LLVM_PROFDATA_BIN="llvm-profdata-21"

echo "--- [1/4] Build with Profile Gen ---"
rm -rf "$PROFILE_DIR"
mkdir -p "$PROFILE_DIR"
# -fdebug-info-for-profiling важен для маппинга
"$CLANG_BIN" -O2 -g -fdebug-info-for-profiling \
    -fprofile-generate="$PROFILE_DIR" \
    "$SRC_FILE" -o "$BINARY_NAME"

echo "--- [2/4] Generate Traffic (1000 runs) ---"
# Запускаем много раз, чтобы счетчики были > 0
for i in {1..1000}; do
    ./"$BINARY_NAME" > /dev/null 2>&1
done

echo "--- [3/4] Merge Profile ---"
"$LLVM_PROFDATA_BIN" merge -output="$PROFILE_DIR/$PROFILE_FILE" "$PROFILE_DIR"/*.profraw

echo "--- [4/4] Emit MIR with PGO ---"
# Используем profile-use. 
# block-freq-propagation помогает проставить частоты в заголовки блоков
"$CLANG_BIN" -O2 -g \
    -fprofile-use="$PROFILE_DIR/$PROFILE_FILE" \
    -c "$SRC_FILE" \
    -mllvm -stop-after=machine-scheduler \
    -fno-discard-value-names \
    -o "$OUTPUT_MIR"

echo "✅ Done. Result: $OUTPUT_MIR"
echo "Now run: python3 main.py analyze $OUTPUT_MIR --out data.json --all"
