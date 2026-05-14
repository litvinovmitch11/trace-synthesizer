"""Reference-trace shaping helpers (proposal-aligned dense + terminal terms)."""

from __future__ import annotations

from trace_synthesizer.rl.rewards import (
    reference_edge_log_reward,
    terminal_short_path_penalty,
)


def test_reference_edge_log_reward_prefers_high_p_action() -> None:
    prof = {"edge_action_p": {"0": [0.2, 0.8]}}
    lo = reference_edge_log_reward(prof, 0, 0, scale=1.0)
    hi = reference_edge_log_reward(prof, 0, 1, scale=1.0)
    assert hi > lo
    assert reference_edge_log_reward(prof, 0, 1, scale=0.0) == 0.0


def test_reference_edge_log_reward_missing_profile() -> None:
    assert reference_edge_log_reward({}, 0, 0, scale=1.0) == 0.0


def test_terminal_short_path_penalty() -> None:
    prof = {"path_stats": {"mean_transitions": 100.0, "p10_transitions": 50.0}}
    assert terminal_short_path_penalty(prof, 2, scale=0.1) > 0.0
    assert terminal_short_path_penalty(prof, 200, scale=0.1) == 0.0
    assert terminal_short_path_penalty(prof, 2, scale=0.0) == 0.0


def test_terminal_short_path_penalty_tiny_mean_skipped() -> None:
    prof = {"path_stats": {"mean_transitions": 2.0, "p10_transitions": 1.0}}
    assert terminal_short_path_penalty(prof, 0, scale=1.0) == 0.0
