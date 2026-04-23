#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_synthesizer.agents.cfg_supervision import (
    successor_action_index,
    trace_context_tensors_for_bb_path,
)
from trace_synthesizer.core.grammar import CfgProgram, max_out_degree_for_function
from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise SystemExit(f"{path}:{i+1}: expected JSON object")
        rows.append(raw)
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-jsonl", type=Path, required=True)
    p.add_argument("--window-back", type=int, default=8)
    p.add_argument("--succ-slots", type=int, default=2)
    p.add_argument("--max-actions", type=int, default=None)
    p.add_argument("--use-global-summary", action="store_true")
    args = p.parse_args()

    rows = _load_jsonl(args.dataset_jsonl)
    if not rows:
        raise SystemExit("empty dataset")

    n_ok = 0
    n_skipped = 0
    n_bad_edge = 0
    feat_dims: dict[int, int] = {}
    cfg_cache: dict[tuple[str, str], tuple[CfgProgram, CFGWalkEnv, int]] = {}

    inferred_max_actions = 1
    for raw in rows:
        func = str(raw.get("func") or raw.get("function_name") or "")
        cfg_p = Path(str(raw["cfg"])).expanduser().resolve()
        g = CfgProgram.from_cfg_json(cfg_p)
        inferred_max_actions = max(
            inferred_max_actions, max(1, max_out_degree_for_function(g.function(func)))
        )
    max_actions = int(args.max_actions) if args.max_actions else inferred_max_actions

    for raw in rows:
        func = str(raw.get("func") or raw.get("function_name") or "")
        cfg_p = Path(str(raw["cfg"])).expanduser().resolve()
        key = (str(cfg_p), func)
        if key not in cfg_cache:
            grammar = CfgProgram.from_cfg_json(cfg_p)
            env = CFGWalkEnv(grammar, func, max_steps=50_000, seed=0, device="cpu")
            fd = int(env.observation_space["features"].shape[0])
            cfg_cache[key] = (grammar, env, fd)
        grammar, env, fd = cfg_cache[key]
        feat_dims[fd] = feat_dims.get(fd, 0) + 1

        seq = raw.get("sequence") or []
        bb_path = [int(e["bb"]) for e in seq if str(e.get("func")) == func]
        if len(bb_path) < 2:
            n_skipped += 1
            continue
        valid = [bb_path[0]]
        for a, b in zip(bb_path, bb_path[1:]):
            if successor_action_index(grammar, func, a, b) is None:
                n_bad_edge += 1
                break
            valid.append(b)
        if len(valid) < 2:
            n_skipped += 1
            continue
        try:
            x, m, y = trace_context_tensors_for_bb_path(
                env,
                grammar,
                func,
                valid[:2000],
                window_back=int(args.window_back),
                succ_feat_slots=int(args.succ_slots),
                max_actions=max_actions,
                use_global_summary=bool(args.use_global_summary),
                reset_seed=None,
            )
        except Exception:
            n_skipped += 1
            continue
        if x.shape[0] < 1 or m.shape[0] != x.shape[0] or y.shape[0] != x.shape[0]:
            n_skipped += 1
            continue
        n_ok += 1

    report = {
        "dataset_jsonl": str(args.dataset_jsonl.resolve()),
        "rows_total": len(rows),
        "rows_ok": n_ok,
        "rows_skipped": n_skipped,
        "rows_with_invalid_cfg_edges": n_bad_edge,
        "feature_dim_hist": feat_dims,
        "max_actions_used": max_actions,
        "window_back": int(args.window_back),
        "succ_slots": int(args.succ_slots),
        "use_global_summary": bool(args.use_global_summary),
    }
    print(json.dumps(report, indent=2))
    if n_ok < 1:
        raise SystemExit("validation failed: zero usable rows")


if __name__ == "__main__":
    main()
