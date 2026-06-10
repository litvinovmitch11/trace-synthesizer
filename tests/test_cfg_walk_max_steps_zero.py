"""max_steps=0 disables env-level truncation (infinite-horizon until CFG sink or hard cap)."""

import json
from pathlib import Path

from trace_synthesizer.core.grammar import CfgProgram
from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv


def test_max_steps_zero_never_truncates_on_cycle(tmp_path: Path) -> None:
    cfg = [
        {
            "function_name": "spin",
            "blocks": [
                {
                    "id": 0,
                    "name": "entry",
                    "instr_count": 1,
                    "is_entry": True,
                    "successors": [
                        {"is_fallthrough": True, "prob": 1.0, "target_id": 1},
                    ],
                },
                {
                    "id": 1,
                    "name": "loop",
                    "instr_count": 1,
                    "is_entry": False,
                    "successors": [
                        {"is_fallthrough": True, "prob": 1.0, "target_id": 0},
                    ],
                },
            ],
        }
    ]
    p = tmp_path / "spin.cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    grammar = CfgProgram.from_cfg_json(p)
    env = CFGWalkEnv(grammar, "spin", max_steps=0, seed=0)
    obs, _ = env.reset(seed=0)
    for _ in range(5000):
        obs, _r, term, trunc, _info = env.step(0)
        assert not trunc
        if term:
            break
    else:
        # No absorbing state: only ``truncated`` could stop us, but max_steps=0 disables it.
        pass
