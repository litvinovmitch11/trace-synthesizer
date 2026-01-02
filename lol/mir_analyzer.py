#!/usr/bin/env python3
import re
import argparse
import logging
import json
import random
import html
import sys
from collections import defaultdict, Counter
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple

# Check dependencies
try:
    import networkx as nx
    from graphviz import Digraph
except ImportError as e:
    sys.exit(f"Error: Missing dependency. Install: pip install networkx graphviz")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MIR_Analyzer")

@dataclass
class MIRBlock:
    id: int
    name: str
    pgo_frequency: int = 0  # Static freq from MIR (if available)
    sim_hits: int = 0       # Dynamic hits from simulation
    instructions: List[str] = field(default_factory=list)

class MIRParser:
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.functions: Dict[str, nx.DiGraph] = {}

    def parse(self) -> Dict[str, nx.DiGraph]:
        logger.info(f"Parsing MIR file: {self.filepath}")
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            sys.exit(f"File not found: {self.filepath}")

        # Split by YAML document separator
        raw_funcs = content.split("---")
        for raw in raw_funcs:
            self._parse_function(raw)
        
        logger.info(f"Parsed {len(self.functions)} functions.")
        return self.functions

    def _parse_function(self, raw_content: str):
        # 1. Extract Name
        name_match = re.search(r"name:\s+([^\s]+)", raw_content)
        if not name_match: return
        func_name = name_match.group(1)

        # 2. Extract Body
        body_match = re.search(r"body:\s+\|\s*(.*)", raw_content, re.DOTALL)
        if not body_match: return
        body = body_match.group(1)

        G = nx.DiGraph(name=func_name)

        # --- REGEX PATTERNS ---
        # Fixed: Handles indentation (^\s*) and complex names
        # Captures: 1=ID, 2=Suffix/Name
        bb_header_re = re.compile(r"^\s*bb\.(\d+)([^:]*):") 
        
        # Captures: (freq 123) - optional
        freq_re = re.compile(r"\(freq\s+(\d+)\)")

        # Captures successors line
        succ_re = re.compile(r"successors:\s*(.*)")
        
        # Captures target and weight: %bb.1(0x40000000)
        succ_target_re = re.compile(r"%bb\.(\d+)(?:\((0x[0-9a-fA-F]+)\))?")

        current_bb_id = None
        current_instrs = []
        current_freq = 0
        current_bb_name = ""

        lines = body.split('\n')
        for line in lines:
            line = line.strip() # Remove indentation for processing
            if not line: continue

            # A. Block Header
            match = bb_header_re.match(line)
            if match:
                # Save previous block
                if current_bb_id is not None:
                    obj = MIRBlock(current_bb_id, current_bb_name, pgo_frequency=current_freq, instructions=list(current_instrs))
                    G.add_node(current_bb_id, obj=obj)

                current_bb_id = int(match.group(1))
                raw_suffix = match.group(2).strip()
                current_bb_name = f"bb.{current_bb_id}{raw_suffix}"
                
                # Try extract static freq
                freq_match = freq_re.search(line)
                current_freq = int(freq_match.group(1)) if freq_match else 0
                
                current_instrs = []
                continue

            if current_bb_id is None: continue

            # B. Successors
            if line.startswith("successors:"):
                succ_match = succ_re.search(line)
                if succ_match:
                    succ_line = succ_match.group(1)
                    parts = succ_line.split(',')
                    for part in parts:
                        t_match = succ_target_re.search(part)
                        if t_match:
                            target = int(t_match.group(1))
                            prob_hex = t_match.group(2)
                            # Default weight 0 if missing (rare)
                            weight = int(prob_hex, 16) if prob_hex else 0
                            G.add_edge(current_bb_id, target, weight=weight)
                continue

            # C. Instructions
            # Skip meta-instructions for cleaner view
            if not any(line.startswith(p) for p in ["liveins:", "frame-setup", "frame-destroy", "EH_LABEL"]):
                current_instrs.append(line)

        # Save last block
        if current_bb_id is not None:
            obj = MIRBlock(current_bb_id, current_bb_name, pgo_frequency=current_freq, instructions=list(current_instrs))
            G.add_node(current_bb_id, obj=obj)

        self._normalize_probabilities(G)
        self.functions[func_name] = G

    def _normalize_probabilities(self, G: nx.DiGraph):
        """Calculates 0.0-1.0 probabilities based on weights."""
        for node in G.nodes:
            out_edges = list(G.out_edges(node, data=True))
            if not out_edges: continue
            
            # Sum of all weights for this block
            total_weight = sum(d.get('weight', 0) for _, _, d in out_edges)
            
            for _, target, data in out_edges:
                w = data.get('weight', 0)
                if total_weight > 0:
                    data['probability'] = w / total_weight
                else:
                    # Fallback: uniform distribution if weights are 0
                    data['probability'] = 1.0 / len(out_edges)

