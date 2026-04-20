# Эксперимент: метрики по «ядру» и длины путей до выхода из функции

## Идея

1. **Пайплайн** (PGO, DynamoRIO, `compress`) привязан к **`entry_func`** из манифеста — обычно `main`, чтобы трассировать весь бинарник и строить полный CFG. Шаг **`visualize`** в `ctuning_full_pipeline_c.sh` использует **`rollout_func`** (как и `rollout-random`), чтобы SVG с оверлеем трассы совпадали по функции с ядром и со скриптом `ctuning_crc32_paired_traces_and_viz.sh`.
2. **`rollout-random`** и блок **метрик** в `ctuning_curated_stats.json` используют **`rollout_func`** — символ функции в том же `*.cfg.json`, где сосредоточена вычислительная нагрузка (без обёртки `ctuning-rtl` / холодного `main`, где это уместно).
3. **`rollout_max_steps`: `0`** в манифесте — не обрезать эпизод по числу шагов в `CFGWalkEnv`: идти, пока не достигнут **сток CFG** (выход из моделируемой функции). Внешняя страховка: жёсткий лимит **10⁷** шагов на эпизод в `rollout_episode` (см. `termination: hard_capped` в `runs.jsonl`).

## Таблица по текущему `benchmarks/ctuning_curated.json`

| `id` | `entry_func` (пайплайн) | `rollout_func` (ядро) | Зачем |
|------|-------------------------|----------------------|--------|
| `shared-matmul-c` | `main` | `main` | В Dynamo-трассе для этого бинарника есть только `main` (тело `matmul` инлайнится). |
| `shared-matmul-c2` | `main` | `main` | Аналогично. |
| `cbench-automotive-bitcount` | `main` | `bit_count` | Символ `bitcount` в CFG — вырожденный граф; для walk берётся `bit_count`. |
| `cbench-telecom-crc32` | `main` | `main1` | Реальная обработка файлов в `main1`; `main` — только ctuning-обёртка. |
| `cbench-security-sha` | `main` | `sha_stream` | Хэширование потока; `main`/`main1` — тонкая обвязка. |

При смене версии LLVM или флагов имена могут слегка отличаться: проверяйте список функций в `*.cfg.json` (массив объектов с полем `function_name`).

## Параметры прогона

Рекомендуемый порядок после `make build`:

```bash
make ctuning-bootstrap
poetry run python3 -m trace_synthesizer ctuning-rollout \
  --episodes 20 --seed 0 --stats-file output/ctuning_curated_stats.json
```

- **`--episodes`**: сколько независимых путей замерить (длины пишутся в `runs.jsonl` и агрегируются в `rollout_path_lengths` в JSON статистики).
- **`rollout_max_steps` в JSON = `0`**: режим «до выхода из функции» для `rollout_func`. CLI `--max-steps` тогда **перекрывается** манифестом (см. поле `rollout_max_steps_used` в статистике).

Для **тяжёлых** CFG (большой `matmul`) случайный walk до стока может занять очень много шагов или упереться в `hard_capped`. Тогда в манифесте временно задайте положительное `rollout_max_steps` (например `500000`) только для этой записи.

## Что смотреть в `output/ctuning_curated_stats.json`

- **`rollout_path_lengths.by_termination.terminated`**: длины успешных путей до стока (`mean` / `min` / `max` / список `lengths`).
- **`hard_capped`**: эпизод исчерпал внутренний лимит шагов — увеличьте лимит в коде, уменьшите CFG, или задайте конечный `rollout_max_steps`.
- **`metrics_vs_dynamo_first_rollout`**: теперь считается для **`rollout_func`** — сравнение ближе к «ядру», а не к обёртке `main`.

## Ручной повтор для одной программы

```bash
poetry run python3 -m trace_synthesizer ctuning-rollout \
  --only cbench-security-sha --skip-pipeline --episodes 10 --seed 1 \
  --stats-file output/sha_core_stats.json
```

(`--skip-pipeline` — если уже есть `output/ctuning_cbench-security-sha/*.cfg.json` после полного прогона.)

English: [same chapter](../en/CTUNING_CORE_EXPERIMENT.md).
