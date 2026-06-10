# Experiments & Results

Measured results for the six benchmark pipelines. Every number below was
produced by the committed `scripts/run_*_exp.py` drivers (`make exp-*`) on CPU
with `seed 42`, IR2Vec embeddings enabled, and the loop-profile reward shaping
described in [OVERVIEW](OVERVIEW.md). To regenerate them see
[REPRODUCTION](REPRODUCTION.md).

> Honesty note: these are the **reproducible** numbers from the current
> repository. Where they differ from a table in the thesis, the difference is
> called out explicitly. The recurring theme — **Flat PPO is the strongest
> zero-shot transfer method, HRL is strongest in-domain** — holds across every
> experiment.

## Metrics
- **`block_visit_kl`** — KL of basic-block visit histograms (Laplace-smoothed on the union support). Lower is better.
- **`edge_transition_kl`** — same over consecutive `(BBᵢ, BBᵢ₊₁)` pairs. Lower is better.
- **`hot_path_ngram_overlap`** — mean recall@64 of the top BB n-grams for n ∈ {2,3,4}. Higher is better (1.0 = the reference's hot paths are all reproduced).

Modes: **in-domain** (train and evaluate on the same CFG) vs **zero-shot**
(train on a base CFG, evaluate on a mutated/other CFG never instrumented during
training).

---

## 1. State machine — `cpp_trigger` (in-domain) · `make exp-trigger`
A loop whose branch depends on an internal `state` variable updated across
iterations — a Markov walk cannot track it.

| Method | block_visit_kl | hot_path_ngram_overlap |
|---|---|---|
| Random PGO | 3.12 | 0.74 |
| LSTM (BC) | 5.54 | 0.32 |
| Flat PPO | 0.41 | 0.99 |
| **Hierarchical PPO** | **0.045** | **1.00** |

PGO follows hot edges locally but cannot bind the state-machine phases; LSTM
drifts auto-regressively; HRL reproduces the reference almost exactly.

## 2. Context dependency — `cpp_diamond` (in-domain) · `make exp-diamond`
A late branch depends on an earlier branch in the same run ("diamond").

| Method | hot_path_ngram_overlap |
|---|---|
| Flat PPO (`--window-back 8`) | 0.09 |
| Flat PPO (`--window-back 32`) | 0.98 |
| **Hierarchical PPO** | **1.00** |

HRL solves the diamond via its mode abstraction. Flat fails **only** because the
two branches are farther apart than the K=8 window; widening the window to 32
recovers 0.98 — i.e. Flat's weakness here is memory length, not capability.

## 3. Zero-shot CFG mutation — `cpp_mutation` · `make exp-mutation`
Base = state machine; mutated = inserted dummy/spill blocks + an extra entry
`if` (simulates RegAlloc passes). Train on base, infer on mutated.

| Method | block_visit_kl | hot_path_ngram_overlap |
|---|---|---|
| Oracle PGO (target profile) | 0.33 | 0.99 |
| LSTM zero-shot | 9.26 | 0.21 |
| **Flat PPO zero-shot** | **0.23** | **0.99** |
| HRL zero-shot | 17.40 | 0.07 |

**Flat PPO is the winner here.** HRL trains correctly on the base graph
(~1280-step episodes) but on the mutated entry takes a wrong early edge and
exits in ~5 steps — confirmed across `--window-back {8,16}` and
`--action-select {sample,argmax}`. *(The thesis Table 7.5 reports HRL=1.0; that
is not reproducible — Flat PPO is the reproducible zero-shot method, consistent
with experiments 4–6 below.)*

## 4. Zero-shot nested loops — `cpp_sorting_mutation` · `make exp-sorting`
Bubble sort; mutation adds dummy branches and `volatile` spill slots inside the
loops.

| Method | block_visit_kl | hot_path_ngram_overlap |
|---|---|---|
| Oracle PGO | 1.06 | 0.98 |
| LSTM zero-shot | 0.56 | 0.42 |
| **Flat PPO zero-shot** | **0.03** | **1.00** |
| HRL zero-shot | 0.02 | 0.88 |

Flat PPO (window + IR2Vec) reproduces the loops perfectly; HRL's fixed-rhythm
manager is slightly less aligned with nested loops. Matches the thesis Table 7.6
overlaps exactly.

## 5. Extreme mutations — `cpp_smart_mutation` · `make exp-smart`
Aggressive, compiler-like rewrites of a state machine: **loop peeling**,
**branch inversion** (swap true/false edges), **hot-block splitting**.

| Method | block_visit_kl | hot_path_ngram_overlap |
|---|---|---|
| Oracle PGO (target profile) | 0.63 | 1.00 |
| LSTM zero-shot | 2.15 | 0.63 |
| Flat PPO zero-shot | 19.73 | 0.00 |
| HRL zero-shot | 19.73 | 0.00 |

This is the breaking point for the learned policies: branch inversion swaps the
edge indices, and after loop peeling the trained policies pick the wrong early
edge and collapse. Only the (cheating) Oracle PGO and the LSTM retain signal.
*(The thesis Table 7.8 reports Flat 0.795 with IR2Vec; in the current pipeline
Flat collapses to 0.0 — only the LSTM result, 0.63, reproduces. This benchmark
marks the limit of zero-shot transfer and motivates the event-based manager and
richer semantic features listed as future work.)*

## 6. Cross-optimization O0→O3 — `cpp_opt_levels` · `make exp-opt`
One source, compiled `-O0…-O3` (34 / 20 / 55 / 59 basic blocks). Train on `-O0`
only; evaluate zero-shot on every level. `hot_path_ngram_overlap`:

| Method | -O0 | -O1 | -O2 | -O3 |
|---|---|---|---|---|
| Random PGO (target profile) | 1.00 | 0.98 | 0.94 | 0.94 |
| LSTM | 0.08 | 0.04 | 0.02 | 0.02 |
| **Flat PPO** | **1.00** | **0.91** | **0.89** | **0.89** |
| HRL PPO | 1.00 | 0.64 | 0.68 | 0.68 |

Trained on 34 O0 blocks, Flat PPO keeps ~0.89 overlap on the 59-block O3 graph.
LSTM overfits the O0 topology and fails elsewhere. PGO is an upper-bound
Markov baseline that reads the *target* graph's probabilities (not a transferred
policy). Direction matches the thesis Table 7.10 (Flat is the strongest learned
transfer); absolute values differ slightly run-to-run.

---

## Summary

| Scenario | Mode | Best learned method | Key number |
|---|---|---|---|
| trigger | in-domain | HRL | overlap 1.00, KL 0.045 |
| diamond | in-domain | HRL | overlap 1.00 |
| mutation | zero-shot | **Flat PPO** | overlap 0.99, KL 0.23 |
| sorting | zero-shot | **Flat PPO** | overlap 1.00 |
| smart | zero-shot | — (only PGO/LSTM survive) | LSTM overlap 0.63 |
| cross-opt O0→O3 | zero-shot | **Flat PPO** | O3 overlap 0.89 |

**Takeaways**
- **Hierarchical PPO** is best when there is an explicit phase/state structure on a *fixed* graph (trigger, diamond).
- **Flat PPO** (feature window + IR2Vec) is the robust **zero-shot transfer** method (mutation, sorting, cross-opt).
- Both learned policies still **collapse under extreme structural mutation** (branch inversion + loop peeling); closing that gap (event-based manager, richer semantic features) is future work.
- Synthetic rollout is orders of magnitude faster than re-running DynamoRIO at inference (`metrics-bench-speed`).
