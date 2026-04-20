# Trace Synthesizer

Research pipeline that couples **LLVM Machine IR CFGs** (with PGO edge weights) to **DynamoRIO instruction traces**, compresses them to basic-block sequences, and compares **ground-truth** runs against **synthetic** traces generated on the same CFG grammar.

**Current stage.** A reproducible **baseline**: Markov random walks driven by normalized PGO weights (`RandomPGOAgent` + `CFGWalkEnv`). The stack is **ML-ready** in the sense that trace JSON (`bb_trace`), compression/validation, metrics, and Gymnasium hooks stay fixed while the policy behind the agent protocol can be swapped for trainable models.

**One-line contract.** *Baseline* = RandomPGO on the CFG grammar; *ML-ready* = same trace formats, same metric entry points, swappable agent.

## Documentation

Documentation is split by language under `docs/en/` and `docs/ru/` (mirrored filenames). Entry points:

- [docs/README.md](docs/README.md) — how to pick a language tree.
- English hub: [docs/en/README.md](docs/en/README.md); Russian hub: [docs/ru/README.md](docs/ru/README.md).
- Reproduction: [docs/en/REPRODUCTION.md](docs/en/REPRODUCTION.md), [docs/ru/REPRODUCTION.md](docs/ru/REPRODUCTION.md).
- Overview: [docs/en/Documentation.md](docs/en/Documentation.md), [docs/ru/Documentation.md](docs/ru/Documentation.md).
- Metrics index: [docs/en/METRICS_AND_TRACE_ML_INFRASTRUCTURE.md](docs/en/METRICS_AND_TRACE_ML_INFRASTRUCTURE.md), [docs/ru/METRICS_AND_TRACE_ML_INFRASTRUCTURE.md](docs/ru/METRICS_AND_TRACE_ML_INFRASTRUCTURE.md).
- Ctuning: [docs/en/CTUNING_PROGRAMS.md](docs/en/CTUNING_PROGRAMS.md), [docs/ru/CTUNING_PROGRAMS.md](docs/ru/CTUNING_PROGRAMS.md); core experiment: [docs/en/CTUNING_CORE_EXPERIMENT.md](docs/en/CTUNING_CORE_EXPERIMENT.md), [docs/ru/CTUNING_CORE_EXPERIMENT.md](docs/ru/CTUNING_CORE_EXPERIMENT.md).
- `benchmark_complex` manual: [docs/en/BENCHMARK_COMPLEX_MANUAL.md](docs/en/BENCHMARK_COMPLEX_MANUAL.md), [docs/ru/BENCHMARK_COMPLEX_MANUAL.md](docs/ru/BENCHMARK_COMPLEX_MANUAL.md).

## Prerequisites

- LLVM 21 (compiler + `llvm-readobj` + `llc` on `PATH` or under `LLVM_INSTALL_DIR`).
- DynamoRIO fetched/built by CMake.
- Python 3.12+ and Poetry.
- CMake, Ninja/Make, a C++ toolchain matching the LLVM major you link against.

## Quickstart

```bash
poetry install
export LLVM_INSTALL_DIR=/path/to/llvm-project/build-install   # override default from Makefile
make configure
make build
make check          # pytest + lightweight native artifact checks
```

End-to-end on one example:

```bash
make e2e-pipeline FILE=examples/complex.cpp ARGS=""
```

Curated ctuning rollouts (needs submodule):

```bash
make ctuning-bootstrap
make ctuning-rollout CTUNING_ARGS='--only cbench-telecom-crc32 --episodes 5 --max-steps 3000 --seed 0'
```

Paired CRC32 visualization (after crc32 artifacts exist):

```bash
./scripts/ctuning_crc32_paired_traces_and_viz.sh
```

## Make targets

Run `make help` for a short list. Common targets: `configure`, `build`, `test-py`, `check`, `e2e-pipeline`, `cfg-examples`, `trace-examples`, `benchmark-complex`, `ctuning-bootstrap`, `ctuning-rollout`.

## Python CLI (after `poetry install`)

```bash
poetry run python -m trace_synthesizer compress \
  --cfg output/foo.cfg.json --map output/foo_bb_map.txt \
  --trace output/foo.trace.bin --out output/foo.compressed_trace.json

poetry run python -m trace_synthesizer rollout-random \
  --cfg output/foo.cfg.json --func main --episodes 10 --seed 0 --out-dir output/rollouts_foo

poetry run python -m trace_synthesizer metrics-compare \
  --reference output/main_intra_real.json \
  --candidate output/rollouts_foo/intra_traces.jsonl \
  --func main --out output/metrics_report.json
```

Shell scripts honor `LLVM_DIR` or `LLVM_INSTALL_DIR` (see `scripts/full_pipeline.sh`, `scripts/generate_cfg.sh`, `scripts/ctuning_full_pipeline_c.sh`).
