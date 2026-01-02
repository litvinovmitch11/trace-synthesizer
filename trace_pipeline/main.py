#!/usr/bin/env python3
import argparse
import json
import os
import random
import logging
from mir_lib.parser import MIRParser
from mir_lib.visualizer import JSONVisualizer

# Простая симуляция для генерации traces
def simulate_trace(func_data, steps=200):
    # func_data - это dict, который мы подготовили для JSON
    # Нам нужно быстро построить граф переходов для рандома
    adj = {}
    for e in func_data['edges']:
        if e['src'] not in adj: adj[e['src']] = ([], [])
        adj[e['src']][0].append(e['dst'])
        adj[e['src']][1].append(e['prob'])
    
    # Находим entry (обычно min id)
    if not func_data['blocks']: return []
    curr = min(b['id'] for b in func_data['blocks'])
    
    path = []
    for _ in range(steps):
        path.append(curr)
        if curr not in adj: break # Terminal
        succs, probs = adj[curr]
        if not succs: break
        
        # Выбор следующего
        try:
            curr = random.choices(succs, weights=probs)[0]
        except ValueError:
            curr = succs[0]
    return path

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    # --- КОМАНДА 1: ANALYZE (MIR -> JSON) ---
    p_an = sub.add_parser("analyze", help="Parse MIR and generate JSON dataset")
    p_an.add_argument("mir_file")
    p_an.add_argument("--out", default="data.json", help="Output JSON file")
    p_an.add_argument("--func", help="Specific function name to process")
    p_an.add_argument("--all", action="store_true", help="Process ALL functions")
    p_an.add_argument("--gen-traces", type=int, default=5, help="How many random traces to generate per function")

    # --- КОМАНДА 2: VIZ (JSON -> SVG) ---
    p_viz = sub.add_parser("viz", help="Visualize from JSON")
    p_viz.add_argument("json_file")
    p_viz.add_argument("--mode", choices=["heatmap", "trace", "clean"], default="heatmap")
    p_viz.add_argument("--out-dir", default="viz_output", help="Directory for SVGs")

    args = parser.parse_args()

    # ================= COMMAND: ANALYZE =================
    if args.cmd == "analyze":
        parser_tool = MIRParser(args.mir_file)
        all_funcs = parser_tool.parse()
        
        if not all_funcs:
            print("❌ No functions parsed!")
            return

        # Фильтрация функций
        targets = []
        if args.all:
            targets = list(all_funcs.keys())
        elif args.func:
            targets = [k for k in all_funcs if args.func in k]
        else:
            # Default: main or first
            mains = [k for k in all_funcs if "main" in k]
            targets = [mains[0]] if mains else [list(all_funcs.keys())[0]]

        output_data = {}
        
        for fname in targets:
            print(f"⚙️  Processing: {fname}")
            f_obj = all_funcs[fname]
            f_json = f_obj.to_json()
            
            # Генерация трасс (симуляция)
            traces = []
            for i in range(args.gen_traces):
                t = simulate_trace(f_json)
                traces.append({"id": i, "path": t})
            
            f_json["generated_traces"] = traces
            output_data[fname] = f_json

        with open(args.out, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"✅ Data saved to {args.out} ({len(targets)} functions)")

    # ================= COMMAND: VIZ =================
    elif args.cmd == "viz":
        with open(args.json_file, 'r') as f:
            data = json.load(f)
        
        os.makedirs(args.out_dir, exist_ok=True)
        
        for fname, f_data in data.items():
            viz = JSONVisualizer(f_data)
            clean_name = fname.replace(":", "_").replace(" ", "_")
            
            if args.mode == "trace":
                # Рендерим первую сгенерированную трассу для примера
                traces = f_data.get("generated_traces", [])
                if traces:
                    trace_path = traces[0]['path']
                    out_name = f"{args.out_dir}/{clean_name}_trace0"
                    viz.render(out_name, mode="trace", trace=trace_path)
                else:
                    print(f"⚠️ No traces found for {fname}")
            else:
                out_name = f"{args.out_dir}/{clean_name}_{args.mode}"
                viz.render(out_name, mode=args.mode)

if __name__ == "__main__":
    main()
