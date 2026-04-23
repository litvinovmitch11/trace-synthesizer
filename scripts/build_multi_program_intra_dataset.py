#!/usr/bin/env python3
"""
Build a multi-program real-trace dataset for the **global** trace LSTM.

Writes ``programs/<id>/train_intra_<func>.jsonl`` (canonical intra + metadata) and a single
``cross.train.jsonl`` where every line has ``cfg``, ``func``, ``sequence`` for
``train_feature_window_lstm.py``. ``dataset_index.json`` lists programs and the cross path.

There is **no** per-CFG merged training split (removed): one shared model is trained only on
``cross.train.jsonl``.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

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
    cross_lines: list[str] = []

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
            raise SystemExit(f"entry {pid!r}: no compressed_paths / compressed_glob matched")

        subdir = prog_root / str(pid)
        subdir.mkdir(parents=True, exist_ok=True)
        jsonl_path = subdir / f"train_intra_{func}.jsonl"
        n_written = 0
        with jsonl_path.open("w", encoding="utf-8") as f:
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
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                cross_lines.append(
                    json.dumps(
                        {
                            "cfg": str(cfg),
                            "func": func,
                            "sequence": rec["sequence"],
                            "program_id": str(pid),
                            "source_compressed": str(comp.resolve()),
                        },
                        ensure_ascii=False,
                    )
                )
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

    cross_path = out_root / "cross.train.jsonl"
    cross_path.write_text("\n".join(cross_lines) + ("\n" if cross_lines else ""), encoding="utf-8")

    index: dict[str, Any] = {
        "schema_version": 2,
        "spec_path": str(spec_path),
        "out_dir": str(out_root),
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
                "cross_program_lines": len(cross_lines),
                "cross_program_jsonl": str(cross_path.resolve()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
