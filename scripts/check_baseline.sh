#!/usr/bin/env bash
# Lightweight artifact checks for the ML-ready baseline (no e2e compile).
# Full acceptance steps live in docs/REPRODUCTION_*.md.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ok=0
fail() { echo "check_baseline: FAIL — $*" >&2; ok=1; }

[[ -f "$ROOT/build/src/CFGDumper/CFGDumper.so" ]] || fail "missing build/src/CFGDumper/CFGDumper.so (run: make configure && make build)"
[[ -f "$ROOT/build/src/InstrTracer/libInstrTracer.so" ]] || fail "missing InstrTracer client"
[[ -f "$ROOT/build/_deps/dynamorio_pkg-src/bin64/drrun" ]] || fail "missing drrun"

if [[ "$ok" -ne 0 ]]; then
  exit 1
fi
echo "check_baseline: build artifacts OK (CFGDumper.so, InstrTracer, drrun)."
