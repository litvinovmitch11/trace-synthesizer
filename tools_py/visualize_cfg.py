import argparse
import json
import sys
import html
from collections import Counter
import graphviz

class CFGVisualizer:
    def __init__(self, cfg_path, trace_path=None):
        self.cfg_data = self._load_json(cfg_path)
        self.trace_data = self._load_json(trace_path) if trace_path else None
        
        self.func_name = self.cfg_data.get("function_name", "unknown")
        # Словарь блоков
        self.blocks = {b['id']: b for b in self.cfg_data['blocks']}
        
        self.trace_counts = Counter()
        self.trace_edges = Counter()
        self.max_visits = 0
        
        if self.trace_data:
            trace_ids = self.trace_data.get("trace_bb_ids", [])
            # Считаем посещения блоков
            self.trace_counts.update(trace_ids)
            if self.trace_counts:
                self.max_visits = max(self.trace_counts.values())
            
            # Считаем переходы (ребра)
            for i in range(len(trace_ids) - 1):
                u, v = trace_ids[i], trace_ids[i+1]
                self.trace_edges[(u, v)] += 1

    def _load_json(self, path):
        if not path: return None
        try:
            with open(path, 'r') as f: return json.load(f)
        except Exception as e:
            print(f"Err loading {path}: {e}")
            sys.exit(1)

    def _get_pgo_color(self, prob):
        """Heatmap color for PGO edges."""
        if prob < 0.01: return "black"
        # От черного к красному через желтый (упрощенно)
        if prob > 0.5: return "red"
        if prob > 0.2: return "orange"
        return "black"

    def render(self, output_file, mode='simple'):
        # Используем engine='dot' явно
        dot = graphviz.Digraph(format='svg', comment=self.func_name, engine='dot')
        
        # Настройки графа для стабильности
        dot.attr(rankdir='TB', fontname='Helvetica', label=f"Func: {self.func_name} [{mode}]")
        dot.attr(newrank='true')  # Помогает с выравниванием
        dot.attr(concentrate='false') # Иногда true вызывает ошибки
        
        # Настройки узлов: shape=plain означает, что мы полностью управляем видом через HTML
        dot.attr('node', shape='plain', fontname='Consolas')

        # 1. Рисуем Узлы
        for b in self.cfg_data['blocks']:
            bid = b['id']
            name = html.escape(b['name'].replace(self.func_name + ":", ""))
            instrs = b.get('instr_count', '?')
            
            # Базовые стили
            bg_color = "white"
            border_color = "black"
            visits_row = ""
            
            # Логика TRACE (раскраска узлов)
            if mode == 'trace' and self.trace_data:
                visits = self.trace_counts[bid]
                if visits > 0:
                    # Легкий зеленый фон, если посетили
                    bg_color = "#e8f5e9"
                    border_color = "darkgreen"
                    visits_row = f"<TR><TD ALIGN='LEFT'><FONT COLOR='darkgreen' POINT-SIZE='10'>x{visits}</FONT></TD></TR>"
                else:
                    border_color = "gray"
                    name = f"<FONT COLOR='gray'>{name}</FONT>"

            # Формируем HTML Label (Таблица)
            # Port='p' нужен, чтобы ребра не терялись
            label = f"""<
            <TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" BGCOLOR="{bg_color}" PORT="p">
                <TR><TD ALIGN="CENTER"><B>BB {bid}</B></TD></TR>
                <TR><TD ALIGN="LEFT" BALIGN="LEFT">{name}</TD></TR>
                <TR><TD ALIGN="LEFT"><FONT POINT-SIZE="10">Instrs: {instrs}</FONT></TD></TR>
                {visits_row}
            </TABLE>
            >"""

            dot.node(str(bid), label=label, color=border_color)

        # 2. Рисуем Ребра (существующие в CFG)
        existing_cfg_edges = set()
        
        for b in self.cfg_data['blocks']:
            src = b['id']
            for succ in b['successors']:
                dst = succ['target_id']
                existing_cfg_edges.add((src, dst))
                
                # Атрибуты ребра
                edge_attrs = {
                    'style': 'solid',
                    'color': 'black',
                    'penwidth': '1',
                    'label': ''
                }
                
                # Fallthrough (визуально прямой поток)
                if succ.get('is_fallthrough'):
                    edge_attrs['weight'] = '10' # Сильное притяжение вниз
                else:
                    edge_attrs['weight'] = '1'

                # Режим PGO
                if mode == 'pgo':
                    prob = succ.get('prob', 0.0)
                    edge_attrs['label'] = f"{prob:.2f}"
                    edge_attrs['color'] = self._get_pgo_color(prob)
                    if prob > 0.5: edge_attrs['penwidth'] = '2.5'

                # Режим TRACE
                elif mode == 'trace' and self.trace_data:
                    visits = self.trace_edges[(src, dst)]
                    if visits > 0:
                        edge_attrs['color'] = '#006400' # DarkGreen
                        edge_attrs['penwidth'] = '3.0'
                        edge_attrs['label'] = f"x{visits}"
                    else:
                        edge_attrs['color'] = 'gray'
                        edge_attrs['style'] = 'dashed'
                        edge_attrs['penwidth'] = '0.5'

                # Рисуем ребро. Используем порты :s (south) и :n (north) или :p для стабильности
                dot.edge(str(src), str(dst), **edge_attrs)

        # 3. Рисуем GHOST-ребра (Аномалии трейса)
        if mode == 'trace':
            for (src, dst), count in self.trace_edges.items():
                if (src, dst) not in existing_cfg_edges:
                    # Это переход, которого нет в CFG!
                    dot.edge(str(src), str(dst), 
                             label=f"GHOST x{count}", 
                             color="red", 
                             style="dotted", 
                             penwidth="2.0",
                             constraint="false") # Не ломать layout

        try:
            out_path = dot.render(output_file, cleanup=True)
            print(f"[+] Rendered to {out_path}")
        except Exception as e:
            print(f"[-] Graphviz failed: {e}")
            print("Try installing: sudo apt-get install graphviz")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cfg", required=True)
    parser.add_argument("--trace")
    parser.add_argument("--mode", choices=['simple', 'pgo', 'trace'], default='simple')
    parser.add_argument("--output", default="viz_output")
    args = parser.parse_args()
    
    CFGVisualizer(args.cfg, args.trace).render(args.output, args.mode)
