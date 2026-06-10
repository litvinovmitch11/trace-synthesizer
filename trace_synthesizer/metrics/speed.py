"""Wall-clock timing for synthetic trace generation (proposal metric 3)."""

from __future__ import annotations

import time
from pathlib import Path

from trace_synthesizer.agents.random_pgo import RandomPGOAgent
from trace_synthesizer.core.grammar import CfgProgram
from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv
from trace_synthesizer.runner.rollout import rollout_episode


def benchmark_rollout_seconds(
    cfg_path: str | Path,
    function_name: str,
    *,
    n_episodes: int,
    max_steps: int,
    seed: int | None,
) -> float:
    """Wall-clock seconds for ``n_episodes`` synthetic rollouts (proposal III.D)."""
    stats = benchmark_random_rollouts(
        cfg_path,
        function_name,
        n_episodes=n_episodes,
        max_steps=max_steps,
        seed=seed,
    )
    return float(stats["seconds"])


def benchmark_random_rollouts(
    cfg_path: str | Path,
    function_name: str,
    *,
    n_episodes: int,
    max_steps: int,
    seed: int | None,
) -> dict[str, float | int]:
    """
    Time ``n_episodes`` of ``rollout_episode`` with ``RandomPGOAgent``.

    DynamoRIO collection time is not measured here; compare offline using
    ``speedup = t_dynamo / seconds`` when ``t_dynamo`` is known.
    """
    grammar = CfgProgram.from_cfg_json(cfg_path)
    env = CFGWalkEnv(grammar, function_name, max_steps=max_steps, seed=seed)
    t0 = time.perf_counter()
    for i in range(n_episodes):
        rs = (seed + i) if seed is not None else None
        agent = RandomPGOAgent(grammar, function_name, seed=rs)
        rollout_episode(env, agent, reset_seed=rs)
    elapsed = time.perf_counter() - t0
    return {
        "n_episodes": n_episodes,
        "seconds": float(elapsed),
        "episodes_per_second": (
            float(n_episodes / elapsed) if elapsed > 0 else float("inf")
        ),
    }


def speedup_vs_dynamo(
    synthetic_seconds_for_n: float, dynamo_seconds_for_n: float, n: int
) -> dict[str, float]:
    """``n`` must be the same for both measurements (e.g. 1000)."""
    if synthetic_seconds_for_n <= 0:
        raise ValueError("synthetic_seconds_for_n must be positive")
    if dynamo_seconds_for_n < 0:
        raise ValueError("dynamo_seconds_for_n must be non-negative")
    return {
        "speedup_dynamo_over_synthetic": float(
            dynamo_seconds_for_n / synthetic_seconds_for_n
        ),
        "synthetic_seconds_for_n": float(synthetic_seconds_for_n),
        "dynamo_seconds_for_n": float(dynamo_seconds_for_n),
        "n": float(n),
    }
