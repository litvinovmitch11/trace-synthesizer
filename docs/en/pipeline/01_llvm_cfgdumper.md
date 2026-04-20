# LLVM CFGDumper (Machine IR → JSON)

## Role

`CFGDumper.so` is a **MachineFunctionPass** registered for `llc` via `RegisterTargetPassConfigCallback`. The pass is inserted **immediately after** `UnpackMachineBundles` in the target pass pipeline:

```173:177:src/CFGDumper/CFGDumper.cpp
static llvm::RegisterTargetPassConfigCallback
    Y([](const TargetMachine &TM, llvm::legacy::PassManagerBase &PM,
         TargetPassConfig *TPC) {
      TPC->insertPass(&llvm::UnpackMachineBundlesID, new CFGJsonDumper());
    });
```

That is **late Machine IR / codegen**, not a claim about a fixed position relative to `AsmPrinter`; upstream may reorder other passes. For background on codegen pass structure see the [LLVM Code Generator documentation](https://llvm.org/docs/CodeGenerator.html).

## Artifact

`llc` emits assembly/object after the pass pipeline; the dumper writes **JSON CFG** (blocks, successors, `prob` when using PGO) to the path configured for the pass.

## Typical `llc` usage (from project scripts)

Your build scripts pass `-load` / plugin flags and output stem. After `make build`, the shared object is under `build/src/CFGDumper/CFGDumper.so`.

```bash
# Example only — exact flags live in scripts/generate_cfg.sh and full_pipeline.sh
"$LLVM_DIR/bin/llc" -load build/src/CFGDumper/CFGDumper.so ...
```

## Related docs

- [02_dynamorio_instrtracer.md](02_dynamorio_instrtracer.md)
- [../formats/03_trace_and_program_interface.md](../formats/03_trace_and_program_interface.md)

Russian: [same chapter](../ru/pipeline/01_llvm_cfgdumper.md).
