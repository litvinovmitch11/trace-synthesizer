#!/usr/bin/env python3
import json
import sys
import os
import subprocess
import tempfile
import html

def demangle_name(name):
    """Деманглинг C++ имен"""
    try:
        # Пробуем использовать c++filt если доступен
        result = subprocess.run(['c++filt', name], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            demangled = result.stdout.strip()
            # Убираем лишние символы
            demangled = demangled.replace('(anonymous namespace)::', '')
            return demangled
    except:
        pass
    return name

def load_cfg_json(filepath):
    """Загружает JSON из файла с несколькими функциями"""
    functions = []
    with open(filepath, 'r') as f:
        content = f.read()
        start_marker = "=== CFG JSON START ==="
        end_marker = "=== CFG JSON END ==="
        
        start_idx = 0
        while True:
            start = content.find(start_marker, start_idx)
            if start == -1:
                break
            start += len(start_marker)
            
            end = content.find(end_marker, start)
            if end == -1:
                break
            
            json_str = content[start:end].strip()
            try:
                func_data = json.loads(json_str)
                # Деманглинг имени функции
                func_name = func_data.get("function_name", "")
                if func_name:
                    func_data["display_name"] = demangle_name(func_name)
                else:
                    func_data["display_name"] = "unknown"
                functions.append(func_data)
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse JSON: {e}")
            
            start_idx = end + len(end_marker)
    
    return functions

def probability_to_color(prob):
    """Преобразует вероятность в цвет от красного (низкая) к зеленому (высокая)"""
    if prob < 0:
        prob = 0
    if prob > 1:
        prob = 1
    
    if prob < 0.5:
        r = 1.0
        g = 2 * prob
        b = 0.0
    else:
        r = 2 * (1 - prob)
        g = 1.0
        b = 0.0
    
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

def demangle_ir_name(ir_name):
    """Деманглинг IR имен"""
    if not ir_name:
        return ""
    
    # Убираем суффиксы LLVM
    name = ir_name
    suffixes = ['.exit', '.i', '.i.i', '.i.i.i', '.i4.i.i', '.exit.2']
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    
    # Деманглинг
    demangled = demangle_name(name)
    
    # Красивое форматирование
    if demangled.startswith('_'):
        return f"BB:{demangled}"
    return demangled

def generate_dot(func_data):
    """Генерирует DOT код для функции с деманглингом"""
    func_name = func_data.get("display_name", func_data.get("function_name", "unknown"))
    blocks = func_data.get("blocks", [])
    
    # Экранируем специальные символы для DOT
    safe_func_name = html.escape(func_name)
    
    dot_lines = [
        f'digraph "{safe_func_name}" {{',
        '  rankdir=TB;',
        '  ranksep=0.3;',  # Уменьшаем расстояние между ранками
        '  nodesep=0.2;',   # Уменьшаем расстояние между узлами
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9];',
        ''
    ]
    
    # Добавляем узлы (блоки)
    for block in blocks:
        block_id = block.get("id", 0)
        ir_name = block.get("ir_name", f"BB{block_id}")
        is_entry = block.get("is_entry", False)
        
        # Деманглинг IR имени
        display_ir_name = demangle_ir_name(ir_name)
        
        # Формируем метку
        if display_ir_name and display_ir_name != f"BB{block_id}":
            # Обрезаем длинные имена
            if len(display_ir_name) > 20:
                display_ir_name = display_ir_name[:17] + "..."
            label = f"BB{block_id}\\n{display_ir_name}"
        else:
            label = f"BB{block_id}"
        
        # Экранируем для DOT
        label = label.replace('"', '\\"')
        
        if is_entry:
            dot_lines.append(f'  {block_id} [label="{label}", fillcolor="lightblue", penwidth=2];')
        else:
            dot_lines.append(f'  {block_id} [label="{label}", fillcolor="lightgrey"];')
    
    dot_lines.append('')
    
    # Добавляем ребра (переходы)
    for block in blocks:
        src_id = block.get("id", 0)
        successors = block.get("successors", [])
        
        for edge in successors:
            target_id = edge.get("target_id", 0)
            prob_float = edge.get("prob_float", 0.0)
            is_fallthrough = edge.get("is_fallthrough", False)
            
            # Форматируем вероятность
            if prob_float < 0.0001:
                label = f"{prob_float:.2e}"
            else:
                label = f"{prob_float:.1%}"
            
            if is_fallthrough:
                label += " (FT)"
            
            color = probability_to_color(prob_float)
            style = "solid"
            if is_fallthrough:
                style = "bold"
            
            # Толщина линии зависит от вероятности
            penwidth = max(0.5, 1 + 3 * prob_float)
            
            dot_lines.append(f'  {src_id} -> {target_id} [label="{label}", color="{color}", style="{style}", penwidth={penwidth:.1f}];')
    
    dot_lines.append('}')
    
    return '\n'.join(dot_lines)

