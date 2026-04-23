#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True)


def _load_metric(path: Path, name: str) -> float:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for m in raw.get("metrics", []):
        if str(m.get("name")) == name:
            return float(m["value"])
    raise KeyError(name)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--dataset-jsonl", type=Path, default=Path("output/dataset_cbench/dataset/cross.train.jsonl"))
    p.add_argument("--cfg", type=Path, default=Path("output/lstm_eval/benchmark_complex.cfg.json"))
    p.add_argument("--func", default="main")
    p.add_argument("--out-dir", type=Path, default=Path("output/hparam_search"))
    p.add_argument("--window-backs", default="8,12")
    p.add_argument("--lrs", default="0.02,0.01,0.005")
    p.add_argument("--epochs", default="20,40")
    p.add_argument("--lstm-hiddens", default="64,128")
    p.add_argument("--seeds", default="17,23")
    p.add_argument("--episodes", type=int, default=24)
    p.add_argument("--max-steps", type=int, default=8000)
    p.add_argument("--temperature", type=float, default=1.2)
    args = p.parse_args()

    root = args.root.resolve()
    out_dir = (root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset = (root / args.dataset_jsonl).resolve()
    cfg = (root / args.cfg).resolve()
    func = str(args.func)

    windows = [int(x) for x in str(args.window_backs).split(",") if x.strip()]
    lrs = [float(x) for x in str(args.lrs).split(",") if x.strip()]
    epochs = [int(x) for x in str(args.epochs).split(",") if x.strip()]
    hiddens = [int(x) for x in str(args.lstm_hiddens).split(",") if x.strip()]
    seeds = [int(x) for x in str(args.seeds).split(",") if x.strip()]

    results: list[dict] = []
    run_idx = 0
    for wb, lr, ep, hid in itertools.product(windows, lrs, epochs, hiddens):
        cfg_tag = f"wb{wb}_lr{lr}_ep{ep}_hid{hid}"
        seed_scores = []
        for seed in seeds:
            run_idx += 1
            stem = out_dir / f"{cfg_tag}_seed{seed}" / "model"
            stem.parent.mkdir(parents=True, exist_ok=True)
            _run(
                [
                    "poetry",
                    "run",
                    "python3",
                    "scripts/train_feature_window_lstm.py",
                    "--dataset-jsonl",
                    str(dataset),
                    "--out-stem",
                    str(stem),
                    "--window-back",
                    str(wb),
                    "--epochs",
                    str(ep),
                    "--lr",
                    str(lr),
                    "--seed",
                    str(seed),
                    "--lstm-hidden",
                    str(hid),
                ],
                cwd=root,
            )
            roll_dir = stem.parent / "roll"
            _run(
                [
                    "poetry",
                    "run",
                    "python3",
                    "-m",
                    "trace_synthesizer",
                    "rollout-lstm",
                    "--cfg",
                    str(cfg),
                    "--func",
                    func,
                    "--episodes",
                    str(int(args.episodes)),
                    "--seed",
                    str(seed),
                    "--max-steps",
                    str(int(args.max_steps)),
                    "--out-dir",
                    str(roll_dir),
                    "--checkpoint",
                    str(stem),
                    "--action-select",
                    "sample",
                    "--temperature",
                    str(float(args.temperature)),
                    "--device",
                    "cpu",
                ],
                cwd=root,
            )
            metrics_path = stem.parent / "metrics.json"
            _run(
                [
                    "poetry",
                    "run",
                    "python3",
                    "-m",
                    "trace_synthesizer",
                    "metrics-compare",
                    "--reference",
                    str(root / "output/lstm_eval/reference_real_intra.json"),
                    "--candidate",
                    str(roll_dir / "intra_traces.jsonl"),
                    "--func",
                    func,
                    "--out",
                    str(metrics_path),
                ],
                cwd=root,
            )
            bkl = _load_metric(metrics_path, "block_visit_kl")
            ekl = _load_metric(metrics_path, "edge_transition_kl")
            hpo = _load_metric(metrics_path, "hot_path_ngram_overlap")
            # Lower is better for KL, higher better for overlap.
            objective = bkl + ekl - 2.0 * hpo
            seed_scores.append(
                {
                    "seed": seed,
                    "block_visit_kl": bkl,
                    "edge_transition_kl": ekl,
                    "hot_path_ngram_overlap": hpo,
                    "objective": objective,
                }
            )
        mean_obj = sum(x["objective"] for x in seed_scores) / len(seed_scores)
        results.append(
            {
                "config": {
                    "window_back": wb,
                    "lr": lr,
                    "epochs": ep,
                    "lstm_hidden": hid,
                    "temperature": float(args.temperature),
                },
                "seeds": seed_scores,
                "mean_objective": mean_obj,
            }
        )
        results.sort(key=lambda r: r["mean_objective"])
        (out_dir / "search_results.json").write_text(
            json.dumps({"runs": results, "best": results[0] if results else None}, indent=2),
            encoding="utf-8",
        )
        print(f"[{run_idx}] {cfg_tag} done, mean objective={mean_obj:.4f}")

    payload = {"runs": results, "best": results[0] if results else None}
    out_path = out_dir / "search_results.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out_path)}, indent=2))


if __name__ == "__main__":
    main()
