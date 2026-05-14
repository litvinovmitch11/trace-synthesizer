#!/usr/bin/env python3
"""Train flat or hierarchical PPO on CFG walk with reward wrapper."""

from __future__ import annotations

import argparse
from pathlib import Path
import json

from trace_synthesizer.rl.train_ppo import run_train_ppo


def _main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cfg", type=Path, required=True)
    p.add_argument("--func", required=True)
    p.add_argument("--out-stem", type=Path, required=True)
    p.add_argument("--device", default="cpu")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-steps", type=int, default=10_000)
    p.add_argument("--iterations", type=int, default=40)
    p.add_argument("--steps-per-iter", type=int, default=4096)
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--minibatch-size", type=int, default=512)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--gae-lambda", type=float, default=0.95)
    p.add_argument("--clip-coef", type=float, default=0.2)
    p.add_argument("--vf-coef", type=float, default=0.5)
    p.add_argument("--ent-coef", type=float, default=0.01)
    p.add_argument("--max-grad-norm", type=float, default=0.5)
    p.add_argument("--hidden", type=int, default=128)
    p.add_argument("--hierarchical", action="store_true")
    p.add_argument("--num-modes", type=int, default=4)
    p.add_argument("--z-embed-dim", type=int, default=8)
    p.add_argument("--manager-every", type=int, default=4)
    p.add_argument("--pgo-log-scale", type=float, default=0.5)
    p.add_argument("--invalid-action-penalty", type=float, default=-1.0)
    p.add_argument("--repeat-bb-penalty-scale", type=float, default=0.0)
    p.add_argument("--truncation-penalty", type=float, default=0.0)
    p.add_argument("--terminal-kl-scale", type=float, default=0.0)
    p.add_argument("--loop-profile", type=Path, default=None)
    p.add_argument("--loop-timing-scale", type=float, default=0.0)
    p.add_argument("--ref-edge-log-scale", type=float, default=0.0)
    p.add_argument("--short-path-penalty-scale", type=float, default=0.0)
    p.add_argument(
        "--no-loop-proposal-defaults",
        action="store_true",
        help="With --loop-profile, do not auto-fill ref-edge / short-path / loop-timing scales",
    )
    p.add_argument("--window-back", type=int, default=1)
    p.add_argument("--aux-exit-head", type=int, choices=(0, 1), default=1)
    p.add_argument("--aux-exit-coef", type=float, default=0.05)
    p.add_argument("--bc-epochs", type=int, default=0)
    p.add_argument("--bc-batch-size", type=int, default=64)
    p.add_argument("--bc-aux-coef", type=float, default=0.1)
    p.add_argument("--reference", type=Path, default=None)
    p.add_argument(
        "--reference-compressed",
        action="store_true",
        help="Treat --reference as compressed_trace.json",
    )
    p.add_argument(
        "--init-checkpoint",
        type=Path,
        default=None,
        help="Optional warm-start checkpoint stem (.pt/.json)",
    )
    p.add_argument(
        "--freeze-mode",
        choices=("none", "head-only"),
        default="none",
        help="Parameter-freeze preset for adaptation",
    )
    p.add_argument("--train-report", type=Path, default=None)
    p.add_argument(
        "--tb-logdir",
        type=Path,
        default=None,
        help="If set, write TensorBoard scalars under this directory",
    )
    p.add_argument(
        "--tb-run-name",
        default="train_hrl_ppo",
        help="TensorBoard run subdir name (used only with --tb-logdir)",
    )
    args = p.parse_args()

    report = run_train_ppo(args)
    print(json.dumps(report))


if __name__ == "__main__":
    _main()
