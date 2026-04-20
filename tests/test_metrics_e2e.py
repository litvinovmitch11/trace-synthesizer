"""End-to-end: complex CFG, rollouts, metrics CLI, speed bench."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from trace_synthesizer.core.grammar import CfgProgram
from trace_synthesizer.metrics.compare import run_metrics
from trace_synthesizer.metrics.loaders import load_paths_from_intra_traces_jsonl
from trace_synthesizer.metrics.speed import benchmark_random_rollouts
from trace_synthesizer.metrics.types import MetricContext
from trace_synthesizer.runner.rollout import rollout_episode
from trace_synthesizer.runner.writers import write_intra_traces_jsonl

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPLEX_CFG = REPO_ROOT / "examples" / "benchmark_complex" / "main.cfg.json"


def test_complex_cfg_loads() -> None:
    g = CfgProgram.from_cfg_json(COMPLEX_CFG)
    assert len(g.function("main").blocks) == 17


def test_complex_cfg_random_walk_terminates_and_varies() -> None:
    from trace_synthesizer.agents.random_pgo import RandomPGOAgent
    from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv

    grammar = CfgProgram.from_cfg_json(COMPLEX_CFG)
    env = CFGWalkEnv(grammar, "main", max_steps=5000, seed=0)
    lengths = set()
    for ep in range(30):
        agent = RandomPGOAgent(grammar, "main", seed=ep)
        r = rollout_episode(env, agent, reset_seed=ep)
        assert r.termination in ("terminated", "truncated", "trivial_terminal")
        lengths.add(r.length)
    assert max(lengths) >= 3


def test_metrics_on_rollout_jsonl(tmp_path: Path) -> None:
    from trace_synthesizer.agents.random_pgo import RandomPGOAgent
    from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv

    grammar = CfgProgram.from_cfg_json(COMPLEX_CFG)
    env = CFGWalkEnv(grammar, "main", max_steps=2000, seed=99)
    ref_episodes = []
    cand_episodes = []
    for i in range(25):
        ref_episodes.append(
            rollout_episode(
                env,
                RandomPGOAgent(grammar, "main", seed=1000 + i),
                reset_seed=1000 + i,
            )
        )
    for i in range(60):
        cand_episodes.append(
            rollout_episode(
                env,
                RandomPGOAgent(grammar, "main", seed=2000 + i),
                reset_seed=2000 + i,
            )
        )
    ref_jsonl = tmp_path / "ref.jsonl"
    cand_jsonl = tmp_path / "cand.jsonl"
    write_intra_traces_jsonl(ref_jsonl, ref_episodes, "main")
    write_intra_traces_jsonl(cand_jsonl, cand_episodes, "main")
    ref_paths = load_paths_from_intra_traces_jsonl(ref_jsonl)
    cand_paths = load_paths_from_intra_traces_jsonl(cand_jsonl)
    ctx = MetricContext(function_name="main", top_k=32, ngram_min=2, ngram_max=4)
    results = run_metrics(ref_paths, cand_paths, ctx)
    assert len(results) == 3
    for r in results:
        assert r.value is not None
        assert r.value == r.value  # not NaN


def test_benchmark_speed_smoke() -> None:
    stats = benchmark_random_rollouts(
        COMPLEX_CFG,
        "main",
        n_episodes=8,
        max_steps=500,
        seed=42,
    )
    assert stats["n_episodes"] == 8
    assert float(stats["seconds"]) > 0.0


@pytest.mark.parametrize("cmd", ["metrics-compare", "metrics-bench-speed"])
def test_metrics_cli_invokes(cmd: str, tmp_path: Path) -> None:
    from trace_synthesizer.agents.random_pgo import RandomPGOAgent
    from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv

    grammar = CfgProgram.from_cfg_json(COMPLEX_CFG)
    env = CFGWalkEnv(grammar, "main", max_steps=800, seed=0)
    episodes = [
        rollout_episode(env, RandomPGOAgent(grammar, "main", seed=i), reset_seed=i)
        for i in range(12)
    ]
    jsonl = tmp_path / "c.jsonl"
    write_intra_traces_jsonl(jsonl, episodes, "main")
    first = json.loads(jsonl.read_text(encoding="utf-8").splitlines()[0])
    ref_path = tmp_path / "ref.json"
    ref_path.write_text(json.dumps(first), encoding="utf-8")
    out = tmp_path / "report.json"
    if cmd == "metrics-compare":
        argv = [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "metrics-compare",
            "--reference",
            str(ref_path),
            "--candidate",
            str(jsonl),
            "--func",
            "main",
            "--out",
            str(out),
        ]
    else:
        argv = [
            sys.executable,
            "-m",
            "trace_synthesizer",
            "metrics-bench-speed",
            "--cfg",
            str(COMPLEX_CFG),
            "--func",
            "main",
            "--n-episodes",
            "6",
            "--max-steps",
            "400",
            "--seed",
            "7",
            "--out",
            str(out),
        ]
    subprocess.run(argv, check=True, cwd=str(REPO_ROOT))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data
