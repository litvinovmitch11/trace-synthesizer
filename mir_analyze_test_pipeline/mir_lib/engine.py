import random
import networkx as nx
from typing import List, Dict, Any

class SimulationEngine:
    def __init__(self, graph: nx.DiGraph):
        self.G = graph
        nodes = sorted(list(self.G.nodes))
        self.entry = nodes[0] if nodes else None

    def is_terminal(self, block_id: int) -> bool:
        """Check if execution should stop at this block."""
        # 1. No successors
        succs = list(self.G.successors(block_id))
        if not succs:
            return True
        # 2. Explicit return instruction
        blk = self.G.nodes[block_id]['obj']
        if blk.is_return:
            return True
        return False

    def run_monte_carlo(self, steps=200) -> List[int]:
        if self.entry is None: return []
        path = []
        curr = self.entry
        
        for _ in range(steps):
            path.append(curr)
            self.G.nodes[curr]['obj'].sim_hits += 1
            
            if self.is_terminal(curr):
                break
                
            succs = list(self.G.successors(curr))
            probs = [self.G.edges[curr, s]['probability'] for s in succs]
            try:
                curr = random.choices(succs, weights=probs)[0]
            except ValueError:
                curr = succs[0]
                
        return path

    def generate_dataset(self, num_traces: int) -> List[Dict[str, Any]]:
        """Generates a corpus of traces (Ground Truth based on PGO)."""
        dataset = []
        for i in range(num_traces):
            # Run simulation without side-effects on 'sim_hits' visual counters if preferred,
            # but for simplicity we let it accumulate or create a fresh engine.
            # Here we just generate the path logic:
            
            trace_path = []
            curr = self.entry
            if curr is None: break
            
            # Simple simulation loop for dataset
            while len(trace_path) < 500: # Safety cap
                trace_path.append(curr)
                if self.is_terminal(curr):
                    break
                succs = list(self.G.successors(curr))
                probs = [self.G.edges[curr, s]['probability'] for s in succs]
                curr = random.choices(succs, weights=probs)[0]
            
            dataset.append({
                "trace_id": i,
                "length": len(trace_path),
                "path": trace_path
            })
        return dataset

    def run_interactive(self) -> List[int]:
        if self.entry is None: return []
        path = []
        curr = self.entry
        
        print(f"\n🎮 Interactive Mode: {self.G.name}")
        
        while True:
            path.append(curr)
            self.G.nodes[curr]['obj'].sim_hits += 1
            blk = self.G.nodes[curr]['obj']
            
            print(f"\n📍 Current: {blk.name}")
            if blk.instructions:
                print(f"   Last Instr: {blk.instructions[-1]}")

            # Check termination
            if self.is_terminal(curr):
                print("🛑 Reached Return/Terminal block. Simulation ends.")
                break

            succs = list(self.G.successors(curr))
            print("   Transitions:")
            options = []
            for i, succ in enumerate(succs):
                prob = self.G.edges[curr, succ]['probability'] * 100
                print(f"   [{i}] -> {self.G.nodes[succ]['obj'].name} (Prob: {prob:.1f}%)")
                options.append(succ)
            
            while True:
                choice = input("   Choose [0-N] or 'q': ").strip().lower()
                if choice == 'q': return path
                if choice.isdigit() and 0 <= int(choice) < len(options):
                    curr = options[int(choice)]
                    break
        return path
