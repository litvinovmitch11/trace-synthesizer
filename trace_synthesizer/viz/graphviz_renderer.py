"""Render CFG (and optional compressed trace) to Graphviz formats."""

from __future__ import annotations

import html
import logging
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

import cxxfilt
import graphviz

from trace_synthesizer.domain.program import FunctionCFG

logger = logging.getLogger(__name__)


def demangle(name: str | None) -> str:
    if not name:
        return name or ""
    try:
        return cxxfilt.demangle(name)
    except Exception:
        return name


class CfgGraphvizRenderer:
    """Build Graphviz Digraph from one function CFG and optional trace overlay."""

    def __init__(
        self,
        func: FunctionCFG,
        *,
        trace_for_func: Iterable[int] | None = None,
        graph_format: str = "svg",
    ) -> None:
        self._func = func
        self._trace = list(trace_for_func) if trace_for_func is not None else None
        self._format = graph_format

    def render(self, out_path_without_ext: str | Path) -> Path:
        """Write ``out_path_without_ext.<format>`` and return the final path."""
        out = Path(out_path_without_ext)
        node_hits: defaultdict[int, int] = defaultdict(int)
        edge_hits: defaultdict[tuple[int, int], int] = defaultdict(int)
        max_node_hits = 0

        if self._trace is not None:
            for bb in self._trace:
                node_hits[bb] += 1
                max_node_hits = max(max_node_hits, node_hits[bb])
            for i in range(len(self._trace) - 1):
                edge_hits[(self._trace[i], self._trace[i + 1])] += 1

        fname = demangle(self._func.function_name)
        dot = graphviz.Digraph(comment=f"CFG of {fname}", format=self._format)
        dot.attr(rankdir="TB", splines="polyline", overlap="false")
        dot.attr(
            "node",
            shape="box",
            style="filled,rounded",
            fontname="Helvetica",
            fillcolor="white",
        )
        dot.attr("edge", fontname="Helvetica", fontsize="10")

        for block in self._func.blocks:
            bb_id = block.id
            name = demangle(block.name or f"BB_{bb_id}")
            instr_count = block.instr_count
            is_entry = block.is_entry
            successors = block.successors
            is_exit = len(successors) == 0
            has_call = block.has_call
            call_target = demangle(block.call_target) if block.call_target else ""

            prefix = ""
            fillcolor = "white"
            penwidth = "1"
            color = "black"

            if is_entry:
                prefix = "<FONT COLOR='green'>[START]</FONT><BR/>"
                penwidth = "3"
                color = "green"
            elif is_exit:
                prefix = "<FONT COLOR='purple'>[EXIT]</FONT><BR/>"
                penwidth = "3"
                color = "purple"

            label = f"<<B>{prefix}{html.escape(name)} (ID: {bb_id})</B><BR/>"
            label += f"<FONT POINT-SIZE='10'>Instrs: {instr_count}</FONT>"

            if has_call:
                escaped_call = html.escape(call_target) if call_target else "Indirect"
                label += (
                    "<BR/><B><FONT POINT-SIZE='11' COLOR='#d9534f'>"
                    f"Call: {escaped_call}</FONT></B>"
                )

            if self._trace is not None and max_node_hits > 0:
                hits = node_hits.get(bb_id, 0)
                if hits > 0:
                    intensity = hits / max_node_hits
                    r, g, b = int(255 - 51 * intensity), 255, int(255 - 51 * intensity)
                    fillcolor = f"#{r:02X}{g:02X}{b:02X}"
                    if not is_entry and not is_exit:
                        penwidth = "2"
                        color = "green"
                    label += f"<BR/><FONT POINT-SIZE='10' COLOR='green'><b>Hits: {hits}</b></FONT>"

            label += ">"
            dot.node(
                str(bb_id),
                label=label,
                fillcolor=fillcolor,
                color=color,
                penwidth=penwidth,
            )

        for block in self._func.blocks:
            bb_id = block.id
            for succ in block.successors:
                target_id = succ.target_id
                prob = succ.prob
                is_fallthrough = succ.is_fallthrough

                edge_label = ""
                color = "black"
                style = "solid"

                if is_fallthrough:
                    style = "bold"

                if prob is not None:
                    edge_label += f"P={prob:.2f}"
                    if self._trace is None:
                        if prob >= 0.8:
                            color = "red"
                        elif prob >= 0.2:
                            color = "blue"
                        else:
                            color = "black"

                if self._trace is not None:
                    hits = edge_hits.get((bb_id, target_id), 0)
                    if hits > 0:
                        color = "green"
                        edge_label += (
                            f" | Hits={hits}" if edge_label else f"Hits={hits}"
                        )
                    else:
                        color = "gray80"

                dot.edge(
                    str(bb_id),
                    str(target_id),
                    label=edge_label,
                    color=color,
                    penwidth="1",
                    style=style,
                    fontcolor=color,
                )

        rendered = dot.render(out.with_suffix("").as_posix(), cleanup=True)
        path = Path(rendered)
        logger.info("Rendered CFG to %s", path)
        return path
