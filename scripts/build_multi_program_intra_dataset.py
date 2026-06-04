#!/usr/bin/env python3
"""
Build a multi-program real-trace dataset for the **global** trace LSTM.

Writes ``programs/<id>/train_intra_<func>.jsonl`` (canonical intra + metadata) and a single
``cross.train.jsonl`` where each line has ``cfg``, ``func``, ``sequence``, and (with
``--with-target-context``) ``context_features``, ``action_mask``, ``target``, ``context_meta``
for direct training in ``train_feature_window_lstm.py``. ``dataset_index.json`` lists programs
and the cross path.

There is **no** per-CFG merged training split (removed): one shared model is trained only on
``cross.train.jsonl``.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

from trace_synthesizer.agents.cfg_supervision import (
    successor_action_index,
    trace_context_tensors_for_bb_path,
)
from trace_synthesizer.core.grammar import CfgProgram, max_out_degree_for_function
from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv
from trace_synthesizer.io.intra_trace import try_intra_record_from_compressed


def _resolve(path_str: str, base: Path) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p.resolve()
    return (base / p).resolve()


def _collect_compressed(entry: dict[str, Any], base: Path) -> list[Path]:
    paths: list[Path] = []
    for raw in entry.get("compressed_paths") or []:
        paths.append(_resolve(str(raw), base))
    g = entry.get("compressed_glob")
    if g:
        gs = str(g)
        pattern = gs if Path(gs).is_absolute() else str(_resolve(gs, base))
        paths.extend(Path(p) for p in sorted(glob.glob(pattern)))
    seen: set[str] = set()
    out: list[Path] = []
    for q in paths:
        key = str(q.resolve())
        if key not in seen:
            seen.add(key)
            out.append(q)
    return out


def _bb_path_from_sequence(sequence: list[dict[str, Any]], func: str) -> list[int]:
    return [int(e["bb"]) for e in sequence if str(e.get("func")) == func]


def _valid_cfg_path(grammar: CfgProgram, func: str, bb_path: list[int]) -> list[int]:
    if not bb_path:
        return []
    valid = [bb_path[0]]
    for a, b in zip(bb_path, bb_path[1:]):
        if successor_action_index(grammar, func, a, b) is None:
            break
        valid.append(b)
    return valid


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--spec",
        type=Path,
        required=True,
        help="JSON spec (schema_version + entries); paths relative to spec file dir unless absolute",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Output root: programs/<id>/..., cross.train.jsonl, dataset_index.json",
    )
    p.add_argument(
        "--max-traces-per-program",
        type=int,
        default=0,
        help="Use at most N compressed traces per program (<=0 means all).",
    )
    p.add_argument(
        "--with-target-context",
        action="store_true",
        help="Precompute training inputs/action-mask/target for each trace row.",
    )
    p.add_argument("--window-back", type=int, default=8)
    p.add_argument("--succ-slots", type=int, default=-1)
    p.add_argument("--max-actions", type=int, default=None)
    p.add_argument("--use-global-summary", action="store_true")
    p.add_argument(
        "--max-path-len",
        type=int,
        default=2000,
        help="Cap valid BB path length before context extraction.",
    )
    args = p.parse_args()

    spec_path = args.spec.resolve()
    base = spec_path.parent
    raw = json.loads(spec_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise SystemExit("spec: expected schema_version 1")
    entries = raw.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("spec: entries must be a non-empty list")

    out_root = args.out_dir.resolve()
    prog_root = out_root / "programs"
    prog_root.mkdir(parents=True, exist_ok=True)

    programs_out: list[dict[str, Any]] = []
    cross_path = out_root / "cross.train.jsonl"
    cross_path.write_text("", encoding="utf-8")
    cross_written = 0
    cfg_cache: dict[tuple[str, str], tuple[CfgProgram, CFGWalkEnv, int]] = {}

    inferred_max_actions = 1
    if args.with_target_context and args.max_actions is None:
        for entry in entries:
            cfg = _resolve(str(entry["cfg"]), base)
            func = str(entry["func"])
            grammar = CfgProgram.from_cfg_json(cfg)
            inferred_max_actions = max(
                inferred_max_actions,
                max(1, max_out_degree_for_function(grammar.function(func))),
            )
    max_actions = (
        int(args.max_actions) if args.max_actions is not None else inferred_max_actions
    )

    for entry in entries:
        pid = entry.get("id")
        if not pid:
            raise SystemExit("each entry needs string id")
        cfg = _resolve(str(entry["cfg"]), base)
        func = str(entry["func"])
        if not cfg.is_file():
            raise SystemExit(f"cfg not found: {cfg}")
        comp_paths = _collect_compressed(entry, base)
        if not comp_paths:
            raise SystemExit(
                f"entry {pid!r}: no compressed_paths / compressed_glob matched"
            )
        if args.max_traces_per_program > 0:
            comp_paths = comp_paths[: int(args.max_traces_per_program)]

        subdir = prog_root / str(pid)
        subdir.mkdir(parents=True, exist_ok=True)
        jsonl_path = subdir / f"train_intra_{func}.jsonl"
        n_written = 0
        with (
            jsonl_path.open("w", encoding="utf-8") as f,
            cross_path.open("a", encoding="utf-8") as cross_f,
        ):
            for i, comp in enumerate(comp_paths):
                if not comp.is_file():
                    raise SystemExit(f"entry {pid!r}: not a file {comp}")
                extra = {
                    "program_id": str(pid),
                    "source_compressed": str(comp.resolve()),
                }
                rec = try_intra_record_from_compressed(
                    comp, func, episode=i, extra_fields=extra
                )
                if rec is None:
                    continue
                if args.with_target_context:
                    key = (str(cfg.resolve()), func)
                    if key not in cfg_cache:
                        grammar = CfgProgram.from_cfg_json(cfg)
                        env = CFGWalkEnv(
                            grammar,
                            func,
                            max_steps=50_000,
                            seed=0,
                            device="cpu",
                        )
                        fd = int(env.observation_space["features"].shape[0])
                        cfg_cache[key] = (grammar, env, fd)
                    grammar, env, fd = cfg_cache[key]
                    succ_slots = int(args.succ_slots)
                    if succ_slots < 0:
                        succ_slots = max_actions
                    bb_path = _bb_path_from_sequence(rec["sequence"], func)
                    valid = _valid_cfg_path(grammar, func, bb_path)[
                        : int(args.max_path_len)
                    ]
                    if len(valid) < 2:
                        continue
                    try:
                        x, m, y = trace_context_tensors_for_bb_path(
                            env,
                            grammar,
                            func,
                            valid,
                            window_back=int(args.window_back),
                            succ_feat_slots=succ_slots,
                            max_actions=max_actions,
                            use_global_summary=bool(args.use_global_summary),
                            reset_seed=None,
                        )
                    except ValueError:
                        continue
                    if x.shape[0] < 1:
                        continue
                    rec["target"] = y.astype("int64").tolist()
                    rec["action_mask"] = m.astype("bool").tolist()
                    rec["context_features"] = x.astype("float32").tolist()
                    rec["context_meta"] = {
                        "window_back": int(args.window_back),
                        "succ_slots": int(succ_slots),
                        "max_actions": int(max_actions),
                        "use_global_summary": bool(args.use_global_summary),
                        "feature_dim": int(fd),
                        "global_dim": (
                            int(fd + 1) if bool(args.use_global_summary) else 0
                        ),
                        "context_dim": int(x.shape[1]),
                    }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                cross_row: dict[str, Any] = {
                    "cfg": str(cfg),
                    "func": func,
                    "sequence": rec["sequence"],
                    "program_id": str(pid),
                    "source_compressed": str(comp.resolve()),
                }
                if args.with_target_context:
                    cross_row["target"] = rec["target"]
                    cross_row["action_mask"] = rec["action_mask"]
                    cross_row["context_features"] = rec["context_features"]
                    cross_row["context_meta"] = rec["context_meta"]
                cross_f.write(json.dumps(cross_row, ensure_ascii=False) + "\n")
                cross_f.flush()
                cross_written += 1
                n_written += 1
        if n_written < 1:
            raise SystemExit(f"entry {pid!r}: zero valid intra traces after filtering")

        programs_out.append(
            {
                "id": str(pid),
                "cfg": str(cfg),
                "func": func,
                "train_jsonl": str(jsonl_path),
                "n_traces": n_written,
                "compressed_inputs": len(comp_paths),
            }
        )

    index: dict[str, Any] = {
        "schema_version": 2,
        "spec_path": str(spec_path),
        "out_dir": str(out_root),
        "with_target_context": bool(args.with_target_context),
        "max_traces_per_program": int(args.max_traces_per_program),
        "programs": programs_out,
        "cross_program_jsonl": str(cross_path.resolve()),
    }
    index_path = out_root / "dataset_index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(index_path),
                "n_programs": len(programs_out),
                "cross_program_lines": cross_written,
                "cross_program_jsonl": str(cross_path.resolve()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
