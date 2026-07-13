"""Fixed-density long-partition-diameter graph-color substrate for SPEC v7-RPD."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
import random
from typing import Any, Mapping


@dataclass(frozen=True)
class ReferenceEngagement:
    solved: bool
    true_rollbacks: int
    candidate_checks: int
    completion_queries: int
    assignment: dict[int, int]


def partition_tree_edges(n_partitions: int, diameter: int) -> list[tuple[int, int]]:
    """Return a tree with fixed n-1 edges and exact requested diameter."""
    n_partitions = int(n_partitions)
    diameter = int(diameter)
    if n_partitions < 3 or not 2 <= diameter <= n_partitions - 1:
        raise ValueError("diameter must be in [2, n_partitions-1]")
    edges = [(node, node + 1) for node in range(diameter)]
    center = diameter // 2
    for node in range(diameter + 1, n_partitions):
        edges.append((center, node))
    if len(edges) != n_partitions - 1:
        raise AssertionError("tree edge count mismatch")
    return sorted(tuple(sorted(edge)) for edge in edges)


def graph_diameter(n_vertices: int, edges: list[tuple[int, int]]) -> int:
    adjacency = [set() for _ in range(int(n_vertices))]
    for left, right in edges:
        adjacency[int(left)].add(int(right))
        adjacency[int(right)].add(int(left))
    if any(not neighbors for neighbors in adjacency) and int(n_vertices) > 1:
        raise ValueError("diameter requires a connected graph")
    maximum = 0
    for source in range(int(n_vertices)):
        distance = [-1] * int(n_vertices)
        distance[source] = 0
        queue = deque([source])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if distance[neighbor] < 0:
                    distance[neighbor] = distance[current] + 1
                    queue.append(neighbor)
        if any(value < 0 for value in distance):
            raise ValueError("graph is disconnected")
        maximum = max(maximum, max(distance))
    return maximum


def _partition_order(n_partitions: int, tree_edges: list[tuple[int, int]]) -> list[int]:
    adjacency = [set() for _ in range(int(n_partitions))]
    for left, right in tree_edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    endpoints = sorted(node for node, neighbors in enumerate(adjacency) if len(neighbors) == 1)
    root = endpoints[0]
    order: list[int] = []
    queue = deque([root])
    seen = {root}
    while queue:
        current = queue.popleft()
        order.append(current)
        for neighbor in sorted(adjacency[current]):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return order


def generate_long_diameter_graph(
    *,
    base_seed: int,
    candidate_index: int,
    diameter: int,
    n_partitions: int = 17,
    vertices_per_partition: int = 4,
    k: int = 3,
    cross_edges_per_tree_edge: int = 2,
    split: str = "development",
) -> dict[str, Any]:
    if int(vertices_per_partition) != 4 or int(k) != 3:
        raise ValueError("v7 development generator is frozen to four vertices and k=3")
    rng = random.Random(
        int(base_seed) * 1_000_003
        + int(candidate_index) * 10_007
        + int(diameter) * 101
        + int(n_partitions) * 17
    )
    tree_edges = partition_tree_edges(int(n_partitions), int(diameter))
    partitions = [block for block in range(int(n_partitions)) for _ in range(int(vertices_per_partition))]
    planted: dict[int, int] = {}
    for block in range(int(n_partitions)):
        colors = [1, 2, 3]
        rng.shuffle(colors)
        pattern = [colors[0], colors[1], colors[2], colors[0]]
        for offset, color in enumerate(pattern):
            planted[block * int(vertices_per_partition) + offset] = int(color)

    edges: set[tuple[int, int]] = set()
    for block in range(int(n_partitions)):
        vertices = [block * int(vertices_per_partition) + offset for offset in range(int(vertices_per_partition))]
        for index, left in enumerate(vertices):
            for right in vertices[index + 1 :]:
                if planted[left] != planted[right]:
                    edges.add((left, right))
    for left_block, right_block in tree_edges:
        left_vertices = [left_block * int(vertices_per_partition) + offset for offset in range(int(vertices_per_partition))]
        right_vertices = [right_block * int(vertices_per_partition) + offset for offset in range(int(vertices_per_partition))]
        candidates = [
            (left, right)
            for left in left_vertices
            for right in right_vertices
            if planted[left] != planted[right]
        ]
        rng.shuffle(candidates)
        for left, right in candidates[: int(cross_edges_per_tree_edge)]:
            edges.add(tuple(sorted((left, right))))

    block_order = _partition_order(int(n_partitions), tree_edges)
    order = [
        block * int(vertices_per_partition) + offset
        for offset in range(int(vertices_per_partition))
        for block in block_order
    ]
    color_orders: dict[str, list[int]] = {}
    for vertex in range(int(n_partitions) * int(vertices_per_partition)):
        colors = [1, 2, 3]
        rng.shuffle(colors)
        color_orders[str(vertex)] = colors
    normalized_edges = sorted(tuple(sorted(edge)) for edge in edges)
    expected_local = int(n_partitions) * 5
    expected_cross = (int(n_partitions) - 1) * int(cross_edges_per_tree_edge)
    if len(normalized_edges) != expected_local + expected_cross:
        raise AssertionError("fixed-density graph edge count mismatch")
    instance_id = f"v7_{split}_s{int(base_seed)}_d{int(diameter)}_{int(candidate_index):06d}"
    return {
        "schema": "recurrent_signal_long_diameter_graph_v1",
        "instance_id": instance_id,
        "split": str(split),
        "base_seed": int(base_seed),
        "candidate_index": int(candidate_index),
        "n_partitions": int(n_partitions),
        "vertices_per_partition": int(vertices_per_partition),
        "n_vertices": int(n_partitions) * int(vertices_per_partition),
        "k": int(k),
        "partition_tree_edges": [list(edge) for edge in tree_edges],
        "partition_diameter": graph_diameter(int(n_partitions), tree_edges),
        "partitions": partitions,
        "edges": [list(edge) for edge in normalized_edges],
        "n_edges": len(normalized_edges),
        "n_local_edges": expected_local,
        "n_cross_edges": expected_cross,
        "order": order,
        "color_orders": color_orders,
        "planted_assignment": {str(key): int(value) for key, value in planted.items()},
    }


def public_instance(instance: dict[str, Any]) -> dict[str, Any]:
    output = {key: value for key, value in instance.items() if key != "planted_assignment"}
    output["planted_assignment_removed"] = True
    return output


def verify_coloring(instance: Mapping[str, Any], assignment: Mapping[int, int]) -> bool:
    n = int(instance["n_vertices"])
    k = int(instance["k"])
    return (
        len(assignment) == n
        and all(int(assignment.get(vertex, 0)) in range(1, k + 1) for vertex in range(n))
        and all(int(assignment[int(left)]) != int(assignment[int(right)]) for left, right in instance["edges"])
    )


def canonical_graph_hash(instance: Mapping[str, Any]) -> str:
    payload = {
        "n_vertices": int(instance["n_vertices"]),
        "k": int(instance["k"]),
        "partition_tree_edges": instance["partition_tree_edges"],
        "partitions": instance["partitions"],
        "edges": instance["edges"],
        "order": instance["order"],
        "color_orders": instance["color_orders"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class GraphCompletionOracle:
    """Exact completion oracle for partial graph colorings, with memoization."""

    def __init__(self, instance: Mapping[str, Any]):
        self.n = int(instance["n_vertices"])
        self.k = int(instance["k"])
        self.adjacency = [set() for _ in range(self.n)]
        for left, right in instance["edges"]:
            self.adjacency[int(left)].add(int(right))
            self.adjacency[int(right)].add(int(left))
        self.nodes_expanded = 0
        self.cache_hits = 0
        self._memo: dict[bytes, bool] = {}

    def _direct_valid(self, state: tuple[int, ...]) -> bool:
        for left in range(self.n):
            color = state[left]
            if color == 0:
                continue
            if any(right > left and state[right] == color for right in self.adjacency[left]):
                return False
        return True

    def _complete(self, state: tuple[int, ...]) -> bool:
        state_key = bytes(state)
        if state_key in self._memo:
            self.cache_hits += 1
            return self._memo[state_key]
        self.nodes_expanded += 1
        if not self._direct_valid(state):
            self._memo[state_key] = False
            return False
        if all(value != 0 for value in state):
            self._memo[state_key] = True
            return True
        best_vertex = -1
        best_domain: list[int] | None = None
        for vertex, value in enumerate(state):
            if value != 0:
                continue
            blocked = {state[neighbor] for neighbor in self.adjacency[vertex] if state[neighbor] != 0}
            domain = [color for color in range(1, self.k + 1) if color not in blocked]
            if not domain:
                self._memo[state_key] = False
                return False
            if best_domain is None or len(domain) < len(best_domain):
                best_vertex = vertex
                best_domain = domain
                if len(domain) == 1:
                    break
        assert best_domain is not None and best_vertex >= 0
        for color in best_domain:
            updated = list(state)
            updated[best_vertex] = int(color)
            if self._complete(tuple(updated)):
                self._memo[state_key] = True
                return True
        self._memo[state_key] = False
        return False

    def is_completable(self, assignment: Mapping[int, int]) -> bool:
        state = tuple(int(assignment.get(vertex, 0)) for vertex in range(self.n))
        return self._complete(state)

    def cache_info(self) -> dict[str, int]:
        return {
            "hits": int(self.cache_hits),
            "misses": int(self.nodes_expanded),
            "size": len(self._memo),
            "nodes_expanded": int(self.nodes_expanded),
        }


def _direct_color_valid(instance: Mapping[str, Any], assignment: Mapping[int, int], vertex: int, color: int) -> bool:
    for left, right in instance["edges"]:
        left = int(left)
        right = int(right)
        if left == int(vertex) and int(assignment.get(right, 0)) == int(color):
            return False
        if right == int(vertex) and int(assignment.get(left, 0)) == int(color):
            return False
    return True


def reference_engagement(instance: Mapping[str, Any]) -> ReferenceEngagement:
    """Oracle-signal fixed-order trace used only for environment selection."""
    oracle = GraphCompletionOracle(instance)
    assignment: dict[int, int] = {}
    true_rollbacks = 0
    candidate_checks = 0
    for raw_vertex in instance["order"]:
        vertex = int(raw_vertex)
        committed = False
        for raw_color in instance["color_orders"][str(vertex)]:
            color = int(raw_color)
            if not _direct_color_valid(instance, assignment, vertex, color):
                continue
            candidate_checks += 1
            proposal = dict(assignment)
            proposal[vertex] = color
            if not oracle.is_completable(proposal):
                true_rollbacks += 1
                continue
            assignment = proposal
            committed = True
            break
        if not committed:
            return ReferenceEngagement(False, true_rollbacks, candidate_checks, oracle.cache_info()["misses"], assignment)
    return ReferenceEngagement(
        verify_coloring(instance, assignment),
        true_rollbacks,
        candidate_checks,
        oracle.cache_info()["misses"],
        assignment,
    )
