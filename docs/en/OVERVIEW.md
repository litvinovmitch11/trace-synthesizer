# TraceSynthesizer — Architecture & Mechanisms Overview

This document explains **what every part of the repository does** and **how to
run it**. It is the practical companion to the thesis: where the thesis argues
the motivation, this document maps each idea to the concrete module, file, and
command that implements it.

- High-level idea and quick start: [README](../../README.md)
- How to reproduce the published numbers: [REPRODUCTION](REPRODUCTION.md)
- Measured results: [EXPERIMENTS](EXPERIMENTS.md)

---

## 1. The problem in one paragraph

Performance-oriented ML in compilers (e.g. MLGO register allocation) needs
**execution traces** — the ordered sequence of basic-block (BB) IDs a program
visits at runtime. Collecting them with dynamic instrumentation (DynamoRIO) is
slow, and every compiler pass that mutates the control-flow graph (CFG)
invalidates the collected trace. TraceSynthesizer learns a generator that, given
only the **static CFG**, a **PGO profile**, and **per-block features**, samples
valid traces that are statistically close to the real ones — including on a
*mutated* CFG it was never instrumented on (zero-shot).

---

## 2. Pipeline at a glance

```
 C/C++ source
     │
     │  scripts/build_cpp_dataset_artifacts.sh
     ▼
 ┌─────────────────────────── STATIC ───────────────────────────┐
 │ clang++ (PGO instrument → run → llvm-profdata merge)          │
 │ llc -load=CFGDumper.so  ───────────────►  <name>.cfg.json     │
 │     (BB features + PGO edge probs + loop/dom info)            │
 │ augment_cfg_with_ir2vec.py ────────────►  + ir2vec_embedding  │
 └──────────────────────────────────────────────────────────────┘
     │                                            ▲
     │ binary                                     │ same CFG
     ▼                                            │
 ┌─────────────────────────── DYNAMIC ──────────────────────────┐
 │ drrun -c InstrTracer.so  ─────────────►  <name>.trace.bin     │
 │ trace_synthesizer compress (RVA→BB)  ──►  compressed_trace.json│
 │ io.intra_trace ────────────────────────►  reference_intra.json │
 └──────────────────────────────────────────────────────────────┘
     │
     │ CFG + reference trace (+ loop_profile.json)
     ▼
 ┌─────────────────────────── LEARN ────────────────────────────┐
 │ env.CFGWalkEnv  +  CFGWalkRewardWrapper  +  FeatureWindow     │
 │ agents: Random-PGO │ LSTM-BC │ Flat PPO │ Hierarchical PPO    │
 └──────────────────────────────────────────────────────────────┘
     │ synthetic intra_traces.jsonl
     ▼
 ┌─────────────────────────── EVALUATE ─────────────────────────┐
 │ metrics: block_visit_kl · edge_transition_kl · hot_path_ngram │
 │ viz: Graphviz heat-map overlay                                │
 └──────────────────────────────────────────────────────────────┘
```

---

## 3. Components (by layer)

### 3.1 Static extraction — the C++ plugins (`src/`)
| File | Role |
|---|---|
| [src/CFGDumper/CFGDumper.cpp](../../src/CFGDumper/CFGDumper.cpp) | LLVM `MachineFunctionPass`. At code-gen time emits `cfg.json`: per-BB scalar features (instruction/branch/load/store/phi counts, terminator kind, loop depth, dominator/post-dominator depth, loop header/latch/exiting flags, back-edge count), **PGO edge probabilities** from `MachineBranchProbabilityInfo`, and BB IDs aligned to the binary's `bb-addr-map`. |
| [src/InstrTracer/InstrTracer.cpp](../../src/InstrTracer/InstrTracer.cpp) | DynamoRIO client. Records the executed instruction stream as little-endian RVAs for the target module(s) → `trace.bin`. |
| [scripts/augment_cfg_with_ir2vec.py](../../scripts/augment_cfg_with_ir2vec.py) | Runs `llvm-ir2vec` and writes a **75-D IR2Vec embedding** per block into `cfg.json` (`ir2vec_embedding`). |

### 3.2 Dynamic reference & canonical trace (`io/`)
| Module | Role |
|---|---|
| [io/bb_addr_map.py](../../trace_synthesizer/io/bb_addr_map.py) | Parse `llvm-readobj --bb-addr-map` into searchable RVA ranges. |
| [io/instruction_trace.py](../../trace_synthesizer/io/instruction_trace.py) | Read the raw `trace.bin` (uint64 LE RVAs). |
| [io/compress_pipeline.py](../../trace_synthesizer/io/compress_pipeline.py) | Map the RVA stream to a BB sequence, drop consecutive duplicates, validate against the CFG → `compressed_trace.json`. |
| [io/intra_trace.py](../../trace_synthesizer/io/intra_trace.py) | The **canonical intra-function trace** — one JSON schema used identically for the DynamoRIO reference and for synthetic rollouts, so metrics compare like-for-like. |

