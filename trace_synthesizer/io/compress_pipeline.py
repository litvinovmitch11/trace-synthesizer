"""Compress RVA instruction trace to BB sequence and validate against CFG."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from trace_synthesizer.core.grammar import CfgProgram, TransitionIndex
from trace_synthesizer.domain.errors import EmptyTraceError
from trace_synthesizer.io.bb_addr_map import BbAddressMap
from trace_synthesizer.io.instruction_trace import read_rva_trace

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompressionStats:
    total_instructions: int
    unmapped_instructions: int
    compressed_length: int
    valid_intra: int
    inter_procedural: int
    invalid_transitions: int


@dataclass(frozen=True)
class CompressionResult:
    """Output of compress + validate."""

    stats: CompressionStats
    compressed_trace: tuple[dict[str, int | str], ...]
    success: bool


def compress_bb_sequence(
    trace_rvas: Iterable[int],
    bb_map: BbAddressMap,
) -> tuple[list[tuple[str, int]], int]:
    """Map RVAs to (func, bb_id), drop consecutive duplicates. Returns (sequence, unmapped)."""
    bb_sequence: list[tuple[str, int]] = []
    unmapped = 0
    for rva in trace_rvas:
        func, bb_id = bb_map.lookup(rva)
        if func is None or bb_id is None:
            unmapped += 1
            continue
        if not bb_sequence or bb_sequence[-1] != (func, bb_id):
            bb_sequence.append((func, bb_id))
    return bb_sequence, unmapped


def validate_transitions(
    bb_sequence: list[tuple[str, int]],
    index: TransitionIndex,
) -> tuple[int, int, int]:
    """
    Count valid intra-procedural, inter-procedural, and invalid transitions.
    Recursive self-call / return-from-exit treated as inter_procedural (same as tools_py).
    """
    valid_intra = 0
    inter_procedural = 0
    invalid = 0
    edges = index.edges
    entry_blocks = index.entry_blocks
    exit_blocks = index.exit_blocks
    calls = index.calls

    for i in range(len(bb_sequence) - 1):
        prev_func, prev_bb = bb_sequence[i]
        curr_func, curr_bb = bb_sequence[i + 1]

        if prev_func != curr_func:
            inter_procedural += 1
            continue

        if prev_func not in edges or prev_bb not in edges[prev_func]:
            continue

        if curr_bb not in edges[prev_func][prev_bb]:
            is_recursive_call = (
                calls[prev_func].get(prev_bb) == curr_func
                and curr_bb in entry_blocks[curr_func]
            )
            is_recursive_return = prev_bb in exit_blocks[prev_func]
            if is_recursive_call or is_recursive_return:
                inter_procedural += 1
                continue
            logger.warning(
                "Invalid transition: %s:%s -> %s:%s",
                prev_func,
                prev_bb,
                curr_func,
                curr_bb,
            )
            invalid += 1
        else:
            valid_intra += 1

    return valid_intra, inter_procedural, invalid


def run_compress_and_validate(
    cfg: CfgProgram,
    bb_map: BbAddressMap,
    trace_rvas: tuple[int, ...],
) -> CompressionResult:
    if not trace_rvas:
        raise EmptyTraceError("Trace is empty")
    seq, unmapped = compress_bb_sequence(trace_rvas, bb_map)
    if not seq:
        raise EmptyTraceError("No mappable instructions in trace")

    vi, inter, inv = validate_transitions(seq, cfg.transition_index)
    stats = CompressionStats(
        total_instructions=len(trace_rvas),
        unmapped_instructions=unmapped,
        compressed_length=len(seq),
        valid_intra=vi,
        inter_procedural=inter,
        invalid_transitions=inv,
    )
    compressed = tuple({"func": f, "bb": b} for f, b in seq)
    return CompressionResult(
        stats=stats,
        compressed_trace=compressed,
        success=inv == 0,
    )


def write_compressed_trace_json(
    path: str | Path, compressed: tuple[dict[str, int | str], ...]
) -> None:
    Path(path).write_text(json.dumps(list(compressed)), encoding="utf-8")


def load_compressed_trace_json(path: str | Path) -> list[dict[str, int | str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("compressed trace must be a JSON array")
    return data
