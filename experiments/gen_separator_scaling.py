"""Separator-scaling pool generator for Rung-1 symbolic experiments."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import random
from statistics import mean
from typing import Any

from reasoning_gym.algorithmic.graph_color import generate_random_graph

from experiments.rung1_distributed_graph_coloring import (
    Instance,
    REFERENCE_NODE_CAP,
    SOURCE,
    _chromatic_number,
    _default_color_orders,
    _normalize_edges,
    _priority_mcv_order,
    _solve,
)

MAX_REJECTION_ATTEMPTS = 50000


def _partitions(m_blocks: int, n_per_block: int) -> tuple[int, ...]:
    return tuple(block for block in range(m_blocks) for _ in range(n_per_block))


def _block_vertices(block: int, n_per_block: int) -> list[int]:
    start = block * n_per_block
    return list(range(start, start + n_per_block))


def _density(edges: tuple[tuple[int, int], ...], n_vertices: int) -> float:
    possible = n_vertices * (n_vertices - 1) / 2
    return len(edges) / possible if possible else 0.0


def _edge_counts(edges: tuple[tuple[int, int], ...], partitions: tuple[int, ...]) -> dict[str, int]:
    boundary = sum(partitions[u] != partitions[v] for u, v in edges)
    return {"n_boundary_edges": boundary, "n_intra_block_edges": len(edges) - boundary}


def _make_separator_instance(
    instance_id: str,
    seed: int,
    source_index: int,
    source_kind: str,
    m_blocks: int,
    n_per_block: int,
    k: int,
    edges: tuple[tuple[int, int], ...],
) -> Instance | None:
    n = m_blocks * n_per_block
    partitions = _partitions(m_blocks, n_per_block)
    chromatic = _chromatic_number(n, edges, k)
    if chromatic != k:
        return None
    order = _priority_mcv_order(n, edges, partitions)
    instance = Instance(
        instance_id=instance_id,
        seed=seed,
        source_index=source_index,
        source_kind=source_kind,
        n=n,
        k=k,
        chromatic_number=chromatic,
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


def _separator_edges(
    rng: random.Random,
    m_blocks: int,
    n_per_block: int,
    b: int,
    p: float,
) -> tuple[tuple[tuple[int, int], ...], list[int]]:
    edges: set[tuple[int, int]] = set()
    boundary_vertices: set[int] = set()
    for block in range(m_blocks):
        vertices, raw_edges = generate_random_graph(rng, n_per_block, p)
        offset = block * n_per_block
        for u, v in raw_edges:
            edges.add(tuple(sorted((offset + int(u), offset + int(v)))))
    for block in range(m_blocks - 1):
        left = _block_vertices(block, n_per_block)
        right = _block_vertices(block + 1, n_per_block)
        left_boundary = rng.sample(left, b)
        right_boundary = rng.sample(right, b)
        boundary_vertices.update(left_boundary)
        boundary_vertices.update(right_boundary)
        for index, u in enumerate(left_boundary):
            v = right_boundary[index % len(right_boundary)]
            edges.add(tuple(sorted((u, v))))
        for u in left_boundary:
            for v in right_boundary:
                if rng.random() < 0.35:
                    edges.add(tuple(sorted((u, v))))
    return _normalize_edges(list(edges)), sorted(boundary_vertices)


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
) -> dict[str, Any]:
    """
    Generate a block-structured graph-coloring pool for separator scaling.

    Each cell is rejection-filtered for measured global CBJ first-conflict depth
    equal to ``d_boundary``. Intra-block and boundary edges are stored separately
    through edge counts and the full edge manifest. Cells that miss the target
    within the rejection budget are returned with ``target_met=False``.
    """
    if b < 1 or b > n_per_block:
        raise ValueError("b must be in [1, n_per_block]")
    rng = random.Random(seed * 1_000_003 + d_boundary * 10_007 + b * 101 + m_blocks * 17 + n_per_block)
    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    attempts = 0
    seen: set[tuple[tuple[int, int], ...]] = set()
    while len(rows) < n_instances and attempts < MAX_REJECTION_ATTEMPTS:
        attempts += 1
        p = rng.uniform(*p_range)
        edges, boundary_vertices = _separator_edges(rng, m_blocks, n_per_block, b, p)
        if edges in seen:
            counters["duplicate_rejected"] += 1
            continue
        seen.add(edges)
        source_index = seed * 1_000_000 + d_boundary * 10_000 + b * 100 + attempts
        instance_id = f"sep_s{seed}_dg{d_boundary}_b{b}_{attempts:06d}"
        instance = _make_separator_instance(
            instance_id=instance_id,
            seed=seed,
            source_index=source_index,
            source_kind=f"separator_scaling:m{m_blocks}_n{n_per_block}_k{k}_b{b}_targetd{d_boundary}",
            m_blocks=m_blocks,
            n_per_block=n_per_block,
            k=k,
            edges=edges,
        )
        if instance is None:
            counters["reference_unsolved_or_chromatic_rejected"] += 1
            continue
        if instance.reference_depth != d_boundary:
            counters[f"depth_{instance.reference_depth}_rejected"] += 1
            continue
        counts = _edge_counts(edges, instance.partitions)
        rows.append({
            "instance_id": instance.instance_id,
            "seed": seed,
            "source_index": source_index,
            "source_kind": instance.source_kind,
            "m_blocks": m_blocks,
            "n_per_block": n_per_block,
            "n_vertices": instance.n,
            "k": k,
            "d_local": d_local,
            "b": b,
            "d_boundary": d_boundary,
            "d_global_reference": instance.reference_depth,
            "reference_cross_agent_conflict_depth": instance.reference_depth,
            **counts,
            "d_local_capacity_ok": d_local <= d_boundary,
            "density": _density(edges, instance.n),
            "target_met": True,
            "edges": [list(edge) for edge in edges],
            "partitions": list(instance.partitions),
            "order": list(instance.order),
            "boundary_vertices": boundary_vertices,
            "boundary_conflict_exact": instance.boundary_conflict_exact,
            "mean_live_domain_at_decision": _live_domain_at_decision(instance),
            "source": SOURCE,
            "provenance": "separator_scaling_generate_random_graph_boundary_rejection_v0",
        })
        counters["accepted"] += 1
    for row in rows:
        row["target_met"] = len(rows) == n_instances
    return {
        "cell": {
            "m_blocks": m_blocks,
            "n_per_block": n_per_block,
            "k": k,
            "d_local": d_local,
            "b": b,
            "d_boundary": d_boundary,
            "n_instances_target": n_instances,
            "n_instances": len(rows),
            "target_met": len(rows) == n_instances,
            "attempts": attempts,
            "p_range": list(p_range),
            "rejection_counters": dict(counters),
            "source": SOURCE,
            "provenance": "separator_scaling_cell_generation_v0",
        },
        "instance_manifest": rows,
    }