def dot_to_svg(dot_code):
    """Конвертирует DOT код в SVG используя Graphviz"""
    try:
        # Создаем временный файл с DOT кодом
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False, encoding='utf-8') as tmp:
            tmp.write(dot_code)
            tmp_path = tmp.name
        
        # Конвертируем в SVG
        svg_path = tmp_path.replace('.dot', '.svg')
        result = subprocess.run(['dot', '-Tsvg', tmp_path, '-o', svg_path], 
                              capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            with open(svg_path, 'r', encoding='utf-8') as f:
                svg_content = f.read()
            
            # Удаляем XML заголовок если есть
            if svg_content.startswith('<?xml'):
                # Находим начало SVG тега
                svg_start = svg_content.find('<svg')
                if svg_start > 0:
                    svg_content = svg_content[svg_start:]
            
            # Добавляем стили для лучшего отображения
            style_insert = 'style="max-width: 100%; height: auto;" '
            svg_content = svg_content.replace('<svg ', f'<svg {style_insert}', 1)
            
            os.unlink(tmp_path)
            os.unlink(svg_path)
            return svg_content
        else:
            print(f"Graphviz error: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        print("Graphviz timed out")
    except Exception as e:
        print(f"SVG generation error: {e}")
    
    # Fallback: показываем DOT код
    escaped_dot = html.escape(dot_code).replace('\n', '<br>')
    return f'<div style="border:1px solid #ccc; padding:10px; font-family:monospace; font-size:10px; overflow:auto; max-height:400px;">{escaped_dot}</div>'

def generate_html_report(functions, output_file):
    """Генерирует HTML отчет со SVG графами"""
    
    html_content = '''<!DOCTYPE html>
<html>
<head>
    <title>CFG Visualization with Branch Probabilities</title>
    <meta charset="utf-8">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        }
        
        .header {
            background: linear-gradient(90deg, #4b6cb7 0%, #182848 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .subtitle {
            font-size: 1.1em;
            opacity: 0.9;
        }
        
        .function-card {
            background: white;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            border-left: 5px solid #4b6cb7;
        }
        
        .function-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }
        
        .function-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #f0f0f0;
        }
        
        .function-name {
            font-size: 1.8em;
            color: #2c3e50;
            font-weight: bold;
        }
        
        .function-meta {
            display: flex;
            gap: 15px;
            font-size: 0.9em;
        }
        
        .meta-badge {
            background: #e3f2fd;
            color: #1565c0;
            padding: 5px 12px;
            border-radius: 20px;
            font-weight: 500;
        }
        
        .graph-container {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            overflow: auto;
            border: 1px solid #e0e0e0;
            text-align: center;
        }
        
        .graph-svg {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        
        .legend {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            align-items: center;
            border: 1px solid #e0e0e0;
        }
        
        .legend-item {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-right: 20px;
        }
        
        .color-box {
            width: 30px;
            height: 20px;
            border-radius: 3px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        
        .stat-label {
            font-size: 0.9em;
            opacity: 0.9;
        }
        
        .probability-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            border-radius: 8px;
            overflow: hidden;
        }
        
        .probability-table th {
            background: linear-gradient(90deg, #4b6cb7 0%, #182848 100%);
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }
        
        .probability-table td {
            padding: 12px 15px;
            border-bottom: 1px solid #e0e0e0;
        }
        
        .probability-table tr:hover {
            background: #f5f7fa;
        }
        
        .probability-bar {
            height: 20px;
            background: #e0e0e0;
            border-radius: 10px;
            overflow: hidden;
            position: relative;
            margin: 5px 0;
        }
        
        .probability-fill {
            height: 100%;
            background: linear-gradient(90deg, #ff6b6b, #ffd93d, #6bcf7f);
            border-radius: 10px;
            transition: width 0.3s ease;
        }
        
        .probability-value {
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            font-size: 0.8em;
            font-weight: bold;
            color: #333;
            text-shadow: 0 0 2px white;
        }
        
        .fallthrough-indicator {
            display: inline-block;
            background: #4CAF50;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            margin-left: 10px;
        }
        
        @media (max-width: 768px) {
            body {
                padding: 10px;
            }
            
            .function-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }
            
            .stats-grid {
                grid-template-columns: 1fr;
            }
            
            .legend {
                flex-direction: column;
                align-items: flex-start;
            }
        }
        
        .toggle-button {
            background: #4b6cb7;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.9em;
            margin: 10px 0;
            transition: background 0.3s;
        }
        
        .toggle-button:hover {
            background: #3a559f;
        }
        
        .collapsible {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
        }
        
        .collapsible.expanded {
            max-height: 500px;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏗️ CFG Visualization with Branch Probabilities</h1>
        <div class="subtitle">
            Interactive Control Flow Graphs with real profile data
            <br>Generated from LLVM MachineFunction analysis
        </div>
    </div>
    
    <div class="legend">
        <h3 style="width:100%; margin-bottom:10px;">📊 Visualization Legend:</h3>
        <div class="legend-item">
            <div class="color-box" style="background: linear-gradient(90deg, #ff6b6b, #ffd93d);"></div>
            <span>Edge Color: Red (0%) → Yellow (50%) → Green (100%)</span>
        </div>
        <div class="legend-item">
            <div class="color-box" style="background: #4b6cb7; width: 40px;"></div>
            <span>Entry Block (Light Blue)</span>
        </div>
        <div class="legend-item">
            <div class="color-box" style="background: #f0f0f0; border: 1px solid #ccc;"></div>
            <span>Regular Block (Light Grey)</span>
        </div>
        <div class="legend-item">
            <strong>FT</strong>
            <span>Fall-through edge (no explicit jump)</span>
        </div>
    </div>
'''
    
    total_functions = len(functions)
    functions_with_profile = sum(1 for f in functions if f.get("has_profile_data", False))
    
    html_content += f'''
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-value">{total_functions}</div>
            <div class="stat-label">Total Functions</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{functions_with_profile}</div>
            <div class="stat-label">With Profile Data</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{sum(len(f.get("blocks", [])) for f in functions)}</div>
            <div class="stat-label">Basic Blocks</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{sum(len(b.get("successors", [])) for f in functions for b in f.get("blocks", []))}</div>
            <div class="stat-label">Control Flow Edges</div>
        </div>
    </div>
'''
    
    for i, func in enumerate(functions):
        func_name = func.get("display_name", demangle_name(func.get("function_name", f"Function_{i}")))
        mangled_name = func.get("function_name", "")
        has_profile = func.get("has_profile_data", False)
        blocks = func.get("blocks", [])
        
        # Генерируем DOT и SVG
        dot_code = generate_dot(func)
        svg_content = dot_to_svg(dot_code)
        
        # Статистика
        total_edges = sum(len(b.get("successors", [])) for b in blocks)
        avg_prob = 0
        if total_edges > 0:
            all_probs = [e.get("prob_float", 0) for b in blocks for e in b.get("successors", [])]
            avg_prob = sum(all_probs) / len(all_probs) if all_probs else 0
        
        html_content += f'''
    <div class="function-card" id="func_{i}">
        <div class="function-header">
            <div class="function-name">📁 {html.escape(func_name)}</div>
            <div class="function-meta">
                <span class="meta-badge">🔢 {len(blocks)} blocks</span>
                <span class="meta-badge">🔗 {total_edges} edges</span>
                <span class="meta-badge" style="background: {"#d4edda" if has_profile else "#f8d7da"}; color: {"#155724" if has_profile else "#721c24"};">
                    📊 {"Profile: YES" if has_profile else "Profile: NO"}
                </span>
            </div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card" style="background: linear-gradient(135deg, #36D1DC 0%, #5B86E5 100%);">
                <div class="stat-value">{len(blocks)}</div>
                <div class="stat-label">Basic Blocks</div>
            </div>
            <div class="stat-card" style="background: linear-gradient(135deg, #FF9A9E 0%, #FAD0C4 100%);">
                <div class="stat-value">{total_edges}</div>
                <div class="stat-label">Control Edges</div>
            </div>
            <div class="stat-card" style="background: linear-gradient(135deg, #A8E6CF 0%, #DCEDC1 100%);">
                <div class="stat-value">{avg_prob:.1%}</div>
                <div class="stat-label">Avg Probability</div>
            </div>
            <div class="stat-card" style="background: linear-gradient(135deg, #FFD3A5 0%, #FD6585 100%);">
                <div class="stat-value">{sum(1 for b in blocks for e in b.get("successors", []) if e.get("is_fallthrough", False))}</div>
                <div class="stat-label">Fall-through Edges</div>
            </div>
        </div>
        
        <h3 style="margin: 20px 0 10px 0; color: #2c3e50;">🎯 Control Flow Graph:</h3>
        <div class="graph-container">
            {svg_content}
        </div>
        
        <button class="toggle-button" onclick="toggleDetails({i})">📋 Show/Hide Detailed Probability Table</button>
        
        <div id="details_{i}" class="collapsible">
            <h3 style="margin: 20px 0 10px 0; color: #2c3e50;">📈 Branch Probability Details:</h3>
            <table class="probability-table">
                <thead>
                    <tr>
                        <th>From → To</th>
                        <th>Probability</th>
                        <th>Fraction</th>
                        <th>Fall-through</th>
                        <th>Visualization</th>
                    </tr>
                </thead>
                <tbody>
'''
        
        # Таблица с вероятностями
        for block in blocks:
            src_id = block.get("id", 0)
            src_ir_name = demangle_ir_name(block.get("ir_name", ""))
            src_label = f"BB{src_id}"
            if src_ir_name and src_ir_name != f"BB{src_id}":
                src_label += f" ({src_ir_name[:20]}{'...' if len(src_ir_name) > 20 else ''})"
            
            successors = block.get("successors", [])
            
            for edge in successors:
                target_id = edge.get("target_id", 0)
                prob_float = edge.get("prob_float", 0.0)
                prob_num = edge.get("prob_numerator", 0)
                prob_den = edge.get("prob_denominator", 1)
                is_ft = edge.get("is_fallthrough", False)
                
                html_content += f'''
                    <tr>
                        <td><strong>{src_label}</strong> → <strong>BB{target_id}</strong></td>
                        <td><strong>{prob_float:.4%}</strong></td>
                        <td><small>{prob_num}/{prob_den}</small></td>
                        <td>{"<span class='fallthrough-indicator'>FT</span>" if is_ft else "—"}</td>
                        <td style="width: 200px;">
                            <div class="probability-bar">
                                <div class="probability-fill" style="width: {prob_float*100}%;"></div>
                                <div class="probability-value">{prob_float:.2%}</div>
                            </div>
                        </td>
                    </tr>'''
        
        html_content += '''
                </tbody>
            </table>
        </div>
        
        <div style="margin-top: 15px; font-size: 0.9em; color: #666;">
            <small>
                <strong>Mangled name:</strong> ''' + html.escape(mangled_name) + '''<br>
                <strong>Blocks:</strong> ''' + ', '.join([f'BB{b["id"]}' for b in blocks]) + '''
            </small>
        </div>
    </div>
'''
    
    # JavaScript для раскрывающихся секций
    html_content += '''
    <script>
        function toggleDetails(funcId) {
            const details = document.getElementById('details_' + funcId);
            details.classList.toggle('expanded');
            const button = event.target;
            button.textContent = details.classList.contains('expanded') 
                ? '📋 Hide Detailed Probability Table' 
                : '📋 Show/Hide Detailed Probability Table';
        }
        
        // Автоматически раскрываем первый граф
        document.addEventListener('DOMContentLoaded', function() {
            if (document.getElementById('details_0')) {
                toggleDetails(0);
            }
        });
        
        // Добавляем возможность масштабирования SVG
        document.querySelectorAll('.graph-svg').forEach(svg => {
            svg.addEventListener('click', function(e) {
                if (e.ctrlKey) {
                    this.style.transform = this.style.transform === 'scale(1.5)' ? 'scale(1)' : 'scale(1.5)';
                    this.style.transition = 'transform 0.3s ease';
                }
            });
        });
    </script>
    
    <div style="text-align: center; margin: 40px 0 20px 0; padding: 20px; color: #666; border-top: 1px solid #e0e0e0;">
        <small>Generated by CFG Json Dumper • LLVM MachineFunction Pass • Visualization Tool</small><br>
        <small>Click on graphs with Ctrl to zoom • Hover over edges to see probabilities</small>
    </div>
</body>
</html>'''
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

def main():
    if len(sys.argv) < 2:
        print("Usage: python visualize_cfg.py <cfg_dump.json> [output_dir]")
        print("Example: python visualize_cfg.py cfg_dump.json ./report")
        sys.exit(1)
    
    json_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    
    # Создаем директорию если нужно
    os.makedirs(output_dir, exist_ok=True)
    
    print("📥 Loading JSON data...")
    functions = load_cfg_json(json_file)
    
    if not functions:
        print("❌ No functions found in the JSON file")
        return
    
    print(f"✅ Loaded {len(functions)} functions")
    
    # Генерируем HTML отчет
    html_file = os.path.join(output_dir, "cfg_report.html")
    print(f"🎨 Generating HTML report...")
    generate_html_report(functions, html_file)
    
    print(f"\n✨ Report generated successfully!")
    print(f"📄 HTML Report: {os.path.abspath(html_file)}")
    print(f"\n🎯 To view the report:")
    print(f"   1. Open in browser: firefox {html_file}")
    print(f"   2. Or use: python -m http.server 8000")
    print(f"\n📊 Summary:")
    print(f"   • Functions: {len(functions)}")
    print(f"   • With profile data: {sum(1 for f in functions if f.get('has_profile_data', False))}")
    print(f"   • Total blocks: {sum(len(f.get('blocks', [])) for f in functions)}")
    
    # Дополнительно: генерируем отдельные SVG файлы
    print(f"\n🎨 Generating individual SVG files...")
    for i, func in enumerate(functions):
        func_name = func.get("display_name", f"func_{i}")
        safe_name = "".join(c if c.isalnum() or c in ' _-' else "_" for c in func_name)
        safe_name = safe_name[:50]  # Ограничиваем длину имени файла
        
        dot_code = generate_dot(func)
        svg_content = dot_to_svg(dot_code)
        
        if svg_content.startswith('<svg'):
            svg_file = os.path.join(output_dir, f"{safe_name}.svg")
            with open(svg_file, 'w', encoding='utf-8') as f:
                f.write(svg_content)
            print(f"   ✅ {func_name} -> {svg_file}")

if __name__ == "__main__":
    main()
