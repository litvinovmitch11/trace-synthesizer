# DynamoRIO и InstrTracer

## Клиент

`build/src/InstrTracer/libInstrTracer.so` — клиент DynamoRIO, логирующий **по одному RVA на каждую исполненную инструкцию** в трассируемом модуле (RVA относительно базы загрузки модуля).

## Буфер

Для производительности используется **кольцевой буфер 64 KiB** (`trace_buffer`); сброс в `*.trace.bin` — по логике клиента (`src/InstrTracer/InstrTracer.cpp`).

## Запуск

После `make build`:

```bash
./scripts/run_tracer.sh output/foo.bin foo.bin
```

Аргументы: путь к бинарнику и **имя модуля** для сопоставления в DynamoRIO (часто basename файла).

## Артефакты

- `output/<stem>.trace.bin` — сырой поток RVA (`trace_synthesizer.io.instruction_trace`).
- Текст `llvm-readobj --bb-addr-map` → `_bb_map.txt` для сжатия RVA→`(func, bb)`.

## Дальше

```bash
poetry run python -m trace_synthesizer compress \
  --cfg output/foo.cfg.json --map output/foo_bb_map.txt \
  --trace output/foo.trace.bin --out output/foo.compressed_trace.json
```

English: [same chapter](../en/pipeline/02_dynamorio_instrtracer.md).
