# mir_parser.py
import re
from typing import Dict
from common import FunctionData, BlockData, EdgeData

class MIRParser:
    def __init__(self, mir_path: str):
        self.mir_path = mir_path
        self.functions: Dict[str, FunctionData] = {}
        self.metadata_cache = {}

    def parse(self):
        print(f"[*] Parsing MIR file: {self.mir_path}...")
        
        # Regex pre-compilation for speed (Fix #7)
        re_meta = re.compile(r'!(\d+)\s*=\s*(?:distinct\s+)?!DILocation\(line:\s*(\d+)')
        re_func_start = re.compile(r'^name:\s+(.+)$')
        re_body_start = re.compile(r'^body:\s+')
        re_bb = re.compile(r'^\s*bb\.(\d+)(?:.*):')
        re_succ = re.compile(r'^\s*successors:\s*(.*)')
        re_instr = re.compile(r'^\s+(?:[a-zA-Z0-9%]+:\s*)?([a-zA-Z0-9_]+)\s+') # Opcode capture
        re_debug_loc = re.compile(r'debug-location\s*!(\d+)')

        current_func_name = None
        current_func_body = []
        in_body = False

        with open(self.mir_path, 'r') as f:
            for line in f:
                # 1. Parse Metadata globally (can be huge, but needed)
                if line.startswith('!'):
                    m = re_meta.search(line)
                    if m:
                        self.metadata_cache[int(m.group(1))] = int(m.group(2))
                    continue

                # 2. Function separation
                m_name = re_func_start.match(line)
                if m_name:
                    # Clean function name (strip quotes)
                    raw_name = m_name.group(1).strip()
                    if raw_name.startswith('"') and raw_name.endswith('"'):
                        raw_name = raw_name[1:-1]
                    current_func_name = raw_name
                    continue
                
                if re_body_start.match(line):
                    in_body = True
                    continue
                
                # End of function (heuristics: '...' or new 'name:')
                if line.startswith('...') or (line.startswith('name:') and in_body):
                    if current_func_name and current_func_body:
                        self._process_function(current_func_name, current_func_body, re_bb, re_succ, re_instr, re_debug_loc)
                    current_func_body = []
                    in_body = False
                    # specific check if we just hit a new name
                    if line.startswith('name:'):
                         m_name = re_func_start.match(line)
                         if m_name:
                             raw_name = m_name.group(1).strip()
                             if raw_name.startswith('"') and raw_name.endswith('"'):
                                raw_name = raw_name[1:-1]
                             current_func_name = raw_name
                    continue

                if in_body:
                    current_func_body.append(line)

        return self.functions

    def _process_function(self, name, body_lines, re_bb, re_succ, re_instr, re_dbg):
        blocks = {}
        edges = []
        
        curr_id = None
        curr_instrs = []
        curr_lines = set()
        
        for line in body_lines:
            # BB Header
            m_bb = re_bb.match(line)
            if m_bb:
                # Finish previous block
                if curr_id is not None:
                    blocks[curr_id] = self._create_block(curr_id, curr_lines, curr_instrs)
                
                curr_id = int(m_bb.group(1))
                curr_instrs = []
                curr_lines = set()
                continue
            
            if curr_id is None: continue

            # Successors
            if "successors:" in line:
                m_succ = re_succ.match(line)
                if m_succ:
                    self._parse_edges(curr_id, m_succ.group(1), edges)
                continue
            
            # Instructions & Debug Info
            # We want actual instructions, not just labels or comments
            m_inst = re_instr.match(line)
            if m_inst and not line.strip().startswith('successors') and not line.strip().startswith('liveins'):
                opcode = m_inst.group(1)
                # Keep simplified instruction text
                clean_line = line.split("debug-location")[0].strip()
                curr_instrs.append(clean_line)
                
                # Debug line mapping
                m_dbg_loc = re_dbg.search(line)
                if m_dbg_loc:
                    mid = int(m_dbg_loc.group(1))
                    if mid in self.metadata_cache:
                        curr_lines.add(self.metadata_cache[mid])

        # Final block
        if curr_id is not None:
            blocks[curr_id] = self._create_block(curr_id, curr_lines, curr_instrs)

        self.functions[name] = FunctionData(name=name, blocks=blocks, edges=edges)

    def _create_block(self, bid, lines, instrs):
        # Fix #6: Store limited instructions for clean visualization
        count = len(instrs)
        head = instrs[:3]
        tail = instrs[-2:] if count > 3 else []
        return BlockData(
            id=bid,
            lines=sorted(list(lines)),
            head_instrs=head,
            tail_instrs=tail,
            instr_count=count
        )

    def _parse_edges(self, src_id, content, edges_list):
        # Format: %bb.1(0xABC...), %bb.2(0x123...)
        parts = content.split(',')
        total_w = 0.0
        temp_edges = []
        
        for p in parts:
            p = p.strip()
            # Regex to pull bb.ID and probability hex
            m = re.search(r'%bb\.(\d+)(?:\((0x[0-9a-fA-F]+)\))?', p)
            if m:
                dst = int(m.group(1))
                w_hex = m.group(2)
                weight = int(w_hex, 16) if w_hex else 0
                total_w += weight
                temp_edges.append((dst, weight))
        
        for dst, w in temp_edges:
            prob = (w / total_w) if total_w > 0 else (1.0 / len(temp_edges))
            edges_list.append(EdgeData(src=src_id, dst=dst, prob=prob))
