# Интеграция [ctuning-programs](https://github.com/ctuning/ctuning-programs)

Репозиторий **ctuning-programs** подключается как **git submodule** в `external/ctuning-programs/`. Внутри — программы Collective Knowledge (`program/<имя>/` + `.cm/meta.json`). Для TraceSynthesizer важно:

- У многих бенчмарков **несколько `.c`**, иногда нужны **внешние dataset** из `ctuning-datasets-*` — такие программы в общий манифест **не попадают**, пока явно не добавлен входной файл или генератор.
- **`entry_func`** в CFG может отличаться от `main` — в манифесте задаётся поле `entry_func`.

## 1. Первичная настройка (submodule)

После `git clone` этого репозитория **обязательно** инициализируйте submodule (один из вариантов):

```bash
git submodule update --init --recursive external/ctuning-programs
```

или через Makefile (вызывает `scripts/init_ctuning_submodule.sh`):

```bash
make ctuning-bootstrap
```

Скрипт `init_ctuning_submodule.sh` делает следующее:

- если `external/ctuning-programs/program` уже есть — ничего не делает;
- если в корне есть секция `[submodule "external/ctuning-programs"]` в `.gitmodules` — выполняет `git submodule update --init --depth 1 external/ctuning-programs`;
- **иначе** (форк без submodule) — откатывается на **legacy** `scripts/bootstrap_ctuning_programs.sh` (shallow clone).

Закреплённая **версия** ctuning-programs — это **коммит**, записанный в индекс git у gitlink `external/ctuning-programs` (как у любого submodule). Обновить на новый upstream:

```bash
cd external/ctuning-programs
git fetch origin && git checkout <commit-or-branch>
cd ../..
git add external/ctuning-programs
git commit -m "Bump ctuning-programs submodule"
```

## 2. Сборка плагинов LLVM / DynamoRIO

Пайплайн `ctuning_full_pipeline_c.sh` использует `build/src/CFGDumper/CFGDumper.so`, `InstrTracer` и `drrun`. Перед прогоном:

```bash
poetry install
make configure
make build
```

Переменные окружения `LLVM_DIR`, `CLANG_C` и т.д. — как в `scripts/ctuning_full_pipeline_c.sh` (по умолчанию путь к вашей сборке LLVM).

## 3. Курируемые примеры (`benchmarks/ctuning_curated.json`)

Сейчас **5** записей, все — **чистый C**, без CK-runtime. Для каждой заданы **`rollout_func`** (ядро для rollouts/метрик) и **`rollout_max_steps`: 0** (идти до стока CFG для этой функции; см. [CTUNING_CORE_EXPERIMENT.md](CTUNING_CORE_EXPERIMENT.md); English: [../en/CTUNING_CORE_EXPERIMENT.md](../en/CTUNING_CORE_EXPERIMENT.md)).

| `id` | Суть входа |
|------|------------|
| `shared-matmul-c` | `CT_MATRIX_DIMENSION`, `CT_REPEAT_MAIN` + файл из `profile_data` (`float_space_separated`) как `argv[1]`. |
| `shared-matmul-c2` | То же семейство, другой размер матрицы; `program/shared-matmul-c2/matmul.c`. |
| `cbench-automotive-bitcount` | Несколько `.c`; один числовой аргумент `argv[1]` — число итераций. |
| `cbench-telecom-crc32` | `crc_32.c` + `ctuning-rtl.c`; `argv[1]` — **временный текстовый файл** (`profile_data.kind`: `text_file`). |
| `cbench-security-sha` | `sha.c`, `sha_driver.c`, `ctuning-rtl.c`; вход — **временный файл** (`text_file`). |

Расширение манифеста — объект с полями:

- `id`, `sources_relative` (от корня `ctuning-programs`),
- опционально `profile_env`, `profile_argv`,
- `profile_data` с `kind`: `float_space_separated` | `text_file`,
- `entry_func` — для пайплайна и визуализации (часто `main`),
- опционально **`rollout_func`** — для `rollout-random` и метрик в статистике (по умолчанию = `entry_func`),
- опционально **`rollout_max_steps`** — если задано, **перекрывает** CLI `--max-steps`; значение **`0`** = не обрезать по шагам в среде (до выхода из функции в CFG, с внутренним лимитом 1e7 на эпизод).

## 4. Запуск пайплайна и rollouts

Все записи манифеста:

```bash
make ctuning-rollout
# эквивалентно (с теми же флагами через CTUNING_ARGS):
poetry run python3 -m trace_synthesizer ctuning-rollout
```

Одна или несколько программ:

