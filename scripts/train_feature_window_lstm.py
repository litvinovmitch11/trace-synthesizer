#!/usr/bin/env python3
"""
Cross-program supervised baseline: LSTM on trace context tensors.

Each JSONL line should include precomputed supervision (from
``build_multi_program_intra_dataset.py --with-target-context``):

- ``context_features``, ``action_mask``, ``target``, ``context_meta``

Legacy mode (``cfg`` + ``func`` + ``sequence`` only) is still supported for small
fixtures; it recomputes windows via ``trace_context_tensors_for_bb_path``.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch.utils.tensorboard import SummaryWriter

from trace_synthesizer.agents.cfg_supervision import (
    successor_action_index,
    trace_context_tensors_for_bb_path,
)
from trace_synthesizer.agents.checkpoint import (
    build_policy_from_meta,
    feature_window_lstm_meta_for_save,
    save_policy_checkpoint,
)
from trace_synthesizer.core.grammar import CfgProgram, max_out_degree_for_function
from trace_synthesizer.env.interproc_walk_env import InterproceduralCFGWalkEnv


def _bb_path_from_intra(sequence: list[dict], function_name: str) -> list[int]:
    return [int(e["bb"]) for e in sequence if str(e.get("func")) == function_name]


def _is_precomputed_row(raw: dict[str, Any]) -> bool:
    return (
        isinstance(raw.get("context_features"), list)
        and isinstance(raw.get("action_mask"), list)
        and isinstance(raw.get("target"), list)
        and isinstance(raw.get("context_meta"), dict)
    )


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict) or "cfg" not in raw:
            raise SystemExit(f"{path}:{i+1}: expected object with cfg")
        pc = _is_precomputed_row(raw)
        if not pc and "sequence" not in raw:
            raise SystemExit(
                f"{path}:{i+1}: expected precomputed (context_features + ...) "
                "or legacy fields (sequence)"
            )
        rows.append(raw)
    return rows


def _scan_precomputed_meta(
    rows: list[dict[str, Any]], func_filter: str | None
) -> dict[str, Any]:
    metas: list[dict[str, Any]] = []
    for raw in rows:
        func = str(raw.get("func") or raw.get("function_name") or "")
        if func_filter is not None and func != func_filter:
            continue
        if not _is_precomputed_row(raw):
            raise SystemExit(
                "dataset mixes precomputed and legacy rows; use a single format "
                "(rebuild with --with-target-context for precomputed-only training)"
            )
        metas.append(raw["context_meta"])
    if not metas:
        raise SystemExit("no rows after func filter")
    first = metas[0]
    for i, m in enumerate(metas[1:], start=2):
        if m != first:
            raise SystemExit(
                f"context_meta mismatch: row 1 vs row {i} "
                "(all traces must use the same window / succ_slots / max_actions)"
            )
    return first


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
        env = InterproceduralCFGWalkEnv(
            grammar, func, max_steps=50_000, seed=0, device=torch.device("cpu")
        )
        max_a = max(max_a, int(env.action_space.n))
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


def _dataset_training_mode(rows: list[dict[str, Any]], func_filter: str | None) -> str:
    has_pc = False
    has_legacy = False
    for raw in rows:
        func = str(raw.get("func") or raw.get("function_name") or "")
        if func_filter is not None and func != func_filter:
            continue
        if _is_precomputed_row(raw):
            has_pc = True
        elif "sequence" in raw:
            has_legacy = True
    if has_pc and has_legacy:
        raise SystemExit(
            "dataset mixes precomputed rows and legacy (sequence-only) rows"
        )
    if has_pc:
        return "precomputed"
    if has_legacy:
        return "legacy"
    raise SystemExit("no usable rows after func filter")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--dataset-jsonl",
        type=Path,
        required=True,
        help="JSONL: precomputed context_features + action_mask + target + context_meta "
        "(or legacy cfg + func + sequence)",
    )
    p.add_argument("--func-filter", default=None, help="If set, only rows with this func")
    p.add_argument("--out-stem", type=Path, required=True)
    p.add_argument(
        "--window-back",
        type=int,
        default=8,
        help="Legacy only: past block-feature window size",
    )
    p.add_argument(
        "--succ-slots",
        type=int,
        default=-1,
        help="Legacy only: successor feature slots (default: max_actions after scan)",
    )
    p.add_argument(
        "--no-global-summary",
        action="store_true",
        help="Legacy only: disable whole-CFG static summary",
    )
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--lr", type=float, default=0.02)
    p.add_argument("--lstm-hidden", type=int, default=64)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default="cpu")
    p.add_argument(
        "--max-actions",
        type=int,
        default=None,
        help="Legacy only: override scan (must be >= all graphs)",
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
        default="train_feature_window_lstm",
        help="TensorBoard run subdir name (used only with --tb-logdir)",
    )
    p.add_argument(
        "--log-every",
        type=int,
        default=1,
        help="Log every N epochs to TensorBoard",
    )
    args = p.parse_args()

    torch.manual_seed(args.seed)
    device = torch.device(args.device)
    rows = _load_jsonl(args.dataset_jsonl)
    if not rows:
        raise SystemExit("empty dataset-jsonl")

    mode = _dataset_training_mode(rows, args.func_filter)

    if mode == "precomputed":
        cm = _scan_precomputed_meta(rows, args.func_filter)
        window_back = int(cm["window_back"])
        succ_slots = int(cm["succ_slots"])
        max_actions = int(cm["max_actions"])
        feat_dim = int(cm["feature_dim"])
        gdim = int(cm["global_dim"])
        meta = feature_window_lstm_meta_for_save(
            window_back=window_back,
            feat_dim=feat_dim,
            max_actions=max_actions,
            succ_feat_slots=succ_slots,
            global_summary_dim=gdim,
            lstm_hidden=int(args.lstm_hidden),
            function_name=args.func_filter,
        )
    else:
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
        gdim = (feat_dim + 1) if use_global else 0
        window_back = int(args.window_back)

        meta = feature_window_lstm_meta_for_save(
            window_back=window_back,
            feat_dim=feat_dim,
            max_actions=max_actions,
            succ_feat_slots=succ_slots,
            global_summary_dim=gdim,
            lstm_hidden=int(args.lstm_hidden),
            function_name=args.func_filter,
        )

    policy = build_policy_from_meta({"schema_version": 1, **meta})
    policy.to(device)
    opt = torch.optim.Adam(policy.parameters(), lr=args.lr)
    writer: SummaryWriter | None = None
    if args.tb_logdir is not None:
        tb_path = args.tb_logdir / args.tb_run_name
        tb_path.mkdir(parents=True, exist_ok=True)
        writer = SummaryWriter(log_dir=str(tb_path))

    prepared: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]] = []
    skipped = 0

    if mode == "precomputed":
        for raw in rows:
            func = str(raw.get("func") or raw.get("function_name") or "")
            if args.func_filter is not None and func != args.func_filter:
                continue
            x = torch.tensor(raw["context_features"], dtype=torch.float32, device=device)
            m = torch.tensor(raw["action_mask"], dtype=torch.bool, device=device)
            y = torch.tensor(raw["target"], dtype=torch.long, device=device)
            if x.shape[0] < 1 or x.shape[0] != m.shape[0] or y.shape[0] != x.shape[0]:
                skipped += 1
                continue
            if m.shape[1] != max_actions or x.shape[1] != int(cm["context_dim"]):
                skipped += 1
                continue
            prepared.append((x, m, y))
    else:
        for raw in rows:
            func = str(raw.get("func") or raw.get("function_name") or "")
            if args.func_filter is not None and func != args.func_filter:
                continue
            cfg_p = Path(raw["cfg"]).expanduser().resolve()
            seq = raw["sequence"]
            grammar = CfgProgram.from_cfg_json(cfg_p)
            env = InterproceduralCFGWalkEnv(grammar, func, max_steps=50_000, seed=args.seed, device=device)
            bb_path = _bb_path_from_intra(seq, func)
            if not bb_path:
                skipped += 1
                continue
            valid_path = [bb_path[0]]
            for a, b in zip(bb_path, bb_path[1:]):
                if successor_action_index(grammar, func, a, b) is None:
                    break
                valid_path.append(b)

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
                    use_global_summary=not args.no_global_summary,
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
    for ep in range(args.epochs):
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
        if writer is not None and ((ep + 1) % max(1, int(args.log_every)) == 0):
            writer.add_scalar("train/loss", last_loss, ep + 1)

    policy.eval()
    args.out_stem.parent.mkdir(parents=True, exist_ok=True)
    save_policy_checkpoint(args.out_stem, policy, {"schema_version": 1, **meta})

    report: dict[str, Any] = {
        "training_mode": f"feature_window_lstm_{mode}",
        "dataset_jsonl": str(args.dataset_jsonl.resolve()),
        "epochs": args.epochs,
        "final_train_loss": last_loss,
        "n_traces": len(prepared),
        "skipped_records": skipped,
    }
    if mode == "precomputed":
        report["context_meta"] = cm
    else:
        report.update(
            {
                "window_back": window_back,
                "succ_feat_slots": succ_slots,
                "global_summary_dim": gdim,
                "feat_dim": feat_dim,
                "max_actions": max_actions,
            }
        )
    if args.train_report is not None:
        args.train_report.parent.mkdir(parents=True, exist_ok=True)
        args.train_report.write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
    if writer is not None:
        hparams: dict[str, Any] = {
            "epochs": args.epochs,
            "lr": args.lr,
            "lstm_hidden": int(args.lstm_hidden),
            "seed": args.seed,
            "mode": mode,
        }
        if mode == "legacy":
            hparams.update(
                {
                    "window_back": window_back,
                    "succ_feat_slots": succ_slots,
                    "global_summary_dim": gdim,
                    "feat_dim": feat_dim,
                    "max_actions": max_actions,
                }
            )
        writer.add_hparams(hparams, {"hparam/final_train_loss": float(last_loss)})
        writer.flush()
        writer.close()
    print(json.dumps(report))


if __name__ == "__main__":
    main()
