"""Sokoban reversible internal-search planning demo tier."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SokobanState:
    walls: set[tuple[int, int]]
    boxes: set[tuple[int, int]]
    targets: set[tuple[int, int]]
    player: tuple[int, int]


def is_dead_end(state: SokobanState) -> bool:
    for x, y in state.boxes:
        if (x, y) in state.targets:
            continue
        horizontal = (x - 1, y) in state.walls or (x + 1, y) in state.walls
        vertical = (x, y - 1) in state.walls or (x, y + 1) in state.walls
        if horizontal and vertical:
            return True
    return False
