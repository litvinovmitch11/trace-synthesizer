# Воспроизведение (RU)

## Требования

- LLVM toolchain (совместимый с проектом, путь по умолчанию в `Makefile`).
- Python + Poetry.
- Хотя бы раз выполненный `make configure`.
- Доступный cBench через `ctuning-bootstrap` (submodule/линк).

## Полный прогон end-to-end

```bash
make clean-output
make build
make plugins-demo
make random-baseline
make dataset-cbench
make train-lstm
make lstm-eval
```

## Ожидаемые артефакты

- Демо плагинов: `output/plugins_demo/*`
- Метрики бейзлайна: `output/random_baseline/results/metrics_random.json`
- cBench-датасет: `output/dataset_cbench/dataset/cross.train.jsonl`
- LSTM-модель: `output/train_lstm/model.pt`
- Лог обучения LSTM: `output/train_lstm/train.log`
- Метрики LSTM: `output/lstm_eval/results/metrics_lstm.json`
- Визуализации:
  - `output/random_baseline/rollouts_random/viz_random_trace.svg`
  - `output/lstm_eval/rollouts_lstm/viz_lstm_trace.svg`
  - `output/lstm_eval/results/viz_real_trace.svg`

## Сравнение двух наборов трасс

```bash
make compare-traces \
  REF=output/lstm_eval/reference_real_intra.json \
  CAND=output/lstm_eval/rollouts_lstm/intra_traces.jsonl \
  FUNC=main \
  OUT=output/lstm_eval/results/metrics_pair_lstm_vs_real.json
```

## Ручная отрисовка CFG + trace overlay

```bash
make visualize-trace \
  CFG=output/lstm_eval/benchmark_complex.cfg.json \
  FUNC=main \
  TRACE=output/lstm_eval/rollouts_lstm/intra_traces.jsonl \
  OUT=output/lstm_eval/rollouts_lstm/viz_manual
```
