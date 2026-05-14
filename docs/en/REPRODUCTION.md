# Reproduction Guide

This document describes how to reproduce the core experiments presented in the project. The infrastructure has been greatly simplified, and all primary experiments are now driven by the `Makefile`.

## 1. Environment Setup

Ensure you have LLVM (version 21 recommended) and the necessary Python dependencies (installed via Poetry).

```bash
# Configure the build system
make configure

# Compile the LLVM CFGDumper plugin and DynamoRIO tracer
make build
```

## 2. Running End-to-End Experiments

We have prepared four major validation benchmarks demonstrating the framework's capability to understand context dependencies and perform zero-shot generalization to mutated Control Flow Graphs (CFGs).

All these commands automatically:
1. Compile the base and mutated C++ programs.
2. Extract CFGs and semantic embeddings (IR2Vec).
3. Gather ground truth traces via DynamoRIO.
4. Train all synthesizer agents (LSTM, Flat PPO, Hierarchical PPO).
5. Perform zero-shot rollouts on the mutated graph.
6. Calculate metrics and render visualizations.

### Experiment 1: Context Dependency (The Diamond Problem)
Demonstrates the agent's ability to maintain internal state and temporal logic (resolving the State Machine Trigger pattern).
```bash
make exp-diamond
```

### Experiment 2: Basic CFG Mutation
Tests zero-shot generalization when compiler optimizations insert simple, non-structural dummy blocks.
```bash
make exp-mutation
```

### Experiment 3: Complex Loops Generalization
Evaluates the framework on a sorting algorithm, proving that IR2Vec embeddings allow the agent to generalize loop semantics across block ID shifts.
```bash
make exp-sorting
```

### Experiment 4: Extreme Compiler Mutations (Loop Peeling)
The ultimate test. The compiler drastically alters the topological path length to the loop (via loop peeling). Demonstrates why Flat PPO with Recurrent Memory (Feature Window) outperforms rigid Hierarchical RL.
```bash
make exp-smart
```

## 3. Reviewing Artifacts and Metrics

After running any experiment, the generated artifacts will be located in the `benchmarks/local/<experiment_name>/out/` directory.

- `metrics_*.json`: Contains the primary evaluations, notably the **Hot Path N-Gram Overlap** and KL Divergences.
- `viz_*.svg`: Visualizations mapping the generated traces onto the actual CFG structure.

To clean all generated artifacts and outputs:
```bash
make clean-output
```