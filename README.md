# Trace Synthesizer (End-to-End PGO & Trace Pipeline)

A research pipeline integrating LLVM Machine IR control-flow graphs with DynamoRIO execution traces to create 100% accurate ground-truth datasets for ML on compilers (e.g., RL agents).

Read the full documentation:
- [Документация (Русский)](docs/Documentation_RU.md)
- [Documentation (English)](docs/Documentation_EN.md)

## Prerequisites

- **LLVM**: Compiled with necessary dependencies (tested with LLVM 21).
- **DynamoRIO**: Automatically fetched and built via CMake.
- **Python 3.12+** with `poetry`.
- **Make & CMake**.

## Setup & Build

1. Install Python dependencies:
   ```bash
   poetry install
   ```

2. Configure and build the project:
   ```bash
   make configure
   make build
   ```

## Available Make Commands

### 1. End-to-End Pipeline
The main entry point. Automatically builds the profile (PGO), collects execution traces via DynamoRIO, generates the CFG via the `CFGDumper` LLVM plugin, compresses the trace, and visualizes the results (SVG) with trace overlays and PGO hot-paths.

Run on all examples:
```bash
make e2e-pipeline
```

Run on a specific file with arguments (e.g., passing arguments to the target binary):
```bash
make e2e-pipeline FILE=examples/complex.cpp ARGS="process"
```

*Note: All generated artifacts (graphs, traces, `.bc`, `.s` files) are placed in the `output/` directory.*

### 2. Run Specific Components

Generate CFGs for all examples (without trace collection):
```bash
make cfg-examples
```

Generate CFGs, run DynamoRIO tracing, and compress/validate the traces for all examples:
```bash
make trace-examples
```

### 3. Cleanup

Clean all generated artifacts from the `output/` directory:
```bash
make clean-output
```

Clean the CMake build directory (keeps DynamoRIO intact):
```bash
make clean
```

### 4. Code Quality & Formatting

Format C++ code (`clang-format`):
```bash
make format
```

Run C++ static analysis (`clang-tidy`):
```bash
make tidy
```

Format Python code (`black` and `isort` via Poetry):
```bash
make format-py
```
