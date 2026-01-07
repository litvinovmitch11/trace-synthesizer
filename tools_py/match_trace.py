import argparse
import json
import re
import struct
import sys
import os

# --- Parsers ---

def parse_cfg_json(cfg_path):
    print(f"[+] Loading CFG: {cfg_path}")
    try:
        with open(cfg_path, 'r') as f:
            data = json.load(f)
        # Create a set of valid BB IDs for quick lookup
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
    func_offsets = {} # Map: offset -> bb_id
    
    # State machine variables
    current_func_name = None
    current_func_addr = None
    in_bb_entries = False
    
    # Temporary variables for the current block processing
    current_bb_id = None
    current_bb_offset = None

    for line in lines:
        line = line.strip()
        
        # 1. Detect start of a new function definition
        if line.startswith("Function {"):
            current_func_name = None
            current_func_addr = None
            in_bb_entries = False
            continue
            
        # 2. Extract Name
        if line.startswith("Name:"):
            parts = line.split(":", 1)
            if len(parts) > 1:
                current_func_name = parts[1].strip()
            continue
            
        # 3. Extract Function Base Address
        if line.startswith("At:"):
            match = re.search(r"At:\s*(0x[0-9a-fA-F]+)", line)
            if match:
                current_func_addr = int(match.group(1), 16)
            continue
        
        # 4. Detect start of BB Entries section
        if "BB Entries [" in line:
            in_bb_entries = True
            # Check if this is the function we want
            if current_func_name == target_func_name:
                target_base_addr = current_func_addr
            continue
        
        # 5. Process BB Entries only for the target function
        if in_bb_entries and current_func_name == target_func_name:
            # Check for closing bracket of entries
            if line.startswith("]"):
                in_bb_entries = False
                continue

            # Check for ID
            id_match = re.search(r"ID:\s*(\d+)", line)
            if id_match:
                current_bb_id = int(id_match.group(1))

            # Check for Offset
            offset_match = re.search(r"Offset:\s*(0x[0-9a-fA-F]+)", line)
            if offset_match:
                current_bb_offset = int(offset_match.group(1), 16)

            # If we have both ID and Offset, save and reset
            if current_bb_id is not None and current_bb_offset is not None:
                func_offsets[current_bb_offset] = current_bb_id
                current_bb_id = None
                current_bb_offset = None

    if target_base_addr is None:
        print(f"Error: Function '{target_func_name}' not found in BBAddrMap (out.txt).")
        return None, None
    
    if not func_offsets:
        print(f"Error: Found function '{target_func_name}' but extracted 0 basic blocks.")
        print("Check if the parser regex matches your out.txt format.")
        return None, None

    print(f"    Extracted {len(func_offsets)} BB entries for '{target_func_name}'.")
    return target_base_addr, func_offsets

def parse_drcov_log(drcov_path):
    trace_events = [] 
    modules = [] 
    
    try:
        with open(drcov_path, 'rb') as f:
            # -- HEADER PARSING --
            header_content = b""
            # Read until "BB Table:" is found
            while b"BB Table:" not in header_content:
                chunk = f.read(1024)
                if not chunk: break
                header_content += chunk
            
            # Reset to start to parse text lines properly
            f.seek(0)
            
            while True:
                line_bytes = f.readline()
                try:
                    line = line_bytes.decode('utf-8', errors='ignore').strip()
                except:
                    continue
                
                if line.startswith("BB Table:"):
                    break
                
                # Parse Module Table Lines
                # Format: id, containing_id, start, end, entry, offset, preferred_base, path
                parts = [x.strip() for x in line.split(',')]
                if len(parts) >= 8 and parts[0].isdigit():
                    mod_id = int(parts[0])
                    # Column 2 is 'start', usually the memory load address
                    start_addr = int(parts[2], 16) 
                    path = parts[-1]
                    modules.append({"id": mod_id, "base": start_addr, "path": path})

            # -- BINARY TRACE PARSING --
            # struct _bb_entry_t { uint32_t offset; uint16_t size; uint16_t mod_id; };
            struct_fmt = "<IHH" 
            entry_size = struct.calcsize(struct_fmt)
            
            while True:
                data = f.read(entry_size)
                if len(data) < entry_size:
                    break
                
                offset, size, mod_id = struct.unpack(struct_fmt, data)
                
                # Resolve absolute address
                base_addr = 0
                is_target = False
                
                for m in modules:
                    if m['id'] == mod_id:
                        base_addr = m['base']
                        # We only care about events in the main app binary
                        if "app_bin" in m['path']:
                            is_target = True
                        break
                
                if is_target:
                    abs_addr = base_addr + offset
                    trace_events.append(abs_addr)

    except Exception as e:
        print(f"Error parsing drcov file: {e}")
        sys.exit(1)
            
    return trace_events

# --- Main Logic ---

def match_trace(cfg_path, readobj_path, drcov_path, output_path):
    # 1. Parse CFG
    cfg_data, valid_block_ids = parse_cfg_json(cfg_path)
    target_func = cfg_data.get("function_name", "main")
    
    # 2. Parse BBAddrMap
    func_base_addr, func_offsets = parse_bb_addr_map(readobj_path, target_func)
    
    if func_base_addr is None:
        sys.exit(1)
        
    print(f"    Function '{target_func}' base address: {hex(func_base_addr)}")
    
    # 3. Create Lookup Table: AbsAddr -> BB ID
    addr_to_id = {}
    for offset, bb_id in func_offsets.items():
        abs_addr = func_base_addr + offset
        addr_to_id[abs_addr] = bb_id
    
    print(f"    Mapped {len(addr_to_id)} addresses to BB IDs.")

    # 4. Parse Trace and Match
    print(f"[+] Parsing Trace: {drcov_path}")
    raw_trace_addrs = parse_drcov_log(drcov_path)
    print(f"    Total events in app_bin: {len(raw_trace_addrs)}")
    
    final_trace = []
    matches = 0
    misses = 0
    
    for addr in raw_trace_addrs:
        if addr in addr_to_id:
            bb_id = addr_to_id[addr]
            final_trace.append(bb_id)
            matches += 1
        else:
            # Optional: Debug misses (addresses in app_bin but not in this function)
            misses += 1

    print(f"[+] Matching Complete")
    print(f"    Matched events (in '{target_func}'): {matches}")
    print(f"    Ignored events (other funcs): {misses}")
    
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
