"""Agent protocol for CFG walk environments."""

from __future__ import annotations

from typing import Any, Protocol


class Agent(Protocol):
    """Selects an action given observation and info (e.g. action_mask)."""

    def act(self, observation: dict[str, Any], info: dict[str, Any]) -> int: ...
