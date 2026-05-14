"""Inter-procedural env: call and return transitions update function context."""

from __future__ import annotations

import json
from pathlib import Path

from trace_synthesizer.core.grammar import CfgProgram
from trace_synthesizer.env.interproc_walk_env import InterproceduralCFGWalkEnv


def test_interproc_call_return(tmp_path: Path) -> None:
    cfg = [
        {
            "function_name": "callee",
            "blocks": [
                {"id": 10, "name": "callee.entry", "is_entry": True, "instr_count": 1, "successors": []}
            ],
        },
        {
            "function_name": "main",
            "blocks": [
                {
                    "id": 0,
                    "name": "entry",
                    "is_entry": True,
                    "instr_count": 1,
                    "has_call": True,
                    "call_target": "callee",
                    "successors": [{"target_id": 1, "prob": 1.0, "is_fallthrough": True}],
                },
                {"id": 1, "name": "ret", "is_entry": False, "instr_count": 1, "successors": []},
            ],
        },
    ]
    p = tmp_path / "inter.cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    g = CfgProgram.from_cfg_json(p)
    env = InterproceduralCFGWalkEnv(g, "main", max_steps=20, seed=0)

    obs, info = env.reset(seed=0)
    mask = info["action_mask"]
    call_action = env.action_space.n - 2
    assert int(mask[call_action]) == 1
    obs, _r, _term, _trunc, info = env.step(call_action)
    assert int(obs["func_id"][0]) != 1  # switched away from main
    assert info["transition"] == "call"

    ret_action = env.action_space.n - 1
    obs, _r, _term, _trunc, info = env.step(ret_action)
    assert info["transition"] == "return"
    assert int(obs["bb_id"][0]) == 1
