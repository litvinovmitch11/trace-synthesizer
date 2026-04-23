# Ручной запуск benchmark_complex (C++ плагины + Python)

Документ описывает **полный** путь: реальный исходник `benchmarks/local/benchmark_complex.cpp` → профиль PGO → LLVM `llc` с плагином **CFGDumper** → бинарь с `.llvm_bb_addr_map` → **DynamoRIO** с клиентом **InstrTracer** → сжатие/валидация и метрики в Python.

**Единая точка входа (рекомендуется):**

```bash
# из корня репозитория, после `make build`
./scripts/run_benchmark_complex.sh
```

или:

```bash
make benchmark-complex
```

или:

```bash
poetry run python -m trace_synthesizer benchmark-complex
```

Ниже — те же шаги **вручную**, если нужно отладить отдельный этап. Пути LLVM/DynamoRIO заданы в `scripts/full_pipeline.sh` (переменная `LLVM_DIR`, бинарники плагинов из `build/`).

---

## 0. Предпосылки

```bash
cd /path/to/trace-synthesizer
make configure   # один раз после клонирования / смены LLVM
make build       # собирает CFGDumper.so, InstrTracer, DynamoRIO
poetry install
```

Проверка артефактов сборки:

```bash
test -f build/src/CFGDumper/CFGDumper.so
test -f build/src/InstrTracer/libInstrTracer.so
test -f build/_deps/dynamorio_pkg-src/bin64/drrun
```

---

## 1. Автоматический полный прогон (эквивалент `run_benchmark_complex.sh` части C++)

Источник по умолчанию: `benchmarks/local/benchmark_complex.cpp`. Аргументы после имени файла передаются **исполняемому бинарнику** на этапе сбора профиля (шаг 2 пайплайна).

```bash
export OUT_DIR="${OUT_DIR:-output}"
./scripts/full_pipeline.sh benchmarks/local/benchmark_complex.cpp
# с аргументами для бинарника:
./scripts/full_pipeline.sh benchmarks/local/benchmark_complex.cpp my_arg
```

Результат в `$OUT_DIR/` (при `OUT_DIR=output` и имени файла `benchmark_complex`):

| Файл | Назначение |
|------|------------|
| `benchmark_complex.cfg.json` | Whole-program CFG (JSON) |
| `benchmark_complex.bin` | Финальный бинарь |
| `benchmark_complex_bb_map.txt` | `llvm-readobj --bb-addr-map` |
| `benchmark_complex.trace.bin` | Сырой RVA-трейс DynamoRIO |
| `benchmark_complex.compressed_trace.json` | Сжатый + валидированный трейс |
| `benchmark_complex_main_cfg_pgo.svg` | Визуализация CFG без трассы |
| `benchmark_complex_main_cfg_pgo_trace.svg` | CFG с оверлеем трассы |

---

## 2. Ручная декомпозиция шагов `full_pipeline.sh`

Ниже команды **как внутри** `full_pipeline.sh` (пути из скрипта; при необходимости поправьте `LLVM_DIR` под свою установку LLVM).

Переменные (пример):

```bash
export LLVM_DIR="/home/mitchell/dev/llvm/llvm-project/build-install"
export CLANG="$LLVM_DIR/bin/clang++"
export LLVM_PROFDATA="$LLVM_DIR/bin/llvm-profdata"
export LLVM_LINK="$LLVM_DIR/bin/llvm-link"
export LLC="$LLVM_DIR/bin/llc"
export LLVM_READOBJ="$LLVM_DIR/bin/llvm-readobj"
export OUT_DIR="${OUT_DIR:-output}"
export BASENAME=benchmark_complex
export INPUT_FILE="benchmarks/local/benchmark_complex.cpp"
export PLUGIN_SO="build/src/CFGDumper/CFGDumper.so"
export DRRUN="build/_deps/dynamorio_pkg-src/bin64/drrun"
export TRACER_SO="build/src/InstrTracer/libInstrTracer.so"
mkdir -p "$OUT_DIR"
```

### [1/6] Сборка профилируемого бинарника

```bash
$CLANG -O3 -fprofile-instr-generate -fcoverage-mapping "$INPUT_FILE" \
  -o "$OUT_DIR/${BASENAME}_prof"
```

### [2/6] Прогон под профиль и merge

```bash
LLVM_PROFILE_FILE="$OUT_DIR/default.profraw" "$OUT_DIR/${BASENAME}_prof"
$LLVM_PROFDATA merge -output="$OUT_DIR/${BASENAME}.profdata" "$OUT_DIR/default.profraw"
```

### [3/6] LTO + PGO + CFGDumper (`llc`) + линковка + bb map

