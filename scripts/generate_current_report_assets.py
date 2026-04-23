#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt


def _metric_map(path: Path) -> dict[str, float]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {str(m["name"]): float(m["value"]) for m in raw.get("metrics", [])}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output" / "report_assets_current"
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline = _metric_map(root / "output" / "random_baseline" / "results" / "metrics_random.json")
    lstm = _metric_map(root / "output" / "lstm_eval" / "results" / "metrics_lstm.json")
    stats = json.loads((root / "output" / "stat_runs" / "stats_report.json").read_text(encoding="utf-8"))
    hpo = json.loads((root / "output" / "hparam_search" / "search_results.json").read_text(encoding="utf-8"))

    names = ["block_visit_kl", "edge_transition_kl", "hot_path_ngram_overlap"]
    x = list(range(len(names)))
    w = 0.36
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar([i - w / 2 for i in x], [baseline[n] for n in names], w, label="Random-PGO")
    ax.bar([i + w / 2 for i in x], [lstm[n] for n in names], w, label="LSTM")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=10)
    ax.set_title("Baseline vs LSTM metrics")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "baseline_vs_lstm_metrics.png", dpi=160)
    plt.close(fig)

    agg = stats["aggregate"]
    vals = [agg[n]["mean"] for n in names]
    errs = [agg[n]["ci95_half_width"] for n in names]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(names, vals, yerr=errs, capsize=6, color="#4C78A8")
    ax.set_title("LSTM pooled metrics with 95% CI")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "lstm_pooled_ci95.png", dpi=160)
    plt.close(fig)

    runs = hpo.get("runs", [])
    labels = []
    objectives = []
    for r in runs:
        cfg = r["config"]
        labels.append(f"wb{cfg['window_back']}_lr{cfg['lr']}")
        objectives.append(float(r["mean_objective"]))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(labels, objectives, color="#F28E2B")
    ax.set_title("Hyperparameter search objective (lower is better)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "hparam_objective.png", dpi=160)
    plt.close(fig)

    summary = {
        "assets_dir": str(out_dir),
        "baseline_metrics": baseline,
        "lstm_metrics": lstm,
        "lstm_ci95": {
            n: {
                "mean": agg[n]["mean"],
                "ci95_half_width": agg[n]["ci95_half_width"],
                "ci95": agg[n]["ci95"],
            }
            for n in names
        },
        "best_hparams": hpo.get("best", {}),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"assets_dir": str(out_dir), "summary": str(out_dir / "summary.json")}, indent=2))


if __name__ == "__main__":
    main()
