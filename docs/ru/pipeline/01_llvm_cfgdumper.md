# LLVM CFGDumper (Machine IR → JSON)

## Назначение

`CFGDumper.so` — это **MachineFunctionPass**, регистрируемый для `llc` через `RegisterTargetPassConfigCallback`. Проход вставляется **сразу после** `UnpackMachineBundles` в target pass pipeline:

```173:177:src/CFGDumper/CFGDumper.cpp
static llvm::RegisterTargetPassConfigCallback
    Y([](const TargetMachine &TM, llvm::legacy::PassManagerBase &PM,
         TargetPassConfig *TPC) {
      TPC->insertPass(&llvm::UnpackMachineBundlesID, new CFGJsonDumper());
    });
```

Это **поздний Machine IR / codegen**; порядок относительно других проходов (включая `AsmPrinter`) определяется LLVM upstream и может меняться. Общая картина пайплайна: [LLVM Code Generator](https://llvm.org/docs/CodeGenerator.html).

## Артефакт

Плагин пишет **JSON CFG** (блоки, преемники, поля `prob` при PGO). Сборка `.s`/объекта выполняется `llc` после проходов.

## Пример вызова

Фактические флаги см. в `scripts/generate_cfg.sh` и `scripts/full_pipeline.sh`. После `make build` плагин: `build/src/CFGDumper/CFGDumper.so`.

## См. также

- [02_dynamorio_instrtracer.md](02_dynamorio_instrtracer.md)
- [../formats/03_trace_and_program_interface.md](../formats/03_trace_and_program_interface.md)

English: [same chapter](../en/pipeline/01_llvm_cfgdumper.md).
