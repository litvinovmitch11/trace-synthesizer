# visualizer.py
import argparse
from graphviz import Digraph
from common import load_project

def render_function(func_name, func_data, trace_name=None, out_format="svg"):
    dot = Digraph(comment=func_name, format=out_format)
    dot.attr(rankdir='TB', fontname='Helvetica', splines='ortho')
    dot.attr('node', shape='none', fontname='Courier New')

    # Calculate Trace Heatmap if trace provided
    visited_blocks = set()
    visited_edges = set()
    
    if trace_name and trace_name in func_data.traces:
        trace = func_data.traces[trace_name]
        visited_blocks = set(trace)
        for i in range(len(trace)-1):
            visited_edges.add((trace[i], trace[i+1]))

    # Nodes
    for bid, block in func_data.blocks.items():
        # Build HTML Label
        rows = ""
        # Header
        color = "#eeeeee"
        if bid in visited_blocks:
            color = "#aaffaa" # Green if visited
        
        rows += f'<TR><TD BGCOLOR="{color}" BORDER="1"><B>BB.{bid}</B></TD></TR>'
        
        # Instructions (Fix #6)
        instr_text = ""
        for instr in block.head_instrs:
            instr_text += f"{instr}<BR ALIGN='LEFT'/>"
        
        if block.instr_count > (len(block.head_instrs) + len(block.tail_instrs)):
            instr_text += f"... {block.instr_count} total ...<BR ALIGN='LEFT'/>"
            
        for instr in block.tail_instrs:
            instr_text += f"{instr}<BR ALIGN='LEFT'/>"
            
        rows += f'<TR><TD BORDER="1" ALIGN="LEFT">{instr_text}</TD></TR>'
        
        label = f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">{rows}</TABLE>>'
        dot.node(str(bid), label=label)

    # Edges
    for edge in func_data.edges:
        color = "black"
        penwidth = "1"
        style = "solid"
        
        if (edge.src, edge.dst) in visited_edges:
            color = "blue"
            penwidth = "3"
        elif edge.prob < 0.01:
             style = "dashed" # Low prob
             color = "gray"

        label = f"{edge.prob:.2%}"
        dot.edge(str(edge.src), str(edge.dst), label=label, color=color, penwidth=penwidth, style=style)

    filename = f"graph_{func_name}_{trace_name if trace_name else 'cfg'}"
    dot.render(filename, cleanup=True)
    print(f"Generated {filename}.{out_format}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("project_file")
    parser.add_argument("--func", required=True)
    parser.add_argument("--trace", help="Name of trace to visualize (e.g. 'real_trace')")
    args = parser.parse_args()

    proj = load_project(args.project_file)
    if args.func in proj:
        render_function(args.func, proj[args.func], args.trace)
    else:
        print("Function not found.")
