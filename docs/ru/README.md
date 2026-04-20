# Оглавление документации (русский)

**Текущий этап.** Воспроизводимый бейзлайн: марковские прогулки `RandomPGOAgent` по грамматике CFG из LLVM; трассы Dynamo дают ground truth; метрики и rollout используют одну **каноническую** схему intra-трассы (`bb_trace`). Обучаемые политики можно подставлять за тем же протоколом агента без смены JSON.

**Зеркало на английском:** [../en/README.md](../en/README.md).

## Быстрые ссылки (RU)

| Тема | Русский файл |
|------|----------------|
| LLVM CFGDumper | [pipeline/01_llvm_cfgdumper.md](pipeline/01_llvm_cfgdumper.md) |
| DynamoRIO + InstrTracer | [pipeline/02_dynamorio_instrtracer.md](pipeline/02_dynamorio_instrtracer.md) |
| Форматы + `ProgramTraceSession` | [formats/03_trace_and_program_interface.md](formats/03_trace_and_program_interface.md) |
| Агенты / среда | [ml/04_agents_and_env.md](ml/04_agents_and_env.md) |
| Метрики (разнесённые) | [metrics/README.md](metrics/README.md) |
| Оглавление метрик | [METRICS_AND_TRACE_ML_INFRASTRUCTURE.md](METRICS_AND_TRACE_ML_INFRASTRUCTURE.md) |
| Воспроизводимость + приёмка | [REPRODUCTION.md](REPRODUCTION.md) |
| Обзор (укороченный) | [Documentation.md](Documentation.md) |
| Интеграция ctuning | [CTUNING_PROGRAMS.md](CTUNING_PROGRAMS.md) |
| Ядро эксперимента ctuning | [CTUNING_CORE_EXPERIMENT.md](CTUNING_CORE_EXPERIMENT.md) |
| Ручной benchmark_complex | [BENCHMARK_COMPLEX_MANUAL.md](BENCHMARK_COMPLEX_MANUAL.md) |

Плоский индекс: [INDEX.md](INDEX.md).
