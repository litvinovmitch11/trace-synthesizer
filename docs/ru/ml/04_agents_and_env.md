# Агенты и среда (`CFGWalkEnv`)

## MDP

`trace_synthesizer.env.cfg_walk_env.CFGWalkEnv` (Gymnasium) задаёт обход **одной функции** `CfgProgram`:

- Наблюдение: текущий BB, признаки, **маска допустимых действий** по исходящим рёбрам (порядок по `target_id`).
- Действие: индекс преемника.
- Эпизод завершается в терминальном блоке без преемников или по `max_steps` (усечение).

## Бейзлайн: `RandomPGOAgent`

`trace_synthesizer.agents.random_pgo.RandomPGOAgent` выбирает исходящее ребро с вероятностью, пропорциональной **нормализованным весам PGO** (`CfgProgram.successor_weights`). Это **марковский** бейзлайн на грамматике CFG: без семантики данных, внутри одной функции.

## CLI

```bash
poetry run python -m trace_synthesizer rollout-random \
  --cfg output/foo.cfg.json --func main \
  --episodes 50 --seed 0 --max-steps 5000 \
  --out-dir output/rollouts_foo
```

Артефакты: `runs.jsonl`, `intra_traces.jsonl`, `summary.json`. Флаг `--write-canonical-intra PATH` — первый эпизод в том же формате, что `export-intra-trace`.

## Контракт «ML-ready»

Форматы (`bb_trace`, compressed JSON) и хуки метрик остаются стабильными; меняется реализация агента за тем же протоколом (см. `trace_synthesizer.agents`, заготовка Torch).

## Ограничения

- Одна функция; whole-program не моделируется.
- Веса PGO — смещение сэмплирования, не полная семантика программы.

English: [same chapter](../en/ml/04_agents_and_env.md).
