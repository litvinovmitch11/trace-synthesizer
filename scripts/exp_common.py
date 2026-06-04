"""Shared helpers for experiment scripts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list, **kwargs) -> None:
    print(f"\n[EXEC] {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def build_artifacts(
    src: Path,
    build_dir: Path,
    func: str,
    *,
    compute_loop_profile: bool = False,
    env: dict | None = None,
) -> tuple[Path, Path, Path, Path | None]:
    """Build CFG + trace artifacts for one experiment program.

    Steps:
      1. Compile via build_cpp_dataset_artifacts.sh (CFG JSON + compressed trace).
      2. Generate reference_intra.json from the compressed trace.
      3. Optionally generate loop_profile.json via compute_loop_profile.py.

    Returns (cfg, comp, ref_intra, loop_profile) — loop_profile is None when
    compute_loop_profile=False.
    """
    build_dir.mkdir(parents=True, exist_ok=True)

    extra: dict = {}
    if env is not None:
        extra["env"] = env

    run_cmd(
        ["bash", "scripts/build_cpp_dataset_artifacts.sh", str(src), str(build_dir)],
        **extra,
    )

    base = src.stem
    cfg = build_dir / f"{base}.cfg.json"
    comp = build_dir / f"{base}.compressed_trace.json"

    from trace_synthesizer.io.intra_trace import (
        canonical_intra_trace_record,
        intra_sequence_from_compressed,
    )

    seq = intra_sequence_from_compressed(json.loads(comp.read_text()), func)
    ref_record = canonical_intra_trace_record(
        function_name=func, sequence=seq, episode=None
    )
    ref_path = build_dir / f"{base}_reference_intra.json"
    ref_path.write_text(json.dumps(ref_record))

    loop_profile: Path | None = None
    if compute_loop_profile:
        loop_profile = build_dir / "loop_profile.json"
        run_cmd(
            [
                sys.executable,
                "scripts/compute_loop_profile.py",
                "--cfg",
                str(cfg),
                "--func",
                func,
                "--reference",
                str(comp),
                "--reference-compressed",
                "--out",
                str(loop_profile),
            ]
        )

    return cfg, comp, ref_path, loop_profile
