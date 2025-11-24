# TODO: just for debug

import subprocess
import re
import tempfile
from graphviz import Digraph
import os
import click

def parse_trace(trace_file):
    """Parse trace file and return list of basic block addresses"""
    with open(trace_file, 'r') as f:
        addresses = [line.strip() for line in f if line.strip()]
    return addresses

def get_basic_blocks_from_binary(binary_path):
    """Extract basic blocks using objdump"""
    try:
        # Run objdump to disassemble the binary
        result = subprocess.run(
            ['objdump', '-d', binary_path],
            capture_output=True, text=True, check=True
        )
        
        basic_blocks = {}
        current_function = None
        current_block = []
        block_addresses = []
        
        for line in result.stdout.split('\n'):
            # Look for function headers
            func_match = re.match(r'^([0-9a-f]+) <(.*)>:', line)
            if func_match:
                if current_function and current_block:
                    basic_blocks[current_function] = block_addresses
                current_function = func_match.group(2)
                current_block = []
                block_addresses = []
                continue
            
            # Look for instruction lines
            instr_match = re.match(r'^\s*([0-9a-f]+):\s', line)
            if instr_match:
                address = instr_match.group(1)
                current_block.append(line.strip())
                block_addresses.append(address)
        
        # Don't forget the last function
        if current_function and current_block:
            basic_blocks[current_function] = block_addresses
            
        return basic_blocks
        
    except subprocess.CalledProcessError as e:
        print(f"Error running objdump: {e}")
        return {}

def build_cfg_with_trace(binary_path, trace_file, output_path):
    """Build CFG and highlight executed basic blocks from trace"""
    
    # Parse the trace
    trace_addresses = parse_trace(trace_file)
    print(f"Found {len(trace_addresses)} trace entries")
    
    # Get basic blocks from binary
    basic_blocks = get_basic_blocks_from_binary(binary_path)
    
    # Create Graphviz diagram
    dot = Digraph(comment='CFG with Execution Trace')
    dot.attr(rankdir='TB')
    
    # Set default node attributes
    dot.attr('node', shape='box', fontname='Courier', fontsize='10')
    dot.attr('edge', fontname='Courier', fontsize='9')
    
    # Track which basic blocks were executed
    executed_blocks = set()
    
    # Process trace to find executed blocks
    for trace_addr in trace_addresses:
        # Remove any leading zeros for matching
        trace_addr_clean = trace_addr.lstrip('0')
        
        for func_name, blocks in basic_blocks.items():
            for block_addr in blocks:
                block_addr_clean = block_addr.lstrip('0')
                if block_addr_clean == trace_addr_clean:
                    block_id = f"{func_name}_{block_addr}"
                    executed_blocks.add(block_id)
    
    print(f"Found {len(executed_blocks)} executed basic blocks")
    
    # Add nodes to graph
    for func_name, blocks in basic_blocks.items():
        with dot.subgraph(name=f'cluster_{func_name}') as subgraph:
            subgraph.attr(label=func_name, style='rounded', color='lightgray')
            
            for i, block_addr in enumerate(blocks):
                block_id = f"{func_name}_{block_addr}"
                
                # Find instructions for this basic block
                block_instrs = []
                for block in basic_blocks[func_name]:
                    if block == block_addr:
                        # This would need more sophisticated parsing
                        block_instrs.append(f"{block_addr}: ...")
                        break
                
                label = f"{func_name}\\n{block_addr}"
                if len(block_instrs) > 0:
                    label += f"\\n{block_instrs[0]}"
                
                # Color executed blocks
                if block_id in executed_blocks:
                    subgraph.node(block_id, label, style='filled', fillcolor='lightgreen')
                else:
                    subgraph.node(block_id, label)
                
                # Add edges between consecutive blocks (simplified)
                if i < len(blocks) - 1:
                    next_block_id = f"{func_name}_{blocks[i+1]}"
                    subgraph.edge(block_id, next_block_id)
    
    # Render the graph
    dot.render(output_path, format='png', cleanup=True)
    print(f"CFG saved to {output_path}.png")

@click.command()
@click.argument('binary_path')
@click.argument('trace_file')
@click.argument('output_path')
def main(binary_path, trace_file, output_path):
    """Visualize CFG with execution trace highlighting"""
    print(f"Analyzing {binary_path} with trace {trace_file}...")
    build_cfg_with_trace(binary_path, trace_file, output_path)

if __name__ == '__main__':
    main()
