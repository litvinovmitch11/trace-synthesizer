# Manual `benchmark_complex` run (C++ plugins + Python)

This document describes the **full** path: real source `examples/benchmark_complex/benchmark_complex.cpp` → PGO profile → LLVM `llc` with **CFGDumper** → binary with `.llvm_bb_addr_map` → **DynamoRIO** with **InstrTracer** → Python compress/validate and metrics.

**Preferred entry points:**

```bash
# from repo root, after `make build`
./scripts/run_benchmark_complex.sh
```

or:

```bash
make benchmark-complex
```

or:

```bash
poetry run python -m trace_synthesizer benchmark-complex
```

The sections below repeat the same steps **by hand** when you need to debug one stage. LLVM/DynamoRIO paths live in `scripts/full_pipeline.sh` (`LLVM_DIR` / `LLVM_INSTALL_DIR`, plugin binaries under `build/`).

---

## 0. Prerequisites

```bash
cd /path/to/trace-synthesizer
make configure   # once after clone / LLVM change
make build       # builds CFGDumper.so, InstrTracer, DynamoRIO
poetry install
```

Check build outputs:

```bash
test -f build/src/CFGDumper/CFGDumper.so
test -f build/src/InstrTracer/libInstrTracer.so
test -f build/_deps/dynamorio_pkg-src/bin64/drrun
```

---

## 1. Full automated C++ path (same as the first half of `run_benchmark_complex.sh`)

Default source: `examples/benchmark_complex/benchmark_complex.cpp`. Arguments after the file name are forwarded to the **instrumented profiling binary** in pipeline step 2.

```bash
export OUT_DIR="${OUT_DIR:-output}"
./scripts/full_pipeline.sh examples/benchmark_complex/benchmark_complex.cpp
# with arguments for the binary:
./scripts/full_pipeline.sh examples/benchmark_complex/benchmark_complex.cpp my_arg
```

Artifacts in `$OUT_DIR/` (with `OUT_DIR=output` and stem `benchmark_complex`):

| File | Role |
|------|------|
| `benchmark_complex.cfg.json` | Whole-program CFG (JSON) |
| `benchmark_complex.bin` | Final executable |
| `benchmark_complex_bb_map.txt` | `llvm-readobj --bb-addr-map` |
| `benchmark_complex.trace.bin` | Raw RVA trace from DynamoRIO |
| `benchmark_complex.compressed_trace.json` | Compressed + validated trace |
| `benchmark_complex_main_cfg_pgo.svg` | CFG visualization without trace |
| `benchmark_complex_main_cfg_pgo_trace.svg` | CFG with trace overlay |

---

## 2. Manual decomposition of `full_pipeline.sh`

Commands mirror the script; adjust `LLVM_DIR` / `LLVM_INSTALL_DIR` for your install.

```bash
export LLVM_DIR="${LLVM_DIR:-${LLVM_INSTALL_DIR:-/home/mitchell/dev/llvm/llvm-project/build-install}}"
export CLANG="$LLVM_DIR/bin/clang++"
export LLVM_PROFDATA="$LLVM_DIR/bin/llvm-profdata"
export LLVM_LINK="$LLVM_DIR/bin/llvm-link"
export LLC="$LLVM_DIR/bin/llc"
export LLVM_READOBJ="$LLVM_DIR/bin/llvm-readobj"
export OUT_DIR="${OUT_DIR:-output}"
export BASENAME=benchmark_complex
export INPUT_FILE="examples/benchmark_complex/benchmark_complex.cpp"
export PLUGIN_SO="build/src/CFGDumper/CFGDumper.so"
export DRRUN="build/_deps/dynamorio_pkg-src/bin64/drrun"
export TRACER_SO="build/src/InstrTracer/libInstrTracer.so"
mkdir -p "$OUT_DIR"
```

### [1/6] Profiling binary

```bash
$CLANG -O3 -fprofile-instr-generate -fcoverage-mapping "$INPUT_FILE" \
  -o "$OUT_DIR/${BASENAME}_prof"
```

### [2/6] Profile run + merge

```bash
LLVM_PROFILE_FILE="$OUT_DIR/default.profraw" "$OUT_DIR/${BASENAME}_prof"
$LLVM_PROFDATA merge -output="$OUT_DIR/${BASENAME}.profdata" "$OUT_DIR/default.profraw"
```

### [3/6] LTO + PGO + CFGDumper (`llc`) + link + bb map

