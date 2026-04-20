# Agents and environment (`CFGWalkEnv`)

## MDP

`trace_synthesizer.env.cfg_walk_env.CFGWalkEnv` (Gymnasium) models one **function** of a `CfgProgram`:

- Observation includes the current BB id, a feature vector, and a **valid action mask** over outgoing edges (sorted by `target_id`).
- Action: successor index.
- Episode ends at a CFG block with no successors or when `max_steps` is reached (`truncated`).

## Baseline policy: `RandomPGOAgent`

`trace_synthesizer.agents.random_pgo.RandomPGOAgent` samples a legal action with probability proportional to **normalized PGO weights** on outgoing edges (`CfgProgram.successor_weights`). This is a **Markov** baseline on the CFG grammar: no data semantics, single-function view.

## CLI

```bash
poetry run python -m trace_synthesizer rollout-random \
  --cfg output/foo.cfg.json --func main \
  --episodes 50 --seed 0 --max-steps 5000 \
  --out-dir output/rollouts_foo
```

Outputs typically include `runs.jsonl`, `intra_traces.jsonl`, `summary.json`. Optional `--write-canonical-intra PATH` writes the first episode in the same schema as `export-intra-trace`.

## ML-ready contract

Keep **formats** (`bb_trace`, compressed JSON) and **metric hooks** fixed; swap the object implementing the agent protocol for trainable policies (see `trace_synthesizer.agents` and the Torch stub).

## Limits

- Intra / env: **one function** at a time; whole-program behavior is not modeled.
- PGO weights bias sampling but do not encode memory effects or calling-context sensitivity.

Russian: [same chapter](../ru/ml/04_agents_and_env.md).
