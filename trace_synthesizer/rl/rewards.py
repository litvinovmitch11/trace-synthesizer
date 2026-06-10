"""Dense PGO shaping and optional terminal KL vs reference BB histogram."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from trace_synthesizer.core.grammar import (
    CfgProgram,
    normalized_successor_weights,
    ordered_successors,
)


def counts_to_probabilities(
    counts: Counter[int], support: set[int], epsilon: float
) -> dict[int, float]:
    if not support:
        return {}
    total = sum(float(counts.get(k, 0)) + float(epsilon) for k in support)
    return {k: (float(counts.get(k, 0)) + float(epsilon)) / total for k in support}


def kl_divergence(p: dict[int, float], q: dict[int, float], support: set[int]) -> float:
    acc = 0.0
    for k in support:
        pi = p[k]
        qi = q[k]
        if pi <= 0.0:
            continue
        if qi <= 0.0:
            return math.inf
        acc += pi * math.log(pi / qi)
    return acc


@dataclass(frozen=True)
class RewardConfig:
    """Weights for RL reward terms (proposal III.C)."""

    pgo_log_scale: float = 0.5
    invalid_action_penalty: float = -1.0
    repeat_bb_penalty_scale: float = 0.0
    """Per-step penalty scaled by repeated visits of current BB (anti-loop-collapse)."""

    truncation_penalty: float = 0.0
    """Applied once when episode ends by truncation instead of natural terminal."""

    terminal_kl_scale: float = 0.0
    """If > 0, add ``-terminal_kl_scale * KL(P_ref || Q_episode)`` on episode end."""

    loop_timing_scale: float = 0.0
    """If > 0, bonus when visits to a loop header match reference mean (see ``loop_timing_reward``)."""

    ref_edge_log_scale: float = 0.0
    """If > 0, add ``scale * log p_ref(action|from_bb)`` from ``loop_profile['edge_action_p']``."""

    short_path_penalty_scale: float = 0.0
    """If > 0, subtract penalty at episode end when transition count is far below reference ``path_stats``."""

    epsilon: float = 1e-6


def transition_pgo_log_reward(
    grammar: CfgProgram,
    function_name: str,
    from_bb: int,
    action_index: int,
    *,
    scale: float,
    epsilon: float = 1e-8,
) -> float:
    """
    Dense shaping: ``scale * log p_PGO(edge)`` for the taken successor index.

    Encourages alignment with profile without requiring a full trajectory model.
    """
    block = grammar.function(function_name).block_by_id()[from_bb]
    w = normalized_successor_weights(block)
    succs = ordered_successors(block)
    if action_index < 0 or action_index >= len(succs):
        return 0.0
    p = float(w[action_index]) if action_index < len(w) else 0.0
    p = max(p, epsilon)
    return float(scale) * math.log(p)


def reference_edge_log_reward(
    loop_profile: dict[str, Any],
    from_bb: int,
    action_index: int,
    *,
    scale: float,
    epsilon: float = 1e-8,
) -> float:
    """Dense shaping from empirical edge distribution in ``compute_loop_profile``."""
    if scale <= 0.0:
        return 0.0
    rows = loop_profile.get("edge_action_p")
    if not isinstance(rows, dict):
        return 0.0
    row = rows.get(str(int(from_bb)))
    if not isinstance(row, list) or action_index < 0 or action_index >= len(row):
        return 0.0
    p = float(row[action_index])
    p = max(p, epsilon)
    return float(scale) * math.log(p)


def terminal_short_path_penalty(
    loop_profile: dict[str, Any],
    n_transitions: int,
    *,
    scale: float,
) -> float:
    """
    Non-negative penalty (subtract from return) when the episode used far fewer
    transitions than reference paths suggest for this function.
    """
    if scale <= 0.0:
        return 0.0
    ps = loop_profile.get("path_stats")
    if not isinstance(ps, dict):
        return 0.0
    mean_t = float(ps.get("mean_transitions", 0.0))
    if mean_t < 4.0:
        return 0.0
    p10 = float(ps.get("p10_transitions", 0.0))
    thr = max(p10, 0.05 * mean_t, 3.0)
    if float(n_transitions) >= thr:
        return 0.0
    gap = (thr - float(n_transitions)) / thr
    return float(scale) * gap


def episode_bb_histogram(
    visit_counts: Counter[int], bb_ids_support: set[int], epsilon: float
) -> dict[int, float]:
    """Normalized visit distribution over BB ids (Laplace on support)."""
    return counts_to_probabilities(visit_counts, bb_ids_support, epsilon)


def terminal_bb_kl_reward(
    visit_counts: Counter[int],
    ref_bb_hist: Counter[int],
    *,
    epsilon: float,
    scale: float,
) -> float:
    """
    Bonus at terminal: ``-scale * KL(P_ref || Q_episode)`` (smaller KL → less negative).

    Support is the union of BB ids seen in reference or episode counts.
    """
    if scale <= 0.0:
        return 0.0
    support = set(ref_bb_hist.keys()) | set(visit_counts.keys())
    if not support:
        return 0.0
    p = counts_to_probabilities(ref_bb_hist, support, epsilon)
    q = counts_to_probabilities(visit_counts, support, epsilon)
    kl = kl_divergence(p, q, support)
    if math.isinf(kl):
        return -float(scale) * 1e3
    return -float(scale) * float(kl)


def reference_bb_histogram_from_paths(
    paths: list[list[int]], *, epsilon: float = 1e-6
) -> tuple[Counter[int], set[int]]:
    """Aggregate BB visits from a list of BB-id paths (intra one function)."""
    c: Counter[int] = Counter()
    for path in paths:
        for bb in path:
            c[int(bb)] += 1
    support = set(c.keys()) if c else set()
    if not support:
        support = {0}
    return c, support
