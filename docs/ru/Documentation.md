# End-to-End PGO & Trace Pipeline Documentation

Этот документ предоставляет полное описание архитектуры, компонентов и процесса использования пайплайна для сбора Profile-Guided Optimization (PGO) статистики, извлечения CFG, наложения динамических трасс DynamoRIO и визуализации.

## 1. Введение

Для задач машинного обучения на компиляторах (например, RL-агентов) необходимы:
1. **Среда (Грамматика)** — Control Flow Graph (CFG), извлеченный из LLVM на самом последнем этапе перед генерацией машинного кода (Machine IR).
2. **PGO Статистика** — Вероятности переходов на основе профилирования реального выполнения, чтобы агент понимал "горячие" пути (hot paths).
3. **Ground Truth данные** — Реальные трассы выполнения (`traces`), которые на 100% совпадают со статическим графом (CFG), для обучения и валидации агента.

---

## 2–6. Подробная архитектура (вынесена в модули)

Описание компонентов, наложение трейсов, шесть этапов shell-пайплайна, визуализация и ограничения перенесены в отдельные главы:

- [Индекс документации (RU)](README.md) — оглавление этого языка; английский: [../en/README.md](../en/README.md).
- Плагин LLVM: [pipeline/01_llvm_cfgdumper.md](pipeline/01_llvm_cfgdumper.md).
- Клиент DynamoRIO: [pipeline/02_dynamorio_instrtracer.md](pipeline/02_dynamorio_instrtracer.md).
- Форматы JSON и фасад `ProgramTraceSession`: [formats/03_trace_and_program_interface.md](formats/03_trace_and_program_interface.md).

Скрипты end-to-end: `scripts/full_pipeline.sh`, цели `Makefile` вроде `e2e-pipeline`.

---

## 7. Python-пакет `trace_synthesizer`

Установка: `poetry install` (PyTorch подтягивается с CPU-индекса; `numpy` зафиксирован на 1.x для совместимости с данной сборкой `torch`). Пакет даёт:

- **Ядро грамматики CFG** (`trace_synthesizer.core`): валидированный `Program` / `CfgProgram`, детерминированный порядок преемников, нормализация весов PGO.
- **Ввод/вывод трейсов** (`trace_synthesizer.io`): `BbAddressMap`, чтение RVA-трейса, сжатие + валидация (в т.ч. рекурсивные вызовы/возвраты).
- **Визуализация** (`trace_synthesizer.viz`): Graphviz для одной функции с опциональным оверлеем сжатого трейса.
- **RL baseline** (`trace_synthesizer.env`, `trace_synthesizer.agents`, `trace_synthesizer.runner`): Gymnasium `CFGWalkEnv`, `RandomPGOAgent`, подкоманда `rollout-random` с записью `runs.jsonl` / `summary.json`.
- **Метрики** (`trace_synthesizer.metrics`): сравнение реальных и синтетических интра-трасс (KL, hot-path, бенчмарк скорости); подробно — [metrics/README.md](metrics/README.md) и оглавление [METRICS_AND_TRACE_ML_INFRASTRUCTURE.md](METRICS_AND_TRACE_ML_INFRASTRUCTURE.md).
- **benchmark_complex**: `make benchmark-complex` / `python -m trace_synthesizer benchmark-complex` / `./scripts/run_benchmark_complex.sh` — реальный C++ через PGO, CFGDumper, DynamoRIO и Python-анализ; команды вручную — [BENCHMARK_COMPLEX_MANUAL.md](BENCHMARK_COMPLEX_MANUAL.md) (EN: [../en/BENCHMARK_COMPLEX_MANUAL.md](../en/BENCHMARK_COMPLEX_MANUAL.md)).
- **ctuning-programs** (cTuning benchmarks): `make ctuning-bootstrap` / `ctuning-rollout` — [CTUNING_PROGRAMS.md](CTUNING_PROGRAMS.md); ядро эксперимента — [CTUNING_CORE_EXPERIMENT.md](CTUNING_CORE_EXPERIMENT.md) (EN: [../en/CTUNING_CORE_EXPERIMENT.md](../en/CTUNING_CORE_EXPERIMENT.md)).
- **Заготовка Torch** (`trace_synthesizer.agents.torch_policy_stub.MaskedLstmPolicyStub`): LSTM-политика с маскированием логитов для будущего обучения (импортируйте подмодуль напрямую; для `compress`/`validate`/`visualize` Torch не подгружается).

### CLI (примеры)

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

**Интра-процедурность:** `CFGWalkEnv` и `rollout-random` работают с **одной функцией** (например, `main`). Глобальный `compressed_trace.json` остаётся межпроцедурным; для сравнения с обходом одной функции фильтруйте по полю `func`.