```bash
$CLANG -O3 -fPIC -fbasic-block-address-map -flto \
  -fprofile-instr-use="$OUT_DIR/${BASENAME}.profdata" \
  -c "$INPUT_FILE" -o "$OUT_DIR/${BASENAME}.bc"

$LLVM_LINK "$OUT_DIR/${BASENAME}.bc" -o "$OUT_DIR/${BASENAME}_whole.bc"

$LLC --basic-block-address-map -relocation-model=pic \
  -load="$PLUGIN_SO" -cfg-pretty=false \
  -cfg-out-file="$OUT_DIR/${BASENAME}.cfg.json" \
  "$OUT_DIR/${BASENAME}_whole.bc" -o "$OUT_DIR/${BASENAME}.s"

$CLANG "$OUT_DIR/${BASENAME}.s" -o "$OUT_DIR/${BASENAME}.bin"

$LLVM_READOBJ --bb-addr-map "$OUT_DIR/${BASENAME}.bin" > "$OUT_DIR/${BASENAME}_bb_map.txt"
```

### [4/6] DynamoRIO + InstrTracer

```bash
$DRRUN -c "$TRACER_SO" -o "$OUT_DIR/${BASENAME}.trace.bin" "${BASENAME}.bin" -- \
  "$OUT_DIR/${BASENAME}.bin"
```

### [5/6] Compress / validate (Python)

```bash
poetry run python3 -m trace_synthesizer compress \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
  --map "$OUT_DIR/${BASENAME}_bb_map.txt" \
  --trace "$OUT_DIR/${BASENAME}.trace.bin" \
  --out "$OUT_DIR/${BASENAME}.compressed_trace.json"
```

### [6/6] Визуализация (Python)

```bash
poetry run python3 -m trace_synthesizer visualize \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" --func main \
  --out "$OUT_DIR/${BASENAME}_main_cfg_pgo"

poetry run python3 -m trace_synthesizer visualize \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" --func main \
  --trace "$OUT_DIR/${BASENAME}.compressed_trace.json" \
  --out "$OUT_DIR/${BASENAME}_main_cfg_pgo_trace"
```

---

## 3. Python-анализ после трассы (как во второй половине `run_benchmark_complex.sh`)

Подставьте `FUNC=main` (или другое имя из `cfg.json`, если манглинг отличается).

```bash
export FUNC=main
```

### Экспорт реальной intra-трассы

```bash
poetry run python3 -m trace_synthesizer export-intra-trace \
  --compressed "$OUT_DIR/${BASENAME}.compressed_trace.json" \
  --func "$FUNC" \
  --out "$OUT_DIR/${BASENAME}_real_intra.json"
```

### Синтетические rollout-ы

```bash
poetry run python3 -m trace_synthesizer rollout-random \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
  --func "$FUNC" \
  --episodes 120 --seed 42 --max-steps 8000 \
  --out-dir "$OUT_DIR/${BASENAME}_rollouts"
```

### Сравнение метрик

```bash
poetry run python3 -m trace_synthesizer metrics-compare \
  --reference "$OUT_DIR/${BASENAME}_real_intra.json" \
  --candidate "$OUT_DIR/${BASENAME}_rollouts/intra_traces.jsonl" \
  --func "$FUNC" \
  --out "$OUT_DIR/${BASENAME}_metrics.json"
```

### Бенчмарк скорости генерации

```bash
poetry run python3 -m trace_synthesizer metrics-bench-speed \
  --cfg "$OUT_DIR/${BASENAME}.cfg.json" \
  --func "$FUNC" \
  --n-episodes 200 --max-steps 4000 --seed 0 \
  --out "$OUT_DIR/${BASENAME}_bench_speed.json"
```

---

## 4. Полезные переменные оркестратора

| Переменная | По умолчанию | Смысл |
|------------|--------------|--------|
| `BENCHMARK_CPP` | `benchmarks/local/benchmark_complex.cpp` | Исходник для пайплайна |
| `OUT_DIR` | `output` | Каталог всех артефактов |
| `FUNC` | `main` | Имя функции для Python-команд |
| `SKIP_ANALYSIS` | `0` | `1` — только `full_pipeline.sh`, без rollout/metrics |
| `ROLL_EPISODES` | `120` | Число эпизодов rollout |
| `ROLL_SEED` | `42` | Семя rollout |
| `ROLL_MAX_STEPS` | `8000` | Лимит шагов на эпизод |
| `BENCH_EPISODES` | `200` | Эпизоды для bench-speed |
| `BENCH_MAX_STEPS` | `4000` | max-steps для bench |
| `BENCH_SEED` | `0` | Семя bench |

Пример:

```bash
OUT_DIR=output/my_run FUNC=main ROLL_EPISODES=200 \
  ./scripts/run_benchmark_complex.sh
```

---

## 5. Связь с «ручным» JSON для юнит-тестов

Файл `examples/benchmark_complex/main.cfg.json` — **синтетический** CFG для офлайн-тестов Python (без LLVM). Он **не** генерируется C++-пайплайном; реальный CFG после сборки — только `output/benchmark_complex.cfg.json` (или ваш `$OUT_DIR`).

English: [same chapter](../en/BENCHMARK_COMPLEX_MANUAL.md).
