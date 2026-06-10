#!/usr/bin/env bash
# Wrapper to visualize a CFG and optionally overlay a trace.
#
# Usage:
#   make visualize-trace CFG=path/to.cfg.json FUNC=main [TRACE=path/to_trace.jsonl] [OUT=path/to_output_stem]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -z "${CFG:-}" || -z "${FUNC:-}" ]]; then
  echo "Usage: make visualize-trace CFG=<cfg_path> FUNC=<func_name> [TRACE=<trace_jsonl>] [OUT=<output_stem>]"
  exit 1
fi

OUT="${OUT:-${CFG%.cfg.json}_viz}"

CMD=(poetry run python3 -m trace_synthesizer visualize --cfg "$CFG" --func "$FUNC" --out "$OUT")

if [[ -n "${TRACE:-}" ]]; then
  if [[ "$TRACE" == *.compressed_trace.json ]]; then
    CMD+=(--trace "$TRACE")
  elif [[ "$TRACE" == *.jsonl ]]; then
    tmp_json=$(mktemp)
    head -n 1 "$TRACE" > "$tmp_json"
    CMD+=(--intra-json "$tmp_json")
  else
    CMD+=(--intra-json "$TRACE")
  fi
fi

echo "Running: ${CMD[*]}"
"${CMD[@]}"

if [[ -n "${tmp_json:-}" ]]; then
  rm -f "$tmp_json"
fi

echo "Saved to ${OUT}.svg"
