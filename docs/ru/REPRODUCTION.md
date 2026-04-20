# Воспроизводимость и приёмка (RU)

**Версии.** LLVM 21 (цепочка `clang-21` / `clang++-21` и утилиты `llvm-readobj`, `llc` из того же префикса установки), Python 3.12+, зависимости через Poetry (`pyproject.toml`).

**Формулировка бейзлайна.** *Бейзлайн* — марковские прогулки `RandomPGOAgent` по грамматике CFG из LLVM; *ML-ready* — те же JSON-трассы (`bb_trace`), те же хуки метрик и сменная политика за протоколом `Agent`.

## Окружение

```bash
export LLVM_INSTALL_DIR=/path/to/llvm-project/build-install   # для CMake/Makefile
export LLVM_DIR="$LLVM_INSTALL_DIR"                             # для scripts/*.sh (эквивалентно)
export PATH="$LLVM_INSTALL_DIR/bin:$PATH"
```

## Python

```bash
cd /path/to/trace-synthesizer
poetry install
```

## Сборка нативных частей

```bash
make configure
make build
./scripts/check_baseline.sh    # также входит в `make check`
```

## Тесты

```bash
make test-py
```

## E2e на одном примере

```bash
make e2e-pipeline FILE=examples/complex.cpp ARGS=""
```

## benchmark_complex

```bash
make benchmark-complex
# подробные команды: docs/ru/BENCHMARK_COMPLEX_MANUAL.md (EN: docs/en/BENCHMARK_COMPLEX_MANUAL.md)
```

## Ctuning и статистика

```bash
git submodule update --init --recursive external/ctuning-programs
# или: make ctuning-bootstrap
make ctuning-rollout CTUNING_ARGS='--only cbench-telecom-crc32 --episodes 5 --max-steps 3000 --seed 0'
# по умолчанию: output/ctuning_curated_stats.json
```

## CRC32: пара трасс и SVG

После появления `output/ctuning_cbench-telecom-crc32/*.cfg.json` и `*.compressed_trace.json`:

```bash
./scripts/ctuning_crc32_paired_traces_and_viz.sh
```

## Чеклист приёмки (чистый клон)

1. **Сборка:** `make configure && make build` — `CFGDumper.so`, `InstrTracer`, `drrun` на месте.
2. **Канон intra:** `export-intra-trace` и `--write-canonical-intra` дают одинаковую схему (`bb_trace`); см. `trace_synthesizer/io/intra_trace.py`, тесты `tests/test_intra_canonical.py`.
3. **Генератор:** `rollout-random` + `RandomPGOAgent` + `CFGWalkEnv` — см. тесты `tests/test_cfg_walk_*.py`, `tests/test_runner_paths_jsonl.py`.
4. **Метрики:** `metrics-compare` и `metrics-bench-speed` — `tests/test_metrics_e2e.py` на `benchmark_complex`.
5. **Курируемый набор:** `make ctuning-rollout` пишет `output/ctuning_curated_stats.json`; `--skip-pipeline` только при уже собранных артефактах.
6. **Визуализация:** `scripts/ctuning_crc32_paired_traces_and_viz.sh` — пара SVG при наличии crc32-артефактов.

`make check` = `make test-py` + `scripts/check_baseline.sh` (подмножество пункта 1).

English: [../en/REPRODUCTION.md](../en/REPRODUCTION.md).
