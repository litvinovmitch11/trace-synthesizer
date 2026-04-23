#!/usr/bin/env bash
# PGO + CFGDumper + DynamoRIO pipeline for one or more C translation units (same as full_pipeline.sh, C front-end).
#
# Usage:
#   CTUNING_SOURCES="abs1.c abs2.c ..." CTUNING_PRIMARY="abs1.c" \
#   PROFILE_ENV_KV="CT_MATRIX_DIMENSION=96,CT_REPEAT_MAIN=3" \
#   ./scripts/ctuning_full_pipeline_c.sh [extra binary args for profile + DR]
#
# CTUNING_PRIMARY sets output basename (stem of file). All sources are compiled and linked into one a.out-style binary.

set -euo pipefail

if [[ -z "${CTUNING_SOURCES:-}" || -z "${CTUNING_PRIMARY:-}" ]]; then
  echo "Set CTUNING_PRIMARY and CTUNING_SOURCES (space-separated absolute paths to .c files)." >&2
  exit 2
fi

read -r -a SOURCES <<<"${CTUNING_SOURCES}"
PRIMARY="${CTUNING_PRIMARY}"
BIN_ARGS=("$@")
DR_TIMEOUT_SEC="${DR_TIMEOUT_SEC:-90}"

# Prefer CTUNING_BASENAME (e.g. manifest id) so outputs are stable when PRIMARY is not the main file.
BASENAME="${CTUNING_BASENAME:-$(basename "$PRIMARY" | sed 's/\.c$//')}"
OUT_DIR="${OUT_DIR:-output}"
mkdir -p "$OUT_DIR"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LLVM_DIR="${LLVM_DIR:-${LLVM_INSTALL_DIR:-/home/mitchell/dev/llvm/llvm-project/build-install}}"
CLANG_C="${CLANG_C:-$LLVM_DIR/bin/clang}"
LLVM_PROFDATA="$LLVM_DIR/bin/llvm-profdata"
LLVM_LINK="$LLVM_DIR/bin/llvm-link"
LLC="$LLVM_DIR/bin/llc"
LLVM_READOBJ="$LLVM_DIR/bin/llvm-readobj"
LLVM_IR2VEC="$LLVM_DIR/bin/llvm-ir2vec"
IR2VEC_VOCAB="${IR2VEC_VOCAB:-/home/mitchell/dev/llvm/llvm-project/llvm/lib/Analysis/models/seedEmbeddingVocab75D.json}"
ENABLE_IR2VEC="${ENABLE_IR2VEC:-1}"

PLUGIN_SO="build/src/CFGDumper/CFGDumper.so"
DRRUN="build/_deps/dynamorio_pkg-src/bin64/drrun"
TRACER_SO="build/src/InstrTracer/libInstrTracer.so"

if [[ ! -f "$PLUGIN_SO" || ! -f "$TRACER_SO" ]]; then
  echo "Error: Plugins not found. Run 'make build' from repo root." >&2
  exit 1
fi

# Export PROFILE_ENV_KV as KEY=VAL,KEY=VAL -> export each
if [[ -n "${PROFILE_ENV_KV:-}" ]]; then
  IFS=',' read -r -a _pairs <<<"${PROFILE_ENV_KV}"
  for _p in "${_pairs[@]}"; do
    export "${_p?}"
  done
fi

echo "========================================="
echo "[ctuning C pipeline] basename=$BASENAME"
echo "========================================="

echo "[1/6] Profile generation build (clang C)"
$CLANG_C -O3 -fprofile-instr-generate -fcoverage-mapping "${SOURCES[@]}" -o "$OUT_DIR/${BASENAME}_prof"

echo "[2/6] Profile collection + merge"
LLVM_PROFILE_FILE="$OUT_DIR/default.profraw" "$OUT_DIR/${BASENAME}_prof" "${BIN_ARGS[@]}" >/dev/null
$LLVM_PROFDATA merge -output="$OUT_DIR/${BASENAME}.profdata" "$OUT_DIR/default.profraw"

echo "[3/6] PGO + LTO + llc CFGDumper"
BC_FILES=()
for src in "${SOURCES[@]}"; do
  stem=$(basename "$src" .c)
  $CLANG_C -O3 -fPIC -fbasic-block-address-map -flto -fprofile-instr-use="$OUT_DIR/${BASENAME}.profdata" -c "$src" -o "$OUT_DIR/${BASENAME}_${stem}.bc"
  BC_FILES+=("$OUT_DIR/${BASENAME}_${stem}.bc")
done
$LLVM_LINK "${BC_FILES[@]}" -o "$OUT_DIR/${BASENAME}_whole.bc"
$LLC --basic-block-address-map -relocation-model=pic -load="$PLUGIN_SO" -cfg-pretty=false \
  -cfg-out-file="$OUT_DIR/${BASENAME}.cfg.json" "$OUT_DIR/${BASENAME}_whole.bc" -o "$OUT_DIR/${BASENAME}.s"
if [[ "$ENABLE_IR2VEC" == "1" && -x "$LLVM_IR2VEC" && -f "$IR2VEC_VOCAB" ]]; then
  poetry run python3 scripts/augment_cfg_with_ir2vec.py \
    --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
    --bc "$OUT_DIR/${BASENAME}_whole.bc" \
    --llvm-ir2vec "$LLVM_IR2VEC" \
    --vocab "$IR2VEC_VOCAB" > /dev/null
fi
$CLANG_C "$OUT_DIR/${BASENAME}.s" -o "$OUT_DIR/${BASENAME}.bin"
$LLVM_READOBJ --bb-addr-map "$OUT_DIR/${BASENAME}.bin" >"$OUT_DIR/${BASENAME}_bb_map.txt"

echo "[4/6] DynamoRIO"
timeout "$DR_TIMEOUT_SEC" "$DRRUN" -c "$TRACER_SO" -o "$OUT_DIR/${BASENAME}.trace.bin" "${BASENAME}.bin" -- "$OUT_DIR/${BASENAME}.bin" "${BIN_ARGS[@]}" >/dev/null

echo "[5/6] Compress + validate"
poetry run python3 -m trace_synthesizer compress \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
  --map "$OUT_DIR/${BASENAME}_bb_map.txt" \
  --trace "$OUT_DIR/${BASENAME}.trace.bin" \
  --out "$OUT_DIR/${BASENAME}.compressed_trace.json"

FUNC="${FUNC:-main}"
echo "[6/6] Visualize ($FUNC)"
poetry run python3 -m trace_synthesizer visualize \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" --func "$FUNC" \
  --out "$OUT_DIR/${BASENAME}_${FUNC}_cfg_pgo"
poetry run python3 -m trace_synthesizer visualize \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" --func "$FUNC" \
  --trace "$OUT_DIR/${BASENAME}.compressed_trace.json" \
  --out "$OUT_DIR/${BASENAME}_${FUNC}_cfg_pgo_trace"

echo "Done: $OUT_DIR/${BASENAME}.{cfg.json,bin,compressed_trace.json}"
