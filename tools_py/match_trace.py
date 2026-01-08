import argparse
import json
import re
import struct
import sys
import os
import bisect

# --- Parsers ---

def parse_cfg_json(cfg_path):
    print(f"[+] Loading CFG: {cfg_path}")
    try:
        with open(cfg_path, 'r') as f:
            data = json.load(f)
        valid_ids = set(block['id'] for block in data['blocks'])
        return data, valid_ids
    except Exception as e:
        print(f"Error reading CFG JSON: {e}")
        sys.exit(1)

def parse_bb_addr_map(readobj_output_path, target_func_name):
    print(f"[+] Parsing BBAddrMap for function: '{target_func_name}'...")
    with open(readobj_output_path, 'r') as f:
        lines = f.readlines()

    target_base_addr = None
    bb_ranges = [] 
    
    current_func_name = None
    current_func_addr = None
    in_bb_entries = False
    
    current_bb_id = None
    current_bb_offset = None
    current_bb_size = None

    for line in lines:
        line = line.strip()
        if line.startswith("Function {"):
            current_func_name = None
            current_func_addr = None
            in_bb_entries = False
            continue
        if line.startswith("Name:"):
            parts = line.split(":", 1)
            if len(parts) > 1: current_func_name = parts[1].strip()
            continue
        if line.startswith("At:"):
            match = re.search(r"At:\s*(0x[0-9a-fA-F]+)", line)
            if match: current_func_addr = int(match.group(1), 16)
            continue
        if "BB Entries [" in line:
            in_bb_entries = True
            if current_func_name == target_func_name:
                target_base_addr = current_func_addr
            continue
        
        if in_bb_entries and current_func_name == target_func_name:
            if line.startswith("]"):
                in_bb_entries = False
                continue
            
            # Парсинг ID, Offset, Size (stateful)
            id_match = re.search(r"ID:\s*(\d+)", line)
            if id_match: current_bb_id = int(id_match.group(1))
            
            off_match = re.search(r"Offset:\s*(0x[0-9a-fA-F]+)", line)
            if off_match: current_bb_offset = int(off_match.group(1), 16)
            
            sz_match = re.search(r"Size:\s*(0x[0-9a-fA-F]+)", line)
            if sz_match: current_bb_size = int(sz_match.group(1), 16)

            if current_bb_id is not None and current_bb_offset is not None and current_bb_size is not None:
                bb_ranges.append({
                    "start": current_bb_offset,
                    "end": current_bb_offset + current_bb_size,
                    "id": current_bb_id
                })
                current_bb_id = None
                current_bb_offset = None
                current_bb_size = None

    if target_base_addr is None:
        print(f"Error: Function '{target_func_name}' not found in out.txt.")
        return None, None, None
    
    bb_ranges.sort(key=lambda x: x["start"])
    return target_base_addr, bb_ranges

def parse_binary_trace(trace_path):
    """Читает файл bb_trace.bin как массив uint64_t адресов"""
    trace_addrs = []
    try:
        with open(trace_path, 'rb') as f:
            while True:
                # Читаем 8 байт (64-бит адрес)
                chunk = f.read(8)
                if len(chunk) < 8:
                    break
                addr = struct.unpack('<Q', chunk)[0] # <Q = little-endian unsigned long long
                trace_addrs.append(addr)
    except Exception as e:
        print(f"Error reading binary trace: {e}")
        sys.exit(1)
    return trace_addrs

def resolve_bb(abs_addr, func_base, bb_ranges):
    rel_offset = abs_addr - func_base
    if rel_offset < 0: return None # Адрес до начала функции (другая секция)

    # Ищем диапазон
    starts = [x['start'] for x in bb_ranges]
    idx = bisect.bisect_right(starts, rel_offset)
    if idx == 0: return None
    
    candidate = bb_ranges[idx - 1]
    # Если адрес попадает в [start, end) блока
    if candidate['start'] <= rel_offset < candidate['end']:
        return candidate['id']
    return None

# --- Main ---

def match_trace(cfg_path, readobj_path, trace_path, output_path):
    cfg_data, valid_block_ids = parse_cfg_json(cfg_path)
    target_func = cfg_data.get("function_name", "main")
    
    func_base_addr, bb_ranges = parse_bb_addr_map(readobj_path, target_func)
    if func_base_addr is None: sys.exit(1)
        
    print(f"    Function '{target_func}' base: {hex(func_base_addr)}")
    print(f"    Loaded {len(bb_ranges)} BB ranges.")

    raw_addrs = parse_binary_trace(trace_path)
    print(f"    Total trace events (raw): {len(raw_addrs)}")
    
    final_trace = []
    matches = 0
    
    for addr in raw_addrs:
        bb_id = resolve_bb(addr, func_base_addr, bb_ranges)
        if bb_id is not None:
            # Опционально: сжимать повторы (1, 1, 1 -> 1)
            # if not final_trace or final_trace[-1] != bb_id:
            final_trace.append(bb_id)
            matches += 1

    print(f"[+] Matching Complete. Matched events: {matches}")
    
    result = {
        "function_name": target_func,
        "trace_bb_ids": final_trace
    }
    
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"    Saved to: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cfg", required=True)
    parser.add_argument("--readobj", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--output", default="final_trace.json")
    args = parser.parse_args()
    match_trace(args.cfg, args.readobj, args.trace, args.output)