```bash
$CLANG -O3 -fPIC -fbasic-block-address-map -flto \
  -fprofile-instr-use="$OUT_DIR/${BASENAME}.profdata" \
  -c "$INPUT_FILE" -o "$OUT_DIR/${BASENAME}.bc"

$LLVM_LINK "$OUT_DIR/${BASENAME}.bc" -o "$OUT_DIR/${BASENAME}_whole.bc"

$LLC --basic-block-address-map -relocation-model=pic \
  -load="$PLUGIN_SO" -cfg-pretty=false \
  -cfg-out-file="$OUT_DIR/${BASENAME}.cfg.json" \
  "$OUT_DIR/${BASENAME}_whole.bc" -o "$OUT_DIR/${BASENAME}.s"

$CLANG "$OUT_DIR/${BASENAME}.s" -o "$OUT_DIR/${BASENAME}.bin"

$LLVM_READOBJ --bb-addr-map "$OUT_DIR/${BASENAME}.bin" > "$OUT_DIR/${BASENAME}_bb_map.txt"
```

### [4/6] DynamoRIO + InstrTracer

```bash
$DRRUN -c "$TRACER_SO" -o "$OUT_DIR/${BASENAME}.trace.bin" "${BASENAME}.bin" -- \
  "$OUT_DIR/${BASENAME}.bin"
```

### [5/6] Compress / validate (Python)

```bash
poetry run python3 -m trace_synthesizer compress \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
  --map "$OUT_DIR/${BASENAME}_bb_map.txt" \
  --trace "$OUT_DIR/${BASENAME}.trace.bin" \
  --out "$OUT_DIR/${BASENAME}.compressed_trace.json"
```

### [6/6] Visualization (Python)

```bash
poetry run python3 -m trace_synthesizer visualize \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" --func main \
  --out "$OUT_DIR/${BASENAME}_main_cfg_pgo"

poetry run python3 -m trace_synthesizer visualize \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" --func main \
  --trace "$OUT_DIR/${BASENAME}.compressed_trace.json" \
  --out "$OUT_DIR/${BASENAME}_main_cfg_pgo_trace"
```

---

## 3. Python analysis after tracing (second half of `run_benchmark_complex.sh`)

Set `FUNC=main` (or another `function_name` from `cfg.json` if mangling differs).

```bash
export FUNC=main
```

### Export real intra trace

```bash
poetry run python3 -m trace_synthesizer export-intra-trace \
  --compressed "$OUT_DIR/${BASENAME}.compressed_trace.json" \
  --func "$FUNC" \
  --out "$OUT_DIR/${BASENAME}_real_intra.json"
```

### Synthetic rollouts

```bash
poetry run python3 -m trace_synthesizer rollout-random \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
  --func "$FUNC" \
  --episodes 120 --seed 42 --max-steps 8000 \
  --out-dir "$OUT_DIR/${BASENAME}_rollouts"
```

### Metrics compare

```bash
poetry run python3 -m trace_synthesizer metrics-compare \
  --reference "$OUT_DIR/${BASENAME}_real_intra.json" \
  --candidate "$OUT_DIR/${BASENAME}_rollouts/intra_traces.jsonl" \
  --func "$FUNC" \
  --out "$OUT_DIR/${BASENAME}_metrics.json"
```

### Synthetic throughput benchmark

```bash
poetry run python3 -m trace_synthesizer metrics-bench-speed \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
  --func "$FUNC" \
  --n-episodes 200 --max-steps 4000 --seed 0 \
  --out "$OUT_DIR/${BASENAME}_bench_speed.json"
```

---

## 4. Orchestrator environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `BENCHMARK_CPP` | `examples/benchmark_complex/benchmark_complex.cpp` | Source for the pipeline |
| `OUT_DIR` | `output` | Artifact directory |
| `FUNC` | `main` | Function name for Python commands |
| `SKIP_ANALYSIS` | `0` | `1` → only `full_pipeline.sh`, no rollout/metrics |
| `ROLL_EPISODES` | `120` | Rollout episode count |
| `ROLL_SEED` | `42` | Rollout RNG seed |
| `ROLL_MAX_STEPS` | `8000` | Per-episode step cap |
| `BENCH_EPISODES` | `200` | Episodes for bench-speed |
| `BENCH_MAX_STEPS` | `4000` | `max-steps` for bench |
| `BENCH_SEED` | `0` | Bench RNG seed |

Example:

```bash
OUT_DIR=output/my_run FUNC=main ROLL_EPISODES=200 \
  ./scripts/run_benchmark_complex.sh
```

---

## 5. Relation to the “hand-made” JSON used in unit tests

`examples/benchmark_complex/main.cfg.json` is a **synthetic** CFG for offline Python tests (no LLVM). It is **not** emitted by the C++ pipeline; the real post-build CFG is `output/benchmark_complex.cfg.json` (or your `$OUT_DIR`).

Russian: [same chapter](../ru/BENCHMARK_COMPLEX_MANUAL.md).
