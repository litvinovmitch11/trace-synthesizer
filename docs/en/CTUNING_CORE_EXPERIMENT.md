# Experiment: “core” metrics and path lengths to the function exit

## Idea

1. The **pipeline** (PGO, DynamoRIO, `compress`) stays tied to **`entry_func`** from the manifest—usually `main`—so the whole binary is traced and the full CFG is built. The **`visualize`** step in `ctuning_full_pipeline_c.sh` uses **`rollout_func`** (same as `rollout-random`) so trace-overlay SVGs match the core function and scripts like `ctuning_crc32_paired_traces_and_viz.sh`.
2. **`rollout-random`** and the metrics block in `ctuning_curated_stats.json` use **`rollout_func`**—the symbol in the same `*.cfg.json` where the real compute lives (skipping the `ctuning-rtl` / cold `main` wrapper when that makes sense).
3. **`rollout_max_steps`: `0`** in the manifest means: do **not** cap episodes by step count inside `CFGWalkEnv`; walk until the **CFG sink** of the modeled function. Safety net: a hard cap of **10⁷** steps per episode inside `rollout_episode` (see `termination: hard_capped` in `runs.jsonl`).

## Table for the current `benchmarks/ctuning_curated.json`

| `id` | `entry_func` (pipeline) | `rollout_func` (core) | Why |
|------|-------------------------|----------------------|-----|
| `shared-matmul-c` | `main` | `main` | The Dynamo trace for this binary only contains `main` (`matmul` is inlined). |
| `shared-matmul-c2` | `main` | `main` | Same pattern. |
| `cbench-automotive-bitcount` | `main` | `bit_count` | Symbol `bitcount` in the CFG is a degenerate graph; walks use `bit_count`. |
| `cbench-telecom-crc32` | `main` | `main1` | Real file processing is in `main1`; `main` is only the ctuning wrapper. |
| `cbench-security-sha` | `main` | `sha_stream` | Stream hashing; `main` / `main1` are thin glue. |

If you change LLVM version or flags, names may drift slightly: inspect `function_name` entries in `*.cfg.json`.

## How to run

Recommended order after `make build`:

```bash
make ctuning-bootstrap
poetry run python3 -m trace_synthesizer ctuning-rollout \
  --episodes 20 --seed 0 --stats-file output/ctuning_curated_stats.json
```

- **`--episodes`**: how many independent paths to sample (lengths land in `runs.jsonl` and aggregate into `rollout_path_lengths` in the stats JSON).
- **`rollout_max_steps` in JSON = `0`**: “until function exit” mode for `rollout_func`. CLI `--max-steps` is then **overridden** by the manifest (see `rollout_max_steps_used` in stats).

For **heavy** CFGs (large `matmul`) a random walk to the sink can take extremely long or hit `hard_capped`. Temporarily set a positive `rollout_max_steps` (e.g. `500000`) for just that manifest row.

## What to read in `output/ctuning_curated_stats.json`

- **`rollout_path_lengths.by_termination.terminated`**: lengths of successful sink-reaching paths (`mean` / `min` / `max` / `lengths` list).
- **`hard_capped`**: episode exhausted the internal step cap—increase the cap in code, shrink the CFG, or set a finite `rollout_max_steps`.
- **`metrics_vs_dynamo_first_rollout`**: now computed for **`rollout_func`**—closer to the “core”, not the `main` wrapper.

## Manual rerun for one program

```bash
poetry run python3 -m trace_synthesizer ctuning-rollout \
  --only cbench-security-sha --skip-pipeline --episodes 10 --seed 1 \
  --stats-file output/sha_core_stats.json
```

(`--skip-pipeline` when `output/ctuning_cbench-security-sha/*.cfg.json` already exists from a full run.)

Russian: [same chapter](../ru/CTUNING_CORE_EXPERIMENT.md).
