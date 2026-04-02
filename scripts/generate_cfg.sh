#!/bin/bash

# Скрипт для автоматической генерации Whole-Program CFG и бинарника с bb_addr_map

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <input.cpp> [additional.cpp ...]"
    exit 1
fi

INPUT_FILES="$@"
BASENAME=$(basename "$1" | cut -d. -f1)

LLVM_DIR="/home/mitchell/dev/llvm/llvm-project/build-install"
CLANG="$LLVM_DIR/bin/clang++"
LLVM_LINK="$LLVM_DIR/bin/llvm-link"
LLC="$LLVM_DIR/bin/llc"
LLVM_READOBJ="$LLVM_DIR/bin/llvm-readobj"

PLUGIN_SO="build/CFGDumper.so"
if [ ! -f "$PLUGIN_SO" ]; then
    PLUGIN_SO="build/src/CFGDumper/CFGDumper.so"
fi

if [ ! -f "$PLUGIN_SO" ]; then
    echo "Error: Plugin not found. Please run 'make build' first."
    exit 1
fi

OUT_DIR="${OUT_DIR:-output}"
mkdir -p "$OUT_DIR"

echo "[1/4] Compiling source files to LLVM IR (-flto)..."
BC_FILES=""
for file in $INPUT_FILES; do
    name=$(basename "$file" | cut -d. -f1)
    $CLANG -O3 -fPIC -fbasic-block-address-map -flto -c "$file" -o "$OUT_DIR/${name}.bc"
    BC_FILES="$BC_FILES $OUT_DIR/${name}.bc"
done

echo "[2/4] Linking into whole program bitcode..."
$LLVM_LINK $BC_FILES -o "$OUT_DIR/${BASENAME}_whole.bc"

echo "[3/4] Running llc to generate CFG JSON and assembly..."
$LLC --basic-block-address-map -relocation-model=pic -load="$PLUGIN_SO" -cfg-pretty=false -cfg-out-file="$OUT_DIR/${BASENAME}.cfg.json" "$OUT_DIR/${BASENAME}_whole.bc" -o "$OUT_DIR/${BASENAME}.s"

echo "[4/4] Assembling final binary..."
$CLANG "$OUT_DIR/${BASENAME}.s" -o "$OUT_DIR/${BASENAME}.bin"

echo "Done! Generated files in $OUT_DIR/:"
echo " - ${BASENAME}.cfg.json (Whole-Program CFG)"
echo " - ${BASENAME}.bin (Executable with .llvm_bb_addr_map section)"

# Дамп маппинга адресов
echo "Dumping bb_addr_map to $OUT_DIR/${BASENAME}_bb_map.txt..."
$LLVM_READOBJ --bb-addr-map "$OUT_DIR/${BASENAME}.bin" > "$OUT_DIR/${BASENAME}_bb_map.txt"
