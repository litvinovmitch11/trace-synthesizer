import json
import sys
from pathlib import Path

import r2pipe
from graphviz import Digraph


class CFGVisualizer:
    def __init__(self):
        # TODO: fix it
        self.traces_dir = Path("traces")
        self.output_dir = Path("traces")
        self.output_dir.mkdir(exist_ok=True)

    def get_trace_addresses(self, trace_file: Path) -> set:
        """Read trace file and return set of executed addresses (int)."""
        addresses = set()

        if not trace_file.exists():
            print(f"Error: Trace file {trace_file} not found.")
            sys.exit(1)

        print(f"[*] Reading trace from {trace_file}...")
        with trace_file.open("r") as f:
            for line in f:
                line = line.strip()
                # Skip headers and empty lines
                if not line or "Trace" in line or "Done" in line:
                    continue
                try:
                    addresses.add(int(line, 16))
                except ValueError:
                    print(f"Warning: Skipping invalid line in trace: {line}")

        print(f"[*] Found {len(addresses)} unique addresses in trace")
        return addresses

    def generate_cfg(
        self, binary_path: Path, trace_addrs: set, output_filename: str
    ) -> bool:
        """Generate CFG with execution highlighting."""
        print(f"[*] Opening binary {binary_path} with Radare2...")

        try:
            # Open binary with r2pipe
            r2 = r2pipe.open(str(binary_path), flags=["-2"])

            # Analyze binary
            print("[*] Analyzing binary structure...")
            r2.cmd("aaa")

            # Extract CFG for main function
            print("[*] Extracting CFG for 'main' function...")
            graph_json_str = r2.cmd("agj @ main")

            if not graph_json_str:
                print("Error: No graph data received from Radare2")
                r2.quit()
                return False

            graph_data = json.loads(graph_json_str)

            if not graph_data:
                print("Error: No graph data found for main function")
                r2.quit()
                return False

            func_graph = graph_data[0]
            blocks = func_graph.get("blocks", [])

            print(f"[*] Found {len(blocks)} basic blocks in main function")

            # Create Graphviz diagram
            dot = Digraph(comment="CFG with Execution Trace", format="png")
            dot.attr(rankdir="TB")
            dot.attr("node", shape="rect", fontname="Courier New", fontsize="10")

            # Process each basic block
            for block in blocks:
                bb_addr = block.get("offset")
                bb_size = block.get("size", 0)

                # Get disassembly for this block
                if bb_size > 0:
                    ops_json = r2.cmd(f"pDj {bb_size} @ {bb_addr}")
                    try:
                        ops = json.loads(ops_json) if ops_json else []
                    except json.JSONDecodeError:
                        ops = []
                else:
                    ops = []

                # Build node label
                label_text = f"Block: {hex(bb_addr)}\n"
                label_text += "─" * 30 + "\n"

                # Check if block was executed
                block_executed = bb_addr in trace_addrs

                # Add instructions to label
                for op in ops:
                    mnemonic = op.get("opcode", "unknown")
                    label_text += f"{mnemonic}\\l"

                # Color executed blocks
                fill_color = "#ffffff"  # white for non-executed
                if block_executed:
                    fill_color = "#98fb98"  # pale green for executed

                dot.node(
                    str(bb_addr), label=label_text, style="filled", fillcolor=fill_color
                )

                # Add edges
                jump_addr = block.get("jump")
                fail_addr = block.get("fail")

                if jump_addr:
                    dot.edge(str(bb_addr), str(jump_addr), color="blue", label="jump")
                if fail_addr:
                    dot.edge(str(bb_addr), str(fail_addr), color="red", label="fail")

                # Handle switch cases
                switch_ops = block.get("switch", [])
                for switch_op in switch_ops:
                    target = switch_op.get("addr")
                    dot.edge(str(bb_addr), str(target), style="dashed", label="switch")

            # Render the graph
            output_path = self.output_dir / output_filename
            print(f"[*] Rendering CFG to {output_path}.png...")
            dot.render(str(output_path), cleanup=True)

            r2.quit()
            print(f"[✓] CFG successfully generated: {output_path}.png")
            return True

        except Exception as e:
            print(f"Error generating CFG: {e}")
            return False

    def run(self, binary_path: str, trace_file: str, output_name: str):
        """Main execution method."""
        binary = Path(binary_path)
        trace = Path(trace_file)

        if not binary.exists():
            print(f"Error: Binary {binary} not found")
            sys.exit(1)

        # Get trace addresses and generate CFG
        trace_addrs = self.get_trace_addresses(trace)
        success = self.generate_cfg(binary, trace_addrs, output_name)

        if not success:
            sys.exit(1)


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python -m tools_py.visualize_cfg <binary_path> <trace_file> <output_name>"
        )
        sys.exit(1)

    binary_path = sys.argv[1]
    trace_file = sys.argv[2]
    output_name = sys.argv[3]

    visualizer = CFGVisualizer()
    visualizer.run(binary_path, trace_file, output_name)


if __name__ == "__main__":
    main()
