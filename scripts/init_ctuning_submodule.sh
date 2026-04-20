#!/usr/bin/env bash
# Initialize external/ctuning-programs as a git submodule (preferred).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUB="$ROOT/external/ctuning-programs"

if [[ -d "$SUB/program" ]]; then
  echo "ctuning-programs already present: $SUB"
  exit 0
fi

if [[ -f "$ROOT/.gitmodules" ]] && grep -qF '[submodule "external/ctuning-programs"]' "$ROOT/.gitmodules" 2>/dev/null; then
  echo "Initializing submodule external/ctuning-programs ..."
  git -C "$ROOT" submodule update --init --depth 1 external/ctuning-programs
  exit 0
fi

echo "No .gitmodules entry for ctuning-programs; falling back to shallow clone (legacy)." >&2
exec "$ROOT/scripts/bootstrap_ctuning_programs.sh"
