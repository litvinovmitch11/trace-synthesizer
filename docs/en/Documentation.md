# End-to-End PGO & Trace Pipeline Documentation

This document provides a comprehensive description of the architecture, components, and usage process of the pipeline for collecting Profile-Guided Optimization (PGO) statistics, extracting the CFG, overlaying dynamic DynamoRIO traces, and visualization.

## 1. Overview

For machine learning tasks on compilers (e.g., RL agents), we require:
1. **Environment (Grammar)** — Control Flow Graph (CFG), extracted from LLVM at the very last stage before machine code generation (Machine IR).
2. **PGO Statistics** — Transition probabilities based on real execution profiling, so the agent understands the hot paths.
3. **Ground Truth Data** — Real execution traces (`traces`) that perfectly (100%) match the static graph (CFG), for training and validating the agent.

---

## 2–6. Detailed architecture (moved)

Component descriptions, trace mapping, the six-stage shell pipeline, Graphviz behavior, and limitations now live in modular chapters:

- [English documentation index](README.md); Russian overview: [../ru/Documentation.md](../ru/Documentation.md).
- LLVM plugin: [pipeline/01_llvm_cfgdumper.md](pipeline/01_llvm_cfgdumper.md).
- DynamoRIO client: [pipeline/02_dynamorio_instrtracer.md](pipeline/02_dynamorio_instrtracer.md).
- JSON formats and `ProgramTraceSession`: [formats/03_trace_and_program_interface.md](formats/03_trace_and_program_interface.md).

End-to-end driver scripts remain `scripts/full_pipeline.sh` and `Makefile` targets such as `e2e-pipeline`.

---

## 7. Python package `trace_synthesizer`

Install dependencies with `poetry install` (PyTorch is resolved from the CPU wheel index; `numpy` is pinned to 1.x for compatibility with the pinned `torch` build). The package provides:

- **CFG grammar core** (`trace_synthesizer.core`): validated `Program` / `CfgProgram`, deterministic successor ordering, PGO weight normalization.
- **Trace I/O** (`trace_synthesizer.io`): `BbAddressMap`, RVA trace reading, compress + validate (including recursive call/return handling).
- **Visualization** (`trace_synthesizer.viz`): Graphviz rendering for one function with optional compressed-trace overlay.
- **RL baseline** (`trace_synthesizer.env`, `trace_synthesizer.agents`, `trace_synthesizer.runner`): Gymnasium `CFGWalkEnv`, `RandomPGOAgent`, `rollout-random` CLI writing `runs.jsonl` / `summary.json`.
- **Torch stub** (`trace_synthesizer.agents.torch_policy_stub.MaskedLstmPolicyStub`): masked LSTM policy module for future training (import this submodule directly; it is not loaded for `compress`/`validate`/`visualize` to avoid pulling Torch).
- **Metrics** (`trace_synthesizer.metrics`): compare real vs synthetic intra-traces (KL, hot-path overlap, synthetic throughput benchmark). Definitions: [metrics/README.md](metrics/README.md), index [METRICS_AND_TRACE_ML_INFRASTRUCTURE.md](METRICS_AND_TRACE_ML_INFRASTRUCTURE.md) / [../ru/METRICS_AND_TRACE_ML_INFRASTRUCTURE.md](../ru/METRICS_AND_TRACE_ML_INFRASTRUCTURE.md).
- **benchmark_complex**: `make benchmark-complex` / `python -m trace_synthesizer benchmark-complex` runs real C++ through PGO, CFGDumper, DynamoRIO, then Python rollouts/metrics. Full manual: [BENCHMARK_COMPLEX_MANUAL.md](BENCHMARK_COMPLEX_MANUAL.md) (RU: [../ru/BENCHMARK_COMPLEX_MANUAL.md](../ru/BENCHMARK_COMPLEX_MANUAL.md)).
- **ctuning-programs**: `make ctuning-bootstrap` / `ctuning-rollout` — [CTUNING_PROGRAMS.md](CTUNING_PROGRAMS.md); core experiment — [CTUNING_CORE_EXPERIMENT.md](CTUNING_CORE_EXPERIMENT.md) (RU: [../ru/CTUNING_CORE_EXPERIMENT.md](../ru/CTUNING_CORE_EXPERIMENT.md)).

### CLI (examples)

```bash
poetry run python -m trace_synthesizer compress \
  --cfg output/foo.cfg.json --map output/foo_bb_map.txt \
  --trace output/foo.trace.bin --out output/foo.compressed_trace.json

poetry run python -m trace_synthesizer validate \
  --cfg output/foo.cfg.json --map output/foo_bb_map.txt --trace output/foo.trace.bin

poetry run python -m trace_synthesizer visualize \
  --cfg output/foo.cfg.json --func main --out output/foo_main_cfg_pgo

poetry run python -m trace_synthesizer rollout-random \
  --cfg output/foo.cfg.json --func main --episodes 20 --seed 0 --out-dir output/rollouts_foo
```

**Intra-procedural note:** `CFGWalkEnv` and `rollout-random` operate on a **single function** at a time (e.g. `main`). The global `compressed_trace.json` remains inter-procedural; filter by `func` when comparing to a single-function walk.
