"""Countdown / Game-of-24 deterministic planning demo tier."""

from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass
class CountdownInstance:
    numbers: list[int]
    target: int
    requires_backtracking: bool = True


def generate_countdown(n_instances: int = 20, seed: int = 42, target: int = 24) -> list[CountdownInstance]:
    rng = random.Random(seed)
    return [CountdownInstance([rng.randint(1, 13) for _ in range(4)], target) for _ in range(n_instances)]
