# Baseline analysis (notebook only)

Exploration of **Dynamo (real) vs RandomPGO synthetic** rollouts for a `output/ctuning_<id>` directory.

All plotting and metric logic live in **`baseline_ctuning.ipynb`** (no separate Python package or `analyze-baseline` CLI).

## Setup

```bash
poetry install --with dev
```

Pick the interpreter **`.venv/bin/python`** (or `poetry env info --executable`) as the Jupyter kernel so it matches `poetry install`. See the troubleshooting section in the first notebook cells / older notes below if `matplotlib` is missing.

## Notebook

Open `baseline_ctuning.ipynb`, set `CTUNING_DIR` to your rollout folder. Expected layout:

- `ctuning_<id>/<id>.compressed_trace.json`
- `ctuning_<id>/rollouts_random/intra_traces.jsonl`
- `ctuning_<id>/rollouts_random/runs.jsonl`

The notebook plots:

- Path lengths: synthetic histogram vs **one real** Dynamo length (vertical line); optional `runs.jsonl` lengths.
- ECDF of synthetic lengths vs Dynamo length.
- Termination counts from `runs.jsonl`.
- **Metrics:** for each built-in metric, histogram of per-episode scores vs vertical lines **Dynamo vs Dynamo** (self-baseline) and **pooled synthetic** (full JSONL as one candidate).
- Normalized heatmap episode × metric (shape comparison only).
- Boxplot + jittered points, and episode-index traces.
- `pandas` summary table when dev deps are installed.

## Troubleshooting: “No module named matplotlib”

`!which python` only shows **which** interpreter runs the notebook. `poetry install` targets Poetry’s env (this repo uses **`poetry.toml` → `virtualenvs.in-project = true`** → `.venv/`).

If you use a separate `./venv`, install into it explicitly, e.g. `./venv/bin/python -m pip install matplotlib jupyter ipykernel pandas`, or switch the kernel to `.venv`.

After changing `poetry.toml`, you may need once: `poetry env remove --all && poetry install --with dev`.
