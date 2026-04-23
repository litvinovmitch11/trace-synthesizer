#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt


def load_metric_map(path: Path) -> dict[str, float]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, float] = {}
    for m in raw.get("metrics", []):
        out[str(m["name"])] = float(m["value"])
    return out


def parse_stage_wall_times(terminal_log: str) -> dict[str, float]:
    stages = ["random-baseline", "dataset-cbench", "train-lstm", "lstm-eval"]
    vals = re.findall(r"^real\s+([0-9]+(?:\.[0-9]+)?)$", terminal_log, flags=re.M)
    if len(vals) < len(stages) + 1:
        return {}
    # first `real` belongs to clean-output
    vals = vals[1 : 1 + len(stages)]
    return {stage: float(v) for stage, v in zip(stages, vals)}


def parse_dr_times(terminal_log: str, marker: str) -> list[float]:
    if marker not in terminal_log:
        return []
    chunk = terminal_log.split(marker, 1)[1]
    next_marker_idx = chunk.find("[5/5]")
    if next_marker_idx >= 0:
        chunk = chunk[:next_marker_idx]
    return [
        float(x)
        for x in re.findall(r"Run\s+\d+\s+time:\s+([0-9]+(?:\.[0-9]+)?)s", chunk)
    ]


def make_metrics_plot(
    baseline: dict[str, float], lstm: dict[str, float], out_path: Path
) -> None:
    names = ["block_visit_kl", "edge_transition_kl", "hot_path_ngram_overlap"]
    x = range(len(names))
    width = 0.35
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar([i - width / 2 for i in x], [baseline[n] for n in names], width, label="Random-PGO baseline")
    ax.bar([i + width / 2 for i in x], [lstm[n] for n in names], width, label="LSTM")
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, rotation=15)
    ax.set_ylabel("metric value")
    ax.set_title("Quality metrics: baseline vs LSTM")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def make_stage_time_plot(stage_times: dict[str, float], out_path: Path) -> None:
    labels = list(stage_times.keys())
    values = [stage_times[k] for k in labels]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(labels, values, color="#4C78A8")
    ax.set_ylabel("seconds")
    ax.set_title("Wall time by stage")
    ax.grid(axis="y", alpha=0.3)
    for i, v in enumerate(values):
        ax.text(i, v, f"{v:.1f}s", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def make_dr_time_plot(base: list[float], lstm: list[float], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(range(len(base)), base, marker="o", label="baseline DR runs")
    ax.plot(range(len(lstm)), lstm, marker="o", label="lstm-eval DR runs")
    ax.set_xlabel("run index")
    ax.set_ylabel("seconds")
    ax.set_title("DynamoRIO run times (10 runs)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def make_length_plot(mean_random: float, mean_lstm: float, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 4.3))
    labels = ["Random-PGO", "LSTM"]
    vals = [mean_random, mean_lstm]
    ax.bar(labels, vals, color=["#59A14F", "#E15759"])
    ax.set_ylabel("mean rollout length")
    ax.set_title("Episode length collapse in LSTM rollout")
    ax.grid(axis="y", alpha=0.3)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.1f}", ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def make_speedup_plot(
    random_speedup: float, lstm_speedup: float, out_path: Path
) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 4.3))
    labels = ["Random-PGO (1000)", "LSTM (1000)"]
    vals = [random_speedup, lstm_speedup]
    ax.bar(labels, vals, color=["#4E79A7", "#F28E2B"])
    ax.set_ylabel("x faster than estimated DynamoRIO")
    ax.set_title("Synthetic generation speedup (1000 traces)")
    ax.grid(axis="y", alpha=0.3)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.2f}x", ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_assets = root / "output" / "report_assets"
    out_assets.mkdir(parents=True, exist_ok=True)

    baseline_metrics = load_metric_map(
        root / "output" / "random_baseline" / "results" / "metrics_random.json"
    )
    lstm_metrics = load_metric_map(
        root / "output" / "lstm_eval" / "results" / "metrics_lstm.json"
    )

    random_summary = json.loads(
        (root / "output" / "random_baseline" / "rollouts_random" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    lstm_summary = json.loads(
        (root / "output" / "lstm_eval" / "rollouts_lstm" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    train_report = json.loads(
        (root / "output" / "train_lstm" / "report.json").read_text(encoding="utf-8")
    )
    ds_index = json.loads(
        (root / "output" / "dataset_cbench" / "dataset" / "dataset_index.json").read_text(
            encoding="utf-8"
        )
    )

    terminal_path = Path(
        "/home/mitchell/.cursor/projects/home-mitchell-dev-llvm-trace-synthesizer/terminals/239784.txt"
    )
    terminal_log = terminal_path.read_text(encoding="utf-8")
    stage_times = parse_stage_wall_times(terminal_log)
    dr_times_base = parse_dr_times(terminal_log, "Random Baseline: benchmark_complex")
    dr_times_lstm = parse_dr_times(terminal_log, "LSTM Evaluation: benchmark_complex")

    make_metrics_plot(baseline_metrics, lstm_metrics, out_assets / "metrics_baseline_vs_lstm.png")
    if stage_times:
        make_stage_time_plot(stage_times, out_assets / "stage_wall_time.png")
    if dr_times_base and dr_times_lstm:
        make_dr_time_plot(dr_times_base, dr_times_lstm, out_assets / "dr_run_times.png")
    make_length_plot(
        float(random_summary.get("mean_length", 0.0)),
        float(lstm_summary.get("mean_length", 0.0)),
        out_assets / "rollout_mean_length.png",
    )

    random_speed_1000 = json.loads(
        (root / "output" / "report_assets" / "random_speed_1000.json").read_text(
            encoding="utf-8"
        )
    )["synthetic_benchmark"]["seconds"]
    lstm_terminal_text = Path(
        "/home/mitchell/.cursor/projects/home-mitchell-dev-llvm-trace-synthesizer/terminals/171286.txt"
    ).read_text(encoding="utf-8")
    m = re.search(r"^real\s+([0-9]+(?:\.[0-9]+)?)$", lstm_terminal_text, flags=re.M)
    lstm_speed_1000 = float(m.group(1)) if m else None
    dr_random_avg = sum(dr_times_base) / len(dr_times_base)
    dr_lstm_avg = sum(dr_times_lstm) / len(dr_times_lstm)
    speed_cmp = {
        "random_1000": {
            "synthetic_seconds": float(random_speed_1000),
            "estimated_dynamo_seconds": float(dr_random_avg * 1000.0),
            "synthetic_vs_dynamo_speedup": float((dr_random_avg * 1000.0) / random_speed_1000),
        }
    }
    if lstm_speed_1000 is not None:
        speed_cmp["lstm_1000"] = {
            "synthetic_seconds": float(lstm_speed_1000),
            "estimated_dynamo_seconds": float(dr_lstm_avg * 1000.0),
            "synthetic_vs_dynamo_speedup": float((dr_lstm_avg * 1000.0) / lstm_speed_1000),
        }
        make_speedup_plot(
            speed_cmp["random_1000"]["synthetic_vs_dynamo_speedup"],
            speed_cmp["lstm_1000"]["synthetic_vs_dynamo_speedup"],
            out_assets / "speedup_1000.png",
        )
    (out_assets / "speed_1000_comparison.json").write_text(
        json.dumps(speed_cmp, indent=2), encoding="utf-8"
    )

    report = {
        "baseline_metrics": baseline_metrics,
        "lstm_metrics": lstm_metrics,
        "dataset": {
            "n_programs": len(ds_index.get("programs", [])),
            "n_traces_total": int(sum(int(p.get("n_traces", 0)) for p in ds_index.get("programs", []))),
            "programs": [
                {
                    "id": p.get("id"),
                    "func": p.get("func"),
                    "n_traces": p.get("n_traces"),
                }
                for p in ds_index.get("programs", [])
            ],
        },
        "train_report": train_report,
        "rollout_summary": {
            "random": random_summary,
            "lstm": lstm_summary,
        },
        "timings": {
            "stage_wall_time_sec": stage_times,
            "dynamorio_random_sec_runs": dr_times_base,
            "dynamorio_lstm_eval_sec_runs": dr_times_lstm,
            "speed_1000_comparison": speed_cmp,
        },
        "assets_dir": str(out_assets),
    }
    (out_assets / "experiment_summary.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps({"assets_dir": str(out_assets), "summary": str(out_assets / "experiment_summary.json")}, indent=2))


if __name__ == "__main__":
    main()
