"""Distributed planted graph coloring with a controlled cross-partition edge ratio."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Mapping


@dataclass(frozen=True)
class Instance:
    instance_id: str
    n: int
    k: int
    P: int
    rho_target: float
    rho_actual: float
    seed: int
    edges: tuple[tuple[int, int], ...]
    partitions: tuple[int, ...]
    planted_coloring: tuple[int, ...]
    frontier_width: int = 1


def _partition(n: int, blocks: int) -> tuple[int, ...]:
    return tuple(min(blocks - 1, vertex * blocks // n) for vertex in range(n))


def _sample_without_replacement(rng: random.Random, pool: list[tuple[int, int]], count: int) -> list[tuple[int, int]]:
    if count <= 0:
        return []
    if count >= len(pool):
        return list(pool)
    return rng.sample(pool, count)


def make_instance(n, k, P, rho, seed) -> Instance:
    """Create a guaranteed-colorable graph with approximately ``rho`` crossing edges."""
    n = int(n)
    k = int(k)
    P = int(P)
    rho = float(rho)
    if n < 4 or k < 2 or P < 1 or P > n:
        raise ValueError("requires n>=4, k>=2, and 1<=P<=n")
    if not 0.0 <= rho <= 1.0:
        raise ValueError("rho must lie in [0,1]")
    rng = random.Random(int(seed))
    partitions = _partition(n, P)
    colors = [index % k + 1 for index in range(n)]
    rng.shuffle(colors)
    within: list[tuple[int, int]] = []
    crossing: list[tuple[int, int]] = []
    for left in range(n):
        for right in range(left + 1, n):
            if colors[left] == colors[right]:
                continue
            target = crossing if partitions[left] != partitions[right] else within
            target.append((left, right))
    # Use one rho-independent edge budget per seed. This keeps density fixed
    # while the coupling sweep replaces within-partition edges with crossing
    # edges. Taking the smaller pool also keeps the rho endpoints feasible.
    desired_edges = max(n + 1, 2 * n)
    target_edges = max(1, min(desired_edges, len(within), len(crossing)))
    cross_count = int(round(rho * target_edges))
    within_count = target_edges - cross_count
    edges = _sample_without_replacement(rng, crossing, cross_count) + _sample_without_replacement(rng, within, within_count)
    edges = sorted(set(edges))
    actual = sum(partitions[left] != partitions[right] for left, right in edges) / max(len(edges), 1)
    return Instance(
        instance_id=f"dist_color_n{n}_k{k}_p{P}_rho{rho:.2f}_s{int(seed)}",
        n=n,
        k=k,
        P=P,
        rho_target=rho,
        rho_actual=actual,
        seed=int(seed),
        edges=tuple(edges),
        partitions=partitions,
        planted_coloring=tuple(colors),
    )


def edge_violations(instance: Instance, coloring: Mapping[int, int]) -> tuple[int, int]:
    """Return total and cross-partition violations for a proposed coloring."""
    total = 0
    cross = 0
    for left, right in instance.edges:
        if left not in coloring or right not in coloring or int(coloring[left]) == int(coloring[right]):
            total += 1
            cross += int(instance.partitions[left] != instance.partitions[right])
    return total, cross


def solved(instance, coloring) -> bool:
    """Return whether all vertices are colored and every edge is satisfied."""
    if len(coloring) != int(instance.n):
        return False
    if any(int(coloring.get(vertex, 0)) not in range(1, int(instance.k) + 1) for vertex in range(int(instance.n))):
        return False
    return edge_violations(instance, coloring)[0] == 0


def with_frontier_width(instance: Instance, width: int) -> Instance:
    return Instance(**{**instance.__dict__, "frontier_width": int(width)})
