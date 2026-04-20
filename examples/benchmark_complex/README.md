# benchmark_complex

## Реальный C++ end-to-end

Исходник **[benchmark_complex.cpp](benchmark_complex.cpp)** прогоняется через весь пайплайн: PGO → `llc` + **CFGDumper** → бинарь → **DynamoRIO** + **InstrTracer** → `trace_synthesizer compress` / `visualize` → rollout и метрики.

**Одна команда:**

```bash
# или:
./scripts/run_benchmark_complex.sh
# или:
poetry run python -m trace_synthesizer benchmark-complex
```

Полный список ручных команд и переменных окружения: [docs/ru/BENCHMARK_COMPLEX_MANUAL.md](../../docs/ru/BENCHMARK_COMPLEX_MANUAL.md) (English: [docs/en/BENCHMARK_COMPLEX_MANUAL.md](../../docs/en/BENCHMARK_COMPLEX_MANUAL.md)).

## Синтетический CFG для юнит-тестов (без LLVM)

Файл [main.cfg.json](main.cfg.json) — руками заданный CFG для офлайн-тестов Python; **не** является выводом компилятора. Реальный CFG после сборки лежит в `output/benchmark_complex.cfg.json` (или в вашем `OUT_DIR`).
