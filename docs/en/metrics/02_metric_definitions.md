# Metrics: mathematical definitions (part 2)

This is part 2 of the trace/metrics series; see [01_trace_levels_and_context.md](01_trace_levels_and_context.md) and [03_cli_scenarios_appendices.md](03_cli_scenarios_appendices.md).

Russian version: [../ru/metrics/02_metric_definitions.md](../ru/metrics/02_metric_definitions.md).

## 4. Comparison metrics (`trace_synthesizer.metrics`)

Definitions match the implementation. Defaults can be overridden via `MetricContext` and the CLI.

### 4.1 Empirical distributions and smoothing

Given a finite alphabet \(S\) (BB ids or directed edges), counts \(c(s)\) are built from one or more traces. On the union support \(S' = \{s: c_{\mathrm{ref}}(s) > 0 \vee c_{\mathrm{cand}}(s) > 0\}\),

\[
\hat p(s) = \frac{c(s) + \varepsilon}{\sum_{t \in S'} (c(t) + \varepsilon)},
\]

with small \(\varepsilon > 0\) (default `1e-8`).

### 4.2 `block_visit_kl`

Per-BB visit counts over a corpus of intra traces yield \(\hat P\) (reference) and \(\hat Q\) (candidate). The reported `value` is \(D_{\mathrm{KL}}(\hat P \| \hat Q)\). `details` may include the symmetrized KL and support size.

**Note.** Block marginals ignore reorderings with identical counts; use transitions and n-grams for order effects.

### 4.3 `edge_transition_kl`

Counts of consecutive pairs \((bb_i, bb_{i+1})\) over the corpus; KL on the empirical edge distribution. Interprets similarity of a **first-order Markov** model to data.

### 4.4 `hot_path_ngram_overlap`

For each \(n \in [n_{\min}, n_{\max}]\) (default 2–4), rank BB n-grams by frequency on each corpus, take top-\(K\) sets \(T_{\mathrm{ref}}\), \(T_{\mathrm{cand}}\). Report recall of reference top n-grams in the candidate corpus, Jaccard on the tops, and aggregate `value` as mean recall over \(n\).

### 4.5 `metrics-bench-speed`

Measures **CPU time** in-process for `N` `rollout_episode` calls with `RandomPGOAgent`. Dynamo time for `N` equivalent traces is **not** measured automatically: supply wall/CPU seconds via `--dynamo-seconds` (alias `--dynamo-sec-for-1000` when phrased for \(N=1000\)) to compute `speedup_vs_dynamo`.