```bash
poetry run python3 -m trace_synthesizer ctuning-rollout \
  --only shared-matmul-c,cbench-security-sha \
  --episodes 20 --max-steps 5000 --seed 1
```

Полезные флаги CLI:

| Флаг | Назначение |
|------|------------|
| `--ctuning-root PATH` | Другой checkout ctuning-programs. |
| `--out DIR` | Каталог-родитель для `ctuning_<id>/` (по умолчанию `output/`). |
| `--only id1,id2` | Подмножество id из JSON. |
| `--limit N` | Взять первые N записей после `--only`. |
| `--skip-pipeline` | Только `rollout-random` (CFG уже есть из прошлого прогона). |
| `--no-bootstrap` | Не вызывать init submodule, если каталог отсутствует (ошибка). |
| `--stats-file PATH` | Куда писать **агрегированную статистику** (см. ниже). По умолчанию: `output/ctuning_curated_stats.json`. |
| `--no-stats` | Не писать JSON и не печатать сводку метрик в конце. |
| `--no-metrics` | В JSON не считать блок «метрики vs Dynamo» (быстрее). |

Артефакты одной программы: `output/ctuning_<id>/` — `*.cfg.json`, `*.compressed_trace.json`, `rollouts_random/` (`runs.jsonl`, `intra_traces.jsonl`, `summary.json`), SVG визуализации.

## 4b. Один формат трасс (реальная и синтетическая)

Все intra-JSON (и `export-intra-trace` из Dynamo, и строки `intra_traces.jsonl` после `rollout-random`) используют **одну схему**: поля в фиксированном порядке `schema_version`, `function_name`, `source`, `episode`, `sequence`, при этом **`source` всегда строка `bb_trace`**. Отличается только содержимое **`sequence`** (и при необходимости `episode`, по умолчанию `null` в одиночных файлах экспорта).

Пара **CFG + нагрузка трассы** для небольшого `cbench-telecom-crc32` (`main1`): скрипт генерирует два SVG (реальная и синтетическая трасса в одном и том же JSON-формате):

```bash
./scripts/ctuning_crc32_paired_traces_and_viz.sh
```

Артефакты: `output/ctuning_cbench-telecom-crc32/paired_viz/main1_{real,synthetic}.intra.json` и `main1_cfg_{real_trace,synth_trace}.svg`.

Дополнительно: `rollout-random --write-canonical-intra PATH` записывает **первый** эпизод в такой же файл, как у `export-intra-trace`. Для визуализации по intra-JSON: `visualize --intra-json FILE` (вместо `--trace` с полным compressed).

## 5. Файл статистики и метрики

После каждого прогона (если не указан `--no-stats`) создаётся JSON, по умолчанию:

`output/ctuning_curated_stats.json`

Структура (верхний уровень):

- `generated_at_utc` — время записи (UTC, ISO-8601),
- `episodes`, `max_steps` — параметры rollouts,
- `entries` — массив по одному объекту на каждую программу:
  - `id`
  - `wall_seconds_pipeline_and_rollout` — время полного шага (пайплайн + `rollout-random`)
  - `out_dir`, `rollouts_dir`
  - `rollout_summary` — содержимое `rollouts_random/summary.json` (число эпизодов, средняя длина, `termination_counts`, частоты рёбер)
  - `synthetic_bench_subset` — короткий замер **синтетической** генерации трасс (`benchmark_random_rollouts`, до 50 эпизодов, `max_steps=2000`): `seconds`, `episodes_per_second`
  - `metrics_vs_dynamo_first_rollout` — сравнение **реальной** трассы из `*.compressed_trace.json` с **первой** синтетической трассой из `intra_traces.jsonl`: `block_visit_kl`, `edge_transition_kl`, `hot_path_ngram_overlap` (см. [metrics/README.md](metrics/README.md)).

Те же метрики вручную для одной пары трасс:

```bash
poetry run python3 -m trace_synthesizer metrics-compare \
  --reference output/ctuning_shared-matmul-c/shared-matmul-c.compressed_trace.json \
  --reference-compressed \
  --candidate output/ctuning_shared-matmul-c/rollouts_random/intra_traces.jsonl \
  --func main
```

## 6. CI и клонирование

В CI при `git clone` добавьте:

```bash
git submodule update --init --recursive
```

или `GIT_SUBMODULE_STRATEGY: recursive` (GitLab) / аналог в вашей системе.

---

**Краткий чеклист:** `git submodule update --init` → `make build` → `make ctuning-rollout` → смотреть `output/ctuning_curated_stats.json` и таблицу метрик в логе.

English: [same chapter](../en/CTUNING_PROGRAMS.md).
