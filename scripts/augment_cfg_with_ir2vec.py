#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path


def _parse_ir2vec_bb_output(text: str) -> dict[str, dict[str, list[float]]]:
    out: dict[str, dict[str, list[float]]] = {}
    cur_fn: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Function: "):
            cur_fn = line[len("Function: ") :].strip()
            out.setdefault(cur_fn, {})
            continue
        if cur_fn is None:
            continue
        m = re.match(r"^(.*?):\s*\[(.*)\]\s*$", line)
        if not m:
            continue
        bb_name = m.group(1).strip()
        vec_raw = m.group(2).strip()
        if not vec_raw:
            continue
        vals = [float(x) for x in vec_raw.split()]
        out[cur_fn][bb_name] = vals
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cfg", type=Path, required=True)
    p.add_argument("--bc", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--llvm-ir2vec", type=Path, required=True)
    p.add_argument("--vocab", type=Path, required=True)
    p.add_argument("--kind", choices=("symbolic", "flow-aware"), default="symbolic")
    args = p.parse_args()

    cfg = args.cfg.resolve()
    bc = args.bc.resolve()
    out = (args.out or args.cfg).resolve()
    if not cfg.is_file():
        raise SystemExit(f"cfg not found: {cfg}")
    if not bc.is_file():
        raise SystemExit(f"bc not found: {bc}")

    with tempfile.NamedTemporaryFile(
        prefix="ir2vec_", suffix=".txt", delete=False
    ) as tf:
        tmp = Path(tf.name)
    cmd = [
        str(args.llvm_ir2vec.resolve()),
        "embeddings",
        "--mode=llvm",
        f"--ir2vec-vocab-path={args.vocab.resolve()}",
        f"--ir2vec-kind={args.kind}",
        "--level=bb",
        str(bc),
        "-o",
        str(tmp),
    ]
    subprocess.run(cmd, check=True)
    text = tmp.read_text(encoding="utf-8")
    tmp.unlink(missing_ok=True)
    emb = _parse_ir2vec_bb_output(text)

    raw = json.loads(cfg.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("cfg root must be list")

    n_blocks = 0
    n_matched = 0
    emb_dim = None
    for fmap in emb.values():
        for v in fmap.values():
            emb_dim = len(v)
            break
        if emb_dim is not None:
            break
    for fn in raw:
        fn_name = str(fn.get("function_name", ""))
        bb_map = emb.get(fn_name, {})
        blocks = fn.get("blocks") or []
        for b in blocks:
            n_blocks += 1
            name = str(b.get("name", ""))
            vec = bb_map.get(name)
            if vec is not None:
                b["ir2vec_embedding"] = vec
                n_matched += 1
            elif emb_dim is not None:
                b["ir2vec_embedding"] = [0.0] * emb_dim

    out.write_text(json.dumps(raw), encoding="utf-8")
    print(
        json.dumps(
            {
                "cfg": str(cfg),
                "out": str(out),
                "n_blocks": n_blocks,
                "n_with_embedding": n_matched,
                "embedding_dim": emb_dim,
            }
        )
    )


if __name__ == "__main__":
    main()
