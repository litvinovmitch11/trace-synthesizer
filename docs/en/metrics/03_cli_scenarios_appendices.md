# Metrics: CLI, scenarios, appendices (part 3)

Parts 1–2: [01_trace_levels_and_context.md](01_trace_levels_and_context.md), [02_metric_definitions.md](02_metric_definitions.md).

Russian version: [../ru/metrics/03_cli_scenarios_appendices.md](../ru/metrics/03_cli_scenarios_appendices.md).

## 5. Python API and CLI

From `trace_synthesizer.metrics`:

- loaders: `load_path_from_intra_trace_json`, `load_paths_from_intra_traces_jsonl`, `load_path_from_compressed_trace`;
- `MetricContext`, `run_metrics`, `results_to_jsonable`;
- speed: `benchmark_random_rollouts`, `benchmark_rollout_seconds`, `speedup_vs_dynamo`.

CLI:

```bash
poetry run python -m trace_synthesizer metrics-compare \
  --reference <path> --candidate <path> --func <name> \
  [--reference-compressed] [--candidate-compressed] [--metrics ...] [--out report.json]

poetry run python -m trace_synthesizer metrics-bench-speed \
  --cfg <cfg.json> --func <name> --n-episodes <N> \
  [--dynamo-seconds T | --dynamo-sec-for-1000 T] [--out ...]
```

### Complex CFG example

[`examples/benchmark_complex/main.cfg.json`](../../../examples/benchmark_complex/main.cfg.json) is a rich single-function `main` graph (hub, three chains, loop, merge) useful for non-trivial KL and n-gram experiments.

## 6. Experiment reporting tips

1. Pin binary, PGO profile, Dynamo inputs, generator seed, \(N\), `max_steps`.
2. Distinguish “one real trace vs synthetic corpus” from “two synthetic corpora” when discussing confidence intervals.
3. For speed, document hardware, cores, turbo policy, and how Dynamo time was measured.
4. Intra traces **drop** inter-procedural context; be careful generalizing to whole-program behavior.

## 7. Proposal reference

Primary motivation: Project Proposal section III.D (*Evaluation Metrics*), [Project_Proposal_Litvinov_Michael.pdf](../../Project_Proposal_Litvinov_Michael.pdf).

---

## Appendix A — Formal intra trace

Let \(G=(V,E)\) be the CFG of function \(f\). An **intra trace** (after deduplicating consecutive duplicates) is \(\tau=(v_0,\ldots,v_T)\) with \(v_0\) an entry block, \((v_t,v_{t+1})\in E\) for \(t<T\), and \(v_T\) terminal (or truncated at `max_steps`).

Under policy \(\pi\) (baseline: `RandomPGOAgent`), rollouts induce a distribution over valid \(\tau\). Dynamo traces induce \(\tilde\tau\) over the same alphabet \(V\) from program semantics. Section-4 metrics compare **empirical** samples, not closed forms.

## Appendix B — MDP and RL

State: current BB (plus optional features in observations). Action: successor index in sorted `target_id` order. Deterministic transition. Reward is zero until terminal in the current env; RL extensions may add trace-similarity rewards. Metrics apply **outside** the RL loop to finished traces.

## Appendix C — JSON schema

Single intra object: `schema_version`, `function_name`, `source` = `bb_trace`, `episode` (int or null), `sequence` of `{func, bb}`. `rollout-random` JSONL lines use the same keys with `episode` set.

## Appendix D — `metrics-compare` flags

| Flag | Role |
|------|------|
| `--reference` | Intra JSON or compressed (with `--reference-compressed`) |
| `--candidate` | Intra JSON, JSONL, or compressed (with flag) |
| `--func` | Function filter for compressed inputs |
| `--metrics` | Comma list: `block_visit_kl`, `edge_transition_kl`, `hot_path_ngram_overlap` |
| `--epsilon`, `--ngram-min`, `--ngram-max`, `--top-k`, `--out` | Standard tuning knobs |

## Appendix E — Source map

| Concern | Module |
|---------|--------|
| Block visits | [`trace_synthesizer/metrics/block_frequency.py`](../../../trace_synthesizer/metrics/block_frequency.py) |
| Edge transitions | [`edge_transition.py`](../../../trace_synthesizer/metrics/edge_transition.py) |
| Hot-path | [`hot_path.py`](../../../trace_synthesizer/metrics/hot_path.py) |
| KL helpers | [`discrete.py`](../../../trace_synthesizer/metrics/discrete.py) |
| Loaders | [`loaders.py`](../../../trace_synthesizer/metrics/loaders.py) |
| Driver | [`compare.py`](../../../trace_synthesizer/metrics/compare.py) |
| Protocol / registry | [`protocol.py`](../../../trace_synthesizer/metrics/protocol.py), [`registry.py`](../../../trace_synthesizer/metrics/registry.py) |
| Speed | [`speed.py`](../../../trace_synthesizer/metrics/speed.py) |

## Appendix F — Tiny KL numeric example

If smoothed estimates on \(\{a,b\}\) give \(\hat P(a)=0.6\), \(\hat P(b)=0.4\) and \(\hat Q(a)=\hat Q(b)=0.5\), then \(D_{\mathrm{KL}}(\hat P\|\hat Q) \approx 0.029\).

## Appendix G — Repro on `benchmark_complex`

1. `poetry run python -m trace_synthesizer rollout-random --cfg examples/benchmark_complex/main.cfg.json --func main --episodes 500 --seed 0 --max-steps 5000 --out-dir output/rollouts_complex`
2. `poetry run python -m trace_synthesizer export-intra-trace --compressed output/<prog>.compressed_trace.json --func main --out output/main_intra_real.json`
3. `poetry run python -m trace_synthesizer metrics-compare --reference output/main_intra_real.json --candidate output/rollouts_complex/intra_traces.jsonl --func main --out output/metrics_main.json`
4. `poetry run python -m trace_synthesizer metrics-bench-speed --cfg examples/benchmark_complex/main.cfg.json --func main --n-episodes 1000 --max-steps 5000 --seed 1`

For regression coverage see [`tests/test_metrics_e2e.py`](../../../tests/test_metrics_e2e.py).
