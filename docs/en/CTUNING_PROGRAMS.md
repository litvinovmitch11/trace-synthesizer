# [ctuning-programs](https://github.com/ctuning/ctuning-programs) integration

The **ctuning-programs** tree is wired as a **git submodule** at `external/ctuning-programs/`. Inside you will find Collective Knowledge programs (`program/<name>/` plus `.cm/meta.json`). For TraceSynthesizer:

- Many benchmarks ship **multiple `.c` files** and sometimes need **external datasets** from `ctuning-datasets-*`; those programs stay **out** of the shared manifest until an input file or generator is wired in.
- CFG **`entry_func`** may differ from `main`; the manifest field `entry_func` controls that.

## 1. First-time setup (submodule)

After `git clone` of this repo, initialize the submodule (pick one):

```bash
git submodule update --init --recursive external/ctuning-programs
```

or via Makefile (calls `scripts/init_ctuning_submodule.sh`):

```bash
make ctuning-bootstrap
```

`init_ctuning_submodule.sh` behavior:

- If `external/ctuning-programs/program` already exists — no-op.
- If `.gitmodules` contains `[submodule "external/ctuning-programs"]` — runs `git submodule update --init --depth 1 external/ctuning-programs`.
- **Otherwise** (fork without submodule metadata) — falls back to the **legacy** `scripts/bootstrap_ctuning_programs.sh` shallow clone.

The pinned **version** of ctuning-programs is the **commit** recorded for the gitlink `external/ctuning-programs`. Bump upstream like any submodule:

```bash
cd external/ctuning-programs
git fetch origin && git checkout <commit-or-branch>
cd ../..
git add external/ctuning-programs
git commit -m "Bump ctuning-programs submodule"
```

## 2. Build LLVM plugins and DynamoRIO

`ctuning_full_pipeline_c.sh` expects `build/src/CFGDumper/CFGDumper.so`, `InstrTracer`, and `drrun`. Before running:

```bash
poetry install
make configure
make build
```

Environment variables `LLVM_DIR`, `CLANG_C`, etc. follow `scripts/ctuning_full_pipeline_c.sh` (defaulting to your local LLVM install prefix).

## 3. Curated manifest (`benchmarks/ctuning_curated.json`)

There are **5** entries today, all **plain C** without the CK runtime. Each specifies **`rollout_func`** (kernel for rollouts/metrics) and **`rollout_max_steps`: 0** (walk until the CFG sink for that function; see [CTUNING_CORE_EXPERIMENT.md](CTUNING_CORE_EXPERIMENT.md)).

| `id` | Input gist |
|------|------------|
| `shared-matmul-c` | `CT_MATRIX_DIMENSION`, `CT_REPEAT_MAIN` + `profile_data` file (`float_space_separated`) as `argv[1]`. |
| `shared-matmul-c2` | Same family, different matrix size; `program/shared-matmul-c2/matmul.c`. |
| `cbench-automotive-bitcount` | Multiple `.c` files; numeric `argv[1]` iteration count. |
| `cbench-telecom-crc32` | `crc_32.c` + `ctuning-rtl.c`; `argv[1]` is a **temporary text file** (`profile_data.kind`: `text_file`). |
| `cbench-security-sha` | `sha.c`, `sha_driver.c`, `ctuning-rtl.c`; input is a **temporary file** (`text_file`). |

Manifest extension fields:

- `id`, `sources_relative` (relative to ctuning-programs root),
- optional `profile_env`, `profile_argv`,
- `profile_data` with `kind`: `float_space_separated` | `text_file`,
- `entry_func` — pipeline + visualization (often `main`),
- optional **`rollout_func`** — for `rollout-random` and stats (defaults to `entry_func`),
- optional **`rollout_max_steps`** — when set, **overrides** CLI `--max-steps`; value **`0`** means do not cap steps in the env (until the CFG exit for that function, with an internal 1e7 safety cap per episode).

## 4. Pipeline + rollouts

All manifest rows:

```bash
make ctuning-rollout
# same flags via:
poetry run python3 -m trace_synthesizer ctuning-rollout
```

