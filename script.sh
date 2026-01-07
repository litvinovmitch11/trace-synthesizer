#!/bin/bash
set -e

# --- НАСТРОЙКИ ---
LLVM_ROOT="/home/mitchell/dev/llvm/llvm-project/build-install"
CLANG="$LLVM_ROOT/bin/clang++"
LLC="$LLVM_ROOT/bin/llc"
LLVM_READOBJ="$LLVM_ROOT/bin/llvm-readobj"
PROJECT_ROOT="/home/mitchell/dev/llvm/trace-synthesizer"
SRC_FILE="$PROJECT_ROOT/examples/main.cpp"
PLUGIN_SO="$PROJECT_ROOT/build/src/tracer/CFGJsonDumper.so"
TOOLS_PY="$PROJECT_ROOT/tools_py"

# 1. Компиляция
echo "[1] Compiling Application..."
$CLANG -O2 -emit-llvm -c $SRC_FILE -o app.bc
$LLC -load $PLUGIN_SO --basic-block-address-map app.bc -o app.s
$CLANG -O2 -no-pie app.s -o app_bin

# 2. Сбор трейса
echo "[2] Collecting Trace..."
/home/mitchell/dev/llvm/DynamoRIO-Linux-11.3.0/bin64/drrun -t drcov -- ./app_bin

DRCOV_FILE=$(ls -t drcov.app_bin.*.proc.log 2>/dev/null | head -1)
if [ -z "$DRCOV_FILE" ]; then
    echo "Error: No drcov trace file found!"
    exit 1
fi

# 3. Извлечение адресов
echo "[3] Extracting BB Map..."
$LLVM_READOBJ --bb-addr-map ./app_bin > out.txt

# 4. Матчинг (используем ОБНОВЛЕННЫЙ match_trace.py)
echo "[4] Matching Trace..."
python3 $TOOLS_PY/match_trace.py \
    --cfg main.cfg.json \
    --readobj out.txt \
    --trace $DRCOV_FILE \
    --output final_trace.json

# 5. Визуализация
echo "[5] Visualizing..."

# 5.1 Simple CFG
python3 $TOOLS_PY/visualize_cfg.py \
    --cfg main.cfg.json \
    --mode simple \
    --output visualization_simple

# 5.2 PGO CFG (Static probabilities)
python3 $TOOLS_PY/visualize_cfg.py \
    --cfg main.cfg.json \
    --mode pgo \
    --output visualization_pgo

# 5.3 Trace CFG (Real execution path)
python3 $TOOLS_PY/visualize_cfg.py \
    --cfg main.cfg.json \
    --trace final_trace.json \
    --mode trace \
    --output visualization_trace

echo "Done! Check .svg files."
