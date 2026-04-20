"""Roll out one episode using a Gymnasium env and an agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from trace_synthesizer.agents.protocol import Agent


@dataclass
class StepRecord:
    step_index: int
    from_bb: int
    to_bb: int
    action: int
    reward: float
    terminated: bool
    truncated: bool


@dataclass
class EpisodeRollout:
    """entry_bb_id is the basic block after reset (before any step)."""

    entry_bb_id: int
    steps: tuple[StepRecord, ...]
    termination: str

    @property
    def length(self) -> int:
        return len(self.steps)


def rollout_episode(
    env: Any, agent: Agent, *, reset_seed: int | None = None
) -> EpisodeRollout:
    if reset_seed is not None:
        obs, info = env.reset(seed=reset_seed)
    else:
        obs, info = env.reset()
    entry_bb_id = int(obs["bb_id"][0])
    if info.get("terminal"):
        return EpisodeRollout(
            entry_bb_id=entry_bb_id, steps=tuple(), termination="trivial_terminal"
        )
    from_bb = entry_bb_id
    records: list[StepRecord] = []
    termination = "unknown"
    hard_limit = 10_000_000
    for t in range(hard_limit):
        action = agent.act(obs, info)
        obs, reward, terminated, truncated, info = env.step(action)
        to_bb = int(obs["bb_id"][0])
        records.append(
            StepRecord(
                step_index=t,
                from_bb=from_bb,
                to_bb=to_bb,
                action=int(action),
                reward=float(reward),
                terminated=bool(terminated),
                truncated=bool(truncated),
            )
        )
        from_bb = to_bb
        if terminated:
            termination = "terminated"
            break
        if truncated:
            termination = "truncated"
            break
    else:
        termination = "hard_capped"
    return EpisodeRollout(
        entry_bb_id=entry_bb_id, steps=tuple(records), termination=termination
    )
