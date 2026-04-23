#!/usr/bin/env python3
"""
Cross-program supervised baseline: LSTM on stacked BlockFeatures windows only.

Each JSONL line: ``{"cfg": path, "func": name, "sequence": [...]}`` (plus optional metadata).
``BlockFeatures`` base dim is fixed (5) for all programs without embeddings — the same head
can be trained on traces from different CFGs. ``max_actions`` is the maximum out-degree
over all CFGs appearing in the dataset (padding + mask at train time).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import torch
import torch.nn.functional as F

from trace_synthesizer.agents.cfg_supervision import (
    GLOBAL_CFG_SUMMARY_DIM,
    trace_context_tensors_for_bb_path,
    successor_action_index,
)
from trace_synthesizer.agents.checkpoint import (
    build_policy_from_meta,
    feature_window_lstm_meta_for_save,
    save_policy_checkpoint,
)
from trace_synthesizer.core.grammar import CfgProgram, max_out_degree_for_function
from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv


def _bb_path_from_intra(sequence: list[dict], function_name: str) -> list[int]:
    return [int(e["bb"]) for e in sequence if str(e.get("func")) == function_name]


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict) or "sequence" not in raw or "cfg" not in raw:
            raise SystemExit(f"{path}:{i+1}: expected object with cfg + sequence")
        rows.append(raw)
    return rows


def _scan_max_actions_and_feat_dim(
    rows: list[dict], func_filter: str | None
) -> tuple[int, int]:
    max_a = 1
    feat_dim: int | None = None
    for raw in rows:
        func = str(raw.get("func") or raw.get("function_name") or "")
        if func_filter is not None and func != func_filter:
            continue
        if not func:
            raise SystemExit("each row needs func or function_name")
        cfg_p = Path(raw["cfg"]).expanduser().resolve()
        if not cfg_p.is_file():
            raise SystemExit(f"cfg not found: {cfg_p}")
        grammar = CfgProgram.from_cfg_json(cfg_p)
        max_a = max(
            max_a,
            max(1, max_out_degree_for_function(grammar.function(func))),
        )
        env = CFGWalkEnv(
            grammar, func, max_steps=50_000, seed=0, device=torch.device("cpu")
        )
        fd = int(env.observation_space["features"].shape[0])
        if feat_dim is None:
            feat_dim = fd
        elif feat_dim != fd:
            raise SystemExit(
                f"Inconsistent BlockFeatures dim {feat_dim} vs {fd} for {cfg_p} "
                "(disable custom embeddings in BlockFeatures for cross-program training)."
            )
    if feat_dim is None:
        raise SystemExit("no rows after func filter")
    return max_a, feat_dim


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--dataset-jsonl",
        type=Path,
        required=True,
        help="One object per line: cfg, func (or function_name), sequence",
    )
    p.add_argument("--func-filter", default=None, help="If set, only rows with this func")
    p.add_argument("--out-stem", type=Path, required=True)
    p.add_argument(
        "--window-back",
        type=int,
        default=8,
        help="How many past block-feature vectors to stack (current at tail)",
    )
    p.add_argument(
        "--succ-slots",
        type=int,
        default=-1,
        help="Successor feature slots (default: same as max_actions after scan)",
    )
    p.add_argument(
        "--no-global-summary",
        action="store_true",
        help="Disable whole-CFG static summary (mean block features + log|blocks|)",
    )
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--lr", type=float, default=0.02)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default="cpu")
    p.add_argument("--max-actions", type=int, default=None, help="Override scan (must be >= all graphs)")
    p.add_argument("--train-report", type=Path, default=None)
    args = p.parse_args()

    torch.manual_seed(args.seed)
    device = torch.device(args.device)
    rows = _load_jsonl(args.dataset_jsonl)
    if not rows:
        raise SystemExit("empty dataset-jsonl")

    max_actions, feat_dim = _scan_max_actions_and_feat_dim(rows, args.func_filter)
    if args.max_actions is not None:
        if args.max_actions < max_actions:
            raise SystemExit(
                f"--max-actions {args.max_actions} < required {max_actions} from dataset"
            )
        max_actions = args.max_actions

    succ_slots = int(args.succ_slots)
    if succ_slots < 0:
        succ_slots = max_actions
    use_global = not args.no_global_summary
    gdim = GLOBAL_CFG_SUMMARY_DIM if use_global else 0
    window_back = int(args.window_back)

    meta = feature_window_lstm_meta_for_save(
        window_back=window_back,
        feat_dim=feat_dim,
        max_actions=max_actions,
        succ_feat_slots=succ_slots,
        global_summary_dim=gdim,
        lstm_hidden=64,
        function_name=args.func_filter,
    )
    policy = build_policy_from_meta({"schema_version": 1, **meta})
    policy.to(device)
    opt = torch.optim.Adam(policy.parameters(), lr=args.lr)

    prepared: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]] = []
    skipped = 0
    for raw in rows:
        func = str(raw.get("func") or raw.get("function_name") or "")
        if args.func_filter is not None and func != args.func_filter:
            continue
        cfg_p = Path(raw["cfg"]).expanduser().resolve()
        seq = raw["sequence"]
        grammar = CfgProgram.from_cfg_json(cfg_p)
        env = CFGWalkEnv(grammar, func, max_steps=50_000, seed=args.seed, device=device)
        bb_path = _bb_path_from_intra(seq, func)
        if not bb_path:
            skipped += 1
            continue
        valid_path = [bb_path[0]]
        for a, b in zip(bb_path, bb_path[1:]):
            if successor_action_index(grammar, func, a, b) is None:
                break
            valid_path.append(b)
        
        # limit sequence length so memory doesn't explode
        bb_path = valid_path[:2000]

        try:
            win_np, mask_np, tgt_np = trace_context_tensors_for_bb_path(
                env,
                grammar,
                func,
                bb_path,
                window_back=window_back,
                succ_feat_slots=succ_slots,
                max_actions=max_actions,
                use_global_summary=use_global,
                reset_seed=None,
            )
        except ValueError:
            skipped += 1
            continue
        if win_np.shape[0] < 1:
            skipped += 1
            continue
        prepared.append(
            (
                torch.tensor(win_np, dtype=torch.float32, device=device),
                torch.tensor(mask_np, dtype=torch.bool, device=device),
                torch.tensor(tgt_np, dtype=torch.long, device=device),
            )
        )

    if not prepared:
        raise SystemExit(f"no valid traces (skipped={skipped})")

    policy.train()
    last_loss = 0.0

    random.seed(args.seed)
    indices = list(range(len(prepared)))
    for _ep in range(args.epochs):
        random.shuffle(indices)
        epoch_loss = 0.0
        for j in indices:
            wins, masks, targets = prepared[j]
            logits, _ = policy(
                wins.unsqueeze(0), action_mask=masks.unsqueeze(0)
            )
            loss = F.cross_entropy(logits[0], targets)
            opt.zero_grad()
            loss.backward()
            opt.step()
            epoch_loss += float(loss.detach())
        last_loss = epoch_loss / len(prepared)

    policy.eval()
    args.out_stem.parent.mkdir(parents=True, exist_ok=True)
    save_policy_checkpoint(args.out_stem, policy, {"schema_version": 1, **meta})

    report = {
        "training_mode": "feature_window_lstm_cross_program",
        "dataset_jsonl": str(args.dataset_jsonl.resolve()),
        "window_back": window_back,
        "succ_feat_slots": succ_slots,
        "global_summary_dim": gdim,
        "feat_dim": feat_dim,
        "max_actions": max_actions,
        "epochs": args.epochs,
        "final_train_loss": last_loss,
        "n_traces": len(prepared),
        "skipped_records": skipped,
    }
    if args.train_report is not None:
        args.train_report.parent.mkdir(parents=True, exist_ok=True)
        args.train_report.write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
