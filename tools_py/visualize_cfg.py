import argparse
import html
import json
import sys
from collections import defaultdict

import cxxfilt
import graphviz


def demangle(name):
    if not name:
        return name
    try:
        return cxxfilt.demangle(name)
    except Exception:
        return name


def main():
    parser = argparse.ArgumentParser(
        description="Visualize CFG with optional PGO and Trace overlay."
    )
    parser.add_argument("--cfg", required=True, help="Path to main.cfg.json")
    parser.add_argument(
        "--func", required=True, help="Name of the function to visualize"
    )
    parser.add_argument(
        "--trace", required=False, help="Path to compressed_trace.json (optional)"
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output image path (without extension, e.g. 'output/graph')",
    )
    parser.add_argument(
        "--format", required=False, default="svg", help="Output format (svg, png, pdf)"
    )

    args = parser.parse_args()

    # Load CFG
    with open(args.cfg, "r") as f:
        cfg_data = json.load(f)

    func_data = None
    for func in cfg_data:
        if func["function_name"] == args.func:
            func_data = func
            break

    if not func_data:
        print(f"Error: Function '{args.func}' not found in CFG.")
        sys.exit(1)

    # Load Trace if provided
    node_hits = defaultdict(int)
    edge_hits = defaultdict(int)
    max_node_hits = 0

    if args.trace:
        with open(args.trace, "r") as f:
            trace_data = json.load(f)

        # Filter trace for this function only
        func_trace = [entry["bb"] for entry in trace_data if entry["func"] == args.func]

        for bb in func_trace:
            node_hits[bb] += 1
            if node_hits[bb] > max_node_hits:
                max_node_hits = node_hits[bb]

        for i in range(len(func_trace) - 1):
            src = func_trace[i]
            dst = func_trace[i + 1]
            edge_hits[(src, dst)] += 1

    dot = graphviz.Digraph(comment=f"CFG of {demangle(args.func)}", format=args.format)
    dot.attr(rankdir="TB", splines="polyline", overlap="false")
    dot.attr(
        "node",
        shape="box",
        style="filled,rounded",
        fontname="Helvetica",
        fillcolor="white",
    )
    dot.attr("edge", fontname="Helvetica", fontsize="10")

    # Build Nodes
    for block in func_data["blocks"]:
        bb_id = block["id"]
        name = demangle(block.get("name", f"BB_{bb_id}"))
        instr_count = block.get("instr_count", 0)
        is_entry = block.get("is_entry", False)
        successors = block.get("successors", [])
        is_exit = len(successors) == 0
        has_call = block.get("has_call", False)
        call_target = block.get("call_target", "")
        if call_target:
            call_target = demangle(call_target)

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
            label += f"<BR/><B><FONT POINT-SIZE='11' COLOR='#d9534f'>Call: {escaped_call}</FONT></B>"

        if args.trace and max_node_hits > 0:
            hits = node_hits.get(bb_id, 0)
            if hits > 0:
                intensity = hits / max_node_hits
                # 0.0 -> white, 1.0 -> #ccffcc (light green)
                r, g, b = int(255 - 51 * intensity), 255, int(255 - 51 * intensity)
                fillcolor = f"#{r:02X}{g:02X}{b:02X}"
                # If we are coloring the border for start/exit, let's keep it thick and original color
                if not is_entry and not is_exit:
                    penwidth = "2"
                    color = "green"
                label += f"<BR/><FONT POINT-SIZE='10' COLOR='green'><b>Hits: {hits}</b></FONT>"

        label += ">"
        dot.node(
            str(bb_id), label=label, fillcolor=fillcolor, color=color, penwidth=penwidth
        )

    # Build Edges
    for block in func_data["blocks"]:
        bb_id = block["id"]
        for succ in block.get("successors", []):
            target_id = succ["target_id"]
            prob = succ.get("prob", None)
            is_fallthrough = succ.get("is_fallthrough", False)

            edge_label = ""
            color = "black"
            style = "solid"

            if is_fallthrough:
                style = "bold"

            if prob is not None:
                edge_label += f"P={prob:.2f}"
                if not args.trace:
                    if prob >= 0.8:
                        color = "red"
                    elif prob >= 0.2:
                        color = "blue"
                    else:
                        color = "black"

            if args.trace:
                hits = edge_hits.get((bb_id, target_id), 0)
                if hits > 0:
                    color = "green"
                    if edge_label:
                        edge_label += f" | Hits={hits}"
                    else:
                        edge_label = f"Hits={hits}"
                else:
                    color = "gray80"  # Unvisited edges become gray

            # Use label directly. polyline + overlap=false handles it better than ortho.
            dot.edge(
                str(bb_id),
                str(target_id),
                label=edge_label,
                color=color,
                penwidth="1",
                style=style,
                fontcolor=color,
            )

    print(f"[Visualizer] Rendering graph to {args.out}.{args.format} ...")
    dot.render(args.out, cleanup=True)
    print("[Visualizer] Done!")


if __name__ == "__main__":
    main()
