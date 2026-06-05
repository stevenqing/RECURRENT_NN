"""Graph k-coloring generator with controllable branch factor K."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import random

from tasks.oracle.dpll_oracle import DPLLOracle, OracleTrace


@dataclass
class GraphColoringInstance:
    n: int
    k: int
    edges: list[tuple[int, int]]
    dpll_backtrack_depth: int
    oracle_trace: OracleTrace


def generate_graph_coloring(n: int = 8, k: int = 3, edge_prob: float = 0.35, target_depth: Optional[int] = None, n_instances: int = 20, seed: int = 42) -> list[GraphColoringInstance]:
    rng = random.Random(seed)
    out = []
    for _ in range(n_instances * 100):
        if len(out) >= n_instances:
            break
        edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < edge_prob]
        constraints = [((u, v), lambda values: values[0] != values[1]) for u, v in edges]
        variables = list(range(n))
        trace = DPLLOracle().solve(variables, {v: set(range(1, k + 1)) for v in variables}, constraints)
        depth = trace.max_backtrack_depth
        if trace.solved and (target_depth is None or depth == target_depth):
            out.append(GraphColoringInstance(n, k, edges, depth, trace))
    return out
