#!/usr/bin/env python3
"""Build FINDINGS.md from production validation artifacts under OUT_DIR."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("out_dir", type=Path, help="Same OUT_DIR as the experiment")
    args = p.parse_args()
    od = args.out_dir.resolve()
    manifest_path = od / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pgo = _read_jsonl(od / "results" / "pgo_runs.jsonl")
    dr = _read_jsonl(od / "results" / "dr_compress_runs.jsonl")
    m_rand = od / "results" / "metrics_random.json"
    m_lstm = od / "results" / "metrics_lstm.json"
    rand_txt = m_rand.read_text(encoding="utf-8") if m_rand.is_file() else "{}"
    lstm_txt = m_lstm.read_text(encoding="utf-8") if m_lstm.is_file() else "{}"
    lstm_train = od / "results" / "lstm_train.json"
    lstm_train_txt = (
        lstm_train.read_text(encoding="utf-8") if lstm_train.is_file() else "{}"
    )

    lines = [
        "# Production validation — findings",
        "",
        "Auto-generated from `manifest.json` and `results/*.json(l)`. Re-run the "
        "orchestrator to refresh; align narrative with `docs/Project_Proposal_Litvinov_Michael.pdf`.",
        "",
        "## Reproducibility",
        "",
        f"- **OUT_DIR:** `{od}`",
        f"- **Git HEAD:** `{manifest.get('git_head', '')}`",
        f"- **SEED / FUNC:** `{manifest.get('seed')}` / `{manifest.get('func')}`",
        f"- **Benchmark source:** `{manifest.get('benchmark_cpp')}`",
        "",
    ]
    ds = manifest.get("lstm_cross_dataset_jsonl") or manifest.get(
        "lstm_train_intra_jsonl"
    )
    if ds:
        lines.append(f"- **Global LSTM training JSONL (cfg+sequence per line):** `{ds}`")
    lines.extend(["", "## PGO profiling (10 runs)", ""])
    if pgo:
        times = [float(r.get("wall_seconds", 0)) for r in pgo]
        lines.append(
            f"- Runs: {len(pgo)}, wall seconds mean={sum(times)/len(times):.4f} min={min(times):.4f} max={max(times):.4f}"
        )
    else:
        lines.append("- (no pgo_runs.jsonl)")
    lines.extend(["", "## DynamoRIO + compress (full cycles)", ""])
    if dr:
        times = [float(r.get("wall_seconds", 0)) for r in dr]
        lines.append(
            f"- Runs: {len(dr)}, wall seconds mean={sum(times)/len(times):.4f} min={min(times):.4f} max={max(times):.4f}"
        )
    else:
        lines.append("- (no dr_compress_runs.jsonl)")
    lines.extend(
        [
            "",
            "## Metrics (reference = Dynamo run `reference_run_index`)",
            "",
            "### RandomPGO rollout (`results/metrics_random.json`)",
            "",
            "```json",
            rand_txt[:8000],
            "```",
            "",
            "### LSTM rollout (`results/metrics_lstm.json`)",
            "",
            "```json",
            lstm_txt[:8000],
            "```",
            "",
            "### LSTM training meta (`results/lstm_train.json`)",
            "",
            "```json",
            lstm_train_txt[:4000],
            "```",
            "",
            "## Interpretation (edit after review)",
            "",
            "- Compare pooled / per-metric values between Random and LSTM vs the same reference intra.",
            "- LSTM is the **global feature-window** model on `dataset/cross_<func>.jsonl` (back window + "
            "successor block features + whole-CFG summary); see `lstm_train.json`.",
            "- DR+compress timings quantify collection cost variance across identical binary, different argv.",
            "- PGO runs intentionally vary `argv` to spread profile coverage before merge.",
            "",
        ]
    )
    out = od / "FINDINGS.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
