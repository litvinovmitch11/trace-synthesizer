#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${OUT_DIR:-$ROOT/output/train_lstm}"
DATASET="${DATASET:-$ROOT/output/dataset_cbench/dataset/cross.train.jsonl}"
EPOCHS="${LSTM_EPOCHS:-20}"

if [[ ! -f "$DATASET" ]]; then
  echo "Error: Dataset not found at $DATASET. Please run 'make dataset_cbench' first." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

echo "========================================="
echo "Training LSTM on $DATASET"
echo "========================================="

poetry run python3 scripts/train_feature_window_lstm.py \
  --dataset-jsonl "$DATASET" \
  --out-stem "$OUT_DIR/model" \
  --window-back 8 \
  --epochs "$EPOCHS" \
  --seed 42 \
  --train-report "$OUT_DIR/report.json" 2>&1 | tee "$OUT_DIR/train.log"

echo "Model saved to $OUT_DIR/model.pt"