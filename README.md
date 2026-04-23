# TraceSynthesizer

TraceSynthesizer is a production-style research pipeline for program trace synthesis:

- LLVM MIR CFG extraction with PGO-aware edge weights (`CFGDumper`).
- Real instruction tracing via DynamoRIO (`InstrTracer`).
- Trace compression to BB-level sequences and CFG-valid transition checks.
- Synthetic generators: probabilistic Random-PGO baseline and CFG-agnostic Feature-Window LSTM.
- Metrics and visualization for real-vs-synthetic comparison.

## Scope Aligned With Proposal

The repository currently targets the stage up to a simple supervised LSTM model trained on default block features:

- tracer + LLVM plugin,
- Python CFG environment,
- random probabilistic baseline,
- LSTM training and rollout,
- cBench-based training corpus build,
- local benchmark evaluation,
- metrics and trace-on-CFG visualization.

Future RL/embedding extensions remain possible, but are not part of the required main pipeline.

## Main Make Targets

```bash
make plugins-demo
make random-baseline
make dataset-cbench
make train-lstm
make lstm-eval
make visualize-trace
make compare-traces
```

## Reproducible Pipeline

```bash
make clean-output
make build
make plugins-demo
make random-baseline
make dataset-cbench
make train-lstm
make lstm-eval
make tensorboard ARGS="output/tensorboard"
make package-artifacts
```

Training data is collected from curated cBench entries in `benchmarks/external/ctuning_curated.json`, while evaluation is performed on the local example `benchmarks/local/benchmark_complex.cpp`.

## Utilities

- `make visualize-trace CFG=... FUNC=... [TRACE=...] [OUT=...]`
- `make compare-traces REF=... CAND=... FUNC=... OUT=...`
- `make test-py`
- `make tensorboard ARGS="output/tensorboard"` (open TensorBoard UI)
- `make package-artifacts` (save final dataset/model/reports to `output/final_artifacts`)

## Colab / Kaggle (CPU-friendly)

You can run training in Colab or Kaggle on CPU:

```bash
pip install poetry
poetry install
N_DR=2 DR_TIMEOUT_SEC=60 make dataset-cbench
LSTM_EPOCHS=20 LSTM_TB_LOGDIR=output/tensorboard make train-lstm
poetry run python3 scripts/run_lstm_stat_experiments.py --root . --seeds 17,23,31,43,59 --episodes 16 --max-steps 4000
make package-artifacts
```

This repository uses LLVM + DynamoRIO for full trace collection, so Colab/Kaggle should be used mainly for Python-side training/evaluation on already collected datasets.

## Documentation

- Docs index: `docs/README.md`
- English: `docs/en/README.md`, `docs/en/REPRODUCTION.md`
- Russian: `docs/ru/README.md`, `docs/ru/REPRODUCTION.md`
