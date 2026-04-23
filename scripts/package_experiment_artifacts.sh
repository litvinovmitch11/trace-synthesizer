#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${1:-$ROOT/output/final_artifacts}"
mkdir -p "$OUT_DIR"

copy_if_exists() {
  local src="$1"
  local dst="$2"
  if [[ -e "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -r "$src" "$dst"
  fi
}

copy_if_exists "$ROOT/output/dataset_cbench/dataset/cross.train.jsonl" "$OUT_DIR/dataset/cross.train.jsonl"
copy_if_exists "$ROOT/output/dataset_cbench/dataset/dataset_index.json" "$OUT_DIR/dataset/dataset_index.json"
copy_if_exists "$ROOT/output/train_lstm/model.pt" "$OUT_DIR/model/model.pt"
copy_if_exists "$ROOT/output/train_lstm/model.meta.json" "$OUT_DIR/model/model.meta.json"
copy_if_exists "$ROOT/output/train_lstm/report.json" "$OUT_DIR/model/train_report.json"
copy_if_exists "$ROOT/output/stat_runs/stats_report.json" "$OUT_DIR/eval/stats_report.json"
copy_if_exists "$ROOT/output/hparam_search/search_results.json" "$OUT_DIR/eval/search_results.json"

echo "Artifacts packaged to: $OUT_DIR"
