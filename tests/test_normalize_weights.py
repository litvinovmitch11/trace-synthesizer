"""Smoke tests for PGO weight normalization."""

from trace_synthesizer.core.grammar import (
    normalized_successor_weights,
    ordered_successors,
)
from trace_synthesizer.domain.program import BasicBlock, SuccessorEdge


def test_uniform_when_all_probs_none() -> None:
    b = BasicBlock(
        id=0,
        name="a",
        is_entry=True,
        instr_count=1,
        has_call=False,
        call_target=None,
        successors=(
            SuccessorEdge(1, None, True),
            SuccessorEdge(2, None, False),
        ),
    )
    w = normalized_successor_weights(b)
    assert len(w) == 2
    assert abs(sum(w) - 1.0) < 1e-6
    assert abs(w[0] - w[1]) < 1e-6


def test_renorm_when_probs_sum_not_one() -> None:
    b = BasicBlock(
        id=0,
        name="a",
        is_entry=True,
        instr_count=1,
        has_call=False,
        call_target=None,
        successors=(
            SuccessorEdge(1, 0.8, True),
            SuccessorEdge(2, 0.4, False),
        ),
    )
    w = normalized_successor_weights(b)
    assert abs(sum(w) - 1.0) < 1e-6
    assert w[0] > w[1]
