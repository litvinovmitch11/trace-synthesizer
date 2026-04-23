#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOGDIR="${1:-$ROOT/output/tensorboard}"
PORT="${TB_PORT:-6006}"

echo "TensorBoard logdir: $LOGDIR"
echo "Open: http://localhost:${PORT}"
poetry run tensorboard --logdir "$LOGDIR" --port "$PORT" --bind_all
