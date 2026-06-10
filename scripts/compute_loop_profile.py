#!/usr/bin/env python3
"""Compute loop / exit statistics JSON from CFG + one or more reference traces."""

from __future__ import annotations

import argparse
from pathlib import Path

from trace_synthesizer.core.grammar import CfgProgram
from trace_synthesizer.rl.loop_profile import (
    compute_loop_profile,
    load_reference_paths_as_bb_sequences,
    save_loop_profile,
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cfg", type=Path, required=True)
    p.add_argument("--func", required=True)
    p.add_argument(
        "--reference",
        type=Path,
        action="append",
        required=True,
        help="Reference trace (repeatable); compressed or intra JSONL",
    )
    p.add_argument("--reference-compressed", action="store_true")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    grammar = CfgProgram.from_cfg_json(args.cfg.resolve())
    paths: list[list[int]] = []
    for ref in args.reference:
        paths.extend(
            load_reference_paths_as_bb_sequences(
                ref=ref.resolve(),
                ref_compressed=bool(args.reference_compressed),
                function_name=str(args.func),
            )
        )
    if not paths:
        raise SystemExit("no valid BB paths extracted from references")
    prof = compute_loop_profile(grammar, str(args.func), paths)
    save_loop_profile(args.out.resolve(), prof)
    print(f"Wrote {args.out.resolve()} ({prof['n_paths']} path(s))")


if __name__ == "__main__":
    main()
