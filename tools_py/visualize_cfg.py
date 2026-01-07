import argparse
import json
import os
import sys
from collections import Counter
import graphviz

class CFGVisualizer:
    def __init__(self, cfg_path, trace_path=None):
        self.cfg_data = self._load_json(cfg_path)
        self.trace_data = self._load_json(trace_path) if trace_path else None
        
        self.func_name = self.cfg_data.get("function_name", "unknown_func")
        self.blocks = {b['id']: b for b in self.cfg_data['blocks']}
        
        # Подготовка данных трейса
        self.block_visits = Counter()
        self.edge_visits = Counter()
        self.trace_path_set = set() # (src_id, dst_id)
        
        if self.trace_data:
            trace_ids = self.trace_data.get("trace_bb_ids", [])
            self.block_visits.update(trace_ids)
            
            # Собираем переходы из трейса (ребра)
            for i in range(len(trace_ids) - 1):
                src = trace_ids[i]
                dst = trace_ids[i+1]
                self.edge_visits[(src, dst)] += 1
                self.trace_path_set.add((src, dst))

    def _load_json(self, path):
        if not path: return None
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {path}: {e}")
            sys.exit(1)

    def _get_color_heatmap(self, probability):
        """Возвращает цвет от синего (холодно) до красного (горячо) на основе вероятности."""
        # Простая градиентная логика для HEX цвета
        val = int(probability * 255)
        return f"#{val:02x}00{255-val:02x}"

    def _get_trace_color(self, visits, max_visits):
        """Зеленый градиент в зависимости от частоты посещения."""
        if visits == 0: return "black" # или lightgray
        if max_visits == 0: return "green"
        
        # Чем чаще посещали, тем темнее/насыщеннее зеленый
        intensity = 0.2 + 0.8 * (visits / max_visits)
        # В graphviz можно использовать HSV
        return f"0.33 {intensity:.2f} 0.9" # H S V (Green approx)

    def render(self, output_file, mode='simple'):
        """
        mode: 'simple' | 'pgo' | 'trace'
        """
        dot = graphviz.Digraph(comment=self.func_name, format='svg')
        dot.attr(rankdir='TB', label=f"CFG: {self.func_name} [{mode.upper()}]", fontname="Helvetica")
        dot.attr('node', shape='record', fontname="Consolas", style='filled', fillcolor='white')

        max_block_visits = max(self.block_visits.values()) if self.block_visits else 1
        
        # 1. Рисуем узлы
        for b in self.cfg_data['blocks']:
            bb_id = b['id']
            name = b['name'].replace(self.func_name + ":", "") # Упрощаем имя
            
            # Формируем HTML-подобную метку
            label = f"{{ ID: {bb_id} | {name} }}"
            
            # Доп инфо (инструкции)
            instr_count = b.get('instr_count', '?')
            first_i = b.get('first_instr', '')
            last_i = b.get('last_instr', '')
            details = f"{instr_count} instrs\\nStart: {first_i}\\nEnd: {last_i}"
            label += f"| {details}"

            # Стилизация узла
            fillcolor = "white"
            penwidth = "1"
            color = "black"

            if mode == 'trace' and self.trace_data:
                visits = self.block_visits[bb_id]
                if visits > 0:
                    fillcolor = "#e6fffa" # Light Mint
                    color = "darkgreen"
                    penwidth = "2"
                    label += f"| Visits: {visits}"
                else:
                    color = "lightgray"
                    fontcolor = "gray"

            elif mode == 'pgo':
                # Здесь можно красить блоки, если есть BlockFrequencyInfo (в JSON пока нет),
                # либо оставить белыми и красить только ребра.
                pass

            dot.node(str(bb_id), label=label, fillcolor=fillcolor, color=color, penwidth=penwidth)

        # 2. Рисуем ребра
        for b in self.cfg_data['blocks']:
            src_id = b['id']
            for succ in b['successors']:
                dst_id = succ['target_id']
                prob = succ['prob']
                is_fallthrough = succ['is_fallthrough']
                
                # Базовый стиль
                style = "solid" if is_fallthrough else "dashed"
                weight = "10" if is_fallthrough else "1" # Пытаемся выстроить fallthrough вертикально
                label = f"{prob:.2f}"
                color = "black"
                penwidth = "1"

                if mode == 'trace' and self.trace_data:
                    visits = self.edge_visits[(src_id, dst_id)]
                    if visits > 0:
                        color = "green" # darkgreen
                        penwidth = "2.5"
                        label = f"x{visits}"
                    else:
                        color = "lightgray"
                        style = "dotted"
                
                elif mode == 'pgo':
                    color = self._get_color_heatmap(prob)
                    if prob > 0.5:
                        penwidth = "2"
                    label = f"{prob:.1%}"

                dot.edge(str(src_id), str(dst_id), label=label, style=style, color=color, penwidth=penwidth, weight=weight)

        # Рендеринг
        output_path = dot.render(output_file, cleanup=True)
        print(f"[+] Graph generated: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize CFG from JSON")
    parser.add_argument("--cfg", required=True, help="Path to main.cfg.json")
    parser.add_argument("--trace", help="Path to final_trace.json (required for 'trace' mode)")
    parser.add_argument("--mode", choices=['simple', 'pgo', 'trace'], default='simple')
    parser.add_argument("--output", default="cfg_output", help="Output filename (without extension)")
    
    args = parser.parse_args()
    
    viz = CFGVisualizer(args.cfg, args.trace)
    viz.render(args.output, args.mode)
