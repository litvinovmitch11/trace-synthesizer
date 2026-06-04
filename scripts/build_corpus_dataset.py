#!/usr/bin/env python3
"""EXPERIMENTAL: build a multi-program corpus from cBench/ctuning programs.

For each curated program (benchmarks/external/ctuning_curated.json) this:
  1. compiles its (multi-file, C) sources with PGO instrumentation,
  2. runs the binary with `profile_argv` / a `profile_data` input file,
  3. dumps the CFG (CFGDumper) + IR2Vec embeddings,
  4. records a DynamoRIO trace and compresses it to a BB sequence,
  5. emits a `spec.json` entry pointing at (cfg, rollout_func, compressed_trace).

The resulting `spec.json` feeds `build_multi_program_intra_dataset.py`, whose
`cross.train.jsonl` trains the shared LSTM (`train_feature_window_lstm.py`).

This is the generalization of `build_cpp_dataset_artifacts.sh` (single C++ file,
no args) to the multi-file C cBench programs. See docs/en/OVERVIEW.md §4.4.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LLVM_DIR = Path(
    os.environ.get(
        "LLVM_INSTALL_DIR", "/home/mitchell/dev/llvm/llvm-project/build-install"
    )
)
CLANG = LLVM_DIR / "bin" / "clang"
PROFDATA = LLVM_DIR / "bin" / "llvm-profdata"
LLVM_LINK = LLVM_DIR / "bin" / "llvm-link"
LLC = LLVM_DIR / "bin" / "llc"
READOBJ = LLVM_DIR / "bin" / "llvm-readobj"
IR2VEC = LLVM_DIR / "bin" / "llvm-ir2vec"
VOCAB = (
    LLVM_DIR.parent
    / "llvm"
    / "lib"
    / "Analysis"
    / "models"
    / "seedEmbeddingVocab75D.json"
)
PLUGIN = ROOT / "build" / "src" / "CFGDumper" / "CFGDumper.so"
TRACER = ROOT / "build" / "src" / "InstrTracer" / "libInstrTracer.so"
DRRUN = ROOT / "build" / "_deps" / "dynamorio_pkg-src" / "bin64" / "drrun"

DEFAULT_CURATED = ROOT / "benchmarks" / "external" / "ctuning_curated.json"
DEFAULT_SUBMODULE = ROOT / "benchmarks" / "external" / "ctuning-programs"
DEFAULT_HINTS = ROOT / "benchmarks" / "cbench_support" / "compile_hints.json"


def run(cmd, cwd=None, env=None, out=None):
    pretty = " ".join(str(c) for c in cmd)
    print(f"[EXEC] {pretty}" + (f"  > {out}" if out else ""))
    stdout = open(out, "w") if out else None
    try:
        subprocess.run(
            [str(c) for c in cmd], check=True, cwd=cwd, env=env, stdout=stdout
        )
    finally:
        if stdout:
            stdout.close()


def build_one(entry, submodule, outdir, hints, n_pgo, opt):
    pid = entry["id"]
    work = outdir / pid
    work.mkdir(parents=True, exist_ok=True)
    srcs = [submodule / s for s in entry["sources_relative"]]
    for s in srcs:
        if not s.is_file():
            raise SystemExit(
                f"{pid}: source not found {s} (is the submodule checked out?)"
            )
    extra = list(hints.get(pid, {}).get("clang_extra_cflags", []))

    # Invocation: explicit profile_argv, else the profile_data input filename.
    argv = list(entry.get("profile_argv") or [])
    pd = entry.get("profile_data")
    if pd and pd.get("kind") == "text_file":
        (work / pd["filename"]).write_text(pd["content"], encoding="utf-8")
        if not argv:
            argv = [pd["filename"]]

    print(f"\n=== {pid}: argv={argv} rollout_func={entry['rollout_func']} ===")

    # 1. PGO instrument build + runs
    prof = work / "prog_prof"
    run(
        [
            CLANG,
            opt,
            "-fprofile-instr-generate",
            "-fcoverage-mapping",
            "-w",
            *extra,
            *srcs,
            "-lm",
            "-o",
            prof,
        ]
    )
    raws = []
    for i in range(n_pgo):
        raw = work / f"run_{i}.profraw"
        raws.append(raw)
        run([prof, *argv], cwd=work, env={**os.environ, "LLVM_PROFILE_FILE": str(raw)})
    run([PROFDATA, "merge", "-output", work / "prog.profdata", *raws])

    # 2. Per-file LTO bitcode -> link -> CFG dump + binary
    bcs = []
    for j, s in enumerate(srcs):
        bc = work / f"u{j}.bc"
        bcs.append(bc)
        run(
            [
                CLANG,
                opt,
                "-fPIC",
                "-fbasic-block-address-map",
                "-flto",
                "-w",
                *extra,
                f"-fprofile-instr-use={work / 'prog.profdata'}",
                "-c",
                s,
                "-o",
                bc,
            ]
        )
    whole = work / "whole.bc"
    run([LLVM_LINK, *bcs, "-o", whole])
    cfg = work / "prog.cfg.json"
    run(
        [
            LLC,
            "--basic-block-address-map",
            "-relocation-model=pic",
            "-load",
            PLUGIN,
            "-cfg-pretty=false",
            f"-cfg-out-file={cfg}",
            whole,
            "-o",
            work / "prog.s",
        ]
    )
    binp = work / "prog.bin"
    run([CLANG, work / "prog.s", "-lm", "-o", binp])
    run([READOBJ, "--bb-addr-map", binp], out=work / "prog_bb_map.txt")

    # 3. IR2Vec augmentation (best effort)
    if IR2VEC.is_file() and VOCAB.is_file():
        run(
            [
                sys.executable,
                ROOT / "scripts" / "augment_cfg_with_ir2vec.py",
                "--cfg",
                cfg,
                "--bc",
                whole,
                "--llvm-ir2vec",
                IR2VEC,
                "--vocab",
                VOCAB,
            ]
        )
    else:
        print("  (skipping IR2Vec: llvm-ir2vec or vocab not found)")

    # 4. DynamoRIO trace + compress. Use basenames with cwd=work so InstrTracer's
    # module-name match works exactly like build_cpp_dataset_artifacts.sh.
    run(
        [
            DRRUN,
            "-c",
            TRACER,
            "-o",
            "prog.trace.bin",
            "prog.bin",
            "--",
            "./prog.bin",
            *argv,
        ],
        cwd=work,
    )
    comp = work / "prog.compressed_trace.json"
    run(
        [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "compress",
            "--cfg",
            cfg,
            "--map",
            work / "prog_bb_map.txt",
            "--trace",
            work / "prog.trace.bin",
            "--out",
            comp,
        ]
    )

    return {
        "id": pid,
        "cfg": str(cfg.resolve()),
        "func": entry["rollout_func"],
        "compressed_paths": [str(comp.resolve())],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--curated", type=Path, default=DEFAULT_CURATED)
    ap.add_argument("--submodule", type=Path, default=DEFAULT_SUBMODULE)
    ap.add_argument("--hints", type=Path, default=DEFAULT_HINTS)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--spec-out", type=Path, required=True)
    ap.add_argument(
        "--ids", nargs="*", default=None, help="Subset of curated ids (default: all)"
    )
    ap.add_argument("--n-pgo", type=int, default=2)
    ap.add_argument(
        "--opt", default="-O1", help="Opt level (lower preserves named functions)"
    )
    args = ap.parse_args()

    for tool in (CLANG, LLC, LLVM_LINK, READOBJ, PLUGIN, TRACER, DRRUN):
        if not Path(tool).exists():
            raise SystemExit(f"missing prerequisite: {tool} (run `make build`?)")

    # Absolute so per-program binaries/inputs resolve when run with cwd=<work>.
    args.out_dir = args.out_dir.resolve()
    curated = json.loads(args.curated.read_text())
    hints = json.loads(args.hints.read_text()) if args.hints.is_file() else {}
    if args.ids:
        curated = [e for e in curated if e["id"] in set(args.ids)]
        if not curated:
            raise SystemExit(f"no curated entries match {args.ids}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    entries, failed = [], []
    for entry in curated:
        try:
            entries.append(
                build_one(
                    entry, args.submodule, args.out_dir, hints, args.n_pgo, args.opt
                )
            )
        except subprocess.CalledProcessError as e:
            print(f"  !! {entry['id']} failed: {e}", file=sys.stderr)
            failed.append(entry["id"])

    if not entries:
        raise SystemExit("no programs built successfully")
    spec = {"schema_version": 1, "entries": entries}
    args.spec_out.parent.mkdir(parents=True, exist_ok=True)
    args.spec_out.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(
        f"\nWrote {args.spec_out} with {len(entries)} program(s)"
        + (f"; failed: {failed}" if failed else "")
    )


if __name__ == "__main__":
    main()
