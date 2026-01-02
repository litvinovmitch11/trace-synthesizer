#!/bin/bash
set -e

SRC="$1" # e.g. main.cpp
FUNC_FILTER="$2" # e.g. "main" or "get_random" (Important for scalability!)

# 1. PGO Gen Build
clang++-21 -O2 -g -fdebug-info-for-profiling -fprofile-generate=./pgo_data "$SRC" -o app_gen

# 2. Run
./app_gen

# 3. Merge
llvm-profdata-21 merge -output=merged.profdata ./pgo_data/*.profraw

# 4. Generate MIR (Targeted)
# Fix #7: We use -print-machineinstrs=... to only dump the specific function we care about.
# This prevents output.mir from becoming 500MB+ for large C++ projects.
echo "Generating MIR for $FUNC_FILTER..."
clang++-21 -O2 -g -fprofile-use=merged.profdata -c "$SRC" \
    -mllvm -stop-after=machine-scheduler \
    -mllvm -print-machineinstrs="$FUNC_FILTER" \
    -o /dev/null > output.mir 2>&1

# Note: clang writes MIR to stderr when using -print-machineinstrs, so we redirect > output.mir

# 5. Build Tracer
clang++-21 -O2 -g -fprofile-use=merged.profdata -fsanitize-coverage=trace-pc-guard "$SRC" trace_runtime.cpp -o app_trace

# 6. Trace
./app_trace
