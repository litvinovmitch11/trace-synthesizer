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

### Problem: Basic Block Boundary Mismatch
The main technical challenge currently is that **statically determined basic block boundaries don't always align with actual execution patterns**, leading to:

1. **False edges** in the CFG visualization
2. **Inaccurate transition counts** between blocks
3. **Difficulty correlating** static analysis with dynamic behavior

This occurs because:
- Compiler optimizations can create complex control flow
- Indirect jumps/branches are hard to resolve statically
- Library calls and system interrupts create non-deterministic patterns

### Future Direction: ML-based Trace Synthesis
The ultimate goal is to develop ML/RL models that can:
- **Learn execution patterns** from real traces
- **Synthesize realistic traces** for unseen programs
- **Predict likely execution paths** for security analysis
- **Generate test inputs** that maximize code coverage

Planned ML applications:
- **Sequence models** (LSTM/Transformers) for trace generation
- **Reinforcement learning** for coverage-guided fuzzing
- **Graph neural networks** for CFG-aware prediction
- **Few-shot learning** to generalize across binaries

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
