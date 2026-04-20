# Reproduction and acceptance (EN)

**Versions.** LLVM 21 toolchain (`clang-21`, `clang++-21`, matching `llvm-readobj`/`llc` under your install prefix), Python 3.12+, Poetry-managed deps (see `pyproject.toml`).

**One-line baseline story.** *Baseline* = RandomPGO Markov walks on the LLVM CFG grammar; *ML-ready* = the same trace JSON (`bb_trace`), the same metric hooks, and a swappable agent behind the `Agent` protocol.

## Environment

```bash
export LLVM_INSTALL_DIR=/path/to/llvm-project/build-install   # or LLVM_DIR for shell scripts
export PATH="$LLVM_INSTALL_DIR/bin:$PATH"
```

## Python

```bash
cd /path/to/trace-synthesizer
poetry install
```

## Native build

```bash
make configure    # passes -DLT_LLVM_INSTALL_DIR=$(LLVM_INSTALL_DIR)
make build
./scripts/check_baseline.sh   # also run by `make check`
```

## Tests (required smoke)

```bash
make test-py
# or
poetry run pytest tests/ -q
```

## End-to-end on one example

```bash
make e2e-pipeline FILE=examples/complex.cpp ARGS=""
# artifacts under output/
```

## `benchmark_complex`

```bash
make benchmark-complex
# manual: docs/en/BENCHMARK_COMPLEX_MANUAL.md (RU: docs/ru/BENCHMARK_COMPLEX_MANUAL.md)
```

## Ctuning rollouts and stats

```bash
git submodule update --init --recursive external/ctuning-programs   # or: make ctuning-bootstrap
make ctuning-rollout CTUNING_ARGS='--only cbench-telecom-crc32 --episodes 5 --max-steps 3000 --seed 0'
# expect output/ctuning_curated_stats.json unless --no-stats
```

## CRC32 paired traces + SVG (visualization acceptance)

After the crc32 row exists under `output/ctuning_cbench-telecom-crc32/`:

```bash
./scripts/ctuning_crc32_paired_traces_and_viz.sh
# SVG pair under output/ctuning_cbench-telecom-crc32/paired_viz/
```

## Acceptance checklist (clean clone)

All steps should pass after the commands above on a machine with LLVM + build deps installed.

1. **Build.** `make configure && make build` produces `build/src/CFGDumper/CFGDumper.so`, `build/src/InstrTracer/libInstrTracer.so`, and `build/_deps/dynamorio_pkg-src/bin64/drrun`.
2. **Canonical intra schema.** `export-intra-trace` and `rollout-random --write-canonical-intra` emit the same top-level JSON keys and `source: bb_trace` (see `trace_synthesizer/io/intra_trace.py`). Covered by `tests/test_intra_canonical.py`.
3. **Baseline generator.** `rollout-random` with `RandomPGOAgent` + `CFGWalkEnv` completes on small fixtures (`tests/test_cfg_walk_*.py`, `tests/test_runner_paths_jsonl.py`).
4. **Metrics.** `metrics-compare` accepts ref/cand for the same `function_name`; `metrics-bench-speed` runs (`tests/test_metrics_e2e.py` exercises the stack on `benchmark_complex`).
5. **Curated set.** `make ctuning-rollout` (with submodule) writes `output/ctuning_curated_stats.json` without hand-edited paths; use `--skip-pipeline` only when prior artifacts exist.
6. **Visualization.** `scripts/ctuning_crc32_paired_traces_and_viz.sh` yields two SVG files when crc32 artifacts exist.

`make check` runs Python tests plus `scripts/check_baseline.sh` (subset of item 1).

Russian version: [../ru/REPRODUCTION.md](../ru/REPRODUCTION.md).
