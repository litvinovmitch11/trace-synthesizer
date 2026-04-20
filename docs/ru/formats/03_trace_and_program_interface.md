# Форматы трасс, CLI и `ProgramTraceSession`

## Каноническая интра-трасса (`bb_trace`)

Модуль: `trace_synthesizer.io.intra_trace`.

Поля: `schema_version`, `function_name`, `source` (литерал `bb_trace`), опционально `episode`, массив `sequence` с `{ "func", "bb" }`.

`export-intra-trace` из сжатого трейса и вывод `rollout-random` / `--write-canonical-intra` используют **одну схему**, чтобы эталон Dynamo и синтетика были сопоставимы по JSON.

```bash
poetry run python -m trace_synthesizer export-intra-trace \
  --compressed output/foo.compressed_trace.json --func main \
  --out output/main.intra.json
```

## Сжатый глобальный трейс

JSON-массив `{ "func", "bb" }` после RVA→BB и дедупликации подряд идущих пар. См. `compress` и `trace_synthesizer.io.compress_pipeline` (`validate_transitions`, `run_compress_and_validate`).

## CLI

| Команда | Назначение |
|---------|------------|
| `compress` | RVA + bb map + cfg → `compressed_trace.json` |
| `validate` | Проверка без записи |
| `export-intra-trace` | Срез одной функции в канонический intra JSON |
| `visualize` | SVG CFG; `--trace` или `--intra-json` |
| `rollout-random` | `CFGWalkEnv` + `RandomPGOAgent` → `intra_traces.jsonl` |

## Фасад `ProgramTraceSession`

Модуль: `trace_synthesizer.program_trace` — тонкая обёртка над `CfgProgram`, `compress_pipeline`, `intra_trace`, `CfgGraphvizRenderer` (валидация, экспорт intra, путь BB, визуализация).

Тесты: `tests/test_program_trace_session.py`.

## Матрица модулей (без фасада)

| Операция | Модуль |
|----------|--------|
| Грамматика CFG / PGO | `trace_synthesizer.core.grammar` |
| MDP | `trace_synthesizer.env.cfg_walk_env` |
| Сжатие и валидация | `trace_synthesizer.io.compress_pipeline` |
| Канон intra | `trace_synthesizer.io.intra_trace` |
| Визуализация | `trace_synthesizer.viz.graphviz_renderer` |
| CLI | `trace_synthesizer.cli.main` |

English: [same chapter](../en/formats/03_trace_and_program_interface.md).
