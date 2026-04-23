"""Map real traces to (current_bb, successor_action_index) for supervised training."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from trace_synthesizer.core.grammar import CfgProgram, ordered_successors
from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv
from trace_synthesizer.features.block_features import BlockFeatures

if TYPE_CHECKING:
    from trace_synthesizer.runner.rollout import EpisodeRollout


def successor_action_index(
    grammar: CfgProgram,
    function_name: str,
    from_bb: int,
    to_bb: int,
) -> int | None:
    """
    Index into ``ordered_successors`` at ``from_bb`` that leads to ``to_bb``.

    Returns ``None`` if ``to_bb`` is not a successor of ``from_bb``.
    """
    block = grammar.function(function_name).block_by_id()[from_bb]
    succs = ordered_successors(block)
    for i, e in enumerate(succs):
        if e.target_id == to_bb:
            return i
    return None


def bb_path_from_rollout(ep: EpisodeRollout) -> list[int]:
    """Block ids visited in order (entry, then each ``to_bb``)."""
    out = [ep.entry_bb_id]
    for s in ep.steps:
        out.append(s.to_bb)
    return out


def action_mask_rows_for_bb_prefix(
    grammar: CfgProgram,
    function_name: str,
    bb_prefix: list[int],
    *,
    max_actions: int,
) -> np.ndarray:
    """
    Shape ``(len(bb_prefix), max_actions)`` bool: True for valid successor indices
    at each current block (same padding rule as ``CFGWalkEnv``).
    """
    fn = grammar.function(function_name)
    by_id = fn.block_by_id()
    rows = np.zeros((len(bb_prefix), max_actions), dtype=np.bool_)
    for i, bb in enumerate(bb_prefix):
        succs = ordered_successors(by_id[bb])
        n = min(len(succs), max_actions)
        rows[i, :n] = True
    return rows


def supervision_pairs_from_bb_path(
    grammar: CfgProgram, function_name: str, bb_path: list[int]
) -> list[tuple[int, int]]:
    """
    List of ``(from_bb, action_index)`` for each edge along ``bb_path``.

    Skips edges where the transition is not a valid CFG successor (returns
    partial supervision rather than raising).
    """
    pairs: list[tuple[int, int]] = []
    for i in range(len(bb_path) - 1):
        a = bb_path[i]
        b = bb_path[i + 1]
        idx = successor_action_index(grammar, function_name, a, b)
        if idx is not None:
            pairs.append((a, idx))
    return pairs


def supervision_pairs_from_intra_sequence(
    grammar: CfgProgram,
    function_name: str,
    sequence: list[dict[str, Any]],
) -> list[tuple[int, int]]:
    """
    Build supervision from canonical intra ``sequence`` entries ``{func, bb}``.

    Only consecutive pairs where both entries use ``function_name`` are used.
    """
    bbs: list[int] = []
    for ev in sequence:
        if str(ev.get("func")) != function_name:
            continue
        bbs.append(int(ev["bb"]))
    return supervision_pairs_from_bb_path(grammar, function_name, bbs)


def prefix_features_along_bb_path(
    env: CFGWalkEnv,
    grammar: CfgProgram,
    function_name: str,
    bb_path: list[int],
    *,
    reset_seed: int | None = 0,
) -> np.ndarray:
    """
    Stack ``observation['features']`` at each prefix block ``bb_path[0..len-2]``.

    Replays ``bb_path`` in the env using ``successor_action_index`` so rows align
    with teacher-forcing inputs ``bb_path[:-1]`` and targets from
    ``supervision_pairs_from_bb_path``.
    """
    if len(bb_path) < 2:
        return np.zeros(
            (0, int(env.observation_space["features"].shape[0])), dtype=np.float32
        )
    if reset_seed is not None:
        obs, _info = env.reset(seed=reset_seed)
    else:
        obs, _info = env.reset()
    rows: list[np.ndarray] = [np.asarray(obs["features"], dtype=np.float32)]
    for i in range(len(bb_path) - 1):
        a = bb_path[i]
        b = bb_path[i + 1]
        ai = successor_action_index(grammar, function_name, a, b)
        if ai is None:
            raise ValueError(f"No CFG edge {a} -> {b} for {function_name!r}")
        obs, _r, _term, _trunc, _info2 = env.step(ai)
        if i < len(bb_path) - 2:
            rows.append(np.asarray(obs["features"], dtype=np.float32))
    return np.stack(rows, axis=0)


GLOBAL_CFG_SUMMARY_DIM = 0


def global_cfg_summary_vector(grammar: CfgProgram, function_name: str) -> np.ndarray:
    """Fixed-size summary of the whole function CFG from static ``BlockFeatures`` only."""
    fn = grammar.function(function_name)
    mats = [
        BlockFeatures.from_block(b)
        .as_tensor()
        .detach()
        .cpu()
        .numpy()
        .astype(np.float32)
        for b in fn.blocks
    ]
    mean = np.mean(np.stack(mats, axis=0), axis=0)
    logn = np.array([np.log1p(len(fn.blocks)) / 10.0], dtype=np.float32)
    out = np.concatenate([mean, logn], axis=0)
    # Keep this dynamic so extending BlockFeatures doesn't break training.
    if out.shape[0] != (mean.shape[0] + 1):
        raise ValueError("invalid global CFG summary dim")
    return out


def successor_features_flat(
    grammar: CfgProgram,
    function_name: str,
    from_bb: int,
    succ_slots: int,
    feat_dim: int,
) -> np.ndarray:
    """Concat ``BlockFeatures`` of up to ``succ_slots`` successors (ordered), zero-padded."""
    if succ_slots <= 0:
        return np.zeros(0, dtype=np.float32)
    fn = grammar.function(function_name)
    by_id = fn.block_by_id()
    succs = ordered_successors(by_id[from_bb])
    parts: list[np.ndarray] = []
    for j in range(succ_slots):
        if j < len(succs):
            tb = by_id[succs[j].target_id]
            vec = (
                BlockFeatures.from_block(tb)
                .as_tensor()
                .detach()
                .cpu()
                .numpy()
                .astype(np.float32)
            )
            parts.append(vec)
        else:
            parts.append(np.zeros(feat_dim, dtype=np.float32))
    return np.concatenate(parts, axis=0)


def trace_context_tensors_for_bb_path(
    env: CFGWalkEnv,
    grammar: CfgProgram,
    function_name: str,
    bb_path: list[int],
    *,
    window_back: int,
    succ_feat_slots: int,
    max_actions: int,
    use_global_summary: bool,
    reset_seed: int | None = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Rows for the trace LSTM: back-window of visited block features + static one-hop
    successor block features + optional whole-CFG summary vector (constant across steps).
    """
    fd = int(env.observation_space["features"].shape[0])
    gdim = (fd + 1) if use_global_summary else 0
    in_dim = window_back * fd + succ_feat_slots * fd + gdim
    pairs = supervision_pairs_from_bb_path(grammar, function_name, bb_path)
    if len(pairs) < 1:
        return (
            np.zeros((0, in_dim), dtype=np.float32),
            np.zeros((0, max_actions), dtype=bool),
            np.zeros((0,), dtype=np.int64),
        )
    if len(pairs) != len(bb_path) - 1:
        raise ValueError(
            f"Incomplete CFG walk: {len(pairs)} pairs for path len {len(bb_path)}"
        )
    global_vec = (
        global_cfg_summary_vector(grammar, function_name)
        if use_global_summary
        else np.zeros(0, dtype=np.float32)
    )
    feat_rows = prefix_features_along_bb_path(
        env, grammar, function_name, bb_path, reset_seed=reset_seed
    )
    masks = action_mask_rows_for_bb_prefix(
        grammar, function_name, bb_path[:-1], max_actions=max_actions
    )
    t, fd2 = feat_rows.shape
    if fd2 != fd:
        raise ValueError("feature dim mismatch")
    out = np.zeros((t, in_dim), dtype=np.float32)
    for ti in range(t):
        start = max(0, ti - window_back + 1)
        chunk = feat_rows[start : ti + 1]
        flat_b = chunk.reshape(-1)
        back = np.zeros(window_back * fd, dtype=np.float32)
        back[-len(flat_b) :] = flat_b
        bb_from = bb_path[ti]
        succ_flat = successor_features_flat(
            grammar, function_name, bb_from, succ_feat_slots, fd
        )
        out[ti] = np.concatenate([back, succ_flat, global_vec], axis=0)
    targets = np.array([a for _, a in pairs], dtype=np.int64)
    return out, masks.astype(np.bool_), targets


def feature_window_tensors_for_bb_path(
    env: CFGWalkEnv,
    grammar: CfgProgram,
    function_name: str,
    bb_path: list[int],
    *,
    window: int,
    max_actions: int,
    reset_seed: int | None = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Backward-compatible: back-window only (no successor concat, no global summary)."""
    return trace_context_tensors_for_bb_path(
        env,
        grammar,
        function_name,
        bb_path,
        window_back=window,
        succ_feat_slots=0,
        max_actions=max_actions,
        use_global_summary=False,
        reset_seed=reset_seed,
    )
