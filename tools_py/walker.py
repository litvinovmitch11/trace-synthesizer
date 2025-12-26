"""
TODO
"""

# import sys
# import json
# import r2pipe
# from pathlib import Path

# class TraceWalker:
#     def __init__(self, binary_path, trace_path):
#         self.binary_path = binary_path
#         self.trace_path = trace_path
#         self.trace_sequence = []
#         self.trace_ptr = 0 # Указатель на текущую позицию в логе

#         # R2 Init
#         self.r2 = r2pipe.open(binary_path, flags=["-2"])
#         self.r2.cmd("aaa")

#         # Загрузка трейса
#         self.load_trace()

#     def load_trace(self):
#         with open(self.trace_path, 'r') as f:
#             for line in f:
#                 try: self.trace_sequence.append(int(line.strip(), 16))
#                 except: pass
#         print(f"[*] Trace loaded: {len(self.trace_sequence)} steps.")

#     def get_block_info(self, addr):
#         # Получаем инфо о блоке через r2
#         # abj = analyze block json
#         b_json = self.r2.cmd(f"abj @ {addr}")
#         if not b_json: return None
#         return json.loads(b_json)[0]

#     def get_disasm(self, addr, size):
#         return json.loads(self.r2.cmd(f"pDj {size} @ {addr}"))

#     def start(self):
#         if not self.trace_sequence:
#             return

#         curr_addr = self.trace_sequence[0]

#         while True:
#             print("\n" + "="*50)
#             print(f"[*] Current Block: {hex(curr_addr)}")

#             # 1. Показываем код
#             block = self.get_block_info(curr_addr)
#             if not block:
#                 print("Error: Unknown block.")
#                 break

#             ops = self.get_disasm(curr_addr, block['size'])
#             for op in ops:
#                 print(f"  {hex(op['offset'])}: {op.get('disasm', '???')}")

#             # 2. Определяем, куда пошел трейс
#             next_trace_addr = None
#             if self.trace_ptr + 1 < len(self.trace_sequence):
#                 next_trace_addr = self.trace_sequence[self.trace_ptr + 1]

#             print("-" * 20)
#             print(f"[Trace Info]: Step {self.trace_ptr}/{len(self.trace_sequence)}")
#             if next_trace_addr:
#                 print(f" -> Trace went to: {hex(next_trace_addr)}")
#             else:
#                 print(" -> End of Trace reached.")

#             # 3. Определяем возможные переходы (Static Analysis)
#             options = []
#             if 'jump' in block: options.append(('True/Jump', block['jump']))
#             if 'fail' in block: options.append(('False/Next', block['fail']))
#             if 'switch' in block:
#                 for s in block['switch']: options.append(('Case', s['addr']))

#             print("[Available Paths]:")
#             valid_choice_indices = []

#             for idx, (desc, addr) in enumerate(options):
#                 marker = " "
#                 if next_trace_addr and addr == next_trace_addr:
#                     marker = "*" # Звездочка маркирует путь из трейса

#                 print(f"  [{idx}] {marker} {desc} -> {hex(addr)}")
#                 valid_choice_indices.append(idx)

#             # 4. Выбор пользователя
#             print("\nCommands: [Enter]=Follow Trace, [0-9]=Force Path, [q]=Quit")
#             choice = input("Your move > ").strip()

#             if choice == 'q':
#                 break

#             next_addr_candidate = None

#             if choice == "":
#                 # Идем по трейсу
#                 if next_trace_addr:
#                     next_addr_candidate = next_trace_addr
#                     self.trace_ptr += 1
#                 else:
#                     print("Trace ended!")
#                     continue
#             elif choice.isdigit() and int(choice) < len(options):
#                 # Форсируем путь (идем не по трейсу)
#                 sel = int(choice)
#                 next_addr_candidate = options[sel][1]

#                 # Если мы ушли с трейса, мы теряем синхронизацию
#                 # Пытаемся найти, вернется ли трейс сюда позже?
#                 # Или просто останавливаем указатель трейса.
#                 if next_addr_candidate == next_trace_addr:
#                      self.trace_ptr += 1
#                 else:
#                     print("[!] WARNING: Deviating from execution trace!")
#             else:
#                 print("Invalid command.")
#                 continue

#             curr_addr = next_addr_candidate

# if __name__ == "__main__":
#     if len(sys.argv) != 3:
#         print("Usage: python walker.py <binary> <trace>")
#     else:
#         TraceWalker(sys.argv[1], sys.argv[2]).start()
