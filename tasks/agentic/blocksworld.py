"""Blocksworld reversible planning demo tier."""

from __future__ import annotations

from dataclasses import dataclass
import copy


@dataclass
class BlocksworldState:
    stacks: list[list[str]]
    holding: str | None = None


class BlocksworldSimulator:
    def __init__(self, state: BlocksworldState):
        self.state = copy.deepcopy(state)
        self.history: list[BlocksworldState] = []

    def snapshot(self) -> BlocksworldState:
        return copy.deepcopy(self.state)

    def restore(self, state: BlocksworldState) -> None:
        self.state = copy.deepcopy(state)

    def reversible_apply(self, action: str) -> bool:
        self.history.append(self.snapshot())
        return True

    def undo(self) -> bool:
        if not self.history:
            return False
        self.restore(self.history.pop())
        return True
