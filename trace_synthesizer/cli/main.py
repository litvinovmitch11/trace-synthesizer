"""Command-line interface for trace_synthesizer."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from trace_synthesizer.core.grammar import CfgProgram
from trace_synthesizer.io.bb_addr_map import BbAddressMap
from trace_synthesizer.io.compress_pipeline import (
    load_compressed_trace_json,
    run_compress_and_validate,
    write_compressed_trace_json,
)
from trace_synthesizer.io.instruction_trace import read_rva_trace
from trace_synthesizer.viz.graphviz_renderer import CfgGraphvizRenderer


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def cmd_compress(args: argparse.Namespace) -> int:
    grammar = CfgProgram.from_cfg_json(args.cfg)
    bb_map = BbAddressMap.from_readobj_file(args.map)
    rvas = read_rva_trace(args.trace)
    result = run_compress_and_validate(grammar, bb_map, rvas)
    s = result.stats
    print(f"Total instructions logged: {s.total_instructions}")
    print(f"Unmapped instructions: {s.unmapped_instructions}")
    print(f"Compressed BB sequence length: {s.compressed_length}")
    print(f"Valid intra-procedural transitions: {s.valid_intra}")
    print(f"Inter-procedural transitions (calls/returns): {s.inter_procedural}")
    if not result.success:
        print(f"FAILED: Found {s.invalid_transitions} invalid transitions.")
        return 1
    print("SUCCESS: 100% Valid trace!")
    write_compressed_trace_json(args.out, result.compressed_trace)
    print(f"Compressed trace saved to: {args.out}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    grammar = CfgProgram.from_cfg_json(args.cfg)
    bb_map = BbAddressMap.from_readobj_file(args.map)
    rvas = read_rva_trace(args.trace)
    result = run_compress_and_validate(grammar, bb_map, rvas)
    s = result.stats
    print(f"Total instructions logged: {s.total_instructions}")
    print(f"Unmapped instructions: {s.unmapped_instructions}")
    print(f"Compressed BB sequence length: {s.compressed_length}")
    print(f"Valid intra-procedural transitions: {s.valid_intra}")
    print(f"Inter-procedural transitions (calls/returns): {s.inter_procedural}")
    if not result.success:
        print(f"FAILED: Found {s.invalid_transitions} invalid transitions.")
        return 1
    print(
        "SUCCESS: 100% Valid trace! All intra-procedural transitions match the LLVM CFG."
    )
    return 0


def cmd_visualize(args: argparse.Namespace) -> int:
    from trace_synthesizer.io.intra_trace import load_intra_trace_bbs_for_visualize

    grammar = CfgProgram.from_cfg_json(args.cfg)
    fn = grammar.function(args.func)
    trace_bb: list[int] | None = None
    if getattr(args, "intra_json", None):
        trace_bb = load_intra_trace_bbs_for_visualize(args.intra_json, args.func)
    elif args.trace:
        raw = load_compressed_trace_json(args.trace)
        trace_bb = [int(e["bb"]) for e in raw if e["func"] == args.func]
    renderer = CfgGraphvizRenderer(
        fn, trace_for_func=trace_bb, graph_format=args.format
    )
    renderer.render(args.out)
    return 0


def cmd_export_intra_trace(args: argparse.Namespace) -> int:
    from trace_synthesizer.io.intra_trace import export_intra_trace_from_compressed_file

    export_intra_trace_from_compressed_file(args.compressed, args.func, args.out)
    print(f"Wrote {args.out}")
    return 0


def cmd_metrics_compare(args: argparse.Namespace) -> int:
    from trace_synthesizer.metrics.compare import (
        DEFAULT_METRIC_ORDER,
        results_to_jsonable,
        run_metrics,
    )
    from trace_synthesizer.metrics.loaders import (
        load_path_from_compressed_trace,
        load_path_from_intra_trace_json,
        load_paths_from_intra_traces_jsonl,
    )
    from trace_synthesizer.metrics.types import MetricContext

    func = args.func

    def load_ref() -> list:
        if args.reference_compressed:
            return [load_path_from_compressed_trace(args.reference, func)]
        return [load_path_from_intra_trace_json(args.reference)]

    def load_cand() -> list:
        p = Path(args.candidate)
        if args.candidate_compressed:
            return [load_path_from_compressed_trace(args.candidate, func)]
        if p.suffix.lower() == ".jsonl":
            return load_paths_from_intra_traces_jsonl(p)
        return [load_path_from_intra_trace_json(p)]

    names = tuple(x.strip() for x in args.metrics.split(",") if x.strip())
    if not names:
        names = DEFAULT_METRIC_ORDER
    ctx = MetricContext(
        function_name=func,
        epsilon=args.epsilon,
        ngram_min=args.ngram_min,
        ngram_max=args.ngram_max,
        top_k=args.top_k,
    )
    results = run_metrics(load_ref(), load_cand(), ctx, names=names)
    payload = {
        "function_name": func,
        "metrics": results_to_jsonable(results),
    }
    text = json.dumps(payload, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    print(text)
    return 0


def cmd_metrics_bench_speed(args: argparse.Namespace) -> int:
    from trace_synthesizer.metrics.speed import (
        benchmark_random_rollouts,
        speedup_vs_dynamo,
    )

    stats = benchmark_random_rollouts(
        args.cfg,
        args.func,
        n_episodes=args.n_episodes,
        max_steps=args.max_steps,
        seed=args.seed,
    )
    out: dict = {"synthetic_benchmark": stats}
    if args.dynamo_seconds is not None and args.dynamo_seconds >= 0:
        out["speedup"] = speedup_vs_dynamo(
            float(stats["seconds"]),
            float(args.dynamo_seconds),
            int(args.n_episodes),
        )
    text = json.dumps(out, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    print(text)
    return 0


def cmd_ctuning_rollout(args: argparse.Namespace) -> int:
    from trace_synthesizer.benchmarks.ctuning_curated import run_ctuning_curated_cli

    repo = Path(__file__).resolve().parents[2]
    return int(run_ctuning_curated_cli(repo, args))


def cmd_benchmark_complex(args: argparse.Namespace) -> int:
    """
    Single entry: ``scripts/run_benchmark_complex.sh`` (PGO, CFGDumper, DynamoRIO,
    compress, visualize, export-intra, rollouts, metrics, bench-speed).
    """
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "run_benchmark_complex.sh"
    if not script.is_file():
        print(f"Missing orchestrator script: {script}", file=sys.stderr)
        return 2
    env = os.environ.copy()
    if args.cpp is not None:
        env["BENCHMARK_CPP"] = str(args.cpp.resolve())
    if args.out_dir is not None:
        env["OUT_DIR"] = str(args.out_dir.resolve())
    if args.func is not None:
        env["FUNC"] = args.func
    if args.skip_analysis:
        env["SKIP_ANALYSIS"] = "1"
    cmd = ["bash", str(script), *args.bin_args]
    return int(subprocess.call(cmd, cwd=str(repo), env=env))


def cmd_rollout_random(args: argparse.Namespace) -> int:
    from trace_synthesizer.agents.random_pgo import RandomPGOAgent
    from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv
    from trace_synthesizer.io.intra_trace import (
        dump_canonical_intra_json,
        intra_sequence_from_bb_path,
    )
    from trace_synthesizer.runner.rollout import rollout_episode
    from trace_synthesizer.runner.stats import summarize_rollouts
    from trace_synthesizer.runner.writers import (
        write_episodes_jsonl,
        write_intra_traces_jsonl,
        write_summary_json,
    )

    grammar = CfgProgram.from_cfg_json(args.cfg)
    env = CFGWalkEnv(
        grammar,
        args.func,
        max_steps=args.max_steps,
        seed=args.seed,
    )
    episodes = []
    rng_seed = args.seed
    for ep in range(args.episodes):
        rs = (rng_seed + ep) if rng_seed is not None else None
        agent = RandomPGOAgent(grammar, args.func, seed=rs)
        episodes.append(rollout_episode(env, agent, reset_seed=rs))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_rollouts(episodes)
    write_episodes_jsonl(out_dir / "runs.jsonl", episodes, seed=args.seed or 0)
    write_intra_traces_jsonl(out_dir / "intra_traces.jsonl", episodes, args.func)
    write_summary_json(out_dir / "summary.json", summary)
    wpath = getattr(args, "write_canonical_intra", None)
    if wpath and episodes:
        ep0 = episodes[0]
        seq = intra_sequence_from_bb_path(
            args.func, ep0.entry_bb_id, [s.to_bb for s in ep0.steps]
        )
        dump_canonical_intra_json(
            wpath, function_name=args.func, sequence=seq, episode=None
        )
        print(f"Wrote canonical intra (episode 0): {wpath}", flush=True)
    print(summary.to_dict())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m trace_synthesizer")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("compress", help="Compress and validate trace, write JSON")
    c.add_argument("--cfg", required=True)
    c.add_argument("--map", required=True)
    c.add_argument("--trace", required=True)
    c.add_argument("--out", required=True)
    c.set_defaults(handler=cmd_compress)

    v = sub.add_parser("validate", help="Validate trace against CFG (no JSON output)")
    v.add_argument("--cfg", required=True)
    v.add_argument("--map", required=True)
    v.add_argument("--trace", required=True)
    v.set_defaults(handler=cmd_validate)

    g = sub.add_parser("visualize", help="Render CFG (optional trace overlay)")
    g.add_argument("--cfg", required=True)
    g.add_argument("--func", required=True)
    g.add_argument("--out", required=True, help="Output path without extension")
    g.add_argument(
        "--trace",
        default=None,
        help="Full compressed_trace.json (global inter-procedural sequence)",
    )
    g.add_argument(
        "--intra-json",
        type=Path,
        default=None,
        help="Canonical intra trace JSON (same schema as export-intra-trace / rollouts)",
    )
    g.add_argument("--format", default="svg")
    g.set_defaults(handler=cmd_visualize)

    e = sub.add_parser(
        "export-intra-trace",
        help="Export one function's trace in canonical intra_trace JSON (from compressed)",
    )
    e.add_argument("--compressed", required=True, help="compressed_trace.json")
    e.add_argument("--func", required=True)
    e.add_argument("--out", required=True)
    e.set_defaults(handler=cmd_export_intra_trace)

    m = sub.add_parser(
        "metrics-compare",
        help="Compare reference vs candidate traces (KL, hot-path overlap)",
    )
    m.add_argument(
        "--reference", required=True, help="Intra JSON or compressed_trace.json"
    )
    m.add_argument(
        "--reference-compressed",
        action="store_true",
        help="Treat reference as full compressed_trace.json (requires --func)",
    )
    m.add_argument(
        "--candidate", required=True, help="Intra JSON, JSONL, or compressed"
    )
    m.add_argument(
        "--candidate-compressed",
        action="store_true",
        help="Treat candidate as compressed_trace.json",
    )
    m.add_argument("--func", required=True)
    m.add_argument(
        "--metrics",
        default=",".join(
            ("block_visit_kl", "edge_transition_kl", "hot_path_ngram_overlap")
        ),
        help="Comma-separated metric ids",
    )
    m.add_argument("--epsilon", type=float, default=1e-8)
    m.add_argument("--ngram-min", type=int, default=2)
    m.add_argument("--ngram-max", type=int, default=4)
    m.add_argument("--top-k", type=int, default=64)
    m.add_argument("--out", default=None, help="Write JSON report to this path")
    m.set_defaults(handler=cmd_metrics_compare)

    b = sub.add_parser(
        "metrics-bench-speed",
        help="Benchmark wall time for N random PGO rollouts (synthetic only)",
    )
    b.add_argument("--cfg", required=True)
    b.add_argument("--func", required=True)
    b.add_argument("--n-episodes", type=int, default=100)
    b.add_argument("--max-steps", type=int, default=10_000)
    b.add_argument("--seed", type=int, default=None)
    b.add_argument(
        "--dynamo-seconds",
        "--dynamo-sec-for-1000",
        dest="dynamo_seconds",
        type=float,
        default=None,
        help=(
            "Optional: wall-clock seconds to collect the same N DynamoRIO traces "
            "(speedup ratio; alias name reflects proposal N=1000)"
        ),
    )
    b.add_argument("--out", default=None)
    b.set_defaults(handler=cmd_metrics_bench_speed)

    bc = sub.add_parser(
        "benchmark-complex",
        help=(
            "C++ benchmark via full_pipeline (LLVM CFGDumper, DR InstrTracer) "
            "+ rollout/metrics (see docs/en/BENCHMARK_COMPLEX_MANUAL.md)"
        ),
    )
    bc.add_argument(
        "--cpp",
        type=Path,
        default=None,
        help="Source .cpp (default: examples/benchmark_complex/benchmark_complex.cpp)",
    )
    bc.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Artifact directory (default: output); sets OUT_DIR for the shell script",
    )
    bc.add_argument(
        "--func",
        default=None,
        help="Function symbol for Python steps (default: main)",
    )
    bc.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Run only full_pipeline.sh (no rollout/metrics)",
    )
    bc.add_argument(
        "bin_args",
        nargs="*",
        help="Arguments passed through to the benchmark binary (profile run + DR run)",
    )
    bc.set_defaults(handler=cmd_benchmark_complex)

    ct = sub.add_parser(
        "ctuning-rollout",
        help=(
            "Init ctuning-programs submodule if needed, run C PGO+DR pipeline on curated entries, "
            "then rollout-random (see benchmarks/ctuning_curated.json)"
        ),
    )
    ct.add_argument(
        "--ctuning-root",
        type=Path,
        default=None,
        help="Path to ctuning-programs checkout (default: external/ctuning-programs)",
    )
    ct.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Parent directory for output/ctuning_<id>/ (default: repo output/)",
    )
    ct.add_argument(
        "--only",
        default=None,
        help="Comma-separated entry ids from ctuning_curated.json (default: all)",
    )
    ct.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N manifest entries (after --only filter)",
    )
    ct.add_argument("--episodes", type=int, default=30)
    ct.add_argument("--max-steps", type=int, default=5000)
    ct.add_argument("--seed", type=int, default=None)
    ct.add_argument(
        "--skip-pipeline",
        action="store_true",
        help="Only rollout-random (expect cfg already from a previous run)",
    )
    ct.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Do not run scripts/init_ctuning_submodule.sh when ctuning-programs is missing",
    )
    ct.add_argument(
        "--stats-file",
        type=Path,
        default=None,
        help="Write aggregate JSON stats here (default: <repo>/output/ctuning_curated_stats.json)",
    )
    ct.add_argument(
        "--no-stats",
        action="store_true",
        help="Do not write stats file or print metrics summary",
    )
    ct.add_argument(
        "--no-metrics",
        action="store_true",
        help="Skip metrics-compare block in stats (faster)",
    )
    ct.set_defaults(handler=cmd_ctuning_rollout)

    r = sub.add_parser("rollout-random", help="Random PGO rollouts for one function")
    r.add_argument("--cfg", required=True)
    r.add_argument("--func", required=True)
    r.add_argument("--episodes", type=int, default=10)
    r.add_argument("--seed", type=int, default=None)
    r.add_argument(
        "--max-steps",
        type=int,
        default=10_000,
        help="Truncate an episode after this many steps. Use 0 for no truncation (walk until a CFG sink); "
        "still bounded by an internal hard cap (1e7) in rollout_episode.",
    )
    r.add_argument("--out-dir", required=True)
    r.add_argument(
        "--write-canonical-intra",
        type=Path,
        default=None,
        help="Also write first episode as a single canonical intra JSON (schema identical to export-intra-trace)",
    )
    r.set_defaults(handler=cmd_rollout_random)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(args))


if __name__ == "__main__":
    sys.exit(main())
