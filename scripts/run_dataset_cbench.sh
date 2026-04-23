#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${OUT_DIR:-$ROOT/output/dataset_cbench}"
N_DR="${N_DR:-4}"
DR_TIMEOUT_SEC="${DR_TIMEOUT_SEC:-90}"
CTUNING_ROOT="${CTUNING_ROOT:-$ROOT/external/ctuning-programs}"
if [[ ! -d "$CTUNING_ROOT/program" && -d "$ROOT/benchmarks/external/ctuning-programs/program" ]]; then
  CTUNING_ROOT="$ROOT/benchmarks/external/ctuning-programs"
fi
MANIFEST="${MANIFEST:-$ROOT/benchmarks/external/ctuning_curated.json}"

PLUGIN_SO="build/src/CFGDumper/CFGDumper.so"
DRRUN="build/_deps/dynamorio_pkg-src/bin64/drrun"
TRACER_SO="build/src/InstrTracer/libInstrTracer.so"

if [[ ! -d "$CTUNING_ROOT/program" ]]; then
  echo "Error: cbench not found at $CTUNING_ROOT. Run 'make ctuning-bootstrap' first." >&2
  exit 1
fi

if [[ ! -f "$PLUGIN_SO" || ! -f "$TRACER_SO" ]]; then
  echo "Error: Plugins not found. Please run 'make build'." >&2
  exit 1
fi

if [[ ! -f "$MANIFEST" ]]; then
  echo "Error: manifest not found: $MANIFEST" >&2
  exit 1
fi

mkdir -p "$OUT_DIR/inputs" "$OUT_DIR/dr_runs"

echo "========================================="
echo "Dataset cbench (PGO+CFG+DR)"
echo "========================================="

export ROOT OUT_DIR CTUNING_ROOT MANIFEST

python3 -c '
import json, os
from pathlib import Path

manifest = Path(os.environ["MANIFEST"])
entries = json.loads(manifest.read_text(encoding="utf-8"))
spec_entries = []
for e in entries:
    pid = e["id"]
    spec_entries.append(
        {
            "id": pid,
            "cfg": f"{pid}.cfg.json",
            "func": e.get("rollout_func", e.get("entry_func", "main")),
            "compressed_glob": f"dr_runs/{pid}/*/{pid}.compressed_trace.json",
        }
    )
Path(os.environ["OUT_DIR"]).joinpath("spec.json").write_text(
    json.dumps({"schema_version": 1, "entries": spec_entries}, indent=2),
    encoding="utf-8",
)
' 

mapfile -t IDS < <(python3 -c '
import json, os
from pathlib import Path
for e in json.loads(Path(os.environ["MANIFEST"]).read_text(encoding="utf-8")):
    print(e["id"])
')

for id in "${IDS[@]}"; do
  echo "Processing $id..."

  mapfile -t META < <(ENTRY_ID="$id" python3 -c '
import json, os
from pathlib import Path

pid = os.environ["ENTRY_ID"]
manifest = json.loads(Path(os.environ["MANIFEST"]).read_text(encoding="utf-8"))
entry = next(x for x in manifest if x["id"] == pid)
root = Path(os.environ["ROOT"])
out = Path(os.environ["OUT_DIR"])
ct = Path(os.environ["CTUNING_ROOT"])

sources = [str((ct / rel).resolve()) for rel in entry["sources_relative"]]
profile_env = entry.get("profile_env", {})
profile_env_kv = ",".join(f"{k}={v}" for k, v in profile_env.items())
bin_args = [str(x) for x in entry.get("profile_argv", [])]
pd = entry.get("profile_data")
if isinstance(pd, dict):
    kind = pd.get("kind")
    if kind == "text_file":
        path = out / "inputs" / (pid + "_" + str(pd.get("filename", "input.txt")))
        path.write_text(str(pd.get("content", "")), encoding="utf-8")
        bin_args.insert(0, str(path))
    elif kind == "float_space_separated":
        path = out / "inputs" / f"{pid}_floats.txt"
        n = int(pd.get("float_count", 16))
        v = str(pd.get("value", "0.1"))
        path.write_text(" ".join([v] * n) + "\n", encoding="utf-8")
        bin_args.insert(0, str(path))

print(entry.get("rollout_func", entry.get("entry_func", "main")))
print(profile_env_kv)
print(" ".join(sources))
print("\n".join(bin_args))
')

  if [[ ${#META[@]} -lt 3 ]]; then
    echo "Error: manifest parsing failed for $id" >&2
    exit 1
  fi
  profile_env_kv="${META[1]}"
  sources_joined="${META[2]}"

  declare -a args_array=()
  if [[ ${#META[@]} -gt 3 ]]; then
    for ((k=3; k<${#META[@]}; k++)); do
      if [[ -n "${META[$k]}" ]]; then
        args_array+=("${META[$k]}")
      fi
    done
  fi

  PROFILE_ENV_KV="$profile_env_kv" \
  CTUNING_BASENAME="$id" \
  CTUNING_PRIMARY="$CTUNING_ROOT/program/$id" \
  CTUNING_SOURCES="$sources_joined" \
  bash scripts/ctuning_full_pipeline_c.sh "${args_array[@]}" >/dev/null

  for ((i=0; i<N_DR; i++)); do
    d="$OUT_DIR/dr_runs/$id/$(printf '%02d' "$i")"
    mkdir -p "$d"
    timeout "$DR_TIMEOUT_SEC" "$DRRUN" -c "$TRACER_SO" -o "$d/${id}.trace.bin" "${id}.bin" -- "$OUT_DIR/${id}.bin" "${args_array[@]}" >/dev/null || true
    if [[ ! -s "$d/${id}.trace.bin" ]]; then
      echo "  skip dr run $i for $id (timeout or empty trace)"
      continue
    fi
    poetry run python3 -m trace_synthesizer compress \
      --cfg "$OUT_DIR/${id}.cfg.json" \
      --map "$OUT_DIR/${id}_bb_map.txt" \
      --trace "$d/${id}.trace.bin" \
      --out "$d/${id}.compressed_trace.json" >/dev/null
  done
done

echo "========================================="
echo "Building JSONL Dataset"
echo "========================================="

poetry run python3 scripts/build_multi_program_intra_dataset.py \
  --spec "$OUT_DIR/spec.json" \
  --out-dir "$OUT_DIR/dataset"

echo "Dataset cbench ready: $OUT_DIR/dataset/cross.train.jsonl"
