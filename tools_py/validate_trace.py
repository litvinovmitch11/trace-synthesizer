import json
import struct
import sys


def parse_bb_map(map_file):
    # Возвращает список кортежей (start_rva, end_rva, func_name, bb_id)
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

    # Сортировка для бинарного поиска
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


def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <cfg.json> <bb_map.txt> <trace.bin>")
        sys.exit(1)

    cfg_file = sys.argv[1]
    map_file = sys.argv[2]
    trace_file = sys.argv[3]

    # 1. Загрузка CFG
    with open(cfg_file, "r") as f:
        cfg_data = json.load(f)

    # Построение словаря ребер: func_name -> {bb_id -> set(target_id)}
    edges = {}
    for func in cfg_data:
        func_name = func["function_name"]
        edges[func_name] = {}
        for block in func["blocks"]:
            bb_id = block["id"]
            edges[func_name][bb_id] = set()
            for succ in block.get("successors", []):
                edges[func_name][bb_id].add(succ["target_id"])

    # 2. Загрузка маппинга (Anchors)
    bb_ranges = parse_bb_map(map_file)

    # 3. Чтение сырого трейса (DynamoRIO)
    trace_rvas = []
    with open(trace_file, "rb") as f:
        while True:
            chunk = f.read(8)
            if not chunk:
                break
            rva = struct.unpack("<Q", chunk)[0]
            trace_rvas.append(rva)

    if not trace_rvas:
        print("Error: Trace is empty.")
        sys.exit(1)

    # 4. Преобразование RVA -> BB Sequence (Сжатие)
    bb_sequence = []
    unmapped_count = 0

    for rva in trace_rvas:
        func, bb_id = get_bb(rva, bb_ranges)
        if func is None:
            unmapped_count += 1
            continue

        # Удаляем подряд идущие дубликаты (т.к. логировали каждую инструкцию в блоке)
        if not bb_sequence or bb_sequence[-1] != (func, bb_id):
            bb_sequence.append((func, bb_id))

    print(f"\n--- Trace Statistics ---")
    print(f"Total instructions logged: {len(trace_rvas)}")
    print(f"Unmapped instructions: {unmapped_count}")
    print(f"Compressed BB sequence length: {len(bb_sequence)}")

    if len(bb_sequence) == 0:
        print("Error: Empty valid BB sequence.")
        sys.exit(1)

    # 5. Валидация переходов (Transitions)
    invalid_transitions = 0
    valid_transitions = 0
    inter_procedural = 0

    for i in range(len(bb_sequence) - 1):
        prev_func, prev_bb = bb_sequence[i]
        curr_func, curr_bb = bb_sequence[i + 1]

        if prev_func != curr_func:
            # Межпроцедурный переход (Call / Return)
            inter_procedural += 1
            continue

        if prev_func not in edges:
            continue

        if prev_bb not in edges[prev_func]:
            continue

        # Внутрипроцедурный переход ДОЛЖЕН существовать в CFG
        if curr_bb not in edges[prev_func][prev_bb]:
            print(
                f"Invalid transition detected: {prev_func}:{prev_bb} -> {curr_func}:{curr_bb}"
            )
            invalid_transitions += 1
        else:
            valid_transitions += 1

    print(f"\n--- Validation Results ---")
    print(f"Valid intra-procedural transitions: {valid_transitions}")
    print(f"Inter-procedural transitions (calls/returns): {inter_procedural}")

    if invalid_transitions == 0:
        print(
            "\n✅ SUCCESS: 100% Valid trace! All intra-procedural transitions perfectly match the LLVM CFG."
        )
    else:
        print(f"\n❌ FAILED: Found {invalid_transitions} invalid transitions.")
        sys.exit(1)


if __name__ == "__main__":
    main()