Subset:

```bash
poetry run python3 -m trace_synthesizer ctuning-rollout \
  --only shared-matmul-c,cbench-security-sha \
  --episodes 20 --max-steps 5000 --seed 1
```

Useful CLI flags:

| Flag | Purpose |
|------|---------|
| `--ctuning-root PATH` | Alternate ctuning-programs checkout. |
| `--out DIR` | Parent directory for `ctuning_<id>/` (default `output/`). |
| `--only id1,id2` | Filter manifest ids. |
| `--limit N` | Take first `N` rows after `--only`. |
| `--skip-pipeline` | Only `rollout-random` (reuse CFG from a prior run). |
| `--no-bootstrap` | Do not auto-init submodule (fails if missing). |
| `--stats-file PATH` | Aggregated stats output (default `output/ctuning_curated_stats.json`). |
| `--no-stats` | Skip JSON + final metric table. |
| `--no-metrics` | Skip the “metrics vs Dynamo” block inside JSON (faster). |

Per-program artifacts under `output/ctuning_<id>/`: `*.cfg.json`, `*.compressed_trace.json`, `rollouts_random/` (`runs.jsonl`, `intra_traces.jsonl`, `summary.json`), SVG renders.

## 4b. One trace format (real + synthetic)

All intra JSON objects—whether from `export-intra-trace` on Dynamo data or lines in `intra_traces.jsonl` after `rollout-random`—share **one schema**: keys in a fixed order (`schema_version`, `function_name`, `source`, `episode`, `sequence`) with **`source` always `bb_trace`**. Only **`sequence`** (and optionally `episode`, `null` in single-file exports) differs.

For `cbench-telecom-crc32` (`main1`), a paired real/synthetic visualization:

```bash
./scripts/ctuning_crc32_paired_traces_and_viz.sh
```

Outputs: `output/ctuning_cbench-telecom-crc32/paired_viz/main1_{real,synthetic}.intra.json` and `main1_cfg_{real_trace,synth_trace}.svg`.

Also: `rollout-random --write-canonical-intra PATH` writes the **first** episode using the same schema as `export-intra-trace`. For intra-based renders: `visualize --intra-json FILE` instead of `--trace` on the full compressed trace.

## 5. Stats JSON + metrics

Unless `--no-stats` is passed, each run writes (by default):

`output/ctuning_curated_stats.json`

Top-level fields:

- `generated_at_utc` — UTC ISO-8601 timestamp,
- `episodes`, `max_steps` — rollout parameters,
- `entries` — one object per program:
  - `id`
  - `wall_seconds_pipeline_and_rollout` — pipeline + `rollout-random`
  - `out_dir`, `rollouts_dir`
  - `rollout_summary` — copy of `rollouts_random/summary.json`
  - `synthetic_bench_subset` — short synthetic throughput sample (`benchmark_random_rollouts`, up to 50 episodes, `max_steps=2000`)
  - `metrics_vs_dynamo_first_rollout` — compares the **real** trace in `*.compressed_trace.json` with the **first** synthetic line in `intra_traces.jsonl` (`block_visit_kl`, `edge_transition_kl`, `hot_path_ngram_overlap`; definitions in [metrics/README.md](metrics/README.md)).

Manual replay for one pair:

```bash
poetry run python3 -m trace_synthesizer metrics-compare \
  --reference output/ctuning_shared-matmul-c/shared-matmul-c.compressed_trace.json \
  --reference-compressed \
  --candidate output/ctuning_shared-matmul-c/rollouts_random/intra_traces.jsonl \
  --func main
```

## 6. CI and cloning

Teach CI to recurse submodules:

```bash
git submodule update --init --recursive
```

or `GIT_SUBMODULE_STRATEGY: recursive` on GitLab (or your CI equivalent).

---

**Short checklist:** `git submodule update --init` → `make build` → `make ctuning-rollout` → inspect `output/ctuning_curated_stats.json` and the metric table in the log.

Russian version: [../ru/CTUNING_PROGRAMS.md](../ru/CTUNING_PROGRAMS.md).
