# Reproduction Guide

How to rebuild the tooling and regenerate every result in
[EXPERIMENTS](EXPERIMENTS.md). For what each component does, see
[OVERVIEW](OVERVIEW.md).

## 1. Prerequisites
- **LLVM 21** with `clang++`, `llc`, `llvm-link`, `llvm-readobj`, `llvm-profdata`, and `llvm-ir2vec` (+ the 75-D seed vocab). Point `LLVM_INSTALL_DIR` at your install.
- **DynamoRIO** (fetched by CMake into `build/_deps/`).
- **Python ≥3.12** with Poetry (CPU PyTorch).

```bash
export LLVM_INSTALL_DIR=/path/to/llvm-install   # if not the Makefile default
make configure        # cmake
make build            # CFGDumper.so + InstrTracer.so + DynamoRIO
poetry install        # Python dependencies
make test-py          # sanity: unit + integration tests should pass
```

## 2. Run the experiments
Each target builds artifacts (CFG + IR2Vec + DynamoRIO reference), trains the
agents, performs the rollouts, and writes metrics + visualizations under
`benchmarks/local/<name>/out/`.

| Command | Thesis | What it shows |
|---|---|---|
| `make exp-trigger`  | 7.2.3 / Table 7.3  | State machine, in-domain (PGO/LSTM/Flat/HRL) |
| `make exp-diamond`  | 7.2.4 / Table 7.4  | Context dependency (diamond) |
| `make exp-mutation` | 7.3.3 / Table 7.5  | Zero-shot CFG mutation |
| `make exp-sorting`  | 7.3.5 / Table 7.6  | Zero-shot nested loops (bubble sort) |
| `make exp-smart`    | 7.4 / Tables 7.7-7.8 | Extreme mutations (peeling, inversion) |
| `make exp-opt`      | 7.5 / Table 7.10   | Cross-optimization O0→O3 |
| `make exp-all`      | —                  | All of the above |

```bash
make exp-trigger      # ~minutes on CPU; trains LSTM + Flat PPO + HRL PPO
```

Results land in `benchmarks/local/<name>/out/metrics_*.json`. Print one:
```bash
python -c "import json;print(json.load(open('benchmarks/local/cpp_trigger/out/metrics_hrl_ppo.json'))['metrics'])"
```

## 3. Notes on reproducibility
- Training is CPU PPO with `seed 42`; absolute KL values vary slightly run-to-run, but the **rankings** in [EXPERIMENTS](EXPERIMENTS.md) are stable.
- `make exp-diamond` uses `--window-back 8` (matches the thesis). To reproduce the window-sensitivity result (Flat 0.09 → 0.98), re-run Flat with `--window-back 32` as shown in [OVERVIEW §4.2](OVERVIEW.md#42-one-program-end-to-end-manual).
- `exp-smart` is the hardest case; the learned policies collapse there (see EXPERIMENTS §5). This is expected and documented.

## 4. Inspecting artifacts
- `metrics_*.json` — block/edge KL and hot-path overlap.
- `viz_*.svg` — the synthesized trace overlaid on the CFG (heat-map).
- `rollouts_*/intra_traces.jsonl` — the raw synthesized traces.

```bash
make clean-output     # remove all generated artifacts
```

## 5. One program, manually
To run the pipeline on your own C/C++ file (build artifacts → loop profile →
train → rollout → metrics), follow the step-by-step commands in
[OVERVIEW §4.2](OVERVIEW.md#42-one-program-end-to-end-manual).
