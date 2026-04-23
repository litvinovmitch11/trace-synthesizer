from __future__ import annotations

from pathlib import Path

from trace_synthesizer.agents.cfg_supervision import action_mask_rows_for_bb_prefix
from trace_synthesizer.core.grammar import CfgProgram


def test_action_mask_matches_successors() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = CfgProgram.from_cfg_json(
        root / "tests" / "fixtures" / "test" / "main.cfg.json"
    )
    # path 0 -> 1: two successors at 0, index 1 is valid
    m = action_mask_rows_for_bb_prefix(cfg, "main", [0], max_actions=2)
    assert m.shape == (1, 2)
    assert m[0, 0] and m[0, 1]
    m2 = action_mask_rows_for_bb_prefix(cfg, "main", [1], max_actions=2)
    assert m2[0, 0] and not m2[0, 1]
