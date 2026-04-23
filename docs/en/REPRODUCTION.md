# Reproduction (EN)

## Prerequisites

- LLVM toolchain (compatible with this project, default path from `Makefile`).
- Python + Poetry.
- Build tree already configured at least once (`make configure`).
- cBench sources available via `ctuning-bootstrap` (submodule/link).

## Full End-to-End Run

```bash
make clean-output
make build
make plugins-demo
make random-baseline
make dataset-cbench
make train-lstm
make lstm-eval
```

## Expected Outputs

- Plugin demo: `output/plugins_demo/*`
- Random baseline metrics: `output/random_baseline/results/metrics_random.json`
- cBench dataset: `output/dataset_cbench/dataset/cross.train.jsonl`
- LSTM model: `output/train_lstm/model.pt`
- LSTM train log: `output/train_lstm/train.log`
- LSTM eval metrics: `output/lstm_eval/results/metrics_lstm.json`
- Visual overlays:
  - `output/random_baseline/rollouts_random/viz_random_trace.svg`
  - `output/lstm_eval/rollouts_lstm/viz_lstm_trace.svg`
  - `output/lstm_eval/results/viz_real_trace.svg`

## Compare Any Two Trace Sets

```bash
make compare-traces \
  REF=output/lstm_eval/reference_real_intra.json \
  CAND=output/lstm_eval/rollouts_lstm/intra_traces.jsonl \
  FUNC=main \
  OUT=output/lstm_eval/results/metrics_pair_lstm_vs_real.json
```

## Render CFG + Trace Overlay Manually

```bash
make visualize-trace \
  CFG=output/lstm_eval/benchmark_complex.cfg.json \
  FUNC=main \
  TRACE=output/lstm_eval/rollouts_lstm/intra_traces.jsonl \
  OUT=output/lstm_eval/rollouts_lstm/viz_manual
```
