#!/bin/bash

# Настройка путей (как у тебя)
LLVM_BIN="/home/mitchell/dev/llvm/llvm-project/build-install/bin"
CLANG="$LLVM_BIN/clang++"
LLC="$LLVM_BIN/llc"
PROFDATA="$LLVM_BIN/llvm-profdata"
PLUGIN="/home/mitchell/dev/llvm/trace-synthesizer/build/src/tracer/CFGJsonDumper.so"

SRC="/home/mitchell/dev/llvm/trace-synthesizer/examples/main.cpp"

echo "--- 1. Компиляция с инструментацией (Instrumentation Build) ---"
# Генерирует бинарник, который при запуске пишет сырой профиль
$CLANG -O2 -fprofile-instr-generate -o main_instrumented $SRC

echo "--- 2. Запуск для сбора профиля ---"
# Запускаем программу. Она создаст файл default.profraw
./main_instrumented

echo "--- 3. Конвертация профиля (Merge Profile) ---"
# LLVM не читает сырой .profraw, ему нужен индексированный .profdata
$PROFDATA merge -output=code.profdata default.profraw

echo "--- 4. Компиляция в Bitcode с использованием профиля ---"
# Теперь компилируем исходник в .bc, скармливая ему профиль.
# Clang пометит в IR вероятности ветвления (BranchWeights).
$CLANG -O2 -fprofile-instr-use=code.profdata -c -emit-llvm -o main_optimized.bc $SRC

echo "--- 5. Генерация ASM с нашим плагином ---"
# Запускаем llc. На этом этапе MachineBranchProbabilityInfo считает данные из IR,
# которые туда положил Clang на шаге 4.
$LLC -load $PLUGIN -O2 main_optimized.bc -o main.s 2> cfg_dump.json

echo "Done! Check cfg_dump.json"
