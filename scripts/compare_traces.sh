#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -z "${REF:-}" || -z "${CAND:-}" || -z "${FUNC:-}" || -z "${OUT:-}" ]]; then
  echo "Usage: make compare-traces REF=<reference_intra.json|jsonl> CAND=<candidate_intra.json|jsonl> FUNC=<func> OUT=<metrics.json>" >&2
  exit 1
fi

poetry run python3 -m trace_synthesizer metrics-compare \
  --reference "$REF" \
  --candidate "$CAND" \
  --func "$FUNC" \
  --out "$OUT"

echo "Metrics saved to $OUT"
