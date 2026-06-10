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

    dedupe_compressed = not bool(
        getattr(args, "metrics_preserve_consecutive_bb", False)
    )

    def load_ref() -> list:
        if args.reference_compressed:
            return [
                load_path_from_compressed_trace(
                    args.reference, func, dedupe_consecutive=dedupe_compressed
                )
            ]
        return [load_path_from_intra_trace_json(args.reference)]

    def load_cand() -> list:
        p = Path(args.candidate)
        if args.candidate_compressed:
            return [
                load_path_from_compressed_trace(
                    args.candidate, func, dedupe_consecutive=dedupe_compressed
                )
            ]
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


def cmd_rollout_random(args: argparse.Namespace) -> int:
    from trace_synthesizer.agents.random_pgo import RandomPGOAgent
    from trace_synthesizer.env.interproc_walk_env import InterproceduralCFGWalkEnv
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
    env = InterproceduralCFGWalkEnv(
        grammar,
        args.func,
        max_steps=args.max_steps,
        seed=args.seed,
    )
    full_intra = bool(getattr(args, "full_intra_trace", False)) or not bool(
        getattr(args, "dedupe_intra_trace", False)
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
    write_intra_traces_jsonl(
        out_dir / "intra_traces.jsonl",
        episodes,
        args.func,
        dedupe_intra=not full_intra,
    )
    write_summary_json(out_dir / "summary.json", summary)
    wpath = getattr(args, "write_canonical_intra", None)
    if wpath and episodes:
        ep0 = episodes[0]
        seq = intra_sequence_from_bb_path(
            args.func,
            ep0.entry_bb_id,
            [s.to_bb for s in ep0.steps],
            dedupe_consecutive=not full_intra,
        )
        dump_canonical_intra_json(
            wpath, function_name=args.func, sequence=seq, episode=None
        )
        print(f"Wrote canonical intra (episode 0): {wpath}", flush=True)
    print(summary.to_dict())
    return 0


def cmd_rollout_lstm(args: argparse.Namespace) -> int:
    import torch

    from trace_synthesizer.agents.checkpoint import (
        POLICY_TYPE_FEATURE_WINDOW_LSTM,
        load_policy_checkpoint,
    )
    from trace_synthesizer.agents.feature_window_lstm_agent import (
        FeatureWindowLSTMCfgAgent,
    )
    from trace_synthesizer.env.interproc_walk_env import InterproceduralCFGWalkEnv
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

    device = torch.device(args.device)
    grammar = CfgProgram.from_cfg_json(args.cfg)
    env = InterproceduralCFGWalkEnv(
        grammar,
        args.func,
        max_steps=args.max_steps,
        seed=args.seed,
        device=device,
    )
    policy = None
    meta: dict = {}
    ck = getattr(args, "checkpoint", None)
    if ck:
        policy, meta = load_policy_checkpoint(Path(ck), device=device)

    episodes = []
    rng_seed = args.seed
    for ep in range(args.episodes):
        rs = (rng_seed + ep) if rng_seed is not None else None
        if rs is not None:
            torch.manual_seed(rs)
        agent = FeatureWindowLSTMCfgAgent(
            grammar,
            args.func,
            env,
            device=device,
            action_select=args.action_select,
            sample_temperature=args.temperature,
            seed=rs,
            checkpoint_stem=None if policy is not None else ck,
            policy=policy,
        )
        if policy is None:
            policy = agent.policy
        episodes.append(rollout_episode(env, agent, reset_seed=rs))
    full_intra = bool(getattr(args, "full_intra_trace", False)) or not bool(
        getattr(args, "dedupe_intra_trace", False)
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_rollouts(episodes)
    write_episodes_jsonl(out_dir / "runs.jsonl", episodes, seed=args.seed or 0)
    write_intra_traces_jsonl(
        out_dir / "intra_traces.jsonl",
        episodes,
        args.func,
        dedupe_intra=not full_intra,
    )
    write_summary_json(out_dir / "summary.json", summary)
    wpath = getattr(args, "write_canonical_intra", None)
    if wpath and episodes:
        ep0 = episodes[0]
        seq = intra_sequence_from_bb_path(
            args.func,
            ep0.entry_bb_id,
            [s.to_bb for s in ep0.steps],
            dedupe_consecutive=not full_intra,
        )
        dump_canonical_intra_json(
            wpath, function_name=args.func, sequence=seq, episode=None
        )
        print(f"Wrote canonical intra (episode 0): {wpath}", flush=True)
    print(summary.to_dict())
    return 0


def cmd_rollout_hrl(args: argparse.Namespace) -> int:
    import torch

    from trace_synthesizer.agents.hrl_ppo_agent import HRLPPOCfgAgent
    from trace_synthesizer.env.cfg_reward_wrapper import CFGWalkRewardWrapper
    from trace_synthesizer.env.interproc_walk_env import InterproceduralCFGWalkEnv
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
    if getattr(args, "cpu_threads", None):
        torch.set_num_threads(int(args.cpu_threads))
    action_select = args.action_select
    temperature = float(args.temperature)
    top_p = float(args.top_p)
    if args.preset == "fast":
        action_select = "argmax"
        temperature = 1.0
        top_p = 1.0
    elif args.preset == "quality":
        action_select = "sample"
        # Keep quality preset genuinely stochastic to avoid greedy loop collapse.
        temperature = max(1.1, temperature)
        top_p = max(0.98, top_p)
    base_env = InterproceduralCFGWalkEnv(
        grammar,
        args.func,
        max_steps=args.max_steps,
        seed=args.seed,
    )
    loop_profile: dict | None = None
    if getattr(args, "loop_profile", None) is not None:
        from trace_synthesizer.rl.loop_profile import load_loop_profile

        loop_profile = load_loop_profile(Path(args.loop_profile))
    else:
        meta_path = Path(args.checkpoint).expanduser().resolve().with_suffix(".json")
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            lp = meta.get("loop_profile")
            if lp:
                lp_path = Path(str(lp)).expanduser().resolve()
                if lp_path.is_file():
                    from trace_synthesizer.rl.loop_profile import load_loop_profile

                    loop_profile = load_loop_profile(lp_path)
    env = CFGWalkRewardWrapper(base_env, grammar, args.func, loop_profile=loop_profile)

    window_back = int(getattr(args, "window_back", 1))
    from trace_synthesizer.env.feature_window_wrapper import FeatureWindowWrapper

    env = FeatureWindowWrapper(env, window_back=window_back)

    episodes = []
    rng_seed = args.seed
    batch_n = max(1, int(getattr(args, "batch_episodes", 1)))
    for start in range(0, int(args.episodes), batch_n):
        end = min(int(args.episodes), start + batch_n)
        for ep in range(start, end):
            rs = (rng_seed + ep) if rng_seed is not None else None
            agent = HRLPPOCfgAgent(
                checkpoint_stem=args.checkpoint,
                device=args.device,
                action_select=action_select,
                sample_temperature=temperature,
                top_p=top_p,
                seed=rs,
            )
            episodes.append(rollout_episode(env, agent, reset_seed=rs))
    full_intra = bool(getattr(args, "full_intra_trace", False)) or not bool(
        getattr(args, "dedupe_intra_trace", False)
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_rollouts(episodes)
    write_episodes_jsonl(out_dir / "runs.jsonl", episodes, seed=args.seed or 0)
    write_intra_traces_jsonl(
        out_dir / "intra_traces.jsonl",
        episodes,
        args.func,
        dedupe_intra=not full_intra,
    )
    write_summary_json(out_dir / "summary.json", summary)
    wpath = getattr(args, "write_canonical_intra", None)
    if wpath and episodes:
        ep0 = episodes[0]
        seq = intra_sequence_from_bb_path(
            args.func,
            ep0.entry_bb_id,
            [s.to_bb for s in ep0.steps],
            dedupe_consecutive=not full_intra,
        )
        dump_canonical_intra_json(
            wpath, function_name=args.func, sequence=seq, episode=None
        )
        print(f"Wrote canonical intra (episode 0): {wpath}", flush=True)
    print(summary.to_dict())
    return 0


def cmd_train_hrl_ppo(args: argparse.Namespace) -> int:
    from trace_synthesizer.rl.train_ppo import run_train_ppo

    report = run_train_ppo(args)
    print(json.dumps(report))
    return 0


def cmd_compute_loop_profile(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    cmd = [
        sys.executable,
        str(root / "scripts" / "compute_loop_profile.py"),
        "--cfg",
        str(args.cfg),
        "--func",
        str(args.func),
        "--out",
        str(args.out),
    ]
    for r in args.reference:
        cmd.extend(["--reference", str(r)])
    if args.reference_compressed:
        cmd.append("--reference-compressed")
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.stdout:
        print(cp.stdout, end="")
    if cp.returncode != 0:
        if cp.stderr:
            print(cp.stderr, file=sys.stderr, end="")
        return int(cp.returncode)
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
    m.add_argument(
        "--metrics-preserve-consecutive-bb",
        action="store_true",
        help="When loading compressed traces, keep consecutive same-BB events (edge / length metrics)",
    )
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
    r.add_argument(
        "--full-intra-trace",
        action="store_true",
        help="Deprecated: full BB stream is now the default; kept for compatibility",
    )
    r.add_argument(
        "--dedupe-intra-trace",
        action="store_true",
        help="Collapse consecutive identical BB in intra_traces.jsonl (hurts edge/hotpath metrics)",
    )
    r.set_defaults(handler=cmd_rollout_random)

    lstm = sub.add_parser(
        "rollout-lstm",
        help="LSTM policy rollouts for one function (same outputs as rollout-random)",
    )
    lstm.add_argument("--cfg", required=True)
    lstm.add_argument("--func", required=True)
    lstm.add_argument("--episodes", type=int, default=10)
    lstm.add_argument("--seed", type=int, default=None)
    lstm.add_argument(
        "--max-steps",
        type=int,
        default=10_000,
        help="Same semantics as rollout-random (0 = walk until CFG sink).",
    )
    lstm.add_argument("--out-dir", required=True)
    lstm.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Stem path to policy .pt + .json (from save_policy_checkpoint); optional if fresh random init",
    )
    lstm.add_argument(
        "--action-select",
        choices=("argmax", "sample"),
        default="argmax",
        help="How to pick an action from masked logits",
    )
    lstm.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Sampling temperature for --action-select sample (ignored for argmax).",
    )
    lstm.add_argument(
        "--device",
        default="cpu",
        help="torch device string (e.g. cpu, cuda)",
    )
    lstm.add_argument(
        "--write-canonical-intra",
        type=Path,
        default=None,
        help="Also write first episode as a single canonical intra JSON",
    )
    lstm.add_argument(
        "--full-intra-trace",
        action="store_true",
        help="Deprecated: full BB stream is now the default",
    )
    lstm.add_argument(
        "--dedupe-intra-trace",
        action="store_true",
        help="Collapse consecutive identical BB in intra_traces.jsonl",
    )
    lstm.set_defaults(handler=cmd_rollout_lstm)

    hrl = sub.add_parser(
        "rollout-hrl",
        help="PPO flat/hierarchical checkpoint rollouts for one function",
    )
    hrl.add_argument("--cfg", required=True)
    hrl.add_argument("--func", required=True)
    hrl.add_argument("--episodes", type=int, default=10)
    hrl.add_argument("--seed", type=int, default=None)
    hrl.add_argument(
        "--max-steps",
        type=int,
        default=10_000,
        help="Same semantics as rollout-random (0 = walk until CFG sink).",
    )
    hrl.add_argument("--out-dir", required=True)
    hrl.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Stem path to policy .pt + .json from train-hrl-ppo",
    )
    hrl.add_argument(
        "--loop-profile",
        type=Path,
        default=None,
        help="Optional loop_profile.json; default: use loop_profile path stored in checkpoint .json",
    )
    hrl.add_argument(
        "--action-select",
        choices=("argmax", "sample"),
        default="argmax",
    )
    hrl.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Sampling temperature when --action-select sample",
    )
    hrl.add_argument(
        "--top-p",
        type=float,
        default=1.0,
        help="Top-p nucleus filtering for sampling (<=1.0)",
    )
    hrl.add_argument(
        "--batch-episodes",
        type=int,
        default=1,
        help="Run episodes in chunks (host-level microbatch scheduling)",
    )
    hrl.add_argument(
        "--preset",
        choices=("default", "fast", "quality"),
        default="default",
        help="Inference preset: fast=argmax, quality=stochastic sample",
    )
    hrl.add_argument(
        "--cpu-threads",
        type=int,
        default=None,
        help="Optional torch CPU thread count for rollout",
    )
    hrl.add_argument("--device", default="cpu")
    hrl.add_argument(
        "--write-canonical-intra",
        type=Path,
        default=None,
        help="Also write first episode as a single canonical intra JSON",
    )
    hrl.add_argument(
        "--full-intra-trace",
        action="store_true",
        help="Deprecated: full BB stream is now the default",
    )
    hrl.add_argument(
        "--dedupe-intra-trace",
        action="store_true",
        help="Collapse consecutive identical BB in intra_traces.jsonl",
    )
    hrl.add_argument("--window-back", type=int, default=1)
    hrl.set_defaults(handler=cmd_rollout_hrl)

    tr = sub.add_parser(
        "train-hrl-ppo",
        help="Train flat or hierarchical PPO for CFG trace synthesis",
    )
    tr.add_argument("--cfg", type=Path, required=True)
    tr.add_argument("--func", required=True)
    tr.add_argument("--out-stem", type=Path, required=True)
    tr.add_argument("--device", default="cpu")
    tr.add_argument("--seed", type=int, default=42)
    tr.add_argument("--max-steps", type=int, default=10_000)
    tr.add_argument("--iterations", type=int, default=40)
    tr.add_argument("--steps-per-iter", type=int, default=4096)
    tr.add_argument("--epochs", type=int, default=4)
    tr.add_argument("--minibatch-size", type=int, default=512)
    tr.add_argument("--lr", type=float, default=3e-4)
    tr.add_argument("--gamma", type=float, default=0.99)
    tr.add_argument("--gae-lambda", type=float, default=0.95)
    tr.add_argument("--clip-coef", type=float, default=0.2)
    tr.add_argument("--vf-coef", type=float, default=0.5)
    tr.add_argument("--ent-coef", type=float, default=0.01)
    tr.add_argument("--max-grad-norm", type=float, default=0.5)
    tr.add_argument("--hidden", type=int, default=128)
    tr.add_argument("--hierarchical", action="store_true")
    tr.add_argument("--num-modes", type=int, default=4)
    tr.add_argument("--z-embed-dim", type=int, default=8)
    tr.add_argument("--manager-every", type=int, default=4)
    tr.add_argument("--pgo-log-scale", type=float, default=0.5)
    tr.add_argument("--invalid-action-penalty", type=float, default=-1.0)
    tr.add_argument("--repeat-bb-penalty-scale", type=float, default=0.0)
    tr.add_argument("--truncation-penalty", type=float, default=0.0)
    tr.add_argument("--terminal-kl-scale", type=float, default=0.0)
    tr.add_argument("--reference", type=Path, default=None)
    tr.add_argument("--reference-compressed", action="store_true")
    tr.add_argument(
        "--init-checkpoint",
        type=Path,
        default=None,
        help="Optional warm-start checkpoint stem (.pt/.json)",
    )
    tr.add_argument(
        "--freeze-mode",
        choices=("none", "head-only"),
        default="none",
        help="Parameter-freeze preset for adaptation",
    )
    tr.add_argument("--train-report", type=Path, default=None)
    tr.add_argument(
        "--tb-logdir",
        type=Path,
        default=None,
        help="If set, write TensorBoard scalars under this directory",
    )
    tr.add_argument(
        "--tb-run-name",
        default="train_hrl_ppo",
        help="TensorBoard run subdir name (used only with --tb-logdir)",
    )
    tr.add_argument(
        "--loop-profile",
        type=Path,
        default=None,
        help="Optional JSON from compute-loop-profile (adds loop obs + optional aux head)",
    )
    tr.add_argument(
        "--loop-timing-scale",
        type=float,
        default=0.0,
        help="Reward scale for matching loop-header visit counts to reference",
    )
    tr.add_argument(
        "--ref-edge-log-scale",
        type=float,
        default=0.0,
        help="Reward scale * log p_ref(action|bb) from loop_profile (needs --loop-profile)",
    )
    tr.add_argument(
        "--short-path-penalty-scale",
        type=float,
        default=0.0,
        help="Subtract at episode end when transition count << reference path_stats",
    )
    tr.add_argument(
        "--no-loop-proposal-defaults",
        action="store_true",
        help="With --loop-profile, do not auto-fill ref-edge / short-path / loop-timing scales",
    )
    tr.add_argument("--window-back", type=int, default=1)
    tr.add_argument("--aux-exit-head", type=int, choices=(0, 1), default=1)
    tr.add_argument("--aux-exit-coef", type=float, default=0.05)
    tr.add_argument("--bc-epochs", type=int, default=0)
    tr.add_argument("--bc-batch-size", type=int, default=64)
    tr.add_argument("--bc-aux-coef", type=float, default=0.1)
    tr.set_defaults(handler=cmd_train_hrl_ppo)

    clp = sub.add_parser(
        "compute-loop-profile",
        help="Compute loop/exit statistics JSON from CFG + reference trace(s)",
    )
    clp.add_argument("--cfg", type=Path, required=True)
    clp.add_argument("--func", required=True)
    clp.add_argument(
        "--reference",
        type=Path,
        action="append",
        required=True,
        help="Reference trace path (repeat for multiple)",
    )
    clp.add_argument("--reference-compressed", action="store_true")
    clp.add_argument("--out", type=Path, required=True)
    clp.set_defaults(handler=cmd_compute_loop_profile)

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
