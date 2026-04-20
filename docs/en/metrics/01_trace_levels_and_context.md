# Traces, synthetic generation, and comparison metrics (part 1)

**Purpose.** This note fixes terminology and data levels used in TraceSynthesizer when comparing *real* DynamoRIO traces (aligned with the LLVM CFG) and *synthetic* traces drawn from the same CFG grammar and PGO statistics.

**Link to the project proposal.** Metric formalization follows section *III.D Evaluation Metrics* (KL-style distribution comparison, hot-path overlap, throughput of trace generation).

Russian version: [../ru/metrics/01_trace_levels_and_context.md](../ru/metrics/01_trace_levels_and_context.md).

---

## 1. Why traces matter for ML on compilers

Compiler ML often needs **observations of program behavior**. A CFG describes *possible* paths; a **trace** records the *actual* sequence of events at run time and approximates the “true” behavior distribution for a workload.

Full dynamic collection (DynamoRIO, etc.) is expensive. **Trace synthesis** builds plausible sequences without repeating full collection while staying tied to the static CFG and PGO statistics.

---

## 2. Trace levels in this repository

### 2.1 Raw instruction stream (RVA)

The DynamoRIO client `InstrTracer` logs **relative virtual addresses (RVA)** of each executed instruction in the module. At this level:

- volume is large;
- DR basic-block boundaries differ from LLVM Machine IR blocks;
- mapping to the compiler needs `.llvm_bb_addr_map` (exported to `_bb_map.txt`).

Metrics do **not** compare at the RVA level; RVAs feed compression only.

### 2.2 Compressed interprocedural BB sequence

`trace_synthesizer.io.compress_pipeline` maps RVAs to **(function name, LLVM BB id)** with:

1. **Run-length merge** of identical consecutive `(func, bb)` pairs (we care about transitions, not instruction ticks inside one block).
2. **CFG validation** for intra-procedural edges; inter-procedural jumps are counted separately.

Output is a JSON array of `{"func": "...", "bb": <int>}` — a **global** trace.

### 2.3 Intra-procedural trace for one function

For RL and single-function generators, filter the global trace by `func`, then merge consecutive duplicates again.

Canonical schema lives in `trace_synthesizer.io.intra_trace`: `schema_version`, `function_name`, `source` (`bb_trace`), optional `episode`, and `sequence` of `{func, bb}` events.

### 2.4 Synthetic trace (PGO random walk)

`CFGWalkEnv` (Gymnasium) defines an MDP: state = current block; action = outgoing edge index in deterministic successor order; `RandomPGOAgent` samples edges proportional to normalized PGO weights. Episodes end at a CFG sink or at `max_steps`.

Each episode yields one intra trace; many episodes define an **empirical trace distribution** for the generator.

---

## 3. Static CFG and PGO as grammar and prior

The LLVM-extracted CFG is the **grammar** of allowed intra-procedural transitions; synthetic traces from the env are valid by construction.

Edge `prob` fields reflect **relative profiling frequency**. They bias random walks toward hot edges but **do not** guarantee agreement with a Dynamo trace on the same binary (different runs, inputs, and dropped inter-procedural context).

---

Next: [02_metric_definitions.md](02_metric_definitions.md), [03_cli_scenarios_appendices.md](03_cli_scenarios_appendices.md).
