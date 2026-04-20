# External dependencies

## ctuning-programs

[cTuning programs](https://github.com/ctuning/ctuning-programs) подключается как **git submodule** в `external/ctuning-programs/`.

Инициализация после клона:

```bash
git submodule update --init --recursive external/ctuning-programs
```

или из корня репозитория:

```bash
make ctuning-bootstrap
```

Драйвер `ctuning-rollout` читает `benchmarks/ctuning_curated.json` и резолвит пути относительно `external/ctuning-programs`.
