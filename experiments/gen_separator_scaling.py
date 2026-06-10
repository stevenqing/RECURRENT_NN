"""Separator-scaling pool generator for Rung-1 symbolic experiments."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import random
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import (
    Instance,
    REFERENCE_NODE_CAP,
    SOURCE,
    _default_color_orders,
    _normalize_edges,
    _solve,
)

MAX_REJECTION_ATTEMPTS = 300


def _partitions(m_blocks: int, n_per_block: int) -> tuple[int, ...]:
    return tuple(block for block in range(m_blocks) for _ in range(n_per_block))


def _block_vertices(block: int, n_per_block: int) -> list[int]:
    start = block * n_per_block
    return list(range(start, start + n_per_block))


def target_depth(m_blocks: int, d_local: int, d_boundary: int) -> int:
    return d_boundary + max(1, round(m_blocks * d_local / 4))


def _density(edges: tuple[tuple[int, int], ...], n_vertices: int) -> float:
    possible = n_vertices * (n_vertices - 1) / 2
    return len(edges) / possible if possible else 0.0


def _edge_counts(edges: tuple[tuple[int, int], ...], partitions: tuple[int, ...]) -> dict[str, int]:
    boundary = sum(partitions[u] != partitions[v] for u, v in edges)
    return {"n_boundary_edges": boundary, "n_intra_block_edges": len(edges) - boundary}


def _planted_order(n: int, required_prefix: list[int], conflict_vertex: int, rng: random.Random) -> tuple[int, ...]:
    used = set(required_prefix + [conflict_vertex])
    remaining = [vertex for vertex in range(n) if vertex not in used]
    rng.shuffle(remaining)
    return tuple(required_prefix + [conflict_vertex] + remaining)


def _planted_separator_edges(
    rng: random.Random,
    m_blocks: int,
    n_per_block: int,
    b: int,
    target_d_global: int,
) -> tuple[tuple[tuple[int, int], ...], tuple[int, ...], list[int]]:
    if m_blocks < 2:
        raise ValueError("m_blocks must be at least 2 for separator cells")
    if n_per_block < 12:
        raise ValueError("n_per_block must be at least 12 for b=12 separator cells")
    if b < 1 or b > n_per_block:
        raise ValueError("b must be in [1, n_per_block]")
    if target_d_global < 4:
        raise ValueError("target_d_global must be at least 4 for four-color planting")
    n = m_blocks * n_per_block
    block0 = _block_vertices(0, n_per_block)
    block1 = _block_vertices(1, n_per_block)
    boundary_vertices = block0[:b]
    earliest_boundary = boundary_vertices[0]
    p1, p2, p3, color4, conflict = block1[:5]
    prefix = [p1, earliest_boundary, p2, p3, color4] if target_d_global == 4 else [earliest_boundary, p1, p2, p3, color4]
    filler = [vertex for vertex in range(n) if vertex not in set(prefix + [conflict])]
    rng.shuffle(filler)
    while len(prefix) < target_d_global:
        prefix.append(filler.pop())
    order = _planted_order(n, prefix, conflict, rng)
    edges: set[tuple[int, int]] = set()

    def add(u: int, v: int) -> None:
        if u != v:
            edges.add(tuple(sorted((u, v))))

    add(p2, p1)
    add(p3, p1)
    add(p3, p2)
    add(color4, p1)
    add(color4, p2)
    add(color4, p3)
    add(conflict, earliest_boundary)
    add(conflict, p2)
    add(conflict, p3)
    add(conflict, color4)

    satellite_pool = [vertex for vertex in order[target_d_global + 1 :] if vertex not in set(boundary_vertices)]
    for index, boundary_vertex in enumerate(boundary_vertices):
        if index >= len(satellite_pool):
            break
        satellite = satellite_pool[index]
        add(satellite, boundary_vertex)

    for block in range(m_blocks):
        vertices = _block_vertices(block, n_per_block)
        for offset in range(0, min(8, n_per_block - 3), 4):
            clique = vertices[offset : offset + 4]
            for i, u in enumerate(clique):
                for v in clique[i + 1 :]:
                    add(u, v)
        for u in vertices:
            for v in vertices:
                if u < v and rng.random() < 0.012:
                    add(u, v)

    for left_block in range(m_blocks - 1):
        left = _block_vertices(left_block, n_per_block)
        right = _block_vertices(left_block + 1, n_per_block)
        for index in range(min(b, len(left), len(right))):
            if left_block == 0 and index == 0:
                continue
            add(left[index], right[index])
        for _ in range(max(1, b // 3)):
            add(rng.choice(left), rng.choice(right))
    return _normalize_edges(list(edges)), order, boundary_vertices


def _make_separator_instance(
    instance_id: str,
    seed: int,
    source_index: int,
    source_kind: str,
    m_blocks: int,
    n_per_block: int,
    k: int,
    edges: tuple[tuple[int, int], ...],
    order: tuple[int, ...],
) -> Instance | None:
    n = m_blocks * n_per_block
    partitions = _partitions(m_blocks, n_per_block)
    instance = Instance(
        instance_id=instance_id,
        seed=seed,
        source_index=source_index,
        source_kind=source_kind,
        n=n,
        k=k,
        chromatic_number=k,
        edges=edges,
        partitions=partitions,
        order=order,
        color_orders=_default_color_orders(n, k),
        reference_depth=0,
        band="separator",
        boundary_conflict_exact=True,
    )
    reference = _solve(instance, "cbj_bounded", node_cap=REFERENCE_NODE_CAP, register_capacity=max(n, 64))
    if not reference.solved:
        return None
    return replace(
        instance,
        reference_depth=int(reference.first_conflict_depth or 0),
        boundary_conflict_exact=reference.boundary_conflict_exact,
    )


def _live_domain_at_decision(instance: Instance) -> float:
    adjacency = {vertex: set() for vertex in range(instance.n)}
    for u, v in instance.edges:
        adjacency[u].add(v)
        adjacency[v].add(u)
    assignment: dict[int, int] = {}
    domains: list[int] = []
    for vertex in instance.order:
        feasible = []
        for color in range(1, instance.k + 1):
            if all(assignment.get(neighbor) != color for neighbor in adjacency[vertex]):
                feasible.append(color)
        domains.append(len(feasible))
        if not feasible:
            break
        assignment[vertex] = feasible[0]
    positive = [value for value in domains if value > 0]
    return mean(positive) if positive else float(instance.k)


def generate_separator_scaling_pool(
    m_blocks: int,
    n_per_block: int,
    k: int,
    d_local: int,
    b: int,
    d_boundary: int,
    n_instances: int,
    seed: int,
    p_range: tuple[float, float] = (0.30, 0.48),
    target_d_global: int | None = None,
    cell_id: str = "separator_cell",
    sweep: str = "separator_scaling",
) -> dict[str, Any]:
    """
    Generate a planted separator-scaling graph-coloring pool.

    The planted first conflict has measured global depth greater than the nominal
    boundary depth. This records ``local_contribution`` while reusing the frozen
    symbolic solver unchanged for reference and downstream arms.
    """
    if d_local < 3:
        raise ValueError("d_local must be at least 3 for separator-scaling v0.1")
    target = target_d_global if target_d_global is not None else target_depth(m_blocks, d_local, d_boundary)
    rng = random.Random(seed * 1_000_003 + target * 10_007 + b * 101 + m_blocks * 17 + n_per_block)
    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    attempts = 0
    while len(rows) < n_instances and attempts < MAX_REJECTION_ATTEMPTS:
        attempts += 1
        edges, order, boundary_vertices = _planted_separator_edges(rng, m_blocks, n_per_block, b, target)
        source_index = seed * 1_000_000 + target * 10_000 + b * 100 + attempts
        instance_id = f"sep_s{seed}_{cell_id}_{attempts:06d}"
        instance = _make_separator_instance(
            instance_id=instance_id,
            seed=seed,
            source_index=source_index,
            source_kind=f"separator_scaling_v01:{cell_id}:m{m_blocks}_n{n_per_block}_k{k}_dl{d_local}_b{b}_db{d_boundary}_targetd{target}",
            m_blocks=m_blocks,
            n_per_block=n_per_block,
            k=k,
            edges=edges,
            order=order,
        )
        if instance is None:
            counters["reference_unsolved_rejected"] += 1
            continue
        if instance.reference_depth != target:
            counters[f"depth_{instance.reference_depth}_rejected"] += 1
            continue
        local_contribution = instance.reference_depth - d_boundary
        if local_contribution <= 0:
            counters["local_contribution_nonpositive_rejected"] += 1
            continue
        counts = _edge_counts(edges, instance.partitions)
        rows.append({
            "instance_id": instance.instance_id,
            "seed": seed,
            "source_index": source_index,
            "source_kind": instance.source_kind,
            "cell_id": cell_id,
            "sweep": sweep,
            "m_blocks": m_blocks,
            "n_per_block": n_per_block,
            "n_vertices": instance.n,
            "k": k,
            "d_local": d_local,
            "b": b,
            "d_boundary": d_boundary,
            "target_d_global": target,
            "d_global_reference": instance.reference_depth,
            "reference_cross_agent_conflict_depth": instance.reference_depth,
            "local_contribution": local_contribution,
            **counts,
            "d_local_capacity_ok": local_contribution > 0,
            "density": _density(edges, instance.n),
            "target_met": True,
            "edges": [list(edge) for edge in edges],
            "partitions": list(instance.partitions),
            "order": list(instance.order),
            "boundary_vertices": boundary_vertices,
            "boundary_conflict_exact": instance.boundary_conflict_exact,
            "mean_live_domain_at_decision": _live_domain_at_decision(instance),
            "source": SOURCE,
            "provenance": "separator_scaling_v01_planted_local_boundary_pool",
        })
        counters["accepted"] += 1
    for row in rows:
        row["target_met"] = len(rows) == n_instances
    return {
        "cell": {
            "cell_id": cell_id,
            "sweep": sweep,
            "m_blocks": m_blocks,
            "n_per_block": n_per_block,
            "k": k,
            "d_local": d_local,
            "b": b,
            "d_boundary": d_boundary,
            "target_d_global": target,
            "n_instances_target": n_instances,
            "n_instances": len(rows),
            "target_met": len(rows) == n_instances,
            "attempts": attempts,
            "p_range": list(p_range),
            "rejection_counters": dict(counters),
            "source": SOURCE,
            "provenance": "separator_scaling_v01_cell_generation",
        },
        "instance_manifest": rows,
    }
