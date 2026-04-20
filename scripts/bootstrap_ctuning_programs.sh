#!/usr/bin/env bash
# Legacy shallow clone when the repo has no git submodule for ctuning-programs.
# Prefer: ./scripts/init_ctuning_submodule.sh (or `git submodule update --init`).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/external/ctuning-programs"
URL="${CTUNING_PROGRAMS_URL:-https://github.com/ctuning/ctuning-programs.git}"
if [[ -d "$DEST/.git" ]]; then
  echo "Already present: $DEST"
  exit 0
fi

mkdir -p "$(dirname "$DEST")"
echo "Cloning ctuning-programs -> $DEST"
git clone --depth 50 "$URL" "$DEST"
echo "Done."
