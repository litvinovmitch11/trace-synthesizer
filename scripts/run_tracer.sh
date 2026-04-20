#!/usr/bin/env bash
# Run DynamoRIO with the InstrTracer client plugin.
#
# Usage: ./scripts/run_tracer.sh <binary_path> <module_name_to_trace>
# Example: ./scripts/run_tracer.sh output/simple.bin simple.bin
# Must be run from repo root (or any cwd): paths to build/ are resolved relative to the repo.

set -euo pipefail

if [[ "$#" -lt 2 ]]; then
  echo "Usage: $0 <binary_path> <module_name_to_trace>" >&2
  echo "Example: $0 output/simple.bin simple.bin" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BINARY=$1
MODULE_NAME=$2
BASENAME=$(basename "$BINARY" | cut -d. -f1)

OUT_DIR=$(dirname "$BINARY")
TRACE_OUT="$OUT_DIR/${BASENAME}.trace.bin"

DRRUN="build/_deps/dynamorio_pkg-src/bin64/drrun"
if [[ ! -f "$DRRUN" ]]; then
  echo "Error: drrun not found at $DRRUN. Please build the project to download DynamoRIO." >&2
  exit 1
fi

PLUGIN_SO="build/src/InstrTracer/libInstrTracer.so"
if [[ ! -f "$PLUGIN_SO" ]]; then
  echo "Error: InstrTracer plugin not found. Please run 'make build'." >&2
  exit 1
fi

echo "Running DynamoRIO with InstrTracer..."
"$DRRUN" -c "$PLUGIN_SO" -o "$TRACE_OUT" "$MODULE_NAME" -- "$BINARY"

echo "Trace saved to $TRACE_OUT"
