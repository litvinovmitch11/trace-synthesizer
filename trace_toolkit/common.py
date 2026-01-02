# common.py
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

@dataclass
class BlockData:
    id: int
    lines: List[int] = field(default_factory=list)
    # Fix #6: Store instruction summary instead of just lines
    head_instrs: List[str] = field(default_factory=list)
    tail_instrs: List[str] = field(default_factory=list)
    instr_count: int = 0
    pgo_count: int = 0  # Raw PGO count if available

@dataclass
class EdgeData:
    src: int
    dst: int
    prob: float
    type: str = "branch" # branch, fallthrough, etc.

@dataclass
class FunctionData:
    name: str
    blocks: Dict[int, BlockData] = field(default_factory=dict)
    edges: List[EdgeData] = field(default_factory=list)
    # Fix #2: Traces are stored here
    traces: Dict[str, List[int]] = field(default_factory=dict)

def save_project(data: Dict[str, FunctionData], filename: str):
    """Saves the project to a JSON file compatible with all tools."""
    serializable = {
        k: asdict(v) for k, v in data.items()
    }
    with open(filename, 'w') as f:
        json.dump(serializable, f, indent=2)

def load_project(filename: str) -> Dict[str, FunctionData]:
    with open(filename, 'r') as f:
        raw = json.load(f)
    
    result = {}
    for fname, f_data in raw.items():
        blocks = {}
        for bid, b_raw in f_data['blocks'].items():
            # Reconstruction of BlockData from dict
            blocks[int(bid)] = BlockData(**b_raw)
        
        edges = [EdgeData(**e) for e in f_data['edges']]
        func = FunctionData(name=fname, blocks=blocks, edges=edges)
        func.traces = f_data.get('traces', {})
        result[fname] = func
    return result
