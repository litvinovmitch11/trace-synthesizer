#!/usr/bin/env bash
# Export Dynamo + synthetic intra traces in the same canonical JSON schema, then render two CFG+trace SVGs.
# Prereq: full ctuning pipeline already ran for cbench-telecom-crc32 (cfg + compressed_trace under output/).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
BASE="$ROOT/output/ctuning_cbench-telecom-crc32"
CFG="$BASE/cbench-telecom-crc32.cfg.json"
COMP="$BASE/cbench-telecom-crc32.compressed_trace.json"
FUNC=main1
OUTD="$BASE/paired_viz"

if [[ ! -f "$CFG" || ! -f "$COMP" ]]; then
  echo "Missing $CFG or $COMP — run ctuning-rollout for cbench-telecom-crc32 first." >&2
  exit 1
fi

mkdir -p "$OUTD"
TMP="$OUTD/_rollout_tmp"
rm -rf "$TMP"
mkdir -p "$TMP"

echo "[1/4] Export Dynamo trace -> canonical intra JSON"
poetry run python3 -m trace_synthesizer export-intra-trace \
  --compressed "$COMP" --func "$FUNC" \
  --out "$OUTD/${FUNC}_real.intra.json"

echo "[2/4] One synthetic rollout (until CFG exit) -> canonical intra JSON"
poetry run python3 -m trace_synthesizer rollout-random \
  --cfg "$CFG" --func "$FUNC" \
  --episodes 1 --seed 42 --max-steps 0 \
  --out-dir "$TMP" \
  --write-canonical-intra "$OUTD/${FUNC}_synthetic.intra.json"

echo "[3/4] Visualize CFG + real trace"
poetry run python3 -m trace_synthesizer visualize \
  --cfg "$CFG" --func "$FUNC" \
  --intra-json "$OUTD/${FUNC}_real.intra.json" \
  --out "$OUTD/${FUNC}_cfg_real_trace"

echo "[4/4] Visualize CFG + synthetic trace"
poetry run python3 -m trace_synthesizer visualize \
  --cfg "$CFG" --func "$FUNC" \
  --intra-json "$OUTD/${FUNC}_synthetic.intra.json" \
  --out "$OUTD/${FUNC}_cfg_synth_trace"

rm -rf "$TMP"
echo "Done:"
echo "  $OUTD/${FUNC}_real.intra.json"
echo "  $OUTD/${FUNC}_synthetic.intra.json"
echo "  $OUTD/${FUNC}_cfg_real_trace.svg"
echo "  $OUTD/${FUNC}_cfg_synth_trace.svg"
