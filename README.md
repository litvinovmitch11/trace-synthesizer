# TraceSynthesizer

Synthesize realistic program **execution traces** (basic-block sequences) for
LLVM compiler-ML tasks — directly from the static control-flow graph (CFG),
PGO profile, and per-block features, **without** re-instrumenting the binary
after every compiler pass.

Collecting real traces with dynamic instrumentation (DynamoRIO) is slow, and
every CFG-mutating pass (e.g. RegAlloc spills) invalidates them. TraceSynthesizer
learns a generator that reproduces the statistical behavior of real traces and
transfers **zero-shot** to mutated CFGs — useful for trace-based MLGO pipelines.

## Highlights
- **LLVM CFGDumper plugin** — dumps the CFG with block features + PGO edge weights.
- **IR2Vec embeddings** — 75-D per-block semantics for structural generalization.
- **Four generators** — Random-PGO, LSTM behavioral cloning, Flat PPO, Hierarchical PPO.
- **Masked CFG-walk MDP** — the agent can only emit topologically valid traces.
- **Zero-shot transfer** — Flat PPO carries a base-CFG policy to mutated graphs and across `-O0…-O3`.

## Install & build
```bash
export LLVM_INSTALL_DIR=/path/to/llvm-21-install   # if not the Makefile default
make configure        # cmake
make build            # CFGDumper.so + InstrTracer.so + DynamoRIO
poetry install        # Python deps (CPU PyTorch)
make test-py          # run the test suite
```

## Run the experiments
Each target builds artifacts, trains the agents, rolls out, and scores — one
command, mapped to thesis Section 7:
```bash
make exp-trigger    # state machine (in-domain)
make exp-diamond    # context dependency (diamond)
make exp-mutation   # zero-shot CFG mutation
make exp-sorting    # zero-shot nested loops
make exp-smart      # extreme mutations (peeling / branch inversion)
make exp-opt        # cross-optimization O0 → O3
make exp-all        # all of the above
make clean-output   # remove generated artifacts
```

Run the pipeline on your own program with the CLI
(`python -m trace_synthesizer --help`); see
[OVERVIEW §4.2](docs/en/OVERVIEW.md#42-one-program-end-to-end-manual).

## Documentation
- **[OVERVIEW](docs/en/OVERVIEW.md)** — architecture, every mechanism, and how to run it.
- **[REPRODUCTION](docs/en/REPRODUCTION.md)** — rebuild and regenerate all results.
- **[EXPERIMENTS](docs/en/EXPERIMENTS.md)** — measured results.

## Results in one line
Hierarchical PPO is strongest **in-domain** (trigger, diamond: overlap 1.0);
**Flat PPO** is the strongest **zero-shot transfer** method (mutation 0.99,
sorting 1.0, O3 0.89). See [EXPERIMENTS](docs/en/EXPERIMENTS.md).

## License
See [LICENSE](LICENSE).
