#!/usr/bin/env python3
"""
Trace Analyzer - Production ready version
Analyzes execution traces and generates CFG visualizations
"""

import argparse
import html
import json
import logging
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import r2pipe
from graphviz import Digraph

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


@dataclass
class BinaryInfo:
    """Container for binary analysis results"""

    main_addr: int = 0
    text_start: int = 0
    text_end: int = 0
    entry_point: int = 0


@dataclass
class CFGInfo:
    """Container for CFG analysis results"""

    blocks: List[Dict] = field(default_factory=list)
    block_map: Dict[int, Dict] = field(default_factory=dict)
    call_targets: Dict[int, Set[int]] = field(default_factory=lambda: defaultdict(set))


@dataclass
class TraceStats:
    """Container for trace statistics"""

    total_addresses: int = 0
    addresses_in_text: int = 0
    addresses_outside_text: int = 0
    deduplicated_addresses: int = 0
    blocks_with_hits: int = 0
    total_hits: int = 0
    coverage_percentage: float = 0.0


class TraceAnalyzer:
    """Main analyzer class for processing execution traces"""

    def __init__(self, output_dir: str = "traces"):
        """
        Initialize the trace analyzer

        Args:
            output_dir: Directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.r2 = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        if self.r2:
            try:
                self.r2.quit()
            except Exception as e:
                logger.warning(f"Error closing r2pipe: {e}")
            finally:
                self.r2 = None

    def _safe_r2_cmd(self, cmd: str, default: str = "") -> str:
        """
        Safely execute radare2 command with error handling

        Args:
            cmd: radare2 command to execute
            default: Default value if command fails

        Returns:
            Command output or default value
        """
        try:
            if self.r2:
                return self.r2.cmd(cmd)
        except Exception as e:
            logger.error(f"Error executing r2 command '{cmd}': {e}")
        return default

    def _load_json_or_default(self, json_str: str, default=None):
        """
        Safely parse JSON string

        Args:
            json_str: JSON string to parse
            default: Default value if parsing fails

        Returns:
            Parsed JSON or default value
        """
        if not json_str or json_str.strip() == "[]":
            return default

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return default

    def load_trace(self, trace_file: Path) -> List[int]:
        """
        Load trace from file

        Args:
            trace_file: Path to trace file

        Returns:
            List of addresses from trace
        """
        trace = []

        if not trace_file.exists():
            logger.error(f"Trace file not found: {trace_file}")
            return trace

        logger.info(f"Loading trace from {trace_file}")

        try:
            with trace_file.open("r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    try:
                        # Handle hex addresses with or without 0x prefix
                        if line.startswith("0x"):
                            addr = int(line, 16)
                        else:
                            addr = int(line, 16)
                        trace.append(addr)
                    except ValueError:
                        logger.warning(f"Invalid address on line {line_num}: {line}")
                        continue

        except IOError as e:
            logger.error(f"Error reading trace file: {e}")
            return []

        logger.info(f"Loaded {len(trace)} addresses from trace")
        return trace

    def open_binary(self, binary_path: str) -> bool:
        """
        Open binary file with radare2

        Args:
            binary_path: Path to binary file

        Returns:
            True if successful, False otherwise
        """
        try:
            if not Path(binary_path).exists():
                logger.error(f"Binary file not found: {binary_path}")
                return False

            self.r2 = r2pipe.open(binary_path, flags=["-2"])
            # Perform initial analysis
            self._safe_r2_cmd("aaa")
            logger.info(f"Successfully opened binary: {binary_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to open binary {binary_path}: {e}")
            return False

    def analyze_binary(self) -> BinaryInfo:
        """
        Analyze binary to find important addresses

        Returns:
            BinaryInfo object with analysis results
        """
        logger.info("Performing binary analysis...")

        bin_info = BinaryInfo()

        # Get entry point
        try:
            i_json = self._load_json_or_default(self._safe_r2_cmd("ij"), {})
            if i_json and "bin" in i_json:
                bin_info.entry_point = i_json["bin"].get("entry", 0x400000)
        except Exception as e:
            logger.warning(f"Could not get entry point: {e}")
            bin_info.entry_point = 0x400000

        # Try to find main function
        main_addr = self._find_main_address()
        bin_info.main_addr = main_addr if main_addr else bin_info.entry_point

        # Find .text section
        text_start, text_end = self._find_text_section()
        bin_info.text_start = text_start
        bin_info.text_end = text_end

        logger.info(f"Main function at: {hex(bin_info.main_addr)}")
        logger.info(
            f".text section: {hex(bin_info.text_start)} - {hex(bin_info.text_end)}"
        )

        return bin_info

    def _find_main_address(self) -> Optional[int]:
        """Find address of main function"""
        # Try JSON symbols first
        sym_json = self._safe_r2_cmd("isj~main")
        syms = self._load_json_or_default(sym_json, [])

        if syms:
            if isinstance(syms, list):
                for sym in syms:
                    if sym.get("name") == "main":
                        return sym.get("vaddr")
            elif isinstance(syms, dict) and syms.get("name") == "main":
                return syms.get("vaddr")

        # Try afl output as fallback
        afl_output = self._safe_r2_cmd("afl~main")
        for line in afl_output.split("\n"):
            if "main" in line.lower():
                parts = line.split()
                if parts:
                    try:
                        return int(parts[0], 16)
                    except ValueError:
                        continue

        logger.warning("Could not find main function address")
        return None

    def _find_text_section(self) -> Tuple[int, int]:
        """Find .text section boundaries"""
        default_start = 0x400000
        default_size = 0x10000

        try:
            iSj_output = self._safe_r2_cmd("iSj")
            sections = self._load_json_or_default(iSj_output, [])

            if sections:
                for sec in sections:
                    if sec.get("name") == ".text":
                        start = sec.get("vaddr", default_start)
                        size = sec.get("vsize", default_size)
                        return start, start + size

        except Exception as e:
            logger.warning(f"Could not analyze sections: {e}")

        return default_start, default_start + default_size

    def filter_trace_to_text(
        self, trace_addrs: List[int], text_start: int, text_end: int
    ) -> List[int]:
        """
        Filter trace to only addresses in .text section

        Args:
            trace_addrs: List of trace addresses
            text_start: Start of .text section
            text_end: End of .text section

        Returns:
            Filtered trace addresses
        """
        filtered = []
        outside_count = 0

        for addr in trace_addrs:
            if text_start <= addr < text_end:
                filtered.append(addr)
            else:
                outside_count += 1

        logger.info(f"Addresses in .text: {len(filtered)}")
        logger.info(f"Addresses outside .text: {outside_count}")

        return filtered

    def get_cfg_with_calls(self, main_addr: int) -> Optional[CFGInfo]:
        """
        Build CFG for main function including calls

        Args:
            main_addr: Address of main function

        Returns:
            CFGInfo object or None if failed
        """
        logger.info(f"Building CFG for main at {hex(main_addr)}...")

        graph_json = self._safe_r2_cmd(f"agj @ {main_addr}")
        if not graph_json or graph_json.strip() == "[]":
            logger.error("No CFG found for main")
            return None

        data = self._load_json_or_default(graph_json)
        if not data:
            logger.error("Failed to parse CFG JSON")
            return None

        # Handle different JSON structures
        if isinstance(data, list) and data:
            blocks = data[0].get("blocks", [])
        else:
            blocks = data.get("blocks", [])

        if not blocks:
            logger.error("No basic blocks in CFG")
            return None

        logger.info(f"Found {len(blocks)} basic blocks")

        cfg_info = CFGInfo()
        cfg_info.blocks = blocks
        cfg_info.block_map = {b["offset"]: b for b in blocks}

        # Analyze call instructions
        self._analyze_calls(cfg_info)

        logger.info(
            f"Found {sum(len(targets) for targets in cfg_info.call_targets.values())} call sites"
        )

        return cfg_info

    def _analyze_calls(self, cfg_info: CFGInfo):
        """Analyze call instructions in basic blocks"""
        for block in cfg_info.blocks:
            addr = block["offset"]
            size = block["size"]

            try:
                pdj_output = self._safe_r2_cmd(f"pdj {min(size, 100)} @ {addr}")
                if pdj_output:
                    instructions = self._load_json_or_default(pdj_output, [])

                    for instr in instructions:
                        opcode = instr.get("opcode", "").lower()
                        if "call" in opcode:
                            # Extract call target
                            call_addr = self._extract_call_address(instr)
                            if call_addr:
                                cfg_info.call_targets[addr].add(call_addr)
            except Exception as e:
                logger.debug(f"Error analyzing block {hex(addr)}: {e}")
                continue

    def _extract_call_address(self, instr: Dict) -> Optional[int]:
        """Extract call address from instruction"""
        # Try jump field first
        if "jump" in instr:
            return instr["jump"]

        # Try opex operands
        if "opex" in instr and "operands" in instr["opex"]:
            for op in instr["opex"]["operands"]:
                if "imm" in op:
                    return op["imm"]

        return None

    def analyze_trace_coverage(
        self, trace_addrs: List[int], cfg_info: CFGInfo
    ) -> Tuple[Dict, Dict, TraceStats]:
        """
        Analyze trace coverage against CFG

        Returns:
            Tuple of (block_hits, transitions, stats)
        """
        logger.info("Analyzing trace coverage...")

        # Deduplicate consecutive addresses
        dedup_trace = []
        for addr in trace_addrs:
            if not dedup_trace or addr != dedup_trace[-1]:
                dedup_trace.append(addr)

        # Count block hits
        block_hits = Counter(dedup_trace)

        # Count transitions
        transitions = Counter(zip(dedup_trace, dedup_trace[1:]))

        # Calculate statistics
        stats = TraceStats()
        stats.total_addresses = len(trace_addrs)
        stats.deduplicated_addresses = len(dedup_trace)
        stats.total_hits = sum(block_hits.values())

        # Count blocks in CFG that were hit
        blocks_in_cfg = [addr for addr in dedup_trace if addr in cfg_info.block_map]
        stats.blocks_with_hits = len(set(blocks_in_cfg))
        stats.coverage_percentage = (
            (stats.blocks_with_hits / len(cfg_info.blocks) * 100)
            if cfg_info.blocks
            else 0
        )

        logger.info(
            f"Trace addresses in main CFG: {len(blocks_in_cfg)}/{stats.deduplicated_addresses}"
        )
        logger.info(f"Total transitions: {len(transitions)}")
        logger.info(f"Total block hits: {stats.total_hits}")
        logger.info(f"Coverage: {stats.coverage_percentage:.1f}%")

        return block_hits, transitions, stats

    def create_cfg_graph(
        self,
        cfg_info: CFGInfo,
        block_hits: Dict[int, int],
        transitions: Dict[Tuple[int, int], int],
        output_name: str,
    ) -> Path:
        """
        Create CFG graph visualization

        Returns:
            Path to generated graph file
        """
        logger.info("Creating CFG graph...")

        dot = Digraph(comment="CFG with Trace", format="png")
        dot.attr(rankdir="TB")
        dot.attr("node", shape="plain", fontname="Courier New", fontsize="9")

        # Create nodes
        self._create_nodes(dot, cfg_info, block_hits)

        # Create edges
        self._create_edges(dot, cfg_info, transitions)

        # Add trace-only transitions
        trace_only_count = self._add_trace_only_edges(dot, cfg_info, transitions)
        logger.info(f"Added {trace_only_count} trace-only edges")

        # Save graph
        out_path = self.output_dir / output_name
        logger.info(f"Rendering graph to {out_path}")
        dot.render(str(out_path), cleanup=True)

        return out_path.with_suffix(".png")

    def _create_nodes(
        self, dot: Digraph, cfg_info: CFGInfo, block_hits: Dict[int, int]
    ):
        """Create graph nodes for basic blocks"""
        logger.info(f"Creating {len(cfg_info.blocks)} graph nodes...")

        for block in cfg_info.blocks:
            addr = block["offset"]
            size = block["size"]
            hits = block_hits.get(addr, 0)

            # Get disassembly
            instructions = self._get_block_disassembly(addr, size)

            # Determine node styling
            node_color = "#98fb98" if hits > 0 else "#e0e0e0"
            border_color = "darkgreen" if hits > 0 else "gray"
            border_width = "3" if hits > 0 else "1"

            # Create HTML table for node
            table = self._create_node_html(
                addr, hits, instructions, node_color, border_color, border_width
            )

            dot.node(str(addr), label=table)

    def _get_block_disassembly(self, addr: int, size: int) -> List[Dict]:
        """Get disassembly for a basic block"""
        try:
            pdj_output = self._safe_r2_cmd(f"pdj {min(size, 100)} @ {addr}")
            return self._load_json_or_default(pdj_output, [])
        except Exception:
            return []

    def _create_node_html(
        self,
        addr: int,
        hits: int,
        instructions: List[Dict],
        node_color: str,
        border_color: str,
        border_width: str,
    ) -> str:
        """Create HTML table for graph node"""
        max_instr = 5

        table = f'<<TABLE BORDER="{border_width}" CELLBORDER="1" CELLSPACING="0" CELLPADDING="3"'
        table += f' BGCOLOR="{node_color}" COLOR="{border_color}">'
        table += f'<TR><TD COLSPAN="2" BALIGN="LEFT"><B>{hex(addr)}</B><BR/>Hits: {hits}</TD></TR>'

        for i, instr in enumerate(instructions[:max_instr]):
            opcode = html.escape(instr.get("opcode", "???"))
            instr_addr = hex(instr.get("offset", 0))

            table += (
                f'<TR><TD ALIGN="RIGHT">{instr_addr}</TD>'
                f'<TD ALIGN="LEFT"><FONT FACE="Courier New">{opcode}</FONT></TD></TR>'
            )

        if len(instructions) > max_instr:
            table += f'<TR><TD COLSPAN="2" ALIGN="CENTER">... ({len(instructions)-max_instr} more)</TD></TR>'

        table += "</TABLE>>"
        return table

    def _create_edges(
        self, dot: Digraph, cfg_info: CFGInfo, transitions: Dict[Tuple[int, int], int]
    ):
        """Create edges for CFG"""
        logger.info("Creating graph edges...")

        for block in cfg_info.blocks:
            src = block["offset"]

            # Jump edge
            if "jump" in block:
                self._create_edge(
                    dot, src, block["jump"], "jump", cfg_info, transitions
                )

            # Fall-through edge
            if "fail" in block:
                self._create_edge(
                    dot, src, block["fail"], "next", cfg_info, transitions
                )

    def _create_edge(
        self,
        dot: Digraph,
        src: int,
        dst: int,
        edge_type: str,
        cfg_info: CFGInfo,
        transitions: Dict[Tuple[int, int], int],
    ):
        """Create a single graph edge"""
        if dst not in cfg_info.block_map:
            return

        count = transitions.get((src, dst), 0)

        # Style based on edge type and hit count
        if edge_type == "jump":
            color = "darkblue"
            label = "jump"
        else:  # next/fail
            color = "red"
            label = "next"

        if count > 0:
            label += f" ({count})"
            color = "darkgreen"
            penwidth = "3.0"
        else:
            penwidth = "1.0"

        style = "solid"

        dot.edge(
            str(src), str(dst), label=label, color=color, penwidth=penwidth, style=style
        )

    def _add_trace_only_edges(
        self, dot: Digraph, cfg_info: CFGInfo, transitions: Dict[Tuple[int, int], int]
    ) -> int:
        """Add edges that only exist in trace (not in static CFG)"""
        trace_only_count = 0

        for (src, dst), count in transitions.items():
            if count <= 0:
                continue

            # Check if edge exists in static CFG
            edge_exists = self._is_edge_in_cfg(src, dst, cfg_info)

            # Add if not in static CFG but both nodes are
            if (
                not edge_exists
                and src in cfg_info.block_map
                and dst in cfg_info.block_map
            ):
                trace_only_count += 1
                dot.edge(
                    str(src),
                    str(dst),
                    label=f"trace ({count})",
                    color="orange",
                    penwidth="2.5",
                    style="bold",
                )

        return trace_only_count

    def _is_edge_in_cfg(self, src: int, dst: int, cfg_info: CFGInfo) -> bool:
        """Check if edge exists in static CFG"""
        if src not in cfg_info.block_map:
            return False

        block = cfg_info.block_map[src]

        # Check for regular edges
        if ("jump" in block and block["jump"] == dst) or (
            "fail" in block and block["fail"] == dst
        ):
            return True

        # Check for call edges
        if src in cfg_info.call_targets and dst in cfg_info.call_targets[src]:
            return True

        return False

    def print_analysis_report(
        self,
        cfg_info: CFGInfo,
        block_hits: Dict[int, int],
        transitions: Dict[Tuple[int, int], int],
        stats: TraceStats,
    ):
        """Print detailed analysis report"""
        logger.info("=" * 60)
        logger.info("ANALYSIS REPORT")
        logger.info("=" * 60)

        logger.info(f"Coverage Analysis:")
        logger.info(f"  - Blocks in CFG: {len(cfg_info.blocks)}")
        logger.info(
            f"  - Blocks visited: {stats.blocks_with_hits} ({stats.coverage_percentage:.1f}%)"
        )
        logger.info(f"  - Total trace hits: {stats.total_hits}")

        # Most visited blocks
        self._print_most_visited_blocks(cfg_info, block_hits)

        # Most common transitions
        self._print_common_transitions(cfg_info, transitions)

        logger.info("=" * 60)

    def _print_most_visited_blocks(self, cfg_info: CFGInfo, block_hits: Dict[int, int]):
        """Print most visited basic blocks"""
        main_hits = {
            addr: count
            for addr, count in block_hits.items()
            if addr in cfg_info.block_map
        }

        if not main_hits:
            return

        sorted_hits = sorted(main_hits.items(), key=lambda x: x[1], reverse=True)[:10]

        logger.info("Most visited blocks:")
        for i, (addr, hits) in enumerate(sorted_hits, 1):
            block = cfg_info.block_map.get(addr, {})
            edges = []

            if "jump" in block:
                edges.append(f"jump->{hex(block['jump'])}")
            if "fail" in block:
                edges.append(f"next->{hex(block['fail'])}")

            edge_str = f" ({', '.join(edges)})" if edges else ""
            logger.info(f"  {i:2d}. {hex(addr)}: {hits} hits{edge_str}")

    def _print_common_transitions(
        self, cfg_info: CFGInfo, transitions: Dict[Tuple[int, int], int]
    ):
        """Print most common transitions"""
        main_transitions = [
            (s, d, c)
            for (s, d), c in transitions.items()
            if s in cfg_info.block_map and d in cfg_info.block_map
        ]

        if not main_transitions:
            return

        logger.info(f"Transition Analysis:")
        logger.info(f"  - Transitions within main: {len(main_transitions)}")

        sorted_transitions = sorted(main_transitions, key=lambda x: x[2], reverse=True)[
            :10
        ]

        logger.info(f"  - Most common transitions:")
        for src, dst, count in sorted_transitions:
            src_block = cfg_info.block_map.get(src, {})

            if "jump" in src_block and src_block["jump"] == dst:
                edge_type = "jump"
            elif "fail" in src_block and src_block["fail"] == dst:
                edge_type = "next"
            else:
                edge_type = "trace"

            logger.info(f"    {hex(src)} -> {hex(dst)}: {count}x ({edge_type})")

    def generate(self, binary_path: str, trace_file: str, output_name: str) -> bool:
        """
        Main analysis pipeline

        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()

        try:
            logger.info("=" * 60)
            logger.info(f"Starting analysis of {binary_path}")
            logger.info(f"Trace file: {trace_file}")
            logger.info("=" * 60)

            # Load trace
            trace_addrs = self.load_trace(Path(trace_file))
            if not trace_addrs:
                logger.error("Empty trace file")
                return False

            # Open binary
            if not self.open_binary(binary_path):
                return False

            # Analyze binary
            bin_info = self.analyze_binary()

            # Filter trace to .text section
            filtered_trace = self.filter_trace_to_text(
                trace_addrs, bin_info.text_start, bin_info.text_end
            )

            if not filtered_trace:
                logger.error("No addresses in .text section")
                return False

            # Get CFG
            cfg_info = self.get_cfg_with_calls(bin_info.main_addr)
            if not cfg_info:
                logger.error("Failed to get CFG")
                return False

            # Analyze trace coverage
            block_hits, transitions, stats = self.analyze_trace_coverage(
                filtered_trace, cfg_info
            )

            # Create graph
            graph_path = self.create_cfg_graph(
                cfg_info, block_hits, transitions, output_name
            )

            # Print report
            self.print_analysis_report(cfg_info, block_hits, transitions, stats)

            logger.info(f"Analysis completed in {time.time() - start_time:.2f} seconds")
            logger.info(f"Graph saved to: {graph_path}")

            return True

        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return False

        finally:
            self.cleanup()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Analyze execution traces and generate CFG visualizations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("binary", help="Path to binary file")
    parser.add_argument("trace", help="Path to trace file")
    parser.add_argument("output", help="Output name (without extension)")

    parser.add_argument(
        "-o",
        "--output-dir",
        default="traces",
        help="Output directory (default: traces)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress console output"
    )

    args = parser.parse_args()

    # Adjust logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
        # Remove console handler
        for handler in logging.getLogger().handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                logging.getLogger().removeHandler(handler)

    # Create and run analyzer
    with TraceAnalyzer(args.output_dir) as analyzer:
        success = analyzer.generate(args.binary, args.trace, args.output)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
