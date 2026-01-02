# trace_mapper.py
import subprocess
import struct
import argparse
import sys
from collections import defaultdict
from mir_parser import MIRParser
from common import save_project

def symbolize_trace(binary, trace_bin, symbolizer):
    pcs = []
    try:
        with open(trace_bin, "rb") as f:
            while chunk := f.read(8):
                pcs.append(struct.unpack("Q", chunk)[0])
    except FileNotFoundError:
        print("Trace file not found")
        return []

    print(f"[*] Symbolizing {len(pcs)} events...")
    # Fix: --no-demangle essential for matching MIR names (usually)
    # But sometimes MIR has demangled names in 'name:'. 
    # We will try both or flexible matching.
    args = [symbolizer, "--obj", binary, "--output-style=GNU", "--functions=linkage", "--no-demangle"]
    
    inp = "\n".join([hex(pc) for pc in pcs])
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    out, _ = proc.communicate(input=inp)
    
    events = []
    lines = out.strip().split('\n')
    for i in range(0, len(lines), 2):
        if i+1 >= len(lines): break
        func = lines[i].strip()
        loc = lines[i+1].strip()
        ln = -1
        if ':' in loc:
            parts = loc.split(':')
            for p in parts:
                if p.isdigit(): 
                    ln = int(p)
                    break
        events.append((func, ln))
    return events

def find_closest_block(target_line, block_map):
    """
    Fix #4: Nearest Neighbor Search.
    If line 46 isn't in MIR, but block 2 covers [45, 47], we pick block 2.
    """
    if not block_map: return None
    
    # 1. Exact match
    if target_line in block_map:
        return block_map[target_line]
    
    # 2. Closest match
    # block_map: line_int -> block_id
    best_dist = 999999
    best_blk = None
    
    for line, blk in block_map.items():
        dist = abs(line - target_line)
        if dist < best_dist:
            best_dist = dist
            best_blk = blk
            
    # Heuristic: If closest line is too far (e.g. > 50 lines), it's likely wrong function entry
    if best_dist < 50:
        return best_blk
    return None

def map_trace(events, mir_funcs):
    print("[*] Mapping trace to CFG blocks...")
    
    # Prepare lookup tables
    # FuncName -> { LineNum -> BlockID }
    func_line_maps = {}
    
    for fname, fdata in mir_funcs.items():
        lm = {}
        for bid, bdata in fdata.blocks.items():
            for l in bdata.lines:
                lm[l] = bid
        func_line_maps[fname] = lm

    hits = 0
    misses = 0
    
    # Helper to fuzzy match function names (MIR mangled vs Symbolizer)
    # Cache mapping
    name_cache = {}

    for i, (func_name, line_num) in enumerate(events):
        target_f = name_cache.get(func_name)
        
        if not target_f:
            # Try to find function in MIR keys
            for mk in mir_funcs:
                # Basic string inclusion check
                if func_name in mk or mk in func_name:
                    target_f = mk
                    name_cache[func_name] = target_f
                    break
        
        if target_f and target_f in mir_funcs:
            # Resolve Block
            blk_id = find_closest_block(line_num, func_line_maps[target_f])
            
            if blk_id is not None:
                # Add to trace in FunctionData
                trace_list = mir_funcs[target_f].traces.get("real_trace", [])
                
                # Simple compression: don't add same block 2x in a row unless you want full instruction trace
                # Keeping it simple:
                trace_list.append(blk_id)
                mir_funcs[target_f].traces["real_trace"] = trace_list
                hits += 1
            else:
                # Fallback: Map to entry block (usually 0) if we are inside the function but line is weird
                if 0 in mir_funcs[target_f].blocks:
                     trace_list = mir_funcs[target_f].traces.get("real_trace", [])
                     trace_list.append(0)
                     mir_funcs[target_f].traces["real_trace"] = trace_list
                     hits += 1 # Counted as "recovered hit"
                else:
                    misses += 1
        else:
            # System functions (std::) usually end up here. Expected.
            misses += 1

    print(f"[*] Mapping Stats: Hits={hits}, Misses (System/Unmapped)={misses}")
    return mir_funcs

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mir_file")
    parser.add_argument("binary")
    parser.add_argument("trace_bin")
    parser.add_argument("--symbolizer", default="llvm-symbolizer-18")
    parser.add_argument("--out", default="project.json")
    args = parser.parse_args()

    # 1. Parse MIR
    parser_tool = MIRParser(args.mir_file)
    project_data = parser_tool.parse()
    
    # 2. Symbolize Trace
    events = symbolize_trace(args.binary, args.trace_bin, args.symbolizer)
    
    # 3. Map
    final_data = map_trace(events, project_data)
    
    # 4. Save
    save_project(final_data, args.out)
    print(f"[OK] Project saved to {args.out}")
