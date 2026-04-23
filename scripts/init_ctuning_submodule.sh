#!/usr/bin/env bash
# Initialize external/benchmarks/ctuning-programs as a git submodule (preferred).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUB="$ROOT/benchmarks/external/ctuning-programs"

if [[ -d "$SUB/program" ]]; then
  echo "ctuning-programs already present: $SUB"
  exit 0
fi

for CAND in \
  "${CTUNING_ROOT:-}" \
  "$ROOT/../benchmarks/ctuning-programs" \
  "$ROOT/../../benchmarks/ctuning-programs" \
  "$HOME/dev/llvm/ctuning-programs" \
  "$HOME/dev/ctuning-programs"
do
  if [[ -n "$CAND" && -d "$CAND/program" ]]; then
    mkdir -p "$(dirname "$SUB")"
    rm -rf "$SUB"
    ln -s "$CAND" "$SUB"
    echo "Using existing ctuning-programs: $CAND"
    exit 0
  fi
done

if [[ -f "$ROOT/.gitmodules" ]] && grep -qF '[submodule "benchmarks/external/ctuning-programs"]' "$ROOT/.gitmodules" 2>/dev/null; then
  echo "Initializing submodule benchmarks/external/ctuning-programs ..."
  git -C "$ROOT" submodule update --init --depth 1 benchmarks/external/ctuning-programs
  exit 0
fi

echo "No .gitmodules entry for external/ctuning-programs" >&2
echo "Please add submodule or set CTUNING_ROOT to an existing checkout." >&2
exit 1
