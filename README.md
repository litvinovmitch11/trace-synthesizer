# TraceSynthesizer

TraceSynthesizer is a reinforcement learning (RL) framework designed to synthesize realistic program execution traces for LLVM compiler optimization models (specifically targeting the MLGO infrastructure).

Collecting true execution traces post-optimizations (like RegAlloc) is notoriously difficult because compiler passes alter the Control Flow Graph (CFG) topology. TraceSynthesizer solves this by generating statistically accurate, context-aware execution paths directly from the static CFG and profile information (PGO), without needing to run the actual compiled binary.

## Key Features
- **LLVM CFGDumper Plugin:** Extracts the CFG along with node semantics and edge weights.
- **IR2Vec Integration:** Understands code semantics beyond just node IDs.
- **Context-Aware Sequence Modeling:** Employs LSTMs and Proximal Policy Optimization (PPO) with a sliding feature window to resolve complex control-flow dynamics, like the "Diamond Problem".
- **Zero-Shot Structural Generalization:** The models can accurately synthesize traces for programs that have undergone extreme compiler mutations (like loop peeling or branch inversions) without retraining.
- **Hierarchical RL (Optional):** Implements a Manager-Worker FeUdal architecture for handling complex state machines.

## Documentation

Comprehensive documentation is provided in two languages:
- **English**:
  - [Reproduction Guide](docs/en/REPRODUCTION.md)
  - [Experiments Report](docs/en/EXPERIMENTS.md)
- **Russian (Русский)**:
  - [Руководство по воспроизведению](docs/ru/REPRODUCTION.md)
  - [Отчет об экспериментах](docs/ru/EXPERIMENTS.md)

## Quick Start

The easiest way to reproduce the findings is to use the provided `Makefile`.

```bash
# Compile the LLVM plugin and DynamoRIO tools
make configure
make build

# Run the benchmark experiments (Zero-shot generalization tests)
make exp-diamond    # Context Dependency (State Machine / Diamond Problem)
make exp-mutation   # Basic CFG Mutation Generalization
make exp-sorting    # Complex Loops Generalization
make exp-smart      # Extreme Compiler Mutations (Loop Peeling)

# Clean experiment outputs
make clean-output
```

## Creating Large Datasets (e.g. for cBench)

To train the models for industrial use on thousands of functions:
1. Use `scripts/build_cpp_dataset_artifacts.sh` to extract `cfg.json` and DynamoRIO traces from your codebase.
2. Create a JSON manifest (`spec.json`) mapping IDs to these artifacts.
3. Precompute the tensor dataset using `scripts/build_multi_program_intra_dataset.py --with-target-context`.
4. Train the PPO agent or LSTM instantly on the resulting `cross.train.jsonl` using `scripts/train-hrl-ppo` or `scripts/train_feature_window_lstm.py`.