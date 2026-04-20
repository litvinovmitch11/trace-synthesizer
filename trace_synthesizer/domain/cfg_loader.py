"""Load Program from CFGDumper JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from trace_synthesizer.domain.errors import InvalidCfgError
from trace_synthesizer.domain.program import (
    BasicBlock,
    FunctionCFG,
    Program,
    SuccessorEdge,
)


def _parse_block(raw: dict[str, Any]) -> BasicBlock:
    succs: list[SuccessorEdge] = []
    for s in raw.get("successors") or []:
        succs.append(
            SuccessorEdge(
                target_id=int(s["target_id"]),
                prob=float(s["prob"]) if s.get("prob") is not None else None,
                is_fallthrough=bool(s.get("is_fallthrough", False)),
            )
        )
    return BasicBlock(
        id=int(raw["id"]),
        name=str(raw.get("name", "")),
        is_entry=bool(raw.get("is_entry", False)),
        instr_count=int(raw.get("instr_count", 0)),
        has_call=bool(raw.get("has_call", False)),
        call_target=str(raw["call_target"]) if raw.get("call_target") else None,
        successors=tuple(succs),
    )


def _parse_function(raw: dict[str, Any]) -> FunctionCFG:
    name = str(raw["function_name"])
    blocks_raw = raw.get("blocks") or []
    if not isinstance(blocks_raw, list):
        raise InvalidCfgError(f"Function {name}: blocks must be a list")
    blocks = tuple(_parse_block(b) for b in blocks_raw)
    return FunctionCFG(function_name=name, blocks=blocks)


def load_program_from_cfg_json(path: str | Path) -> Program:
    """Parse CFG JSON (list of function objects) into a Program."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return load_program_from_cfg_file(f)


def load_program_from_cfg_file(f: TextIO) -> Program:
    data = json.load(f)
    if not isinstance(data, list):
        raise InvalidCfgError("CFG root must be a JSON array of functions")
    funcs = tuple(_parse_function(item) for item in data)
    program = Program(functions=funcs)
    _validate_references(program)
    return program


def _validate_references(program: Program) -> None:
    for fn in program.functions:
        ids = {b.id for b in fn.blocks}
        for b in fn.blocks:
            for s in b.successors:
                if s.target_id not in ids:
                    raise InvalidCfgError(
                        f"{fn.function_name}: block {b.id} references "
                        f"missing successor {s.target_id}"
                    )
