
# Метрики: CLI, сценарии и приложения

Третья часть материала «трассы и метрики»; начните с [01_trace_levels_and_context.md](01_trace_levels_and_context.md) и [02_metric_definitions.md](02_metric_definitions.md).

## 5. Программный интерфейс и сценарии использования

### 5.1. Модуль Python

Импорт из пакета `trace_synthesizer.metrics`:

- загрузчики: `load_path_from_intra_trace_json`, `load_paths_from_intra_traces_jsonl`, `load_path_from_compressed_trace`;
- контекст: `MetricContext`;
- запуск набора: `run_metrics`, сериализация: `results_to_jsonable`;
- бенчмарк: `benchmark_random_rollouts`, `benchmark_rollout_seconds`, `speedup_vs_dynamo`.

### 5.2. CLI

- `python -m trace_synthesizer metrics-compare --reference <path> --candidate <path> --func <name> [--reference-compressed] [--candidate-compressed] [--metrics ...] [--out report.json]`
  - эталон: один объект intra_trace **или** срез `compressed_trace.json` с флагом `--reference-compressed`;
  - кандидат: один intra JSON, **или** JSONL (`intra_traces.jsonl` после `rollout-random`), **или** compressed с флагом.

- `python -m trace_synthesizer metrics-bench-speed --cfg <cfg.json> --func <name> --n-episodes <N> [--dynamo-seconds T | --dynamo-sec-for-1000 T] [--out ...]`

### 5.3. Сложный пример CFG

Каталог [examples/benchmark_complex/main.cfg.json](../../../examples/benchmark_complex/main.cfg.json) содержит одну функцию `main` с разветвлением из «хаба», тремя цепочками разной длины, циклом с телом из нескольких блоков и общей точкой слияния перед выходом. На этом графе:

- вероятностный генератор демонстрирует нетривиальное распределение длин эпизодов;
- n-граммы отражают различие между «горячей» цепочкой, боковыми цепочками и многократными обходами цикла;
- метрики KL и hot-path получают достаточно богатую поддержку для осмысленных численных экспериментов.

---

## 6. Рекомендации по оформлению эксперимента в дипломной работе

1. **Фиксировать** версию бинарника, профиля PGO, входных данных DynamoRIO и параметров генератора (семя, \(N\), `max_steps`).

2. **Разделять** сравнение «одна реальная трасса против корпуса синтетики» и «два корпуса независимых прогонов» — статистика и доверительные интервалы будут различаться; в тексте явно указать постановку.

3. Для **скорости** приводить аппаратную конфигурацию, число ядер, отключение турбо (если применимо), и метод измерения времени DynamoRIO (wall-clock vs CPU time процесса).

4. Указывать, что интра-трасса **намеренно** отбрасывает межпроцедурный контекст; выводы об обобщении на whole-program следует формулировать осторожно.

---

## 7. Ссылки на исходные формулировки

Первичное обоснование набора метрик: Project Proposal, раздел III.D (*Evaluation Metrics*), файл [Project_Proposal_Litvinov_Michael.pdf](../../Project_Proposal_Litvinov_Michael.pdf).

---

## Приложение A. Формальное определение интра-трассы

Пусть \(G=(V,E)\) — ориентированный граф CFG одной функции с именем \(f\), где \(V\) — множество базовых блоков (идентификаторы `bb`), а \(E \subseteq V \times V\) — допустимые внутрипроцедурные переходы. Выделим подмножество входных блоков \(V_{\mathrm{entry}}\) и терминальных \(V_{\mathrm{term}} = \{ v \in V : \deg^+(v)=0 \}\).

**Интра-трасса** (после сжатия подряд идущих дубликатов) — это конечная последовательность \(\tau = (v_0, v_1, \ldots, v_T)\), где:

- \(v_0 \in V_{\mathrm{entry}}\) (в реализации среды — единственный выбранный entry по правилам загрузчика CFG);
- для каждого \(t<T\) выполняется \((v_t, v_{t+1}) \in E\);
- \(v_T \in V_{\mathrm{term}}\) (досрочная остановка по лимиту шагов даёт усечённую трассу; такие эпизоды следует помечать в эксперименте как truncated).

**Случайная величина.** Фиксируя политику \(\pi\) (в baseline — `RandomPGOAgent`), получаем распределение на множестве допустимых \(\tau\), индуцированное MDP и стохастикой выбора действий. Эмпирическая оценка этого распределения строится по выборке \(\tau^{(1)},\ldots,\tau^{(N)}\).

**Сопоставление с DynamoRIO.** Реальная трасса после компрессии RVA→BB и фильтрации по \(f\) даёт одну или несколько реализаций \(\tilde\tau\) того же алфавита \(V\), но распределение \(\tilde\tau\) определяется семантикой программы и входами, а не политикой \(\pi\). Метрики из раздела 4 измеряют расхождение *эмпирических* распределений, построенных по конечным выборкам, и не требуют явного знания аналитического вида ни одного из распределений.

---

## Приложение B. MDP трассового синтеза (связь с RL)

Состояние на шаге \(t\): идентификатор текущего блока \(v_t\) (и дополнительные признаки блока в векторе наблюдения среды). Действие: индекс исходящего ребра в фиксированном порядке сортировки преемников по `target_id`. Переход детерминирован: выбранное ребро ведёт в \(v_{t+1}\). Награда в текущей реализации среды нулевая до терминала; для обучения RL предполагается ввести сигнал сходства с реальной трассой (см. proposal, раздел о reward как мере близости).

