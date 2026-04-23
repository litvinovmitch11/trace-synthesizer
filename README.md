# Trace Synthesizer

Research pipeline that couples **LLVM Machine IR CFGs** (with PGO edge weights) to **DynamoRIO instruction traces**, compresses them to basic-block sequences, and compares **ground-truth** runs against **synthetic** traces generated on the same CFG grammar.

## Текущие возможности проекта (Current Capabilities)

В рамках проекта реализован полный пайплайн от сбора данных до обучения простой нейросетевой модели:

1. **LLVM Плагин (CFGDumper)**: Извлечение графа потока управления (CFG) на уровне Machine IR вместе с профилировочной информацией (PGO).
2. **DynamoRIO Трейсер (InstrTracer)**: Сбор реальных инструкционных трасс программы.
3. **Описание программы как среды (RL Environment)**: Среда на Python (`CFGWalkEnv`), совместимая с Gymnasium, валидирующая легальность переходов по CFG.
4. **Вероятностный бейзлайн (Random PGO Agent)**: Агент, совершающий марковские случайные блуждания по графу пропорционально PGO-весам.
5. **Нейросетевая модель (Feature-Window LSTM)**: Архитектура LSTM (`feature_window_lstm_agent.py`), которая независима от конкретного CFG. Обучается на корпусе данных с дефолтными признаками блоков (`BlockFeatures`).
6. **Обучение LSTM**: Скрипт `train_feature_window_lstm.py` для тренировки модели на собранном корпусе данных.
7. **Сборка датасета**: Скрипт `build_multi_program_intra_dataset.py` для формирования общего корпуса трасс из разных программ.
8. **Валидация и метрики**: Модуль метрик (KL-дивергенция частот блоков/ребер, Hot-Path Accuracy, оценка ускорения генерации) и скрипты для автоматической валидации сгенерированных трасс (`run_production_validation_experiment.sh`, `summarize_production_validation.py`).
9. **Визуализация и аналитика**: Вспомогательные методы для отрисовки трассы поверх CFG среды. Единый Jupyter-ноутбук (`notebooks/lstm_training_and_metrics.ipynb`) для визуализации графов, запуска обучения LSTM и отрисовки графиков метрик.
10. **Бенчмарки**: Поддержка внешних бенчмарков (`cbench`/`ctuning`) и локального ручного комплексного примера (`benchmarks/local/benchmark_complex.cpp`).
11. **Расширяемость**: Архитектура содержит заготовки (протоколы и стабы) под других агентов (включая RL) и подключение новых фич (например, эмбеддингов IR2Vec/MIR2Vec).

## Documentation

Documentation is split by language under `docs/en/` and `docs/ru/` (mirrored filenames). Entry points:

- [docs/README.md](docs/README.md) — how to pick a language tree.
- English hub: [docs/en/README.md](docs/en/README.md); Russian hub: [docs/ru/README.md](docs/ru/README.md).
- Reproduction: [docs/en/REPRODUCTION.md](docs/en/REPRODUCTION.md), [docs/ru/REPRODUCTION.md](docs/ru/REPRODUCTION.md).
- Overview: [docs/en/Documentation.md](docs/en/Documentation.md), [docs/ru/Documentation.md](docs/ru/Documentation.md).
- Metrics index: [docs/en/METRICS_AND_TRACE_ML_INFRASTRUCTURE.md](docs/en/METRICS_AND_TRACE_ML_INFRASTRUCTURE.md), [docs/ru/METRICS_AND_TRACE_ML_INFRASTRUCTURE.md](docs/ru/METRICS_AND_TRACE_ML_INFRASTRUCTURE.md).
- Ctuning: [docs/en/CTUNING_PROGRAMS.md](docs/en/CTUNING_PROGRAMS.md), [docs/ru/CTUNING_PROGRAMS.md](docs/ru/CTUNING_PROGRAMS.md); core experiment: [docs/en/CTUNING_CORE_EXPERIMENT.md](docs/en/CTUNING_CORE_EXPERIMENT.md), [docs/ru/CTUNING_CORE_EXPERIMENT.md](docs/ru/CTUNING_CORE_EXPERIMENT.md).

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
make e2e-pipeline FILE=benchmarks/local/benchmark_complex.cpp ARGS=""
```

Curated ctuning rollouts (needs submodule):

```bash
make ctuning-bootstrap
make ctuning-rollout CTUNING_ARGS='--only cbench-telecom-crc32 --episodes 5 --max-steps 3000 --seed 0'
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

Shell scripts honor `LLVM_DIR` or `LLVM_INSTALL_DIR` (see scripts in `scripts/`).
