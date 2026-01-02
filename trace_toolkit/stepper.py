# stepper.py
import argparse
import random
import time
from common import load_project, save_project

def run_stepper(project, func_name):
    if func_name not in project:
        print(f"Error: Function {func_name} not found.")
        return

    func = project[func_name]
    # Assuming Block 0 is entry (standard LLVM MIR)
    current_block = 0
    path = [current_block]
    
    print(f"=== Interactive Stepper: {func_name} ===")
    print("Commands: [Enter]=Auto-pick highest prob, [ID]=Go to block, [q]=Quit, [s]=Save")

    while True:
        blk = func.blocks.get(current_block)
        if not blk:
            print("Error: Lost in CFG (Block not found)")
            break

        print(f"\n📍 Current: BB.{current_block}")
        # Show instructions (Fix #6)
        for instr in blk.head_instrs:
            print(f"   {instr}")
        if blk.instr_count > len(blk.head_instrs) + len(blk.tail_instrs):
            print(f"   ... ({blk.instr_count - 5} more) ...")
        for instr in blk.tail_instrs:
            print(f"   {instr}")

        # Find outgoing edges
        succs = [e for e in func.edges if e.src == current_block]
        
        if not succs:
            print("🛑 End of function (Return).")
            break

        print("Options:")
        succs.sort(key=lambda x: x.prob, reverse=True)
        
        for i, edge in enumerate(succs):
            print(f"   [{i}] -> BB.{edge.dst} (Prob: {edge.prob:.2%})")

        choice = input(">> ").strip()
        
        next_block = None
        
        if choice == 'q':
            break
        elif choice == 's':
             # Save current path
             trace_name = f"interactive_{int(time.time())}"
             func.traces[trace_name] = path
             save_project(project, "project_updated.json")
             print(f"Saved trace '{trace_name}' to project_updated.json")
             continue
        elif choice == '':
            # Auto: Pick highest probability
            next_block = succs[0].dst
        elif choice.isdigit():
            # If user types block ID directly
            target = int(choice)
            # Check if valid edge exists or index
            if target < len(succs):
                 next_block = succs[target].dst
            else:
                 # Check if they typed the actual BB ID
                 valid = False
                 for e in succs:
                     if e.dst == target:
                         next_block = target
                         valid = True
                         break
                 if not valid:
                     print("Invalid choice.")
                     continue
        else:
            print("Unknown command.")
            continue

        if next_block is not None:
            current_block = next_block
            path.append(current_block)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("project_file")
    parser.add_argument("--func", required=True, help="Function name to step through")
    args = parser.parse_args()

    proj = load_project(args.project_file)
    run_stepper(proj, args.func)
