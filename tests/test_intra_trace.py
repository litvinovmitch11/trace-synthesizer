"""Canonical intra-function trace extraction and deduplication."""

from trace_synthesizer.io.intra_trace import (
    dedupe_consecutive_func_bb,
    intra_sequence_from_bb_path,
    intra_sequence_from_compressed,
)


def test_dedupe_consecutive() -> None:
    pairs = [("main", 0), ("main", 0), ("main", 1), ("main", 1), ("main", 1)]
    assert dedupe_consecutive_func_bb(pairs) == [("main", 0), ("main", 1)]


def test_intra_from_compressed_filters_and_dedupes() -> None:
    compressed = [
        {"func": "main", "bb": 0},
        {"func": "other", "bb": 3},
        {"func": "main", "bb": 0},
        {"func": "main", "bb": 0},
        {"func": "main", "bb": 1},
    ]
    seq = intra_sequence_from_compressed(compressed, "main")
    assert seq == [{"func": "main", "bb": 0}, {"func": "main", "bb": 1}]


def test_intra_from_bb_path() -> None:
    seq = intra_sequence_from_bb_path("main", 0, [1, 1])
    assert seq == [{"func": "main", "bb": 0}, {"func": "main", "bb": 1}]


def test_trivial_bb_path() -> None:
    assert intra_sequence_from_bb_path("main", 0, []) == [{"func": "main", "bb": 0}]