### 3.3 CFG model & features (`domain/`, `core/`, `features/`)
| Module | Role |
|---|---|
| [domain/program.py](../../trace_synthesizer/domain/program.py), [domain/cfg_loader.py](../../trace_synthesizer/domain/cfg_loader.py) | Immutable `Program`/CFG structures loaded from `cfg.json`. |
| [core/grammar.py](../../trace_synthesizer/core/grammar.py) | The CFG as a **grammar**: validated graph, fixed successor ordering, PGO normalization. This is what makes action masking well-defined. |
| [features/block_features.py](../../trace_synthesizer/features/block_features.py) | The **27 scalar features** per block (`base_dim = 27`), with an optional IR2Vec tail concatenated when present. |

### 3.4 The environment (`env/`)
| Module | Role |
|---|---|
| [env/cfg_walk_env.py](../../trace_synthesizer/env/cfg_walk_env.py) | Gymnasium env: stand at a block, pick **one valid outgoing edge** (discrete action), move. Invalid edges are masked. Episode ends at a sink, on `max_steps`, or on an invalid action. |
| [env/cfg_reward_wrapper.py](../../trace_synthesizer/env/cfg_reward_wrapper.py) | Adds the training reward (PGO shaping, terminal KL, loop-timing, ref-edge, short-path penalty) and the RL service tail of the observation (visit counts, episode progress, optional loop context). |
| [env/feature_window_wrapper.py](../../trace_synthesizer/env/feature_window_wrapper.py) | Stacks the last **K frames** of features → short-term memory without recurrence (`--window-back`). |
| [env/interproc_walk_env.py](../../trace_synthesizer/env/interproc_walk_env.py) | Inter-procedural variant with explicit call/return actions and a call stack. |

### 3.5 Generators (`agents/`)
| Agent | Idea |
|---|---|
| [agents/random_pgo.py](../../trace_synthesizer/agents/random_pgo.py) | **Random-PGO** baseline: sample edges ∝ normalized PGO weight. No training, no memory. |
| [agents/feature_window_lstm_policy.py](../../trace_synthesizer/agents/feature_window_lstm_policy.py) + [_agent](../../trace_synthesizer/agents/feature_window_lstm_agent.py) | **LSTM behavioral cloning**: supervised next-edge prediction over the back-window; autoregressive at inference. |
| [agents/ppo_policies.py](../../trace_synthesizer/agents/ppo_policies.py) | **Flat** actor-critic and **Hierarchical** (manager picks a discrete mode `z` every `manager_every` steps; worker maps `concat(obs, embed(z))` to edge logits). |
| [agents/hrl_ppo_agent.py](../../trace_synthesizer/agents/hrl_ppo_agent.py) | Rollout wrapper for both Flat and HRL checkpoints. |
| [agents/cfg_supervision.py](../../trace_synthesizer/agents/cfg_supervision.py) | Turns real traces into `(observation, successor-index)` pairs for the BC pre-training phase. |

### 3.6 RL training (`rl/`)
| Module | Role |
|---|---|
| [rl/train_ppo.py](../../trace_synthesizer/rl/train_ppo.py) | The two-phase loop: optional BC pre-training → PPO (`rollout → GAE → clipped update`). Also auto-enables loop-proposal reward defaults when a loop profile is given (`_apply_loop_proposal_reward_defaults`). |
| [rl/ppo.py](../../trace_synthesizer/rl/ppo.py) | Clipped-surrogate PPO loss + minibatch epochs. |
| [rl/rewards.py](../../trace_synthesizer/rl/rewards.py) | Reward terms and the KL helper (Laplace-smoothed `KL(p_ref ‖ q_episode)`). |
| [rl/loop_profile.py](../../trace_synthesizer/rl/loop_profile.py) | Loop/exit statistics from the reference trace, used for loop-timing reward and the loop context tail. |
| [rl/rollout_buffer.py](../../trace_synthesizer/rl/rollout_buffer.py) | Vectorized PPO storage (with manager goals in the hierarchical case). |

**Reward** (per valid step, terminal terms only at episode end):
`r = r_PGO + r_ref_edge + r_loop − penalties + I_end·(r_KL + r_short)`.
The defaults that matter (and prevent the "exit-in-3-steps" collapse): step-wise
PGO log-reward is **off** (`--pgo-log-scale 0`), terminal histogram KL is the
dominant global signal (`--terminal-kl-scale 100`), and a short-path penalty
plus loop-timing bonus keep episodes the right length.