Метрики раздела 4 применимы **вне** цикла RL: они сравнивают уже сгенерированные трассовые выборки с эталоном.

---

## Приложение C. Схема полей JSON для сравнения

**Объект intra_trace** (один файл):

| Поле | Тип | Смысл |
|------|-----|--------|
| `schema_version` | int | Версия схемы (текущее значение см. `SCHEMA_VERSION` в коде). |
| `function_name` | str | Имя функции, к которой относится `sequence`. |
| `source` | str | Единый маркер схемы: **`bb_trace`** (и Dynamo export, и rollout; записи отличаются только полем `sequence`). |
| `episode` | int или null | Номер эпизода для синтетики; для экспорта из compressed — `null`. |
| `sequence` | array | Элементы `{ "func": str, "bb": int }` в порядке времени. |

**JSONL** после `rollout-random`: каждая строка — независимый объект того же вида с заполненным `episode`.

---

## Приложение D. Таблица параметров CLI `metrics-compare`

| Аргумент | Назначение |
|----------|------------|
| `--reference` | Путь к одному intra JSON или к `compressed_trace.json` (с флагом). |
| `--reference-compressed` | Интерпретировать reference как полный сжатый трейс; обязателен согласованный `--func`. |
| `--candidate` | Путь к intra JSON, JSONL или compressed (с флагом). |
| `--candidate-compressed` | Аналогично для кандидата. |
| `--func` | Имя функции для фильтрации compressed и для подсчёта метрик. |
| `--metrics` | Список через запятую: `block_visit_kl`, `edge_transition_kl`, `hot_path_ngram_overlap`. |
| `--epsilon` | Параметр сглаживания \(\varepsilon\) для дискретных KL. |
| `--ngram-min`, `--ngram-max` | Диапазон длин n-грамм. |
| `--top-k` | Размер топа по частоте для hot-path метрики. |
| `--out` | Опциональный путь записи JSON-отчёта. |

---

## Приложение E. Соответствие «метрика — исходный файл»

| Метрика | Основные функции / классы |
|---------|---------------------------|
| Посещения блоков | [trace_synthesizer/metrics/block_frequency.py](../../../trace_synthesizer/metrics/block_frequency.py) |
| Переходы | [trace_synthesizer/metrics/edge_transition.py](../../../trace_synthesizer/metrics/edge_transition.py) |
| Hot-path n-граммы | [trace_synthesizer/metrics/hot_path.py](../../../trace_synthesizer/metrics/hot_path.py) |
| Дискретный KL | [trace_synthesizer/metrics/discrete.py](../../../trace_synthesizer/metrics/discrete.py) |
| Загрузка файлов | [trace_synthesizer/metrics/loaders.py](../../../trace_synthesizer/metrics/loaders.py) |
| Сводный запуск | [trace_synthesizer/metrics/compare.py](../../../trace_synthesizer/metrics/compare.py) |
| Плагинный интерфейс | [trace_synthesizer/metrics/protocol.py](../../../trace_synthesizer/metrics/protocol.py) |
| Реестр метрик | [trace_synthesizer/metrics/registry.py](../../../trace_synthesizer/metrics/registry.py) |
| Бенчмарк скорости | [trace_synthesizer/metrics/speed.py](../../../trace_synthesizer/metrics/speed.py) |

---

## Приложение F. Микропример для KL по блокам

Пусть после сглаживания на двух блоках \(\{a,b\}\) эталон даёт \(\hat P(a)=0{,}6\), \(\hat P(b)=0{,}4\), а кандидат \(\hat Q(a)=0{,}5\), \(\hat Q(b)=0{,}5\). Тогда

\[
D_{\mathrm{KL}}(\hat P\|\hat Q) = 0{,}6\log\frac{0{,}6}{0{,}5} + 0{,}4\log\frac{0{,}4}{0{,}5} \approx 0{,}029.
\]

Небольшое положительное значение ожидаемо при любых отличиях; при сильном перекосе (кандидат почти никогда не посещает «горячий» блок эталона) дивергенция растёт. Симметричная версия KL полезна, когда эталон и кандидат взаимозаменяемы по роли (два независимых прогона генератора).

---

## Приложение G. Воспроизводимый сценарий на сложном CFG

1. Сгенерировать синтетику:  
   `poetry run python -m trace_synthesizer rollout-random --cfg examples/benchmark_complex/main.cfg.json --func main --episodes 500 --seed 0 --max-steps 5000 --out-dir output/rollouts_complex`
2. Экспортировать эталон из DynamoRIO (после `compress`):  
   `poetry run python -m trace_synthesizer export-intra-trace --compressed output/<prog>.compressed_trace.json --func main --out output/main_intra_real.json`
3. Сравнить:  
   `poetry run python -m trace_synthesizer metrics-compare --reference output/main_intra_real.json --candidate output/rollouts_complex/intra_traces.jsonl --func main --out output/metrics_main.json`
4. Замер скорости (опционально сравнение с DynamoRIO через `--dynamo-seconds` или синоним `--dynamo-sec-for-1000` для того же `N`):  
   `poetry run python -m trace_synthesizer metrics-bench-speed --cfg examples/benchmark_complex/main.cfg.json --func main --n-episodes 1000 --max-steps 5000 --seed 1`

Шаги 2–3 заменяются синтетическими парами при отсутствии бинарного трейса; для регрессионных тестов см. [tests/test_metrics_e2e.py](../../../tests/test_metrics_e2e.py).

English: [same chapter](../../en/metrics/03_cli_scenarios_appendices.md).
