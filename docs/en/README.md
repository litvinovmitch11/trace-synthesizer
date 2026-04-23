# TraceSynthesizer (EN)

## Goal

This repository implements a practical pipeline for execution-trace synthesis in compiler ML workflows:

1. Extract CFG + profile signals from LLVM MIR.
2. Collect real traces with DynamoRIO.
3. Build a BB-level training corpus.
4. Train a CFG-agnostic Feature-Window LSTM.
5. Compare synthetic traces against real traces with formal metrics.

The current production scope is intentionally limited to baseline + simple LSTM (proposal-aligned stage before RL agents).

## Implemented Components

- LLVM plugin: `CFGDumper`
- DynamoRIO tracer: `InstrTracer`
- CFG environment: `CFGWalkEnv`
- Baseline generator: random walk with PGO transition weights
- LSTM policy: feature-window sequence model
- Dataset builder: curated multi-program cBench JSONL
- Metrics: KL-based distribution metrics + hot-path overlap
- Visualization: CFG overlays for real/random/LSTM traces

## Mathematical Formulation

### MDP view

Trace synthesis over one function CFG is modeled as:

\[
\mathcal{M} = \langle \mathcal{S}, \mathcal{A}, P, R, \gamma \rangle
\]

- \(s_t \in \mathcal{S}\): current BB, path context, optional recurrent state.
- \(a_t \in \mathcal{A}(s_t)\): one of valid outgoing CFG edges.
- \(P(s_{t+1}\mid s_t, a_t)\): deterministic CFG transition.
- \(R\): similarity-driven signal (used later for RL stage).

### Block-visit KL

Given real distribution \(p\) and synthetic \(q\):

\[
D_{KL}(p\|q)=\sum_i p_i \log \frac{p_i}{q_i}
\]

We report directional and symmetrized variants.

### Edge-transition KL

The same KL form is applied to edge-transition frequencies.

### Hot-path overlap

Top-\(K\) n-gram overlap between real and synthetic trace sets:

\[
\text{Jaccard@K} = \frac{|H^{(n)}_{real,K} \cap H^{(n)}_{syn,K}|}{|H^{(n)}_{real,K} \cup H^{(n)}_{syn,K}|}
\]

## Main Targets

```bash
make plugins-demo
make random-baseline
make dataset-cbench
make train-lstm
make lstm-eval
make visualize-trace
make compare-traces
```

## Training vs Evaluation Split

- Training corpus source: curated cBench entries from `benchmarks/external/ctuning_curated.json`.
- Evaluation target: local benchmark `benchmarks/local/benchmark_complex.cpp`.

See full reproducibility steps in `docs/en/REPRODUCTION.md`.
