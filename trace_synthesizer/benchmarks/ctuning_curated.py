"""Run full C pipeline + random PGO rollouts on a curated ctuning-programs subset."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CtuningEntry:
    id: str
    raw: dict[str, Any]

    @property
    def sources_relative(self) -> list[str]:
        return list(self.raw["sources_relative"])

    @property
    def entry_func(self) -> str:
        return str(self.raw.get("entry_func", "main"))

    @property
    def rollout_func(self) -> str:
        """Function symbol for ``rollout-random`` / metrics (defaults to ``entry_func``)."""
        return str(self.raw.get("rollout_func", self.raw.get("entry_func", "main")))

    def resolved_rollout_max_steps(self, cli_default: int) -> int:
        """If ``rollout_max_steps`` is set in the manifest it overrides the CLI value (0 = no CFG truncation)."""
        if "rollout_max_steps" not in self.raw:
            return int(cli_default)
        return int(self.raw["rollout_max_steps"])

    @property
    def profile_env(self) -> dict[str, str]:
        e = self.raw.get("profile_env")
        if not e:
            return {}
        return {str(k): str(v) for k, v in e.items()}

    @property
    def profile_argv(self) -> list[str]:
        return [str(x) for x in self.raw.get("profile_argv", [])]

    @property
    def profile_data(self) -> dict[str, Any] | None:
        pd = self.raw.get("profile_data")
        return pd if isinstance(pd, dict) else None


def default_ctuning_root(repo_root: Path) -> Path:
    return repo_root / "external" / "ctuning-programs"


def load_manifest(repo_root: Path) -> list[CtuningEntry]:
    path = repo_root / "benchmarks" / "ctuning_curated.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("ctuning_curated.json must be a JSON array")
    return [CtuningEntry(id=str(item["id"]), raw=item) for item in data]


def _write_matmul_data(path: Path, *, float_count: int, value: str) -> None:
    path.write_text(" ".join([value] * float_count) + "\n", encoding="utf-8")


def ensure_ctuning_programs(repo_root: Path) -> None:
    script = repo_root / "scripts" / "init_ctuning_submodule.sh"
    subprocess.run(["bash", str(script)], check=True, cwd=str(repo_root))


def _prepare_bin_args(entry: CtuningEntry, out_dir: Path) -> list[str]:
    bin_args: list[str] = list(entry.profile_argv)
    pd = entry.profile_data
    if pd and pd.get("kind") == "float_space_separated":
        data_path = out_dir / f"{entry.id}_profile_data.txt"
        _write_matmul_data(
            data_path,
            float_count=int(pd.get("float_count", 16)),
            value=str(pd.get("value", "0.1")),
        )
        bin_args.insert(0, str(data_path))
    elif pd and pd.get("kind") == "text_file":
        fname = str(pd.get("filename", f"{entry.id}_profile_input.txt"))
        data_path = out_dir / fname
        data_path.write_text(str(pd.get("content", "")), encoding="utf-8")
        bin_args.insert(0, str(data_path))
    return bin_args


def _collect_post_rollout_stats(
    entry: CtuningEntry,
    out_dir: Path,
    roll_dir: Path,
    *,
    wall_seconds: float,
    rollout_max_steps_used: int,
    include_metrics: bool,
    include_bench: bool,
) -> dict[str, Any]:
    summary_path = roll_dir / "summary.json"
    summary: dict[str, Any] = {}
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    cfg = out_dir / f"{entry.id}.cfg.json"
    bench: dict[str, Any] = {}
    if include_bench and cfg.is_file():
        from trace_synthesizer.metrics.speed import benchmark_random_rollouts

        bench = dict(
            benchmark_random_rollouts(
                cfg,
                entry.rollout_func,
                n_episodes=min(50, max(5, summary.get("num_episodes", 10))),
                max_steps=2000,
                seed=0,
            )
        )

    metrics_payload: list[dict[str, object]] | None = None
    if include_metrics:
        comp = out_dir / f"{entry.id}.compressed_trace.json"
        intra = roll_dir / "intra_traces.jsonl"
        if comp.is_file() and intra.is_file():
            from trace_synthesizer.metrics.compare import (
                DEFAULT_METRIC_ORDER,
                results_to_jsonable,
                run_metrics,
            )
            from trace_synthesizer.metrics.loaders import (
                load_path_from_compressed_trace,
                load_paths_from_intra_traces_jsonl,
            )
            from trace_synthesizer.metrics.types import MetricContext

            try:
                ref = load_path_from_compressed_trace(comp, entry.rollout_func)
                cands = load_paths_from_intra_traces_jsonl(intra)
                if cands:
                    ctx = MetricContext(function_name=entry.rollout_func)
                    results = run_metrics(
                        [ref],
                        [cands[0]],
                        ctx,
                        names=DEFAULT_METRIC_ORDER,
                    )
                    metrics_payload = results_to_jsonable(results)
            except (OSError, ValueError, KeyError) as ex:
                metrics_payload = [{"error": str(ex)}]

    from trace_synthesizer.runner.stats import summarize_paths_from_runs_jsonl

    path_stats = summarize_paths_from_runs_jsonl(roll_dir / "runs.jsonl")

    return {
        "id": entry.id,
        "entry_func_pipeline": entry.entry_func,
        "rollout_func": entry.rollout_func,
        "rollout_max_steps_used": rollout_max_steps_used,
        "wall_seconds_pipeline_and_rollout": wall_seconds,
        "out_dir": str(out_dir.resolve()),
        "rollouts_dir": str(roll_dir.resolve()),
        "rollout_summary": summary,
        "rollout_path_lengths": path_stats,
        "synthetic_bench_subset": bench,
        "metrics_vs_dynamo_first_rollout": metrics_payload,
    }


def run_pipeline_and_rollout(
    repo_root: Path,
    entry: CtuningEntry,
    *,
    ctuning_root: Path,
    out_parent: Path,
    episodes: int,
    max_steps: int,
    seed: int | None,
    skip_pipeline: bool,
) -> tuple[Path, float]:
    """Returns rollout output directory and wall-clock seconds for this entry."""
    t0 = time.perf_counter()
    out_dir = out_parent / f"ctuning_{entry.id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    abs_sources = [
        str((ctuning_root / rel).resolve()) for rel in entry.sources_relative
    ]
    primary = abs_sources[0]
    env = os.environ.copy()
    env["OUT_DIR"] = str(out_dir.resolve())
    env["CTUNING_PRIMARY"] = primary
    env["CTUNING_BASENAME"] = entry.id
    env["CTUNING_SOURCES"] = " ".join(abs_sources)
    # Match `visualize` to the same function as rollouts/metrics (`rollout_func`), not only
    # `entry_func`. For e.g. cbench-telecom-crc32, entry is `main` (wrapper) while the core
    # walk and paired_viz script use `main1`; otherwise *_main_cfg_pgo_trace.svg and
    # paired_viz/main1_cfg_real_trace.svg depict different functions.
    env["FUNC"] = entry.rollout_func
    if entry.profile_env:
        env["PROFILE_ENV_KV"] = ",".join(
            f"{k}={v}" for k, v in entry.profile_env.items()
        )

    bin_args = _prepare_bin_args(entry, out_dir)

    pipe = repo_root / "scripts" / "ctuning_full_pipeline_c.sh"
    if not skip_pipeline:
        subprocess.run(
            ["bash", str(pipe), *bin_args],
            check=True,
            cwd=str(repo_root),
            env=env,
        )

    cfg = out_dir / f"{entry.id}.cfg.json"
    if not cfg.is_file():
        raise FileNotFoundError(f"Missing CFG after pipeline: {cfg}")

    roll_dir = out_dir / "rollouts_random"
    subprocess.run(
        [
            "poetry",
            "run",
            "python3",
            "-m",
            "trace_synthesizer",
            "rollout-random",
            "--cfg",
            str(cfg),
            "--func",
            entry.rollout_func,
            "--episodes",
            str(episodes),
            "--max-steps",
            str(max_steps),
            "--out-dir",
            str(roll_dir),
            *(["--seed", str(seed)] if seed is not None else []),
        ],
        check=True,
        cwd=str(repo_root),
    )
    elapsed = time.perf_counter() - t0
    return roll_dir, elapsed


def run_ctuning_curated_cli(repo_root: Path, args: Any) -> int:
    ctuning = (
        Path(args.ctuning_root).resolve()
        if getattr(args, "ctuning_root", None)
        else default_ctuning_root(repo_root)
    )
    if not (ctuning / "program").is_dir():
        if getattr(args, "no_bootstrap", False):
            print(f"ctuning-programs not found at {ctuning}", flush=True)
            return 2
        ensure_ctuning_programs(repo_root)
    if not (ctuning / "program").is_dir():
        print(f"After init, still missing: {ctuning}/program", flush=True)
        return 2

    manifest = load_manifest(repo_root)
    only = getattr(args, "only", None)
    if only:
        wanted = {s.strip() for s in str(only).split(",") if s.strip()}
        manifest = [e for e in manifest if e.id in wanted]
        if not manifest:
            print(f"No entries matched --only {only!r}", flush=True)
            return 2
    limit = int(getattr(args, "limit", 0) or 0)
    if limit > 0:
        manifest = manifest[:limit]

    out_parent = Path(args.out).resolve() if args.out else (repo_root / "output")
    out_parent.mkdir(parents=True, exist_ok=True)

    no_stats = bool(getattr(args, "no_stats", False))
    include_metrics = not bool(getattr(args, "no_metrics", False)) and not no_stats
    include_bench = not no_stats
    stats_entries: list[dict[str, Any]] = []

    for e in manifest:
        print(f"=== ctuning: {e.id} ===", flush=True)
        eff_ms = e.resolved_rollout_max_steps(int(args.max_steps))
        roll_dir, wall_s = run_pipeline_and_rollout(
            repo_root,
            e,
            ctuning_root=ctuning,
            out_parent=out_parent,
            episodes=int(args.episodes),
            max_steps=eff_ms,
            seed=args.seed,
            skip_pipeline=bool(getattr(args, "skip_pipeline", False)),
        )
        out_dir = out_parent / f"ctuning_{e.id}"
        stats_entries.append(
            _collect_post_rollout_stats(
                e,
                out_dir,
                roll_dir,
                wall_seconds=wall_s,
                rollout_max_steps_used=eff_ms,
                include_metrics=include_metrics,
                include_bench=include_bench,
            )
        )
        print(f"OK {e.id} rollouts -> {roll_dir}", flush=True)

    if not no_stats:
        stats_rel = getattr(args, "stats_file", None)
        stats_path = (
            Path(stats_rel).resolve()
            if stats_rel
            else (repo_root / "output" / "ctuning_curated_stats.json")
        )
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "episodes": int(args.episodes),
            "cli_max_steps_default": int(args.max_steps),
            "note_rollout_max_steps": (
                "Per manifest entry: rollout_max_steps overrides CLI; "
                "0 means walk until CFG sink (no truncation), still bounded by "
                "rollout_episode hard limit (1e7 steps)."
            ),
            "entries": stats_entries,
        }
        stats_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        print(f"Wrote stats: {stats_path}", flush=True)
        _print_metrics_table(stats_entries)

    return 0


def _print_metrics_table(entries: list[dict[str, Any]]) -> None:
    print(
        "\n--- Metrics (Dynamo compressed vs first synthetic rollout) ---", flush=True
    )
    for row in entries:
        eid = row.get("id", "?")
        m = row.get("metrics_vs_dynamo_first_rollout")
        if not m:
            print(f"  {eid}: (no metrics)", flush=True)
            continue
        if isinstance(m, list) and m and "error" in m[0]:
            print(f"  {eid}: metrics error: {m[0]['error']}", flush=True)
            continue
        parts = []
        if isinstance(m, list):
            for item in m:
                if isinstance(item, dict) and "name" in item and "value" in item:
                    v = item["value"]
                    if v is None:
                        reason = ""
                        det = item.get("details")
                        if isinstance(det, dict) and det.get("reason"):
                            reason = f" ({det['reason']})"
                        parts.append(f"{item['name']}=null{reason}")
                    elif isinstance(v, (int, float)):
                        parts.append(f"{item['name']}={float(v):.6g}")
                    else:
                        parts.append(f"{item['name']}={v!r}")
        print(f"  {eid}: " + "; ".join(parts), flush=True)
        sb = row.get("synthetic_bench_subset") or {}
        if "episodes_per_second" in sb:
            print(
                f"    synthetic_bench (~50 ep, max_steps=2000): "
                f"{sb['episodes_per_second']:.3f} ep/s, {sb['seconds']:.4f}s total",
                flush=True,
            )
        pl = row.get("rollout_path_lengths") or {}
        bt = pl.get("by_termination") or {}
        if "terminated" in bt:
            t = bt["terminated"]
            print(
                f"    path_lengths [terminated]: n={t.get('count', 0)} "
                f"mean={t.get('mean', 0):.1f} min={t.get('min', 0)} max={t.get('max', 0)}",
                flush=True,
            )
        if "hard_capped" in bt:
            print(
                f"    path_lengths: {bt['hard_capped'].get('count', 0)} episode(s) hit hard step cap",
                flush=True,
            )
