"""Thin facade tying CFG grammar, compressed/intra traces, and optional viz."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from trace_synthesizer.core.grammar import CfgProgram
from trace_synthesizer.io.bb_addr_map import BbAddressMap
from trace_synthesizer.io.compress_pipeline import (
    CompressionResult,
    load_compressed_trace_json,
    run_compress_and_validate,
    validate_transitions,
)
from trace_synthesizer.io.instruction_trace import read_rva_trace
from trace_synthesizer.io.intra_trace import (
    export_intra_trace_from_compressed_file,
    intra_sequence_from_compressed,
    load_intra_trace_bbs_for_visualize,
)


@dataclass
class ProgramTraceSession:
    """
    One function's CFG plus helpers for compress/validate, intra export, and viz.

    This class does not duplicate graph logic; it delegates to ``CfgProgram``,
    ``compress_pipeline``, ``intra_trace``, and ``CfgGraphvizRenderer``.
    """

    grammar: CfgProgram
    cfg_path: Path
    function_name: str

    @classmethod
    def from_cfg_json(
        cls, path: str | Path, *, function_name: str = "main"
    ) -> ProgramTraceSession:
        p = Path(path)
        return cls(CfgProgram.from_cfg_json(p), p, function_name)

    def compressed_to_intra_events(
        self, compressed_path: str | Path
    ) -> list[dict[str, str | int]]:
        data = load_compressed_trace_json(compressed_path)
        return intra_sequence_from_compressed(data, self.function_name)

    def intra_bb_path_from_compressed(self, compressed_path: str | Path) -> list[int]:
        return [int(e["bb"]) for e in self.compressed_to_intra_events(compressed_path)]

    def validate_transition_counts(
        self,
        compressed_or_pairs: list[tuple[str, int]] | str | Path,
    ) -> tuple[int, int, int]:
        if isinstance(compressed_or_pairs, (str, Path)):
            raw = load_compressed_trace_json(compressed_or_pairs)
            pairs = [(str(e["func"]), int(e["bb"])) for e in raw]
        else:
            pairs = compressed_or_pairs
        return validate_transitions(pairs, self.grammar.transition_index)

    def compress_and_validate_rva_trace(
        self,
        bb_map_path: str | Path,
        trace_bin_path: str | Path,
    ) -> CompressionResult:
        bb_map = BbAddressMap.from_readobj_file(bb_map_path)
        rvas = read_rva_trace(trace_bin_path)
        return run_compress_and_validate(self.grammar, bb_map, rvas)

    def export_intra_from_compressed(
        self, compressed_path: str | Path, out_intra_path: str | Path
    ) -> None:
        export_intra_trace_from_compressed_file(
            compressed_path, self.function_name, out_intra_path
        )

    def intra_bb_path_from_intra_json(self, intra_path: str | Path) -> list[int]:
        return load_intra_trace_bbs_for_visualize(intra_path, self.function_name)

    def render_cfg_with_trace(
        self,
        out_stem: str | Path,
        *,
        trace_bbs: Iterable[int] | None = None,
        compressed_path: str | Path | None = None,
        intra_path: str | Path | None = None,
        graph_format: str = "svg",
    ) -> Path:
        from trace_synthesizer.viz.graphviz_renderer import CfgGraphvizRenderer

        if trace_bbs is not None:
            bbs: list[int] | None = list(trace_bbs)
        elif compressed_path is not None:
            bbs = self.intra_bb_path_from_compressed(compressed_path)
        elif intra_path is not None:
            bbs = self.intra_bb_path_from_intra_json(intra_path)
        else:
            bbs = None
        fn = self.grammar.function(self.function_name)
        renderer = CfgGraphvizRenderer(
            fn, trace_for_func=bbs, graph_format=graph_format
        )
        return renderer.render(out_stem)
