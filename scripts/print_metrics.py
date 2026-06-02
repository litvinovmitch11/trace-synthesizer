import json
from pathlib import Path

p = Path("benchmarks/local/cpp_opt_levels/out/final_report_cross_opt.json")
if not p.exists():
    print("Report not found.")
    exit(1)

d = json.loads(p.read_text())

metrics_to_show = ["block_visit_kl", "edge_transition_kl", "hot_path_ngram_overlap"]

for eval_level, models in d.items():
    print(f"\n=== {eval_level} ===")
    
    header = f"{'Model':12}"
    for m in metrics_to_show:
        header += f" | {m:22}"
    print(header)
    print("-" * len(header))
    
    for model_name, metrics in models.items():
        row = f"{model_name:12}"
        for metric_name in metrics_to_show:
            val = next((m["value"] for m in metrics if m["name"] == metric_name), None)
            if val is not None:
                row += f" | {val:22.4f}"
            else:
                row += f" | {'N/A':22}"
        print(row)
