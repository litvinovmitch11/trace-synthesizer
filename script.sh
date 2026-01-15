#!/bin/bash
set -e

# --- НАСТРОЙКИ ---
LLVM_ROOT="/home/mitchell/dev/llvm/llvm-project/build-install"
CLANG="$LLVM_ROOT/bin/clang++"
LLC="$LLVM_ROOT/bin/llc"
LLVM_READOBJ="$LLVM_ROOT/bin/llvm-readobj"
PROJECT_ROOT="/home/mitchell/dev/llvm/trace-synthesizer"
SRC_FILE="$PROJECT_ROOT/examples/main.cpp"
PLUGIN_SO="$PROJECT_ROOT/build/src/CFGDumper/CFGDumper.so"
CLIENT_LIB="$PROJECT_ROOT/build/src/InstrTracer/libInstrTracer.so"
TOOLS_PY="$PROJECT_ROOT/tools_py"

# 1. Компиляция для профилирования
echo "[1] Compiling for profiling..."
mkdir -p pgo_data

# Шаг 1.1: Компилируем с -fprofile-generate
$CLANG -O2 -fprofile-generate=pgo_data -no-pie $SRC_FILE -o app_prof

# Шаг 1.2: Запускаем профилировочную версию
echo "[1.2] Running profiled version..."
./app_prof

# Проверяем, создались ли профили
PROF_DATA=$(ls pgo_data/*.profraw 2>/dev/null | head -1)
if [ -z "$PROF_DATA" ]; then
    echo "Warning: No profraw files generated. Using default compilation."
    # Компилируем без PGO
    $CLANG -O2 -emit-llvm -c $SRC_FILE -o app.bc
else
    echo "Found profraw data: $PROF_DATA"
    
    # Шаг 1.3: Объединяем профили
    echo "[1.3] Merging profile data..."
    $CLANG -fprofile-generate=pgo_data -fprofile-update=atomic -c $SRC_FILE -o dummy.o 2>/dev/null || true
    
    # Конвертируем в indexed формат
    $LLVM_ROOT/bin/llvm-profdata merge -output=pgo.profdata pgo_data/*.profraw
    
    # Шаг 1.4: Компилируем с использованием профиля
    echo "[1.4] Compiling with PGO..."
    $CLANG -O2 -fprofile-use=pgo.profdata -emit-llvm -c $SRC_FILE -o app.bc
fi

# 2. Генерация ASM с CFG JSON (используем плагин)
echo "[2] Generating ASM with CFG info..."
$LLC -load $PLUGIN_SO --basic-block-address-map app.bc -o app.s

# 3. Финальная компиляция
echo "[3] Final compilation..."
$CLANG -O2 -no-pie app.s -o app_bin

# 4. Сбор трейса выполнения с DynamoRIO
echo "[4] Collecting execution trace..."
/home/mitchell/dev/llvm/DynamoRIO-Linux-11.3.0/bin64/drrun \
    -c $CLIENT_LIB \
    -- ./app_bin

# Файл теперь называется bb_trace.bin и лежит в текущей папке
TRACE_FILE="bb_trace.bin"
if [ ! -f "$TRACE_FILE" ]; then
    echo "Error: Trace file not generated!"
    exit 1
fi

# 3. Извлечение адресов
echo "[5] Extracting BB Map..."
$LLVM_READOBJ --bb-addr-map ./app_bin > out.txt

# 6. Матчинг трассировки с CFG
echo "[6] Matching trace to CFG..."
python3 $TOOLS_PY/match_trace.py \
    --cfg main.cfg.json \
    --readobj out.txt \
    --trace $TRACE_FILE \
    --output final_trace.json

echo "[7] Visualizing..."
# 7.1 Simple CFG (без вероятностей)
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
