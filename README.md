# Trace-Synthesizer - Framework for Execution Trace Analysis and Synthesis

A research framework for collecting, analyzing, and eventually synthesizing execution traces using machine learning.

## Overview

This project aims to develop a system for automatically synthesizing realistic program execution traces using ML/RL techniques. Currently, it provides foundational tools for:

- **Real trace collection** via DynamoRIO instrumentation
- **Static CFG analysis** using radare2
- **Trace visualization** with interactive CFG graphs

## Key Components

### 1. Trace Collection (`src/tracer/tracer.cpp`)
DynamoRIO-based instrumentation client that:
- Logs all executed instruction addresses within the main module
- Filters to the `.text` section boundaries
- Outputs trace files with execution frequency statistics
- Thread-safe logging with mutex protection

### 2. Visualization Engine (`tools_py/visualize_cfg.py`)
Production-ready analysis tool that:
- Parses binary files using radare2 for CFG extraction
- Correlates dynamic traces with static control flow graphs
- Generates interactive PNG visualizations with:
  - Color-coded basic blocks (visited/unvisited)
  - Edge weights based on transition frequency
  - Disassembly context for each basic block
  - Coverage statistics and hotspot analysis

## Current Limitations & Research Focus

### 1. Basic Block Boundary Resolution (Current Priority)
The primary technical hurdle is accurately determining basic block boundaries that align with actual execution patterns. This involves:

- **Improving static analysis** to better identify BB start/end points
- **Dynamic validation** of BB boundaries through instrumentation
- **Hybrid approaches** combining static analysis with runtime feedback
- **Addressing compiler optimizations** that create complex control flow

**Expected outcome**: Cleaner CFGs without false edges, enabling more accurate trace analysis.

### 2. Interactive Trace Walker (Next Milestone)
We plan to develop an interactive utility that allows exploration of execution paths:

```
[Trace Walker Concept]
Current Block: 0x400510 (add rsp, 0x28)
Possible Next Blocks:
  1) 0x400515 (jump if condition) - 75% probability
  2) 0x400530 (fall-through) - 25% probability
  3) Manual jump to: ________
```

Features:
- **Trace playback**: Step through recorded execution traces
- **Interactive branching**: Manually choose different paths at branch points
- **Probability guidance**: Show likelihood of each path based on profiling data
- **State tracking**: Maintain register/memory state during exploration

This will serve as both a debugging tool and a foundation for automated trace generation.

## Research Roadmap

### Phase 1: Statistical Trace Generation
**Goal**: Create basic probabilistic models for trace generation

**Approach**:
- **Frequency-based models**: Use collected trace data to compute transition probabilities
- **Context-aware prediction**: Consider recent execution history (Markov models)
- **Path probability estimation**: Calculate likelihood of reaching specific program points
- **Coverage-directed generation**: Bias generation toward uncovered code regions

**Methods**:
- n-gram models over basic block sequences
- Hidden Markov Models for path prediction
- Bayesian networks for branch prediction

### Phase 2: Machine Learning Approaches
**Goal**: Leverage ML to improve trace generation quality

**Potential ML Applications**:

#### A. Sequence Models for Trace Generation
- **LSTMs/GRUs**: Model temporal dependencies in execution sequences
- **Transformers**: Capture long-range dependencies across program execution
- **Attention mechanisms**: Focus on relevant program features for prediction

#### B. Graph Neural Networks for CFG-aware Prediction
- **GNNs over CFGs**: Encode structural information of control flow
- **Message passing**: Propagate execution context through the CFG
- **Node embeddings**: Learn representations of basic blocks
- **Edge prediction**: Directly predict likely transitions between blocks

#### C. Few-shot Learning for Generalization
- **Meta-learning**: Learn to predict traces for unseen programs quickly
- **Transfer learning**: Apply knowledge from analyzed binaries to new ones
- **Domain adaptation**: Handle differences in compiler optimizations, architectures

### Phase 3: Reinforcement Learning for Intelligent Exploration
**Goal**: Develop RL agents that learn optimal exploration strategies

**Why RL is particularly suitable**:
1. **Sequential decision-making**: Choosing next BB is inherently sequential
2. **Reward engineering**: Can design rewards for coverage, novelty, bug finding
3. **Exploration-exploitation**: RL naturally balances trying new paths vs. known good ones
4. **Adaptive learning**: Agents can improve strategies over time

**RL Formulation**:
```
State: Current execution context (PC, registers, recent BB history)
Action: Choose next basic block to execute
Reward: 
  + High: Discovering new uncovered code
  + Medium: Following realistic execution patterns
  + Low: Revisiting frequently covered code
  - Negative: Crashes, infinite loops
```

**Potential RL Approaches**:
- **DQN/DDQN**: Learn Q-values for BB transitions
- **Policy Gradient methods**: Directly learn transition policies
- **Actor-Critic**: Combine value estimation with policy learning
- **Multi-agent RL**: Multiple agents exploring different program paths

**Integration with ML models**:
- Use GNNs as state representation for RL
- Pre-train with supervised learning on collected traces
- Fine-tune with RL for specific objectives (e.g., find vulnerabilities)

## Quick Start

### Prerequisites
```bash
# Install system dependencies
sudo apt-get install cmake clang-21 clang-tidy-21 clang-format-21
pip install poetry

# Install Python dependencies
make install
```

### Basic Usage
```bash
# Build everything and generate traces
make all

# Or run individual steps:
make configure        # Configure CMake project
make build            # Build C++ client
make build-dummy      # Compile test programs
make get-traces       # Collect execution traces
make generate-cfgs    # Generate visualizations
```

## Example Output

The visualization shows:
- **Green blocks**: Executed during trace
- **Gray blocks**: Not executed
- **Edge thickness**: Transition frequency
- **Orange edges**: Transitions not in static CFG (boundary mismatch)
- **Statistics**: Coverage percentage, hottest blocks, common transitions

## Acknowledgments

- **DynamoRIO** for dynamic binary instrumentation
- **radare2** for static binary analysis
- **Graphviz** for visualization
- **LLVM/Clang** toolchain
