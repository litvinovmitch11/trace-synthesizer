import re
from typing import Dict
from .core import MIRFunction, MIRBlock

class MIRParser:
    def __init__(self, filepath: str):
        self.filepath = filepath

    def parse(self) -> Dict[str, MIRFunction]:
        with open(self.filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        funcs = {}
        # Разделяем файл по маркерам YAML документов "---"
        raw_docs = content.split("---")
        
        for raw in raw_docs:
            if "name:" in raw and "body: |" in raw:
                f = self._parse_function(raw)
                if f:
                    funcs[f.name] = f
        return funcs

    def _parse_function(self, raw: str) -> MIRFunction:
        # 1. Извлекаем имя функции
        name_m = re.search(r"name:\s+([^\s]+)", raw)
        if not name_m: return None
        func_name = name_m.group(1)

        # 2. Извлекаем тело (блок body: | ...)
        # Ищем начало body и берем всё до конца или до следующего ключа (обычно body идет последним)
        body_m = re.search(r"body:\s+\|\s*\n(.*)", raw, re.DOTALL)
        if not body_m: return None
        body = body_m.group(1)

        mir_func = MIRFunction(name=func_name)
        
        # --- REGEX PATTERNS ---
        
        # Заголовок блока: bb.0.entry: или bb.1:
        # Группа 1: ID
        # Группа 2: (Optional) Имя/суффикс (например ".entry" или ".init.check")
        bb_header_re = re.compile(r"^\s*bb\.(\d+)([\.\w]*):")
        
        # Successors строка: successors: %bb.1(0x00d85b2b), %bb.9(0x7f27a4d5)
        succ_line_re = re.compile(r"^\s*successors:\s*(.*)")
        
        # Парсинг отдельных таргетов: %bb.1(0x00d85b2b)
        # Группа 1: Target ID
        # Группа 2: Weight (Hex) - опционально
        target_re = re.compile(r"%bb\.(\d+)(?:\((0x[0-9a-fA-F]+)\))?")

        curr_id = None
        curr_instrs = []
        curr_name = ""

        lines = body.split('\n')
        for line in lines:
            line = line.strip()
            if not line: continue

            # A. Начало нового блока
            # Пример: bb.0.entry:
            header_match = bb_header_re.match(line)
            if header_match:
                # Сохраняем предыдущий блок
                if curr_id is not None:
                    mir_func.blocks[curr_id] = MIRBlock(curr_id, curr_name, 0.0, list(curr_instrs))

                curr_id = int(header_match.group(1))
                suffix = header_match.group(2) if header_match.group(2) else ""
                curr_name = f"bb.{curr_id}{suffix}"
                curr_instrs = []
                continue
            
            if curr_id is None: continue

            # B. Successors (Вероятности переходов)
            # Пример: successors: %bb.1(0x00d85b2b), %bb.9(0x7f27a4d5)
            if line.startswith("successors:"):
                succ_match = succ_line_re.match(line)
                if succ_match:
                    raw_targets = succ_match.group(1)
                    # Разбиваем по запятым
                    parts = raw_targets.split(',')
                    
                    targets = {} # {dst_id: weight}
                    total_weight = 0.0
                    
                    for part in parts:
                        part = part.strip()
                        t_m = target_re.search(part)
                        if t_m:
                            dst = int(t_m.group(1))
                            weight_hex = t_m.group(2)
                            # Если веса нет, считаем 0 (или 1 для дефолта, но LLVM обычно ставит вес)
                            weight = int(weight_hex, 16) if weight_hex else 0
                            targets[dst] = weight
                            total_weight += weight
                    
                    # Сохраняем и нормализуем
                    if curr_id not in mir_func.edges:
                        mir_func.edges[curr_id] = {}
                        
                    for dst, w in targets.items():
                        if total_weight > 0:
                            prob = w / total_weight
                        else:
                            # Если все веса 0, делаем равномерное распределение
                            prob = 1.0 / len(targets)
                        mir_func.edges[curr_id][dst] = prob
                continue

            # C. Инструкции
            # Пропускаем мета-инструкции для чистоты, если нужно
            if not any(line.startswith(p) for p in ["liveins:", "frame-setup", "frame-destroy", ";", "EH_LABEL"]):
                 curr_instrs.append(line)

        # Сохраняем последний блок
        if curr_id is not None:
            mir_func.blocks[curr_id] = MIRBlock(curr_id, curr_name, 0.0, list(curr_instrs))

        return mir_func
