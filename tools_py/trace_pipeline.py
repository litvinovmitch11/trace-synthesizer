import argparse
import json
import struct
import sys


def parse_bb_map(map_file):
    bb_ranges = []
    with open(map_file, "r") as f:
        lines = f.readlines()

    current_func = None
    current_base_addr = None
    current_bb_id = None
    current_offset = None
    current_size = None

    for line in lines:
        line = line.strip()
        if line.startswith("Name:"):
            current_func = line.split("Name:")[1].strip()
        elif line.startswith("Base Address:"):
            current_base_addr = int(line.split("Base Address:")[1].strip(), 16)
        elif line.startswith("ID:"):
            current_bb_id = int(line.split("ID:")[1].strip())
        elif line.startswith("Offset:"):
            current_offset = int(line.split("Offset:")[1].strip(), 16)
        elif line.startswith("Size:"):
            current_size = int(line.split("Size:")[1].strip(), 16)
            if (
                current_func
                and current_base_addr is not None
                and current_bb_id is not None
            ):
                start_rva = current_base_addr + current_offset
                end_rva = start_rva + current_size
                bb_ranges.append((start_rva, end_rva, current_func, current_bb_id))
                current_bb_id = None
                current_offset = None
                current_size = None

    bb_ranges.sort(key=lambda x: x[0])
    return bb_ranges


def get_bb(rva, bb_ranges):
    left, right = 0, len(bb_ranges) - 1
    while left <= right:
        mid = (left + right) // 2
        start_rva, end_rva, func, bb_id = bb_ranges[mid]
        if start_rva <= rva < end_rva:
            return func, bb_id
        elif rva < start_rva:
            right = mid - 1
        else:
            left = mid + 1
    return None, None


def load_cfg_edges(cfg_file):
    with open(cfg_file, "r") as f:
        cfg_data = json.load(f)

    edges = {}
    entry_blocks = {}
    exit_blocks = {}
    calls = {}
    for func in cfg_data:
        func_name = func["function_name"]
        edges[func_name] = {}
        entry_blocks[func_name] = set()
        exit_blocks[func_name] = set()
        calls[func_name] = {}
        for block in func["blocks"]:
            bb_id = block["id"]
            edges[func_name][bb_id] = set()

            if block.get("is_entry", False):
                entry_blocks[func_name].add(bb_id)

            if block.get("has_call", False):
                calls[func_name][bb_id] = block.get("call_target", "")

            succs = block.get("successors", [])
            if not succs:
                exit_blocks[func_name].add(bb_id)

            for succ in succs:
                edges[func_name][bb_id].add(succ["target_id"])
    return edges, entry_blocks, exit_blocks, calls


def main():
    parser = argparse.ArgumentParser(
        description="Compress and validate DynamoRIO trace against LLVM CFG."
    )
    parser.add_argument("--cfg", required=True, help="Path to main.cfg.json")
    parser.add_argument("--map", required=True, help="Path to bb_addr_map.txt")
    parser.add_argument(
        "--trace", required=True, help="Path to raw trace.bin from DynamoRIO"
    )
    parser.add_argument(
        "--out", required=True, help="Path to save compressed_trace.json"
    )

    args = parser.parse_args()

    print(f"[Trace Pipeline] Loading CFG edges from {args.cfg}...")
    edges, entry_blocks, exit_blocks, calls = load_cfg_edges(args.cfg)

    print(f"[Trace Pipeline] Loading BB Address Map from {args.map}...")
    bb_ranges = parse_bb_map(args.map)

    print(f"[Trace Pipeline] Reading raw trace from {args.trace}...")
    trace_rvas = []
    with open(args.trace, "rb") as f:
        while True:
            chunk = f.read(8)
            if not chunk:
                break
            rva = struct.unpack("<Q", chunk)[0]
            trace_rvas.append(rva)

    if not trace_rvas:
        print("Error: Trace is empty.")
        sys.exit(1)

    print(f"[Trace Pipeline] Compressing trace...")
    bb_sequence = []
    unmapped_count = 0

    for rva in trace_rvas:
        func, bb_id = get_bb(rva, bb_ranges)
        if func is None:
            unmapped_count += 1
            continue

        if not bb_sequence or bb_sequence[-1] != (func, bb_id):
            bb_sequence.append((func, bb_id))

    print(f"Total instructions logged: {len(trace_rvas)}")
    print(f"Unmapped instructions: {unmapped_count}")
    print(f"Compressed BB sequence length: {len(bb_sequence)}")

    if len(bb_sequence) == 0:
        print("Error: Empty valid BB sequence.")
        sys.exit(1)

    print(f"[Trace Pipeline] Validating transitions...")
    invalid_transitions = 0
    valid_transitions = 0
    inter_procedural = 0

    for i in range(len(bb_sequence) - 1):
        prev_func, prev_bb = bb_sequence[i]
        curr_func, curr_bb = bb_sequence[i + 1]

        if prev_func != curr_func:
            inter_procedural += 1
            continue

        if prev_func not in edges or prev_bb not in edges[prev_func]:
            continue

        if curr_bb not in edges[prev_func][prev_bb]:
            # Check for recursive call (call to itself)
            is_recursive_call = (
                calls[prev_func].get(prev_bb) == curr_func
                and curr_bb in entry_blocks[curr_func]
            )
            # Check for return from recursive call
            # If prev_bb is an exit block, any transition is a return
            is_recursive_return = prev_bb in exit_blocks[prev_func]

            if is_recursive_call or is_recursive_return:
                inter_procedural += 1
                continue

            print(
                f"Invalid transition detected: {prev_func}:{prev_bb} -> {curr_func}:{curr_bb}"
            )
            invalid_transitions += 1
        else:
            valid_transitions += 1

    print(f"Valid intra-procedural transitions: {valid_transitions}")
    print(f"Inter-procedural transitions (calls/returns): {inter_procedural}")

    if invalid_transitions > 0:
        print(f"❌ FAILED: Found {invalid_transitions} invalid transitions.")
        sys.exit(1)
    else:
        print("✅ SUCCESS: 100% Valid trace!")

    # Формируем JSON-документ для сохранения
    compressed_trace = []
    for func, bb_id in bb_sequence:
        compressed_trace.append({"func": func, "bb": bb_id})

    with open(args.out, "w") as f:
        json.dump(compressed_trace, f)

    print(f"Compressed trace perfectly saved to: {args.out}")


if __name__ == "__main__":
    main()
