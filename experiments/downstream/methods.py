"""Unified matched-compute methods for the controlled downstream coloring pilot.

The current backend is an explicitly labelled calibrated symbolic operator proxy.
It exercises search, coupling, frontier width, and v5-measured register reliability,
but is not eligible for a real-Qwen downstream headline claim.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import heapq
import math
import random
from typing import Any

from experiments.downstream.dist_coloring import Instance, edge_violations, solved


METHODS = {
    "A1_dfs_acache",
    "A2_tot",
    "A3_rap",
    "A4_beam_selfeval",
    "B1_self_consistency",
    "B2_best_of_n",
    "B3_universal_sc",
    "C1_debate",
    "C2_routing",
    "C3_saga_rollback",
    "C4_sync_local",
    "D1_reversible_redundancy",
    "D2_no_whiten",
    "D3_in_context",
    "D4_single",
}

# Empirical v5 full-D whitened one-register curve.
_LOAD_CURVE = [
    (48, 1.0), (55, 1.0), (64, 1.0), (74, 1.0), (77, 1.0),
    (86, 1.0), (96, 0.99), (103, 1.0), (128, 0.9766666666666667),
    (155, 0.91), (171, 0.8233333333333334), (192, 0.7433333333333333),
    (256, 0.6166666666666667), (384, 0.30333333333333334), (512, 0.23),
]
_V5_CONSENSUS = {
    384: [0.30333333333333334, 0.30333333333333334, 0.38666666666666666, 0.51, 0.58, 0.6833333333333333, 0.78, 0.84],
    512: [0.23, 0.23, 0.25666666666666665, 0.3333333333333333, 0.38666666666666666, 0.4533333333333333, 0.5233333333333333, 0.5966666666666667],
}


def _unit(*parts: Any) -> float:
    digest = hashlib.blake2b("::".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(2**64)


def _single_register_accuracy(load: int) -> float:
    load = int(load)
    if load <= _LOAD_CURVE[0][0]:
        return 1.0
    for (left_x, left_y), (right_x, right_y) in zip(_LOAD_CURVE, _LOAD_CURVE[1:]):
        if left_x <= load <= right_x:
            alpha = (load - left_x) / max(right_x - left_x, 1)
            return float(left_y + alpha * (right_y - left_y))
    return max(1.0 / max(load, 1), _LOAD_CURVE[-1][1] * _LOAD_CURVE[-1][0] / load)


def _consensus_accuracy(load: int, n_replicas: int) -> float:
    n_replicas = max(1, int(n_replicas))
    if load in _V5_CONSENSUS and n_replicas <= len(_V5_CONSENSUS[load]):
        return float(_V5_CONSENSUS[load][n_replicas - 1])
    p = _single_register_accuracy(load)
    threshold = n_replicas // 2 + 1
    majority = sum(math.comb(n_replicas, count) * p**count * (1 - p) ** (n_replicas - count) for count in range(threshold, n_replicas + 1))
    return max(p, min(1.0, majority))


@dataclass
class BudgetCounter:
    limit: int
    token_limit: int
    forwards: int = 0
    tokens: int = 0
    scorer_forwards: int = 0

    def spend(self, assigned: int, *, scorer: bool = False, multiplier: int = 1) -> bool:
        multiplier = max(1, int(multiplier))
        token_cost = multiplier * (32 + 2 * int(assigned))
        if self.forwards + multiplier > self.limit or self.tokens + token_cost > self.token_limit:
            return False
        self.forwards += multiplier
        self.tokens += token_cost
        self.scorer_forwards += multiplier * int(scorer)
        return True


State = tuple[int, ...]


def _adjacency(instance: Instance) -> list[set[int]]:
    adj = [set() for _ in range(instance.n)]
    for left, right in instance.edges:
        adj[left].add(right)
        adj[right].add(left)
    return adj


def _state_dict(state: State) -> dict[int, int]:
    return {vertex: color for vertex, color in enumerate(state) if color > 0}


def _valid_colors(instance: Instance, adj: list[set[int]], state: State, vertex: int) -> list[int]:
    blocked = {state[neighbor] for neighbor in adj[vertex] if state[neighbor] > 0}
    return [color for color in range(1, instance.k + 1) if color not in blocked]


def _next_vertex(instance: Instance, adj: list[set[int]], state: State) -> int | None:
    open_vertices = [vertex for vertex, color in enumerate(state) if color == 0]
    if not open_vertices:
        return None
    return max(open_vertices, key=lambda vertex: (len({state[n] for n in adj[vertex] if state[n] > 0}), len(adj[vertex]), -vertex))


def _child(state: State, vertex: int, color: int) -> State:
    values = list(state)
    values[vertex] = int(color)
    return tuple(values)


def _operator_color_order(instance: Instance, adj: list[set[int]], state: State, vertex: int, seed: int, replica: int = 0) -> list[int]:
    legal = _valid_colors(instance, adj, state, vertex)
    usage = Counter(color for color in state if color > 0)
    return sorted(legal, key=lambda color: (usage[color], _unit(instance.seed, seed, replica, state, vertex, color)))


def _state_score(instance: Instance, adj: list[set[int]], state: State, seed: int) -> float:
    assigned = sum(color > 0 for color in state)
    dead_domains = 0
    freedom = 0
    for vertex, color in enumerate(state):
        if color > 0:
            continue
        legal = _valid_colors(instance, adj, state, vertex)
        dead_domains += int(not legal)
        freedom += len(legal)
    return assigned * 10.0 + freedom * 0.05 - dead_domains * 100.0 + 1e-4 * _unit(instance.seed, seed, state)


def _read_select(candidates: list[tuple[float, State]], width: int, reliability: float, seed_parts: tuple[Any, ...]) -> list[State]:
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected: list[State] = []
    pool = list(candidates)
    for rank in range(min(int(width), len(pool))):
        if _unit(*seed_parts, rank) <= float(reliability):
            index = 0
        else:
            index = min(len(pool) - 1, 1 + int(_unit(*seed_parts, "miss", rank) * max(len(pool) - 1, 1)))
        selected.append(pool.pop(index)[1])
    return selected


def _best_available(instance: Instance, states: list[State]) -> dict[int, int]:
    if not states:
        return {}
    return _state_dict(max(states, key=lambda state: sum(color > 0 for color in state)))


def _beam_search(instance: Instance, counter: BudgetCounter, width: int, seed: int, reliability: float = 1.0, quadratic_scorer: bool = False) -> tuple[dict[int, int], int, str]:
    adj = _adjacency(instance)
    frontier: list[State] = [tuple(0 for _ in range(instance.n))]
    peak = 1
    level = 0
    while frontier and counter.forwards < counter.limit:
        candidates: list[tuple[float, State]] = []
        for state in frontier:
            vertex = _next_vertex(instance, adj, state)
            if vertex is None:
                return _state_dict(state), peak, "SOLVED"
            for color in _operator_color_order(instance, adj, state, vertex, seed):
                if not counter.spend(sum(value > 0 for value in state)):
                    return _best_available(instance, frontier), peak, "BUDGET_EXHAUSTED"
                child = _child(state, vertex, color)
                score_cost = len(frontier) if quadratic_scorer else 1
                if quadratic_scorer and not counter.spend(sum(value > 0 for value in child), scorer=True, multiplier=score_cost):
                    return _best_available(instance, frontier), peak, "BUDGET_EXHAUSTED"
                candidates.append((_state_score(instance, adj, child, seed), child))
        frontier = _read_select(candidates, width, reliability, (instance.instance_id, seed, level))
        peak = max(peak, len(frontier))
        level += 1
    return _best_available(instance, frontier), peak, "BUDGET_EXHAUSTED"


def _dfs(instance: Instance, counter: BudgetCounter, seed: int, restore_cost: int = 0) -> tuple[dict[int, int], int, str]:
    adj = _adjacency(instance)
    stack: list[State] = [tuple(0 for _ in range(instance.n))]
    peak = 1
    best: State = stack[0]
    while stack and counter.forwards < counter.limit:
        state = stack.pop()
        if sum(value > 0 for value in state) > sum(value > 0 for value in best):
            best = state
        vertex = _next_vertex(instance, adj, state)
        if vertex is None:
            return _state_dict(state), peak, "SOLVED"
        children = []
        for color in _operator_color_order(instance, adj, state, vertex, seed):
            if not counter.spend(sum(value > 0 for value in state)):
                return _state_dict(best), peak, "BUDGET_EXHAUSTED"
            children.append(_child(state, vertex, color))
        if restore_cost and len(children) > 1:
            counter.spend(sum(value > 0 for value in state), multiplier=restore_cost)
        stack.extend(reversed(children))
        peak = max(peak, len(stack))
    return _state_dict(best), peak, "BUDGET_EXHAUSTED"


def _best_first(instance: Instance, counter: BudgetCounter, seed: int) -> tuple[dict[int, int], int, str]:
    adj = _adjacency(instance)
    root = tuple(0 for _ in range(instance.n))
    heap: list[tuple[float, int, State]] = [(-_state_score(instance, adj, root, seed), 0, root)]
    serial = 1
    peak = 1
    best = root
    while heap and counter.forwards < counter.limit:
        _, _, state = heapq.heappop(heap)
        if sum(value > 0 for value in state) > sum(value > 0 for value in best):
            best = state
        vertex = _next_vertex(instance, adj, state)
        if vertex is None:
            return _state_dict(state), peak, "SOLVED"
        for color in _operator_color_order(instance, adj, state, vertex, seed):
            if not counter.spend(sum(value > 0 for value in state)):
                return _state_dict(best), peak, "BUDGET_EXHAUSTED"
            child = _child(state, vertex, color)
            heapq.heappush(heap, (-_state_score(instance, adj, child, seed), serial, child))
            serial += 1
        peak = max(peak, len(heap))
    return _state_dict(best), peak, "BUDGET_EXHAUSTED"


def _greedy_trajectory(instance: Instance, counter: BudgetCounter, seed: int, replica: int) -> dict[int, int]:
    adj = _adjacency(instance)
    state: State = tuple(0 for _ in range(instance.n))
    while counter.forwards < counter.limit:
        vertex = _next_vertex(instance, adj, state)
        if vertex is None:
            break
        order = _operator_color_order(instance, adj, state, vertex, seed, replica)
        if not counter.spend(sum(value > 0 for value in state)) or not order:
            break
        state = _child(state, vertex, order[0])
    coloring = _state_dict(state)
    rng = random.Random(instance.seed * 1009 + seed * 97 + replica)
    for vertex in range(instance.n):
        coloring.setdefault(vertex, rng.randint(1, instance.k))
    return coloring


def _repair(instance: Instance, coloring: dict[int, int], counter: BudgetCounter, seed: int) -> dict[int, int]:
    adj = _adjacency(instance)
    while counter.forwards < counter.limit:
        violated = [(left, right) for left, right in instance.edges if coloring.get(left) == coloring.get(right)]
        if not violated:
            break
        left, right = violated[int(_unit(instance.seed, seed, counter.forwards) * len(violated)) % len(violated)]
        vertex = max((left, right), key=lambda item: len(adj[item]))
        if not counter.spend(instance.n):
            break
        scores = []
        for color in range(1, instance.k + 1):
            conflicts = sum(coloring.get(neighbor) == color for neighbor in adj[vertex])
            scores.append((conflicts, _unit(instance.seed, seed, counter.forwards, vertex, color), color))
        coloring[vertex] = min(scores)[2]
    return coloring


def _ensemble(instance: Instance, budget: int, token_budget: int, N: int, seed: int, mode: str) -> tuple[dict[int, int], BudgetCounter, int, str]:
    counter = BudgetCounter(int(budget), int(token_budget))
    samples = []
    per_budget = max(1, int(budget) // max(int(N), 1))
    per_token_budget = max(32, int(token_budget) // max(int(N), 1))
    for replica in range(int(N)):
        local = BudgetCounter(
            min(per_budget, counter.limit - counter.forwards),
            max(0, min(per_token_budget, counter.token_limit - counter.tokens)),
        )
        coloring = _greedy_trajectory(instance, local, seed, replica)
        counter.forwards += local.forwards
        counter.tokens += local.tokens
        samples.append(coloring)
    if mode == "best":
        coloring = min(samples, key=lambda item: edge_violations(instance, item)[0])
        counter.spend(instance.n, scorer=True, multiplier=min(len(samples), max(0, counter.limit - counter.forwards)))
    else:
        coloring = {}
        for vertex in range(instance.n):
            votes = Counter(sample[vertex] for sample in samples)
            coloring[vertex] = votes.most_common(1)[0][0]
        if mode == "soft":
            coloring = _repair(instance, coloring, counter, seed)
    return coloring, counter, 0, "SOLVED" if solved(instance, coloring) else "UNSOLVED"


def _routing(instance: Instance, budget: int, token_budget: int, N: int, seed: int) -> tuple[dict[int, int], BudgetCounter, int, str]:
    counter = BudgetCounter(int(budget), int(token_budget))
    coloring: dict[int, int] = {}
    adj = _adjacency(instance)
    blocks = {block: [vertex for vertex in range(instance.n) if instance.partitions[vertex] == block] for block in range(instance.P)}
    for block in range(instance.P):
        for vertex in sorted(blocks[block], key=lambda item: -len(adj[item])):
            if not counter.spend(len(coloring)):
                break
            blocked = {coloring[neighbor] for neighbor in adj[vertex] if neighbor in coloring and instance.partitions[neighbor] == block}
            options = [color for color in range(1, instance.k + 1) if color not in blocked]
            coloring[vertex] = options[0] if options else 1
    coloring = _repair(instance, coloring, counter, seed)
    return coloring, counter, max(len(blocks[block]) for block in blocks), "SOLVED" if solved(instance, coloring) else "UNSOLVED"


def solve(instance, method, budget, N=None, w=None, seed=0, token_budget=None) -> dict:
    """Run one calibrated symbolic method under shared forward and token caps."""
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    budget = int(budget)
    token_budget = int(token_budget or budget * (32 + 2 * instance.n))
    N = max(1, int(N or 1))
    width = int(w or instance.frontier_width)
    if method == "A1_dfs_acache":
        counter = BudgetCounter(budget, token_budget); coloring, peak, status = _dfs(instance, counter, seed)
    elif method == "A2_tot":
        counter = BudgetCounter(budget, token_budget); coloring, peak, status = _beam_search(instance, counter, min(4, width), seed)
    elif method == "A3_rap":
        counter = BudgetCounter(budget, token_budget); coloring, peak, status = _best_first(instance, counter, seed)
    elif method == "A4_beam_selfeval":
        counter = BudgetCounter(budget, token_budget); coloring, peak, status = _beam_search(instance, counter, min(width, max(2, int(math.sqrt(budget)))), seed, quadratic_scorer=True)
    elif method == "B1_self_consistency":
        coloring, counter, peak, status = _ensemble(instance, budget, token_budget, N, seed, "vote")
    elif method == "B2_best_of_n":
        coloring, counter, peak, status = _ensemble(instance, budget, token_budget, N, seed, "best")
    elif method == "B3_universal_sc":
        coloring, counter, peak, status = _ensemble(instance, budget, token_budget, N, seed, "soft")
    elif method == "C1_debate":
        coloring, counter, peak, status = _ensemble(instance, budget, token_budget, N, seed, "vote"); coloring = _repair(instance, coloring, counter, seed + 31); status = "SOLVED" if solved(instance, coloring) else "UNSOLVED"
    elif method == "C2_routing":
        coloring, counter, peak, status = _routing(instance, budget, token_budget, N, seed)
    elif method == "C3_saga_rollback":
        counter = BudgetCounter(budget, token_budget); coloring, peak, status = _dfs(instance, counter, seed, restore_cost=1)
    elif method == "C4_sync_local":
        counter = BudgetCounter(budget, token_budget); coloring = {vertex: (vertex % instance.k) + 1 for vertex in range(instance.n)}; coloring = _repair(instance, coloring, counter, seed); peak = 0; status = "SOLVED" if solved(instance, coloring) else "UNSOLVED"
    else:
        if method == "D1_reversible_redundancy":
            reliability = _consensus_accuracy(width, N)
            restore_cost = 0
        elif method == "D2_no_whiten":
            reliability = 1.0 / max(width, 1)
            restore_cost = 0
        elif method == "D3_in_context":
            reliability = _single_register_accuracy(width)
            restore_cost = 1
        else:
            reliability = _single_register_accuracy(width)
            restore_cost = 0
        counter = BudgetCounter(budget, token_budget)
        if restore_cost:
            coloring, peak, status = _dfs(instance, counter, seed, restore_cost=restore_cost)
        else:
            coloring, peak, status = _beam_search(instance, counter, min(width, budget), seed, reliability=reliability)
    total_violations, cross_violations = edge_violations(instance, coloring)
    is_solved = solved(instance, coloring)
    full = len(coloring) == instance.n
    return {
        "method": method,
        "solved": bool(is_solved),
        "status": "SOLVED" if is_solved else status,
        "joint_consistency_rate": float(full and cross_violations == 0),
        "frontier_width_maintained": int(peak),
        "frontier_width_requested": int(width),
        "forwards": int(counter.forwards),
        "tokens": int(counter.tokens),
        "scorer_forwards": int(counter.scorer_forwards),
        "total_violations": int(total_violations),
        "cross_partition_violations": int(cross_violations),
        "coloring": {str(key): int(value) for key, value in coloring.items()},
        "budget": int(budget),
        "token_budget": int(token_budget),
        "N": int(N),
        "evaluation_mode": "calibrated_symbolic_operator_proxy_v6",
        "operator_backend": "shared_deterministic_symbolic_heuristic_with_v5_capacity_calibration",
        "headline_eligible": False,
    }
