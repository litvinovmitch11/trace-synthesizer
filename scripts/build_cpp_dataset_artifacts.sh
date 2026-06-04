#!/usr/bin/env bash
# Build CFG JSON + one DynamoRIO compressed trace from a C++ source.
# Usage: build_cpp_dataset_artifacts.sh <path/to/file.cpp> <output_dir>
# Env: LLVM_INSTALL_DIR (default matches Makefile), N_PGO (default 2).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <source.cpp> <output_dir>" >&2
  exit 1
fi

CPP="$(realpath "$1")"
OUT_DIR="$(realpath "$2")"
mkdir -p "$OUT_DIR/profile"

if [[ ! -f "$CPP" ]]; then
  echo "Error: source not found: $CPP" >&2
  exit 1
fi

BASE=$(basename "$CPP" | cut -d. -f1)
N_PGO="${N_PGO:-2}"

LLVM_DIR="${LLVM_DIR:-${LLVM_INSTALL_DIR:-/home/mitchell/dev/llvm/llvm-project/build-install}}"
CLANG="$LLVM_DIR/bin/clang++"
LLVM_PROFDATA="$LLVM_DIR/bin/llvm-profdata"
LLVM_LINK="$LLVM_DIR/bin/llvm-link"
LLC="$LLVM_DIR/bin/llc"
LLVM_READOBJ="$LLVM_DIR/bin/llvm-readobj"

PLUGIN_SO="$ROOT/build/src/CFGDumper/CFGDumper.so"
DRRUN="$ROOT/build/_deps/dynamorio_pkg-src/bin64/drrun"
TRACER_SO="$ROOT/build/src/InstrTracer/libInstrTracer.so"

for p in "$CLANG" "$PLUGIN_SO" "$TRACER_SO" "$DRRUN"; do
  if [[ ! -e "$p" ]]; then
    echo "Error: missing prerequisite: $p" >&2
    exit 1
  fi
done

echo "[1/5] Profile build"
"$CLANG" ${OPT_LEVEL:--O3} -fprofile-instr-generate -fcoverage-mapping "$CPP" -o "$OUT_DIR/${BASE}_prof"

echo "[2/5] Profile merge (N=$N_PGO)"
PROFRAW_LIST=()
for ((i = 0; i < N_PGO; i++)); do
  prof="$OUT_DIR/profile/run_$i.profraw"
  LLVM_PROFILE_FILE="$prof" "$OUT_DIR/${BASE}_prof" >/dev/null
  PROFRAW_LIST+=("$prof")
done
"$LLVM_PROFDATA" merge -output="$OUT_DIR/${BASE}.profdata" "${PROFRAW_LIST[@]}"

echo "[3/5] CFG + binary"
"$CLANG" ${OPT_LEVEL:--O3} -fPIC -fbasic-block-address-map -flto \
  -fprofile-instr-use="$OUT_DIR/${BASE}.profdata" -c "$CPP" -o "$OUT_DIR/${BASE}.bc"
"$LLVM_LINK" "$OUT_DIR/${BASE}.bc" -o "$OUT_DIR/${BASE}_whole.bc"
"$LLC" --basic-block-address-map -relocation-model=pic \
  -load="$PLUGIN_SO" -cfg-pretty=false -cfg-out-file="$OUT_DIR/${BASE}.cfg.json" \
  "$OUT_DIR/${BASE}_whole.bc" -o "$OUT_DIR/${BASE}.s"
"$CLANG" "$OUT_DIR/${BASE}.s" -o "$OUT_DIR/${BASE}.bin"
"$LLVM_READOBJ" --bb-addr-map "$OUT_DIR/${BASE}.bin" >"$OUT_DIR/${BASE}_bb_map.txt"

echo "[3.5/5] Inject Semantic Embeddings (IR2Vec)"
LLVM_IR2VEC="$LLVM_DIR/bin/llvm-ir2vec"
IR2VEC_VOCAB="$LLVM_DIR/../llvm/lib/Analysis/models/seedEmbeddingVocab75D.json"
if [[ -x "$LLVM_IR2VEC" && -f "$IR2VEC_VOCAB" ]]; then
  poetry run python3 scripts/augment_cfg_with_ir2vec.py \
    --cfg "$OUT_DIR/${BASE}.cfg.json" \
    --bc "$OUT_DIR/${BASE}_whole.bc" \
    --llvm-ir2vec "$LLVM_IR2VEC" \
    --vocab "$IR2VEC_VOCAB" > /dev/null
else
  echo "Warning: llvm-ir2vec or vocab not found, skipping true embeddings."
fi

echo "[4/5] DynamoRIO"
(
  cd "$OUT_DIR"
  "$DRRUN" -c "$TRACER_SO" -o "${BASE}.trace.bin" "${BASE}.bin" -- "./${BASE}.bin"
) >/dev/null

echo "[5/5] Compress trace"
poetry run python3 -m trace_synthesizer compress \
  --cfg "$OUT_DIR/${BASE}.cfg.json" \
  --map "$OUT_DIR/${BASE}_bb_map.txt" \
  --trace "$OUT_DIR/${BASE}.trace.bin" \
  --out "$OUT_DIR/${BASE}.compressed_trace.json"

echo "Wrote $OUT_DIR/${BASE}.cfg.json and $OUT_DIR/${BASE}.compressed_trace.json"
