from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any

@dataclass
class MIRBlock:
    id: int
    name: str
    pgo_frequency: float = 0.0  # Float, т.к. иногда это нормализованное значение
    instructions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "freq": self.pgo_frequency,
            "instructions": self.instructions
        }

@dataclass
class MIRFunction:
    name: str
    blocks: Dict[int, MIRBlock] = field(default_factory=dict)
    # Adjacency list: src -> {dst: probability}
    edges: Dict[int, Dict[int, float]] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "blocks": [b.to_dict() for b in self.blocks.values()],
            # Сериализуем ребра: список [src, dst, prob]
            "edges": [
                {"src": u, "dst": v, "prob": p}
                for u, targets in self.edges.items()
                for v, p in targets.items()
            ]
        }
