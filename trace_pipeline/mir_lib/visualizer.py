import html
import json
from pathlib import Path
from graphviz import Digraph

class JSONVisualizer:
    def __init__(self, json_data):
        # json_data: dict containing 'blocks', 'edges'
        self.data = json_data
        
    def _get_heatmap_color(self, val: float, max_val: float) -> str:
        """Interpolates White -> Red based on val/max_val."""
        if max_val == 0: return "#ffffff"
        ratio = min(1.0, val / max_val)
        
        # White (255, 255, 255) -> Red (255, 0, 0)
        # R is always 255. G and B decrease as ratio increases.
        gb = int(255 * (1 - ratio))
        return f"#ff{gb:02x}{gb:02x}"

    def render(self, output_path: str, mode="heatmap", trace=None):
        dot = Digraph(comment='CFG', format='svg')
        dot.attr(rankdir='TB', splines='polyline', fontname='Courier New')
        dot.attr('node', shape='plain')

        # 1. Подготовка данных
        blocks = {b['id']: b for b in self.data['blocks']}
        edges = self.data['edges']
        
        # Для Heatmap ищем максимум
        max_freq = 0
        for b in blocks.values():
            max_freq = max(max_freq, b['freq'])
        
        # Если есть trace, собираем посещенные
        visited_nodes = set()
        visited_edges = set()
        node_hits = {} # id -> count
        
        if trace:
            # Trace - это список ID блоков [0, 1, 5, ...]
            for b_id in trace:
                node_hits[b_id] = node_hits.get(b_id, 0) + 1
                visited_nodes.add(b_id)
            for i in range(len(trace) - 1):
                visited_edges.add((trace[i], trace[i+1]))

        # 2. Рендер узлов
        for bid, blk in blocks.items():
            freq = blk['freq']
            
            # Стиль по умолчанию
            bgcolor = "#ffffff"
            border_w = "1"
            border_c = "gray"
            header_sub = f"Freq: {int(freq)}"

            if mode == "heatmap":
                bgcolor = self._get_heatmap_color(freq, max_freq)
            
            elif mode == "trace" and trace:
                hits = node_hits.get(bid, 0)
                header_sub = f"Hits: {hits}"
                if bid in visited_nodes:
                    # Зеленоватый для посещенных
                    bgcolor = "#e6ffcc"
                    border_c = "black"
                    border_w = "2"

            # HTML Лейбл
            esc_name = html.escape(blk['name'])
            rows = []
            rows.append(f'<TR><TD BGCOLOR="{bgcolor}" BORDER="{border_w}"><B>{esc_name}</B><BR/>{header_sub}</TD></TR>')
            
            # Инструкции (первые 4)
            for instr in blk['instructions'][:4]:
                esc_instr = html.escape(instr)
                rows.append(f'<TR><TD ALIGN="LEFT" BGCOLOR="{bgcolor}" BORDER="1">{esc_instr}</TD></TR>')
            
            label = f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">{ "".join(rows) }</TABLE>>'
            dot.node(str(bid), label=label, color=border_c)

        # 3. Рендер ребер
        for e in edges:
            u, v, prob = e['src'], e['dst'], e['prob']
            
            color = "#a0a0a0"
            penwidth = "1.0"
            label = ""
            
            if mode == "heatmap":
                label = f"{prob:.2f}"
                # Толщина от вероятности
                penwidth = str(1.0 + prob * 3.0)
                if prob > 0.5: color = "black"
            
            elif mode == "trace":
                if (u, v) in visited_edges:
                    color = "blue"
                    penwidth = "3.0"
            
            dot.edge(str(u), str(v), label=label, color=color, penwidth=penwidth)

        dot.render(output_path, cleanup=True)
        print(f"🖼  Saved visualization: {output_path}.svg")