class TraceSimulator:
    def __init__(self, graph: nx.DiGraph):
        self.G = graph
        # Try to find entry block (usually 0)
        nodes = sorted(list(self.G.nodes))
        self.entry = nodes[0] if nodes else None

    def simulate(self, steps=100) -> List[int]:
        """Runs a Monte-Carlo simulation. Returns list of Block IDs visited."""
        if self.entry is None: return []
        
        path = []
        curr = self.entry
        
        for _ in range(steps):
            path.append(curr)
            
            # Update hit count in the graph object for visualization
            self.G.nodes[curr]['obj'].sim_hits += 1
            
            succs = list(self.G.successors(curr))
            if not succs: break # Return/Exit
            
            # Weighted choice
            probs = [self.G.edges[curr, s]['probability'] for s in succs]
            
            # Handle floating point edge cases where sum is slightly != 1.0
            try:
                curr = random.choices(succs, weights=probs)[0]
            except ValueError:
                curr = succs[0] # Fallback
            
        return path

    def get_transitions(self, block_id: int) -> List[dict]:
        if block_id not in self.G: return []
        transitions = []
        for succ in self.G.successors(block_id):
            prob = self.G.edges[block_id, succ]['probability']
            transitions.append({"next_block": succ, "probability": prob})
        return sorted(transitions, key=lambda x: x['probability'], reverse=True)

