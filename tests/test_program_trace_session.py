"""ProgramTraceSession facade: validate, intra export, BB path length."""

import json
from pathlib import Path

from trace_synthesizer.program_trace import ProgramTraceSession


def _two_block_cfg(tmp_path: Path) -> Path:
    cfg = [
        {
            "function_name": "main",
            "blocks": [
                {
                    "id": 0,
                    "name": "entry",
                    "instr_count": 1,
                    "is_entry": True,
                    "successors": [
                        {
                            "target_id": 1,
                            "prob": 1.0,
                            "is_fallthrough": True,
                        }
                    ],
                },
                {
                    "id": 1,
                    "name": "exit",
                    "instr_count": 1,
                    "is_entry": False,
                    "successors": [],
                },
            ],
        }
    ]
    p = tmp_path / "two_block.cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


def test_validate_and_intra_path_from_compressed(tmp_path: Path) -> None:
    cfg_path = _two_block_cfg(tmp_path)
    session = ProgramTraceSession.from_cfg_json(cfg_path, function_name="main")
    comp = tmp_path / "c.json"
    comp.write_text(
        json.dumps(
            [
                {"func": "main", "bb": 0},
                {"func": "main", "bb": 1},
            ]
        ),
        encoding="utf-8",
    )
    vi, inter, inv = session.validate_transition_counts(comp)
    assert inv == 0
    assert vi >= 1
    bbs = session.intra_bb_path_from_compressed(comp)
    assert bbs == [0, 1]


def test_export_intra_matches_intra_bb_loader(tmp_path: Path) -> None:
    cfg_path = _two_block_cfg(tmp_path)
    session = ProgramTraceSession.from_cfg_json(cfg_path, function_name="main")
    comp = tmp_path / "c.json"
    comp.write_text(
        json.dumps([{"func": "main", "bb": 0}, {"func": "main", "bb": 1}]),
        encoding="utf-8",
    )
    out = tmp_path / "intra.json"
    session.export_intra_from_compressed(comp, out)
    from_disk = session.intra_bb_path_from_intra_json(out)
    assert from_disk == [0, 1]
    rec = json.loads(out.read_text(encoding="utf-8"))
    assert rec["function_name"] == "main"
    assert rec["source"] == "bb_trace"
    assert len(rec["sequence"]) == 2
