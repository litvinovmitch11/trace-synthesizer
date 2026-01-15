import argparse
import bisect
import json
import re
import struct
import sys

# --- Parsers (Оставляем как было, код валидный) ---


def parse_cfg_json(cfg_path):
    print(f"[+] Loading CFG: {cfg_path}")
    try:
        with open(cfg_path, "r") as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error reading CFG JSON: {e}")
        sys.exit(1)


def parse_bb_addr_map(readobj_output_path, target_func_name):
    # (Код парсинга llvm-readobj оставляем без изменений, он корректен)
    print(f"[+] Parsing BBAddrMap for function: '{target_func_name}'...")
    with open(readobj_output_path, "r") as f:
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
            if len(parts) > 1:
                current_func_name = parts[1].strip()
            continue
        if line.startswith("At:"):
            match = re.search(r"At:\s*(0x[0-9a-fA-F]+)", line)
            if match:
                current_func_addr = int(match.group(1), 16)
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

            id_match = re.search(r"ID:\s*(\d+)", line)
            if id_match:
                current_bb_id = int(id_match.group(1))

            off_match = re.search(r"Offset:\s*(0x[0-9a-fA-F]+)", line)
            if off_match:
                current_bb_offset = int(off_match.group(1), 16)

            sz_match = re.search(r"Size:\s*(0x[0-9a-fA-F]+)", line)
            if sz_match:
                current_bb_size = int(sz_match.group(1), 16)

            if (
                current_bb_id is not None
                and current_bb_offset is not None
                and current_bb_size is not None
            ):
                bb_ranges.append(
                    {
                        "start": current_bb_offset,
                        "end": current_bb_offset + current_bb_size,
                        "id": current_bb_id,
                    }
                )
                current_bb_id = None
                current_bb_offset = None
                current_bb_size = None

    if target_base_addr is None:
        print(f"Error: Function '{target_func_name}' not found in out.txt.")
        return None, None

    bb_ranges.sort(key=lambda x: x["start"])
    return target_base_addr, bb_ranges


def parse_binary_trace_generator(trace_path):
    """Генератор, читающий по 8 байт, чтобы не грузить гигабайты в RAM"""
    try:
        with open(trace_path, "rb") as f:
            while True:
                chunk = f.read(8)
                if len(chunk) < 8:
                    break
                yield struct.unpack("<Q", chunk)[0]
    except Exception as e:
        print(f"Error reading binary trace: {e}")
        sys.exit(1)


def resolve_bb(abs_addr, func_base, bb_ranges, bb_starts):
    """
    Оптимизированный поиск.
    bb_ranges: список dict с 'start', 'end', 'id'
    bb_starts: список только start offsets для bisect
    """
    rel_offset = abs_addr - func_base
    if rel_offset < 0:
        return None

    # Бинарный поиск правого диапазона
    idx = bisect.bisect_right(bb_starts, rel_offset)
    if idx == 0:
        return None

    candidate = bb_ranges[idx - 1]
    # Проверяем, попадает ли адрес внутрь BB [start, end)
    if candidate["start"] <= rel_offset < candidate["end"]:
        return candidate["id"]

    return None


# --- Main ---


def match_trace(cfg_path, readobj_path, trace_path, output_path):
    cfg_data = parse_cfg_json(cfg_path)
    target_func = cfg_data.get("function_name", "main")

    func_base_addr, bb_ranges = parse_bb_addr_map(readobj_path, target_func)
    if func_base_addr is None:
        sys.exit(1)

    # Подготовка списков для быстрого поиска (bisect)
    bb_starts = [x["start"] for x in bb_ranges]

    print(f"    Function '{target_func}' base: {hex(func_base_addr)}")
    print(f"    Loaded {len(bb_ranges)} BB ranges.")

    final_trace = []

    # Статистика
    total_events = 0
    matched_instrs = 0

    trace_gen = parse_binary_trace_generator(trace_path)

    print("[+] Processing trace stream...")

    last_bb_id = -1

    for addr in trace_gen:
        total_events += 1
        if total_events % 100000 == 0:
            print(f"    Processed {total_events} instructions...", end="\r")

        bb_id = resolve_bb(addr, func_base_addr, bb_ranges, bb_starts)

        if bb_id is not None:
            matched_instrs += 1
            # Логика сжатия (Deduplication)
            # Если текущая инструкция принадлежит тому же блоку, что и предыдущая -> пропускаем
            if bb_id != last_bb_id:
                final_trace.append(bb_id)
                last_bb_id = bb_id
        else:
            # Адрес не принадлежит нашей функции (библиотека, PLT, etc)
            # Мы просто игнорируем его.
            # Опционально: если мы вышли из функции и вернулись,
            # last_bb_id остался старым, это нормально.
            pass

    print(f"\n[+] Matching Complete.")
    print(f"    Total instructions processed: {total_events}")
    print(f"    Matched to CFG blocks: {matched_instrs}")
    print(f"    Final Compressed Trace Length (BB sequence): {len(final_trace)}")

    result = {"function_name": target_func, "trace_bb_ids": final_trace}

    with open(output_path, "w") as f:
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
