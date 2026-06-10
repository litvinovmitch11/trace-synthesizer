"""Read raw DynamoRIO InstrTracer trace.bin (uint64 LE RVAs)."""

from __future__ import annotations

import struct
from pathlib import Path


def read_rva_trace(path: str | Path) -> tuple[int, ...]:
    """Load trace.bin as a tuple of uint64 RVAs."""
    data = Path(path).read_bytes()
    n = len(data) // 8
    out: list[int] = []
    for i in range(n):
        chunk = data[i * 8 : i * 8 + 8]
        out.append(struct.unpack("<Q", chunk)[0])
    return tuple(out)
