# End-to-End PGO & Trace Pipeline Documentation

This document provides a comprehensive description of the architecture, components, and usage process of the pipeline for collecting Profile-Guided Optimization (PGO) statistics, extracting the CFG, overlaying dynamic DynamoRIO traces, and visualization.

## 1. Overview

For machine learning tasks on compilers (e.g., RL agents), we require:
1. **Environment (Grammar)** — Control Flow Graph (CFG), extracted from LLVM at the very last stage before machine code generation (Machine IR).
2. **PGO Statistics** — Transition probabilities based on real execution profiling, so the agent understands the hot paths.
3. **Ground Truth Data** — Real execution traces (`traces`) that perfectly (100%) match the static graph (CFG), for training and validating the agent.

---

## 2. System Components

### 2.1 CFGDumper (LLVM Plugin)
`CFGDumper.so` is an LLVM plugin that operates at the final stage of compilation. It extracts the control flow graph in JSON format.
- **LTO (Link-Time Optimization)**: Used to obtain a Whole-Program CFG.
- **`.llvm_bb_addr_map`**: A special section in the binary file containing the mapping of basic block addresses to their internal `ID`s. This is critical for linking the dynamic trace with the static graph.
- **Extracted Metrics**: Number of instructions (`instr_count`), transition probabilities (`prob`), presence of calls (`has_call`, `call_target`), and whether the block is an entry point (`is_entry`).

### 2.2 InstrTracer (DynamoRIO Client)
`InstrTracer.so` is a DynamoRIO client that logs the execution of the program.
- Due to the difference in how basic blocks are defined between LLVM and DynamoRIO, the plugin logs **every single instruction**.
- It logs **Relative Virtual Addresses (RVAs)** from the base load address of the module, not absolute addresses.
- For high performance, a 64KB ring buffer (`trace_buffer`) is used.

---

## 3. Trace Mapping Architecture

The main problem was that DynamoRIO and LLVM define basic block boundaries differently. The solution architecture:
1. `InstrTracer` writes the raw RVAs of each executed instruction to `trace.bin`.
2. The `.llvm_bb_addr_map` (LLVM mapping) is extracted from the binary into a `_bb_map.txt` file.
3. The script `tools_py/trace_pipeline.py` reads the RVAs from `trace.bin`, performs a binary search to find the corresponding block in `_bb_map.txt`, and converts the RVA into a tuple `(Function Name, BB_ID)`.
4. The sequence is compressed (duplicate BB_IDs are removed) and **validated** (every transition is checked for existence in the `main.cfg.json` graph).
5. The perfect Ground Truth trace is saved to `compressed_trace.json`.

---

## 4. Execution Pipeline (6 Stages)

The pipeline is integrated into the `scripts/full_pipeline.sh` script and can be run via the `Makefile`.

1. **Profile Generation Build**: Source code is compiled with `-fprofile-instr-generate` and `-fcoverage-mapping` flags to create a profiling binary.
2. **Profile Collection & Merge**: The instrumented binary is executed, producing `default.profraw`, which is then merged into `code.profdata`.
3. **CFG Generation Build (with PGO)**: LTO compilation with `-fprofile-instr-use=code.profdata`. The `CFGDumper` plugin extracts the CFG into `cfg.json`, embedding real PGO probabilities in the `prob` field. The `.llvm_bb_addr_map` is also generated.
4. **DynamoRIO Trace Collection**: The final binary is executed under DynamoRIO with `InstrTracer`, generating `trace.bin`.
5. **Trace Compression & Validation**: `trace_pipeline.py` converts the raw RVA trace into a compressed sequence of BB_IDs, validates it, and saves it to `compressed_trace.json`.
6. **Visualization**: The `tools_py/visualize_cfg.py` script generates SVG graph images highlighting PGO paths and trace overlays.

---

## 5. Visualization

The visualization script (`visualize_cfg.py`) uses `graphviz` and `cxxfilt` (for C++ name demangling).
- **PGO Graph (`*_main_cfg_pgo.svg`)**: 
  - Edges are colored based on probability: Red (`prob >= 0.8`), Blue (`0.2 <= prob < 0.8`), Black (`prob < 0.2`).
  - Entry and exit nodes are highlighted with thick green and purple borders, respectively.
  - External calls (`Call`) are highlighted in bold dark red text.
- **Trace Graph (`*_main_cfg_pgo_trace.svg`)**: 
  - The `compressed_trace.json` is overlaid on the graph. 
  - Visited blocks are filled with a green gradient (based on the number of `Hits`). 
  - Visited edges are highlighted in green.

---

## 6. Limitations and Known Behaviors

- **Interprocedural Transitions (Call/Return)**: The validation script marks transitions between different functions as "Interprocedural" and does not require them to exist as explicit edges within the function-level JSON graph.
- **Comprehensive (Global) Trace**: The `compressed_trace.json` file contains a single, flat, comprehensive array of basic blocks in the exact order the processor visited them. This array includes jumping into functions and returning from them, providing an ideal "Ground Truth" execution labyrinth for the entire program.
- **Recursive Calls**: The validation pipeline correctly identifies and handles recursive calls (jumping from a call block to the entry block of the same function) and recursive returns (jumping from an exit block back into the function).
- **External Libraries / Exceptions**: If the program jumps into an uninstrumented `libc` (or throws a C++ exception) and returns, the trace within our function is not broken. DynamoRIO simply logs the last instruction of the call block and the first instruction of the return block.
- **PGO Accuracy**: PGO statistics are only collected for the paths that were actually executed during the profiling phase.
