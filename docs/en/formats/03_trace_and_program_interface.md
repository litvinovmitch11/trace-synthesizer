# Trace formats, CLI, and `ProgramTraceSession`

## Canonical intra trace (`bb_trace`)

Module: `trace_synthesizer.io.intra_trace`.

- `schema_version`, `function_name`, `source` (`bb_trace` literal), optional `episode`, `sequence` of `{ "func", "bb" }`.
- `export-intra-trace` from a compressed global trace and the first line of `rollout-random` / `--write-canonical-intra` share this schema so reference and synthetic files are comparable.

```bash
poetry run python -m trace_synthesizer export-intra-trace \
  --compressed output/foo.compressed_trace.json --func main \
  --out output/main.intra.json
```

## Compressed global trace

JSON array of `{ "func", "bb" }` after RVA→BB mapping and consecutive dedupe. Produced by `compress` / `run_compress_and_validate`. Validation counts intra, inter-procedural, and invalid transitions (`trace_synthesizer.io.compress_pipeline`).

## CLI surface

| Command | Role |
|---------|------|
| `compress` | RVA trace + bb map + cfg → `compressed_trace.json` |
| `validate` | Same without writing output |
| `export-intra-trace` | Slice one function to canonical intra JSON |
| `visualize` | CFG SVG with PGO coloring; `--trace` compressed or `--intra-json` |
| `rollout-random` | `CFGWalkEnv` + `RandomPGOAgent` → `intra_traces.jsonl` |

## Unified facade: `ProgramTraceSession`

Module: `trace_synthesizer.program_trace`.

Thin wrapper over `CfgProgram`, `compress_pipeline`, `intra_trace`, and `CfgGraphvizRenderer`:

- `from_cfg_json(path, function_name=...)`
- `validate_transition_counts(compressed_path | list[tuple[str,int]])`
- `compress_and_validate_rva_trace(bb_map_path, trace_bin_path)`
- `export_intra_from_compressed`, `intra_bb_path_from_compressed`, `intra_bb_path_from_intra_json`
- `render_cfg_with_trace(out_stem, trace_bbs=... | compressed_path=... | intra_path=...)`

Tests: `tests/test_program_trace_session.py`.

## Module map (without the facade)

| Operation | Location |
|-----------|----------|
| CFG grammar / PGO normalization | `trace_synthesizer.core.grammar` (`CfgProgram`) |
| MDP walk | `trace_synthesizer.env.cfg_walk_env` |
| Compress + validate | `trace_synthesizer.io.compress_pipeline` |
| Intra canonicalization | `trace_synthesizer.io.intra_trace` |
| Graphviz overlay | `trace_synthesizer.viz.graphviz_renderer` |
| CLI entry | `trace_synthesizer.cli.main` |

Russian: [same chapter](../ru/formats/03_trace_and_program_interface.md).
