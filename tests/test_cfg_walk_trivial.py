"""CFG with zero out-degree must not crash Gymnasium spaces."""

import json
from pathlib import Path

from trace_synthesizer.core.grammar import CfgProgram
from trace_synthesizer.env.cfg_walk_env import CFGWalkEnv


def test_zero_max_out_degree_spaces_and_reset(tmp_path: Path) -> None:
    cfg = [
        {
            "function_name": "main",
            "blocks": [
                {
                    "id": 0,
                    "name": "entry",
                    "instr_count": 1,
                    "is_entry": True,
                    "successors": [],
                }
            ],
        }
    ]
    p = tmp_path / "trivial.cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    grammar = CfgProgram.from_cfg_json(p)
    env = CFGWalkEnv(grammar, "main", max_steps=10, seed=0)
    assert env.action_space.n == 1
    assert env.observation_space["valid_mask"].n == 1
    obs, info = env.reset(seed=0)
    assert info.get("terminal") is True
    assert obs["valid_mask"].shape == (1,)
    assert int(obs["valid_mask"][0]) == 0
