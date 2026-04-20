"""Parse llvm-readobj --bb-addr-map text output into searchable RVA ranges."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BbRange:
    start_rva: int
    end_rva: int
    func_name: str
    bb_id: int


class BbAddressMap:
    """Sorted (start_rva) ranges for binary search mapping instruction RVA -> (func, bb_id)."""

    def __init__(self, ranges: tuple[BbRange, ...]) -> None:
        self._ranges = ranges

    @classmethod
    def from_readobj_file(cls, path: str | Path) -> BbAddressMap:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        return cls.from_readobj_text(text)

    @classmethod
    def from_readobj_text(cls, text: str) -> BbAddressMap:
        ranges: list[BbRange] = []
        current_func: str | None = None
        current_base: int | None = None
        current_bb_id: int | None = None
        current_offset: int | None = None
        current_size: int | None = None

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("Name:"):
                current_func = line.split("Name:", 1)[1].strip()
            elif line.startswith("Base Address:"):
                current_base = int(line.split("Base Address:", 1)[1].strip(), 16)
            elif line.startswith("ID:"):
                current_bb_id = int(line.split("ID:", 1)[1].strip())
            elif line.startswith("Offset:"):
                current_offset = int(line.split("Offset:", 1)[1].strip(), 16)
            elif line.startswith("Size:"):
                current_size = int(line.split("Size:", 1)[1].strip(), 16)
                if (
                    current_func
                    and current_base is not None
                    and current_bb_id is not None
                    and current_offset is not None
                    and current_size is not None
                ):
                    start_rva = current_base + current_offset
                    end_rva = start_rva + current_size
                    ranges.append(
                        BbRange(
                            start_rva=start_rva,
                            end_rva=end_rva,
                            func_name=current_func,
                            bb_id=current_bb_id,
                        )
                    )
                current_bb_id = None
                current_offset = None
                current_size = None

        ranges.sort(key=lambda r: r.start_rva)
        return cls(tuple(ranges))

    def lookup(self, rva: int) -> tuple[str | None, int | None]:
        """Return (func_name, bb_id) or (None, None) if unmapped."""
        left, right = 0, len(self._ranges) - 1
        while left <= right:
            mid = (left + right) // 2
            r = self._ranges[mid]
            if r.start_rva <= rva < r.end_rva:
                return r.func_name, r.bb_id
            if rva < r.start_rva:
                right = mid - 1
            else:
                left = mid + 1
        return None, None
