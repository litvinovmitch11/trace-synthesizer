# DynamoRIO and InstrTracer

## Client

`build/src/InstrTracer/libInstrTracer.so` is a DynamoRIO client that logs **one RVA per executed instruction** in the traced module (RVA relative to the module load base, not absolute virtual addresses).

## Buffer

Implementation uses a **64 KiB ring buffer** (`trace_buffer`) for throughput; the client flushes to `*.trace.bin` according to the client logic (see `src/InstrTracer/InstrTracer.cpp`).

## Running

After `make build`, DynamoRIO is under `build/_deps/dynamorio_pkg-src/bin64/drrun`:

```bash
./scripts/run_tracer.sh output/foo.bin foo.bin
```

Inputs: path to the profiled binary and the **module name** string DynamoRIO should match (commonly the on-disk basename).

## Artifacts

- `output/<stem>.trace.bin` — raw RVA stream (see `trace_synthesizer.io.instruction_trace`).
- `llvm-readobj --bb-addr-map` text → `_bb_map.txt` pairs addresses with LLVM BB ids for compression.

## Next step

```bash
poetry run python -m trace_synthesizer compress \
  --cfg output/foo.cfg.json --map output/foo_bb_map.txt \
  --trace output/foo.trace.bin --out output/foo.compressed_trace.json
```

Russian: [same chapter](../ru/pipeline/02_dynamorio_instrtracer.md).
