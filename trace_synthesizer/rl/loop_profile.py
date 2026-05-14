"""Loop / exit statistics from real traces + CFG for RL observation and rewards."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from trace_synthesizer.core.grammar import CfgProgram, ordered_successors
from trace_synthesizer.domain.program import FunctionCFG


def _paths_to_bb_sequences(
    paths: Iterable[list[tuple[str, int]]], function_name: str
) -> list[list[int]]:
    out: list[list[int]] = []
    for p in paths:
        seq = [int(bb) for fn, bb in p if fn == function_name]
        if len(seq) >= 2:
            out.append(seq)
    return out


def load_reference_paths_as_bb_sequences(
    *,
    ref: Path,
    ref_compressed: bool,
    function_name: str,
) -> list[list[int]]:
    # Local imports avoid pulling ``metrics`` package (and env/agents) during ``rl`` init.
    from trace_synthesizer.metrics.loaders import (
        load_path_from_compressed_trace,
        load_path_from_intra_trace_json,
        load_paths_from_intra_traces_jsonl,
    )

    if ref_compressed:
        # Full consecutive BB stream (including self-loops) for empirical edge / length stats.
        p = load_path_from_compressed_trace(
            ref, function_name, dedupe_consecutive=False
        )
        return _paths_to_bb_sequences([p], function_name)
    if ref.suffix.lower() == ".jsonl":
        paths = load_paths_from_intra_traces_jsonl(ref)
        return _paths_to_bb_sequences(paths, function_name)
    p = load_path_from_intra_trace_json(ref)
    return _paths_to_bb_sequences([p], function_name)


def _pctl(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    idx = min(len(sorted_vals) - 1, max(0, int(math.ceil(q * (len(sorted_vals) - 1)))))
    return float(sorted_vals[idx])


def compute_loop_profile(
    grammar: CfgProgram,
    function_name: str,
    bb_paths: list[list[int]],
) -> dict[str, Any]:
    """
    Build a JSON-serializable profile from one or more intra-function BB paths.

    Includes per-loop-header visit statistics and empirical exit-next labels
    per (from_bb, action_index) aligned with ``ordered_successors``.
    """
    fn = grammar.function(function_name)
    by_id = fn.block_by_id()

    header_ids = [b.id for b in fn.blocks if b.is_loop_header]
    visits_per_path_per_h: list[dict[int, int]] = []
    per_bb_visits: list[dict[int, int]] = []

    for path in bb_paths:
        vh: dict[int, int] = {h: 0 for h in header_ids}
        vb: dict[int, int] = defaultdict(int)
        for bb in path:
            vb[int(bb)] += 1
            if int(bb) in vh:
                vh[int(bb)] += 1
        visits_per_path_per_h.append(vh)
        per_bb_visits.append(dict(vb))

    loop_headers: dict[str, dict[str, float]] = {}
    for h in header_ids:
        counts = [float(vh.get(h, 0)) for vh in visits_per_path_per_h]
        counts.sort()
        loop_headers[str(h)] = {
            "mean_visits": float(sum(counts) / len(counts)) if counts else 0.0,
            "p90_visits": _pctl(counts, 0.9),
            "p50_visits": _pctl(counts, 0.5),
        }

    per_bb: dict[str, dict[str, float]] = {}
    all_bbs = {bb for path in bb_paths for bb in path}
    for bb in sorted(all_bbs):
        counts = [float(v.get(int(bb), 0)) for v in per_bb_visits]
        counts.sort()
        per_bb[str(bb)] = {
            "mean_visits": float(sum(counts) / len(counts)) if counts else 0.0,
            "p90_visits": _pctl(counts, 0.9),
        }

    # Empirical exit-next: depth dropped on edge, or exiting block heuristic.
    exit_pair_counts: dict[tuple[int, int], tuple[int, int]] = defaultdict(lambda: (0, 0))
    exit_marginal: dict[int, tuple[int, int]] = defaultdict(lambda: (0, 0))

    for path in bb_paths:
        for u, v in zip(path[:-1], path[1:]):
            u = int(u)
            v = int(v)
            bu, bv = by_id.get(u), by_id.get(v)
            if bu is None or bv is None:
                continue
            succs = ordered_successors(bu)
            action_idx = None
            for i, e in enumerate(succs):
                if int(e.target_id) == int(v):
                    action_idx = i
                    break
            if action_idx is None:
                continue
            # Align with ``exit_aux_label``: primarily LLVM loop-depth drop on edge.
            y = 1 if int(bv.loop_depth) < int(bu.loop_depth) else 0
            a, b = exit_pair_counts[(u, action_idx)]
            exit_pair_counts[(u, action_idx)] = (a + y, b + 1)
            c, d = exit_marginal[u]
            exit_marginal[u] = (c + y, d + 1)

    exit_action: dict[str, list[dict[str, float]]] = {}
    for bb in fn.blocks:
        n = len(ordered_successors(bb))
        row: list[dict[str, float]] = []
        for j in range(n):
            hits, tot = exit_pair_counts.get((bb.id, j), (0, 0))
            row.append(
                {
                    "p_exit": float(hits / tot) if tot > 0 else 0.0,
                    "n": float(tot),
                }
            )
        exit_action[str(bb.id)] = row

    exit_marginal_json: dict[str, float] = {}
    for bid, (hits, tot) in exit_marginal.items():
        exit_marginal_json[str(int(bid))] = float(hits / tot) if tot > 0 else 0.0

    # Empirical (from_bb, action_index) frequencies aligned with ordered_successors.
    edge_action_counts: dict[tuple[int, int], int] = defaultdict(int)
    for path in bb_paths:
        for u, v in zip(path[:-1], path[1:]):
            u = int(u)
            v = int(v)
            bu = by_id.get(u)
            if bu is None:
                continue
            succs = ordered_successors(bu)
            action_idx = None
            for i, e in enumerate(succs):
                if int(e.target_id) == int(v):
                    action_idx = i
                    break
            if action_idx is None:
                continue
            edge_action_counts[(u, action_idx)] += 1

    lap = 1e-6
    edge_action_p: dict[str, list[float]] = {}
    for bb in fn.blocks:
        succs = ordered_successors(bb)
        n = len(succs)
        if n == 0:
            edge_action_p[str(bb.id)] = []
            continue
        counts = [float(edge_action_counts.get((bb.id, j), 0)) for j in range(n)]
        tot_e = sum(counts)
        if tot_e <= 0.0:
            edge_action_p[str(bb.id)] = [1.0 / n] * n
        else:
            edge_action_p[str(bb.id)] = [
                (c + lap) / (tot_e + lap * n) for c in counts
            ]

    trans_lens = sorted(max(0, len(p) - 1) for p in bb_paths if len(p) >= 1)
    if not trans_lens:
        trans_lens = [0]
    trans_f = [float(x) for x in trans_lens]
    path_stats: dict[str, float] = {
        "mean_transitions": float(sum(trans_f) / len(trans_f)),
        "p10_transitions": _pctl(trans_f, 0.1),
        "p50_transitions": _pctl(trans_f, 0.5),
        "p90_transitions": _pctl(trans_f, 0.9),
    }

    return {
        "schema_version": 1,
        "function": function_name,
        "n_paths": len(bb_paths),
        "loop_headers": loop_headers,
        "per_bb": per_bb,
        "exit_action": exit_action,
        "exit_marginal": exit_marginal_json,
        "edge_action_p": edge_action_p,
        "path_stats": path_stats,
    }


def save_loop_profile(path: Path, profile: dict[str, Any]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def load_loop_profile(path: Path) -> dict[str, Any]:
    raw = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    if int(raw.get("schema_version", 0)) != 1:
        raise ValueError(f"{path}: expected schema_version=1")
    return raw


def loop_context_features(
    *,
    from_bb: int,
    visit_bb: dict[int, int],
    last_loop_header: int | None,
    profile: dict[str, Any],
) -> tuple[float, float, float]:
    """
    Three floats appended to RL extras when a loop profile is present:

    1) relative trip vs p90 for last seen loop header
    2) normalized mean visits prior for that header
    3) empirical marginal P(exit) at ``from_bb``
    """
    rel_trip = 0.0
    mean_norm = 0.0
    if last_loop_header is not None:
        lh = str(int(last_loop_header))
        stats = profile.get("loop_headers", {}).get(lh)
        if stats:
            trips = float(visit_bb.get(int(last_loop_header), 0))
            p90 = max(1e-6, float(stats.get("p90_visits", 1.0)))
            mean_v = max(1e-6, float(stats.get("mean_visits", 1.0)))
            rel_trip = min(1.0, trips / p90)
            mean_norm = min(1.0, math.log1p(mean_v) / math.log1p(p90))

    exit_prior = float(profile.get("exit_marginal", {}).get(str(int(from_bb)), 0.0))
    exit_prior = max(0.0, min(1.0, exit_prior))
    return rel_trip, mean_norm, exit_prior


def exit_aux_label(from_bb: int, to_bb: int, fn: FunctionCFG) -> float:
    """Supervision target: loop nest shallows on this edge (matches profile stats)."""
    by_id = fn.block_by_id()
    bu, bv = by_id.get(int(from_bb)), by_id.get(int(to_bb))
    if bu is None or bv is None:
        return 0.0
    return 1.0 if int(bv.loop_depth) < int(bu.loop_depth) else 0.0


def rl_base_extras(
    *,
    current_bb: int,
    visit_bb: dict[int, int] | Counter[int],
    episode_steps: int,
    call_depth: float,
    max_steps: int,
) -> np.ndarray:
    """First four RL tail dims (visit / length / call / reserved)."""
    vc = float(visit_bb[current_bb])  # type: ignore[index]
    len_norm = float(episode_steps) / float(max_steps) if max_steps > 0 else 0.0
    return np.array(
        [
            min(1.0, np.log1p(vc) / 5.0),
            len_norm,
            float(call_depth),
            0.0,
        ],
        dtype=np.float32,
    )


def pack_actor_observation_features(
    grammar: CfgProgram,
    function_name: str,
    current_bb: int,
    *,
    visit_bb: dict[int, int] | Counter[int],
    episode_steps: int,
    last_loop_header: int | None,
    loop_profile: dict[str, Any] | None,
    max_steps: int,
    call_depth: float = 0.0,
    device: Any = None,
) -> np.ndarray:
    """
    Full observation feature vector matching ``CFGWalkRewardWrapper`` (base + tail).
    Used for BC pretraining on reference paths without stepping the env.
    """
    from trace_synthesizer.features.block_features import BlockFeatures

    fn = grammar.function(function_name)
    block = fn.block_by_id()[int(current_bb)]
    feat = BlockFeatures.from_block(block).as_tensor(device=device)
    base = feat.detach().cpu().numpy().astype(np.float32).reshape(-1)
    tail = rl_base_extras(
        current_bb=int(current_bb),
        visit_bb=visit_bb,
        episode_steps=episode_steps,
        call_depth=call_depth,
        max_steps=max_steps,
    )
    if loop_profile is None:
        return np.concatenate([base, tail], axis=0).astype(np.float32)
    rel, mn, ex = loop_context_features(
        from_bb=int(current_bb),
        visit_bb=dict(visit_bb),
        last_loop_header=last_loop_header,
        profile=loop_profile,
    )
    loop_tail = np.array([rel, mn, ex], dtype=np.float32)
    return np.concatenate([base, tail, loop_tail], axis=0).astype(np.float32)


def loop_timing_reward(
    *,
    to_bb: int,
    visit_bb: dict[int, int],
    profile: dict[str, Any],
    by_id: dict[int, Any],
    scale: float,
) -> float:
    """Gaussian bump when visits to a loop header match reference mean (scale 0 disables)."""
    if scale <= 0.0:
        return 0.0
    b = by_id.get(int(to_bb))
    if b is None or not bool(b.is_loop_header):
        return 0.0
    h = int(to_bb)
    stats = profile.get("loop_headers", {}).get(str(h))
    if not stats:
        return 0.0
    trips = float(visit_bb.get(h, 0))
    mean_v = float(stats.get("mean_visits", 0.0))
    p90 = max(1.0, float(stats.get("p90_visits", mean_v + 1.0)))
    sigma = 0.25 * p90 + 1e-6
    err = (trips - mean_v) / sigma
    return float(scale) * math.exp(-err * err)