### 3.7 Metrics (`metrics/`)
| Metric | Module | Meaning (lower KL / higher overlap = better) |
|---|---|---|
| `block_visit_kl` | [block_frequency.py](../../trace_synthesizer/metrics/block_frequency.py) | KL of BB-visit histograms, Laplace-smoothed on the union support. |
| `edge_transition_kl` | [edge_transition.py](../../trace_synthesizer/metrics/edge_transition.py) | Same, over consecutive `(BB_i, BB_{i+1})` pairs. |
| `hot_path_ngram_overlap` | [hot_path.py](../../trace_synthesizer/metrics/hot_path.py) | Mean recall@64 of the top BB n-grams for n ∈ {2,3,4}. |
| `speedup_dynamo_over_synthetic` | [speed.py](../../trace_synthesizer/metrics/speed.py) | Wall-clock synthesis time vs DynamoRIO. |

### 3.8 Glue (`runner/`, `viz/`, `program_trace.py`, `cli/`)
`runner/` rolls episodes and writes JSON/JSONL artifacts; `viz/graphviz_renderer.py`
renders the CFG with a trace heat-map; `program_trace.py` is a thin facade; the
CLI ([cli/main.py](../../trace_synthesizer/cli/main.py)) exposes everything.

---

## 4. How to run

### 4.1 Build the native tooling (once)
```bash
make configure        # cmake (uses LLVM_INSTALL_DIR)
make build            # CFGDumper.so + InstrTracer.so + DynamoRIO
poetry install        # Python deps (CPU PyTorch)
```

### 4.2 One program, end to end (manual)
```bash
# 1. static + dynamic artifacts (CFG, IR2Vec, reference trace)
scripts/build_cpp_dataset_artifacts.sh path/to/prog.cpp build_dir

# 2. loop profile from the reference (enables anti-collapse rewards)
poetry run python -m trace_synthesizer compute-loop-profile \
  --cfg build_dir/prog.cfg.json --func main \
  --reference build_dir/prog.compressed_trace.json --reference-compressed \
  --out build_dir/loop_profile.json

# 3. train Flat PPO (drop --hierarchical for flat; add it for HRL)
poetry run python -m trace_synthesizer train-hrl-ppo \
  --cfg build_dir/prog.cfg.json --func main --out-stem ckpt \
  --reference build_dir/prog.compressed_trace.json --reference-compressed \
  --loop-profile build_dir/loop_profile.json \
  --terminal-kl-scale 100 --pgo-log-scale 0 --window-back 8 --bc-epochs 10 \
  --iterations 15 --steps-per-iter 1024

# 4. synthesize + score
poetry run python -m trace_synthesizer rollout-hrl \
  --cfg build_dir/prog.cfg.json --func main --episodes 10 \
  --checkpoint ckpt --action-select sample --window-back 8 --out-dir roll
poetry run python -m trace_synthesizer metrics-compare \
  --reference build_dir/prog_reference_intra.json \
  --candidate roll/intra_traces.jsonl --func main --out metrics.json
```

### 4.3 The benchmark experiments (one command each)
```bash
make exp-trigger   # 7.2.3 / Table 7.3  state machine (in-domain)
make exp-diamond   # 7.2.4 / Table 7.4  context dependency
make exp-mutation  # 7.3.3 / Table 7.5  zero-shot CFG mutation
make exp-sorting   # 7.3.5 / Table 7.6  zero-shot nested loops
make exp-smart     # 7.4   / Tables 7.7-7.8  extreme mutations
make exp-opt       # 7.5   / Table 7.10  cross-optimization O0→O3
make exp-all       # everything
```
Each `scripts/run_*_exp.py` shares helpers from
[scripts/exp_common.py](../../scripts/exp_common.py): build artifacts → train
LSTM/Flat/HRL → rollout → `metrics-compare`.

### 4.4 Training the LSTM on a large code corpus (advanced)

The LSTM ([scripts/train_feature_window_lstm.py](../../scripts/train_feature_window_lstm.py))
has two input modes:

1. **Single-program (legacy)** — one JSONL row with `cfg` + `func` + `sequence`.
   This is what the `make exp-*` benchmarks use (one base program's trace), which
   is why the LSTM is only a weak single-graph baseline there.
2. **Cross-program corpus** — many programs/functions in one
   `cross.train.jsonl` (with precomputed `context_features`/`action_mask`/`target`),
   producing **one shared** model.

End-to-end corpus flow:
```
benchmarks/external/ctuning_curated.json   (curated cBench program list)
benchmarks/cbench_support/compile_hints.json (per-program clang flags)
benchmarks/external/ctuning-programs        (git submodule: cBench C sources)
  │  scripts/build_corpus_dataset.py  (compile multi-file C + PGO, run with
  │      profile_argv / input file, CFGDumper + IR2Vec, DynamoRIO trace, compress)
  ▼
spec.json   { "schema_version": 1,
              "entries": [ { "id", "cfg", "func",
                             "compressed_paths"|"compressed_glob" }, ... ] }
  ▼
scripts/build_multi_program_intra_dataset.py --spec spec.json --with-target-context
  ▼
cross.train.jsonl   (one row per (program, function) with precomputed context)
  ▼
scripts/train_feature_window_lstm.py --dataset-jsonl cross.train.jsonl
  ▼
one shared LSTM (feature_dim = 27 scalars + 75 IR2Vec)
```

Tested example (2 cBench programs → shared LSTM):
```bash
make corpus-demo      # or, manually:
poetry run python scripts/build_corpus_dataset.py \
  --ids cbench-automotive-bitcount cbench-network-dijkstra \
  --out-dir output/corpus_demo/artifacts --spec-out output/corpus_demo/spec.json
poetry run python scripts/build_multi_program_intra_dataset.py \
  --spec output/corpus_demo/spec.json --out-dir output/corpus_demo/dataset --with-target-context
poetry run python scripts/train_feature_window_lstm.py \
  --dataset-jsonl output/corpus_demo/dataset/cross.train.jsonl --out-stem output/corpus_demo/lstm_corpus
```
Needs the submodule checked out: `git submodule update --init benchmarks/external/ctuning-programs`.

> **TODO / experimental — not part of the thesis results.** The corpus path is a
> work-in-progress for scaling LSTM training beyond the six local benchmarks.
> Known limitations: only 4 programs are curated in `ctuning_curated.json`;
> `build_corpus_dataset.py` runs each program with the curated `profile_argv`
> (e.g. bitcount's `50000` produces a ~150 MB trace — lower it for quick runs);
> at high `-O` the `rollout_func` may be inlined away (the builder defaults to
> `-O1` to preserve named functions); and `build_multi_program_intra_dataset.py`
> only keeps the first CFG-valid contiguous slice per trace, so each program
> contributes one path. The PPO/HRL corpus trainer is **not** wired up — only the
> LSTM consumes `cross.train.jsonl`.

---

## 5. CLI reference (`python -m trace_synthesizer <cmd>`)

| Command | Purpose |
|---|---|
| `compress` | RVA `trace.bin` → validated `compressed_trace.json`. |
| `validate` | Check a trace against a CFG (no output). |
| `visualize` | Render CFG, optionally overlaying a trace. |
| `export-intra-trace` | Compressed trace → canonical intra-trace JSON. |
| `compute-loop-profile` | Loop/exit stats JSON from CFG + reference. |
| `rollout-random` | Random-PGO rollouts. |
| `rollout-lstm` | LSTM-BC rollouts from a checkpoint. |
| `rollout-hrl` | Flat/Hierarchical PPO rollouts from a checkpoint. |
| `train-hrl-ppo` | Train Flat (default) or Hierarchical (`--hierarchical`) PPO. |
| `metrics-compare` | Compute block/edge KL + hot-path overlap. |
| `metrics-bench-speed` | Wall-clock synthesis timing. |

---

## 6. Key knobs

| Flag | Default | Effect |
|---|---|---|
| `--window-back K` | 8 | Frames of short-term memory. Larger K resolves longer-range context (e.g. K=32 solves the diamond with Flat PPO). |
| `--hierarchical`, `--num-modes`, `--manager-every` | off, 4, 4 | Enable HRL; manager re-picks mode `z` every `manager_every` steps. |
| `--pgo-log-scale` | 0.5 (set **0** in experiments) | Step-wise PGO log-reward; non-zero causes early-exit collapse. |
| `--terminal-kl-scale` | 0.02 (set **100**) | Dominant global signal: terminal BB-histogram KL. |
| `--loop-profile` + `--loop-timing/-ref-edge/-short-path-scale` | — | Anti-collapse shaping derived from the reference loop structure. |
| `--bc-epochs` | 0 (set **10**) | Behavioral-cloning warm start before PPO. |

See [EXPERIMENTS.md](EXPERIMENTS.md) for the per-experiment configurations and
the appendix tables in the thesis for full hyperparameters.

---

## 7. Repository layout
```
src/                C++ plugins: CFGDumper (LLVM), InstrTracer (DynamoRIO)
trace_synthesizer/  Python package (domain, core, features, io, env,
                    agents, rl, metrics, runner, viz, cli)
scripts/            artifact build, experiment drivers, training helpers
benchmarks/local/   the six benchmark programs (base + mutated sources)
docs/en/            OVERVIEW · REPRODUCTION · EXPERIMENTS
tests/              pytest unit + integration tests
Makefile            build + experiment targets
```