class CFGVisualizer:
    def __init__(self, graph: nx.DiGraph):
        self.G = graph

    def _escape(self, text: str) -> str:
        if not text: return ""
        if len(text) > 45: text = text[:42] + "..."
        return html.escape(text, quote=True)

    def render(self, output_path: str, trace_path: List[int] = None):
        dot = Digraph(comment='CFG', format='svg')
        # Splines=polyline often looks neater for code flow
        dot.attr(rankdir='TB', splines='polyline', fontname='Courier New')
        dot.attr('node', shape='plain')

        # Convert trace path to a set of edges for quick lookup
        trace_edges = set()
        visited_nodes = set()
        if trace_path:
            visited_nodes = set(trace_path)
            for i in range(len(trace_path)-1):
                trace_edges.add((trace_path[i], trace_path[i+1]))

        # 1. Nodes
        for n, data in self.G.nodes(data=True):
            if 'obj' not in data: continue
            block: MIRBlock = data['obj']
            
            # Style: Light Green if visited, otherwise White
            is_visited = n in visited_nodes
            bgcolor = "#e6ffcc" if is_visited else "#ffffff" # Light Green vs White
            border_color = "black" if is_visited else "gray"
            
            # Header info
            if trace_path is not None:
                # Mode: Simulation/Path
                meta_info = f"Hits: {block.sim_hits}"
            else:
                # Mode: Static PGO
                meta_info = f"Freq: {block.pgo_frequency}"

            # Construct HTML Table
            rows = []
            # Header Row
            rows.append(f'<TR><TD COLSPAN="2" BGCOLOR="{bgcolor}" BORDER="1"><B>{self._escape(block.name)}</B><BR/>{meta_info}</TD></TR>')
            
            # Instructions
            max_instr = 6
            for i, instr in enumerate(block.instructions):
                if i >= max_instr:
                    rows.append(f'<TR><TD COLSPAN="2" ALIGN="LEFT" BGCOLOR="{bgcolor}"><I>... ({len(block.instructions)-max_instr} more)</I></TD></TR>')
                    break
                rows.append(f'<TR><TD ALIGN="LEFT" BGCOLOR="{bgcolor}" BORDER="0"><FONT POINT-SIZE="10">{self._escape(instr)}</FONT></TD></TR>')

            label = f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="2">{ "".join(rows) }</TABLE>>'
            dot.node(str(n), label=label, color=border_color)

        # 2. Edges
        for u, v, data in self.G.edges(data=True):
            prob = data.get('probability', 0.0)
            
            # Default Style
            color = "gray"
            penwidth = "1.0"
            style = "solid"
            fontcolor = "gray"
            
            # Highlight Logic
            if (u, v) in trace_edges:
                color = "#0000FF" # Blue for taken path
                penwidth = "3.0"  # Thick
                fontcolor = "black"
            elif prob > 0.80:
                # Main paths that weren't taken in this specific trace
                color = "black"
                penwidth = "1.5"
            
            # Label (Probability)
            label = f"{prob:.2f}"
            
            dot.edge(str(u), str(v), label=label, color=color, penwidth=penwidth, fontcolor=fontcolor)

        logger.info(f"Rendering to {output_path}.svg ...")
        try:
            dot.render(output_path, cleanup=True)
            logger.info("Done.")
        except Exception as e:
            logger.error(f"Graphviz error: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mir_file")
    parser.add_argument("--func", default=None, help="Function name to analyze")
    parser.add_argument("--out", default="mir_viz", help="Output filename")
    parser.add_argument("--steps", type=int, default=100, help="Simulation steps")
    parser.add_argument("--highlight-path", action="store_true", help="Run simulation and highlight the path")
    parser.add_argument("--check-block", type=int, help="Tool: Print transitions from block ID")
    args = parser.parse_args()

    # 1. Parsing
    parser_tool = MIRParser(args.mir_file)
    funcs = parser_tool.parse()
    
    if not funcs:
        logger.error("No functions found!")
        return

    # Auto-select function (prefer 'main')
    target_name = None
    if args.func:
        target_name = next((n for n in funcs if args.func in n), None)
    else:
        # Heuristic: Prefer "main", then shortest name, then first
        mains = [n for n in funcs if "main" in n]
        if mains:
            target_name = min(mains, key=len) 
        else:
            target_name = list(funcs.keys())[0]
            
    if not target_name:
        sys.exit("Could not identify target function.")
        
    G = funcs[target_name]
    logger.info(f"Analyzing function: {target_name} ({len(G.nodes)} blocks)")

    # 2. Transition Tool
    if args.check_block is not None:
        sim = TraceSimulator(G)
        trans = sim.get_transitions(args.check_block)
        print(f"\n[Tool] Transitions from Block {args.check_block}:")
        if not trans:
            print("  (No successors / Return block)")
        for t in trans:
            print(f"  --> Block {t['next_block']} (Prob: {t['probability']:.4f})")
        return

    # 3. Simulation & Visualization
    # Even if highlight-path is False, we might want to simulate to calculate hits
    # if PGO data is missing.
    sim = TraceSimulator(G)
    
    # Run simulation
    trace_path = sim.simulate(steps=args.steps)
    
    # Save trace to JSON
    trace_json = []
    for bid in trace_path:
        b = G.nodes[bid]['obj']
        trace_json.append({"id": b.id, "name": b.name, "instr_count": len(b.instructions)})
    
    with open(f"{args.out}_trace.json", "w") as f:
        json.dump(trace_json, f, indent=2)

    # 4. Render
    viz = CFGVisualizer(G)
    
    # If user wants to see the path, pass it. 
    # Otherwise pass None (but nodes will still have 'sim_hits' populated if needed)
    path_arg = trace_path if args.highlight_path else None
    
    # If we are NOT highlighting a path, but PGO freq is 0 everywhere,
    # we might want to still show hits from the simulation as a heatmap substitute.
    # But strictly following logic: pass trace_path triggers "Hits: X" label style.
    if args.highlight_path:
        viz.render(f"{args.out}", trace_path=trace_path)
    else:
        # Render clean graph (Heatmap mode logic can be added here if needed)
        # Currently defaults to Freq: 0 (white) for your file
        viz.render(f"{args.out}", trace_path=None)

if __name__ == "__main__":
    main()
