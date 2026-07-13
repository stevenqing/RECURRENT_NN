"""Synchronous Jacobi-style recurrent parallel graph-color reasoning engine."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import product
import hashlib
import json
from typing import Any, Mapping

from experiments.signal.detector import DeterministicNoisyDetector
from experiments.signal.long_diameter_graph import verify_coloring


MODES = (
    "recurrent_parallel",
    "state_reset",
    "shuffled_message",
    "no_message",
    "sequential_sharded",
)

COMPRESSED_MODES = (
    "full_message",
    "compressed_persistent",
    "compressed_cache_reset",
    "compressed_all_reset",
    "compressed_shuffled",
    "no_message",
)

SIGNAL_SYSTEMS = ("R_exact", "R_soft2", "R_commit")


@dataclass
class LocalAgentState:
    agent_id: int
    vertices: tuple[int, ...]
    candidates: tuple[tuple[int, ...], ...]
    candidate_index: int = 0
    tie_cursor: int = 0
    state_changes: int = 0


def _adjacency(n: int, edges: list[list[int]]) -> list[set[int]]:
    output = [set() for _ in range(int(n))]
    for left, right in edges:
        output[int(left)].add(int(right))
        output[int(right)].add(int(left))
    return output


def _root_tree(n_agents: int, tree_edges: list[list[int]], root: int) -> tuple[dict[int, int | None], dict[int, list[int]], dict[int, int], list[int]]:
    adjacency = [set() for _ in range(int(n_agents))]
    for left, right in tree_edges:
        adjacency[int(left)].add(int(right))
        adjacency[int(right)].add(int(left))
    parent: dict[int, int | None] = {int(root): None}
    depth = {int(root): 0}
    children = {agent: [] for agent in range(int(n_agents))}
    order: list[int] = []
    queue = deque([int(root)])
    while queue:
        current = queue.popleft()
        order.append(current)
        for neighbor in sorted(adjacency[current]):
            if neighbor in parent:
                continue
            parent[neighbor] = current
            depth[neighbor] = depth[current] + 1
            children[current].append(neighbor)
            queue.append(neighbor)
    if len(order) != int(n_agents):
        raise ValueError("partition tree is disconnected")
    return parent, children, depth, order


def _enumerate_local_candidates(
    vertices: tuple[int, ...],
    k: int,
    adjacency: list[set[int]],
) -> tuple[tuple[int, ...], ...]:
    vertex_set = set(vertices)
    candidates = []
    for values in product(range(1, int(k) + 1), repeat=len(vertices)):
        assignment = dict(zip(vertices, values))
        valid = all(
            assignment[left] != assignment[right]
            for left in vertices
            for right in adjacency[left]
            if right in vertex_set and left < right
        )
        if valid:
            candidates.append(tuple(map(int, values)))
    if not candidates:
        raise ValueError("agent has no locally valid coloring")
    return tuple(sorted(candidates))


def _candidate_assignment(state: LocalAgentState, candidate_index: int | None = None) -> dict[int, int]:
    index = state.candidate_index if candidate_index is None else int(candidate_index)
    return {vertex: int(color) for vertex, color in zip(state.vertices, state.candidates[index])}


def _candidate_cost(
    state: LocalAgentState,
    candidate_index: int,
    remote_message: Mapping[int, int],
    adjacency: list[set[int]],
) -> int:
    assignment = _candidate_assignment(state, candidate_index)
    return sum(
        int(color == int(remote_message[neighbor]))
        for vertex, color in assignment.items()
        for neighbor in adjacency[vertex]
        if neighbor in remote_message
    )


def _local_candidate_valid(
    state: LocalAgentState,
    candidate_index: int,
    adjacency: list[set[int]],
) -> bool:
    assignment = _candidate_assignment(state, candidate_index)
    vertex_set = set(state.vertices)
    return all(
        assignment[left] != assignment[right]
        for left in state.vertices
        for right in adjacency[left]
        if right in vertex_set and left < right
    )


def _propose(
    state: LocalAgentState,
    remote_message: Mapping[int, int],
    adjacency: list[set[int]],
    *,
    reset_state: bool,
) -> tuple[int, int]:
    current = 0 if reset_state else int(state.candidate_index)
    tie_cursor = 0 if reset_state else int(state.tie_cursor)
    costs = [
        _candidate_cost(state, index, remote_message, adjacency)
        for index in range(len(state.candidates))
    ]
    minimum = min(costs)
    minima = [index for index, cost in enumerate(costs) if cost == minimum]
    if not reset_state and current in minima:
        return current, tie_cursor
    selected = minima[tie_cursor % len(minima)]
    return int(selected), int(tie_cursor + 1)


def _message_for_child(
    parent_state: LocalAgentState,
    child_state: LocalAgentState,
    adjacency: list[set[int]],
) -> dict[int, int]:
    parent_assignment = _candidate_assignment(parent_state)
    child_vertices = set(child_state.vertices)
    return {
        vertex: color
        for vertex, color in parent_assignment.items()
        if any(neighbor in child_vertices for neighbor in adjacency[vertex])
    }


def _state_digest(states: dict[int, LocalAgentState], incoming: dict[int, dict[int, int]]) -> str:
    payload = {
        "states": {
            str(agent): {
                "candidate_index": int(state.candidate_index),
                "tie_cursor": int(state.tie_cursor),
            }
            for agent, state in sorted(states.items())
        },
        "incoming": {
            str(agent): [[int(vertex), int(color)] for vertex, color in sorted(message.items())]
            for agent, message in sorted(incoming.items())
        },
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run_recurrent_parallel(
    instance: Mapping[str, Any],
    *,
    mode: str,
    round_cap: int,
    root_agent: int = 0,
) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unknown recurrent mode: {mode}")
    n_agents = int(instance["n_partitions"])
    n_vertices = int(instance["n_vertices"])
    k = int(instance["k"])
    partitions = [int(value) for value in instance["partitions"]]
    adjacency = _adjacency(n_vertices, list(instance["edges"]))
    parent, children, depth, root_order = _root_tree(
        n_agents,
        list(instance["partition_tree_edges"]),
        int(root_agent),
    )
    states: dict[int, LocalAgentState] = {}
    for agent in range(n_agents):
        vertices = tuple(vertex for vertex, owner in enumerate(partitions) if owner == agent)
        states[agent] = LocalAgentState(
            agent_id=agent,
            vertices=vertices,
            candidates=_enumerate_local_candidates(vertices, k, adjacency),
        )
    local_candidates_valid = all(
        all(_local_candidate_valid(state, index, adjacency) for index in range(len(state.candidates)))
        for state in states.values()
    )

    incoming: dict[int, dict[int, int]] = {agent: {} for agent in states}
    rounds_executed = 0
    agent_updates = 0
    state_changes = 0
    messages_generated = 0
    messages_delivered = 0
    maximum_message_age = 0
    same_round_cross_agent_reads = 0
    snapshot_digests: list[str] = []
    solved = False
    final_assignment: dict[int, int] = {}
    final_cross_conflicts = 0

    for round_index in range(int(round_cap)):
        rounds_executed += 1
        if mode == "sequential_sharded":
            for agent in root_order:
                state = states[agent]
                if parent[agent] is None or mode == "no_message":
                    message: dict[int, int] = {}
                else:
                    message = _message_for_child(states[int(parent[agent])], state, adjacency)
                    messages_generated += 1
                    messages_delivered += 1
                    same_round_cross_agent_reads += 1
                selected, tie_cursor = _propose(
                    state,
                    message,
                    adjacency,
                    reset_state=False,
                )
                agent_updates += 1
                if selected != state.candidate_index:
                    state.state_changes += 1
                    state_changes += 1
                state.candidate_index = selected
                state.tie_cursor = tie_cursor
        else:
            snapshot_digests.append(_state_digest(states, incoming))
            proposals: dict[int, tuple[int, int]] = {}
            for agent, state in states.items():
                message = {} if mode == "no_message" else dict(incoming[agent])
                proposals[agent] = _propose(
                    state,
                    message,
                    adjacency,
                    reset_state=mode == "state_reset",
                )
                agent_updates += 1
            for agent, (selected, tie_cursor) in proposals.items():
                state = states[agent]
                if selected != state.candidate_index:
                    state.state_changes += 1
                    state_changes += 1
                state.candidate_index = int(selected)
                state.tie_cursor = int(tie_cursor)
            generated: dict[int, dict[int, int]] = {agent: {} for agent in states}
            for child, parent_agent in parent.items():
                if parent_agent is None:
                    continue
                generated[child] = _message_for_child(states[int(parent_agent)], states[child], adjacency)
                messages_generated += 1
            if mode == "no_message":
                incoming = {agent: {} for agent in states}
            elif mode == "shuffled_message":
                recipients = sorted(agent for agent in states if parent[agent] is not None)
                shifted = recipients[1:] + recipients[:1]
                incoming = {agent: {} for agent in states}
                for original, recipient in zip(recipients, shifted):
                    incoming[recipient] = dict(generated[original])
                    messages_delivered += 1
                    maximum_message_age = max(maximum_message_age, 1)
            else:
                incoming = generated
                delivered = sum(parent_agent is not None for parent_agent in parent.values())
                messages_delivered += int(delivered)
                maximum_message_age = max(maximum_message_age, int(bool(delivered)))

        final_assignment = {
            vertex: color
            for state in states.values()
            for vertex, color in _candidate_assignment(state).items()
        }
        final_cross_conflicts = sum(
            int(final_assignment[int(left)] == final_assignment[int(right)])
            for left, right in instance["edges"]
            if partitions[int(left)] != partitions[int(right)]
        )
        solved = verify_coloring(instance, final_assignment)
        if solved:
            break

    idealized_parallel_critical_path = rounds_executed if mode != "sequential_sharded" else rounds_executed * n_agents
    sequential_local_update_critical_path = rounds_executed * n_agents
    return {
        "instance_id": str(instance["instance_id"]),
        "partition_diameter": int(instance["partition_diameter"]),
        "mode": mode,
        "round_cap": int(round_cap),
        "solved": bool(solved),
        "status": "SOLVED" if solved else "ROUND_CAP",
        "rounds_executed": rounds_executed,
        "agent_updates": agent_updates,
        "state_changes": state_changes,
        "messages_generated": messages_generated,
        "messages_delivered": messages_delivered,
        "maximum_message_age": maximum_message_age,
        "same_round_cross_agent_reads": same_round_cross_agent_reads,
        "idealized_parallel_critical_path": idealized_parallel_critical_path,
        "sequential_local_update_critical_path": sequential_local_update_critical_path,
        "final_cross_conflicts": final_cross_conflicts,
        "local_candidates_valid": local_candidates_valid,
        "official_verification": bool(solved),
        "planted_assignment_used": False,
        "snapshot_digests": snapshot_digests[:4],
        "candidate_counts": {str(agent): len(state.candidates) for agent, state in states.items()},
        "tree_max_depth": max(depth.values()),
        "message_semantics": "same_round" if mode == "sequential_sharded" else "one_round_delayed",
    }


def _balanced_groups(order: list[int], width: int) -> tuple[dict[int, tuple[int, ...]], dict[int, int]]:
    if not 1 <= int(width) <= len(order):
        raise ValueError("width must lie in [1, number of base partitions]")
    base, remainder = divmod(len(order), int(width))
    groups: dict[int, tuple[int, ...]] = {}
    owner: dict[int, int] = {}
    cursor = 0
    for agent in range(int(width)):
        size = base + int(agent < remainder)
        members = tuple(order[cursor : cursor + size])
        cursor += size
        groups[agent] = members
        for partition in members:
            owner[int(partition)] = agent
    if cursor != len(order):
        raise AssertionError("balanced grouping did not consume all partitions")
    return groups, owner


def _simple_graph_diameter(n_nodes: int, edges: set[tuple[int, int]]) -> int:
    if int(n_nodes) <= 1:
        return 0
    adjacency = [set() for _ in range(int(n_nodes))]
    for left, right in edges:
        adjacency[int(left)].add(int(right))
        adjacency[int(right)].add(int(left))
    maximum = 0
    for source in range(int(n_nodes)):
        distances = [-1] * int(n_nodes)
        distances[source] = 0
        queue = deque([source])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if distances[neighbor] < 0:
                    distances[neighbor] = distances[current] + 1
                    queue.append(neighbor)
        if any(value < 0 for value in distances):
            raise ValueError("induced execution-agent graph is disconnected")
        maximum = max(maximum, max(distances))
    return maximum


def run_fixed_budget_width(
    instance: Mapping[str, Any],
    *,
    width: int,
    budget: int,
    root_agent: int = 0,
) -> dict[str, Any]:
    """Run fixed B=M*T with one base-partition update per agent call."""
    if int(budget) % int(width) != 0:
        raise ValueError("budget must be divisible by width")
    round_cap = int(budget) // int(width)
    n_base = int(instance["n_partitions"])
    n_vertices = int(instance["n_vertices"])
    k = int(instance["k"])
    partitions = [int(value) for value in instance["partitions"]]
    adjacency = _adjacency(n_vertices, list(instance["edges"]))
    parent, _children, _depth, root_order = _root_tree(
        n_base,
        list(instance["partition_tree_edges"]),
        int(root_agent),
    )
    groups, group_owner = _balanced_groups(root_order, int(width))
    states: dict[int, LocalAgentState] = {}
    for partition in range(n_base):
        vertices = tuple(vertex for vertex, owner in enumerate(partitions) if owner == partition)
        states[partition] = LocalAgentState(
            agent_id=partition,
            vertices=vertices,
            candidates=_enumerate_local_candidates(vertices, k, adjacency),
        )
    local_candidates_valid = all(
        all(_local_candidate_valid(state, index, adjacency) for index in range(len(state.candidates)))
        for state in states.values()
    )

    execution_edges = {
        tuple(sorted((group_owner[int(left)], group_owner[int(right)])))
        for left, right in instance["partition_tree_edges"]
        if group_owner[int(left)] != group_owner[int(right)]
    }
    incoming: dict[int, dict[int, int]] = {partition: {} for partition in states}
    rounds_executed = 0
    agent_calls = 0
    primitive_updates = 0
    state_changes = 0
    messages_generated = 0
    messages_delivered = 0
    maximum_message_age = 0
    same_round_cross_agent_reads = 0
    internal_snapshot_reads = 0
    solved = False
    final_assignment: dict[int, int] = {}
    final_cross_conflicts = 0

    for round_index in range(round_cap):
        rounds_executed += 1
        proposals: dict[int, tuple[int, int]] = {}
        for execution_agent, members in groups.items():
            selected_partition = members[round_index % len(members)]
            state = states[selected_partition]
            parent_partition = parent[selected_partition]
            if parent_partition is None:
                message: dict[int, int] = {}
            elif group_owner[int(parent_partition)] == execution_agent:
                message = _message_for_child(states[int(parent_partition)], state, adjacency)
                internal_snapshot_reads += 1
            else:
                message = dict(incoming[selected_partition])
            proposals[selected_partition] = _propose(
                state,
                message,
                adjacency,
                reset_state=False,
            )
            agent_calls += 1
            primitive_updates += 1
        for partition, (selected, tie_cursor) in proposals.items():
            state = states[partition]
            if int(selected) != int(state.candidate_index):
                state.state_changes += 1
                state_changes += 1
            state.candidate_index = int(selected)
            state.tie_cursor = int(tie_cursor)

        generated: dict[int, dict[int, int]] = {partition: {} for partition in states}
        for child, parent_partition in parent.items():
            if parent_partition is None or group_owner[child] == group_owner[int(parent_partition)]:
                continue
            generated[child] = _message_for_child(states[int(parent_partition)], states[child], adjacency)
            messages_generated += 1
        incoming = generated
        delivered = sum(bool(message) for message in incoming.values())
        messages_delivered += int(delivered)
        maximum_message_age = max(maximum_message_age, int(bool(delivered)))

        final_assignment = {
            vertex: color
            for state in states.values()
            for vertex, color in _candidate_assignment(state).items()
        }
        final_cross_conflicts = sum(
            int(final_assignment[int(left)] == final_assignment[int(right)])
            for left, right in instance["edges"]
            if partitions[int(left)] != partitions[int(right)]
        )
        solved = verify_coloring(instance, final_assignment)
        if solved:
            break

    group_sizes = {str(agent): len(members) for agent, members in groups.items()}
    context_variables = {str(agent): len(members) * int(instance["vertices_per_partition"]) for agent, members in groups.items()}
    context_variables_per_round = sum(context_variables.values())
    context_squared_per_round = sum(value * value for value in context_variables.values())
    return {
        "instance_id": str(instance["instance_id"]),
        "partition_diameter": int(instance["partition_diameter"]),
        "mode": "fixed_budget_recurrent",
        "width": int(width),
        "budget_cap": int(budget),
        "round_cap": round_cap,
        "configured_MT": int(width) * round_cap,
        "solved": bool(solved),
        "status": "SOLVED" if solved else "ROUND_CAP",
        "rounds_executed": rounds_executed,
        "agent_calls": agent_calls,
        "primitive_updates": primitive_updates,
        "state_changes": state_changes,
        "messages_generated": messages_generated,
        "messages_delivered": messages_delivered,
        "maximum_message_age": maximum_message_age,
        "same_round_cross_agent_reads": same_round_cross_agent_reads,
        "internal_snapshot_reads": internal_snapshot_reads,
        "idealized_parallel_critical_path": rounds_executed,
        "sequential_local_update_critical_path": agent_calls,
        "final_cross_conflicts": final_cross_conflicts,
        "local_candidates_valid": local_candidates_valid,
        "official_verification": bool(solved),
        "planted_assignment_used": False,
        "group_sizes": group_sizes,
        "context_variables": context_variables,
        "max_context_variables": max(context_variables.values()),
        "mean_context_variables": sum(context_variables.values()) / len(context_variables),
        "context_variables_per_round": context_variables_per_round,
        "context_squared_per_round": context_squared_per_round,
        "total_context_variable_updates": rounds_executed * context_variables_per_round,
        "quadratic_attention_proxy": rounds_executed * context_squared_per_round,
        "cross_agent_partition_edges": len(execution_edges),
        "internal_partition_edges": (n_base - 1) - len(execution_edges),
        "execution_agent_graph_diameter": _simple_graph_diameter(int(width), execution_edges),
        "message_semantics": "one_round_delayed_cross_agent_and_round_snapshot_internal",
    }


def run_compressed_recurrence(
    instance: Mapping[str, Any],
    *,
    mode: str,
    round_cap: int,
    cache_capacity: int = 2,
    root_agent: int = 0,
) -> dict[str, Any]:
    """Run P0 recurrence with full or one-fact compressed parent messages."""
    if mode not in COMPRESSED_MODES:
        raise ValueError(f"unknown compressed recurrence mode: {mode}")
    n_agents = int(instance["n_partitions"])
    n_vertices = int(instance["n_vertices"])
    k = int(instance["k"])
    partitions = [int(value) for value in instance["partitions"]]
    adjacency = _adjacency(n_vertices, list(instance["edges"]))
    parent, _children, _depth, _root_order = _root_tree(
        n_agents,
        list(instance["partition_tree_edges"]),
        int(root_agent),
    )
    states: dict[int, LocalAgentState] = {}
    for agent in range(n_agents):
        vertices = tuple(vertex for vertex, owner in enumerate(partitions) if owner == agent)
        states[agent] = LocalAgentState(
            agent_id=agent,
            vertices=vertices,
            candidates=_enumerate_local_candidates(vertices, k, adjacency),
        )
    local_candidates_valid = all(
        all(_local_candidate_valid(state, index, adjacency) for index in range(len(state.candidates)))
        for state in states.values()
    )

    message_cache: dict[int, dict[int, int]] = {agent: {} for agent in states}
    rounds_executed = 0
    agent_updates = 0
    state_changes = 0
    message_facts_generated = 0
    message_facts_delivered = 0
    full_message_fact_equivalent = 0
    cache_inserts = 0
    cache_updates = 0
    cache_evictions = 0
    max_cache_facts = 0
    max_fragment_facts = 0
    fragment_size_violations = 0
    same_round_cross_agent_reads = 0
    hidden_full_message_reads = 0
    maximum_message_age = 0
    solved = False
    final_assignment: dict[int, int] = {}
    final_cross_conflicts = 0

    for round_index in range(int(round_cap)):
        rounds_executed += 1
        proposals: dict[int, tuple[int, int]] = {}
        for agent, state in states.items():
            proposals[agent] = _propose(
                state,
                dict(message_cache[agent]),
                adjacency,
                reset_state=mode == "compressed_all_reset",
            )
            agent_updates += 1
        for agent, (selected, tie_cursor) in proposals.items():
            state = states[agent]
            if int(selected) != int(state.candidate_index):
                state.state_changes += 1
                state_changes += 1
            state.candidate_index = int(selected)
            state.tie_cursor = int(tie_cursor)

        full_messages: dict[int, dict[int, int]] = {agent: {} for agent in states}
        for child, parent_agent in parent.items():
            if parent_agent is None:
                continue
            full_messages[child] = _message_for_child(states[int(parent_agent)], states[child], adjacency)
        full_message_fact_equivalent += sum(len(message) for message in full_messages.values())

        if mode == "full_message":
            message_cache = {agent: dict(message) for agent, message in full_messages.items()}
            facts = sum(len(message) for message in message_cache.values())
            message_facts_generated += facts
            message_facts_delivered += facts
            max_cache_facts = max(max_cache_facts, max((len(cache) for cache in message_cache.values()), default=0))
            maximum_message_age = max(maximum_message_age, int(facts > 0))
        elif mode == "no_message":
            message_cache = {agent: {} for agent in states}
        else:
            fragments: dict[int, dict[int, int]] = {agent: {} for agent in states}
            for child, message in full_messages.items():
                if not message:
                    continue
                ordered = sorted(message.items())
                vertex, color = ordered[round_index % len(ordered)]
                fragments[child] = {int(vertex): int(color)}
                max_fragment_facts = max(max_fragment_facts, len(fragments[child]))
                fragment_size_violations += int(len(fragments[child]) != 1)
                message_facts_generated += 1
            if mode == "compressed_shuffled":
                recipients = sorted(agent for agent in states if parent[agent] is not None)
                shifted = recipients[1:] + recipients[:1]
                delivered_fragments = {agent: {} for agent in states}
                for source, recipient in zip(recipients, shifted):
                    delivered_fragments[recipient] = dict(fragments[source])
            else:
                delivered_fragments = fragments

            if mode in {"compressed_cache_reset", "compressed_all_reset"}:
                message_cache = {agent: dict(delivered_fragments[agent]) for agent in states}
                message_facts_delivered += sum(len(message) for message in message_cache.values())
                cache_inserts += sum(len(message) for message in message_cache.values())
            else:
                for agent, fragment in delivered_fragments.items():
                    for vertex, color in fragment.items():
                        if vertex in message_cache[agent]:
                            cache_updates += 1
                            message_cache[agent][vertex] = int(color)
                        else:
                            if len(message_cache[agent]) >= int(cache_capacity):
                                oldest = next(iter(message_cache[agent]))
                                message_cache[agent].pop(oldest)
                                cache_evictions += 1
                            message_cache[agent][int(vertex)] = int(color)
                            cache_inserts += 1
                        message_facts_delivered += 1
            max_cache_facts = max(max_cache_facts, max((len(cache) for cache in message_cache.values()), default=0))
            maximum_message_age = max(maximum_message_age, int(any(delivered_fragments.values())))

        final_assignment = {
            vertex: color
            for state in states.values()
            for vertex, color in _candidate_assignment(state).items()
        }
        final_cross_conflicts = sum(
            int(final_assignment[int(left)] == final_assignment[int(right)])
            for left, right in instance["edges"]
            if partitions[int(left)] != partitions[int(right)]
        )
        solved = verify_coloring(instance, final_assignment)
        if solved:
            break

    compression_ratio = (
        message_facts_delivered / full_message_fact_equivalent
        if full_message_fact_equivalent
        else 0.0
    )
    return {
        "instance_id": str(instance["instance_id"]),
        "partition_diameter": int(instance["partition_diameter"]),
        "mode": mode,
        "round_cap": int(round_cap),
        "solved": bool(solved),
        "status": "SOLVED" if solved else "ROUND_CAP",
        "rounds_executed": rounds_executed,
        "agent_updates": agent_updates,
        "state_changes": state_changes,
        "message_facts_generated": message_facts_generated,
        "message_facts_delivered": message_facts_delivered,
        "full_message_fact_equivalent": full_message_fact_equivalent,
        "compression_ratio": compression_ratio,
        "cache_capacity": int(cache_capacity),
        "max_cache_facts": max_cache_facts,
        "cache_inserts": cache_inserts,
        "cache_updates": cache_updates,
        "cache_evictions": cache_evictions,
        "max_fragment_facts": max_fragment_facts,
        "fragment_size_violations": fragment_size_violations,
        "maximum_message_age": maximum_message_age,
        "same_round_cross_agent_reads": same_round_cross_agent_reads,
        "hidden_full_message_reads": hidden_full_message_reads,
        "idealized_parallel_critical_path": rounds_executed,
        "sequential_local_update_critical_path": agent_updates,
        "final_cross_conflicts": final_cross_conflicts,
        "local_candidates_valid": local_candidates_valid,
        "official_verification": bool(solved),
        "planted_assignment_used": False,
        "message_semantics": "one_round_delayed",
    }


def run_noisy_recurrent_correction(
    instance: Mapping[str, Any],
    *,
    system: str,
    eta_fp: float,
    round_cap: int,
    eta_fn: float = 0.0,
    noise_seed: int = 20260712,
    root_agent: int = 0,
    confirmation_hits: int | None = None,
) -> dict[str, Any]:
    """Inject a noisy correction signal into full-message recurrent updates."""
    if system not in SIGNAL_SYSTEMS and system != "R_adaptive":
        raise ValueError(f"unknown recurrent signal system: {system}")
    required_hits = int(confirmation_hits) if system == "R_adaptive" else (2 if system == "R_soft2" else 1)
    if required_hits < 1:
        raise ValueError("confirmation_hits must be positive")
    n_agents = int(instance["n_partitions"])
    n_vertices = int(instance["n_vertices"])
    k = int(instance["k"])
    partitions = [int(value) for value in instance["partitions"]]
    adjacency = _adjacency(n_vertices, list(instance["edges"]))
    parent, _children, _depth, _root_order = _root_tree(
        n_agents,
        list(instance["partition_tree_edges"]),
        int(root_agent),
    )
    states: dict[int, LocalAgentState] = {}
    for agent in range(n_agents):
        vertices = tuple(vertex for vertex, owner in enumerate(partitions) if owner == agent)
        states[agent] = LocalAgentState(
            agent_id=agent,
            vertices=vertices,
            candidates=_enumerate_local_candidates(vertices, k, adjacency),
        )
    local_candidates_valid = all(
        all(_local_candidate_valid(state, index, adjacency) for index in range(len(state.candidates)))
        for state in states.values()
    )
    detector = DeterministicNoisyDetector(float(eta_fp), float(eta_fn), int(noise_seed))
    incoming: dict[int, dict[int, int]] = {agent: {} for agent in states}
    rounds_executed = 0
    agent_updates = 0
    state_changes = 0
    messages_generated = 0
    messages_delivered = 0
    detector_queries = 0
    observed_positive_signals = 0
    true_correction_exposures = 0
    true_corrections_executed = 0
    over_corrections = 0
    false_positives = 0
    false_negatives = 0
    candidate_corrections = 0
    correct_state_destroyed = 0
    same_round_cross_agent_reads = 0
    maximum_message_age = 0
    solved = False
    final_assignment: dict[int, int] = {}
    final_cross_conflicts = 0

    for round_index in range(int(round_cap)):
        rounds_executed += 1
        proposals: dict[int, tuple[int, int]] = {}
        for agent, state in states.items():
            message = dict(incoming[agent])
            if parent[agent] is None or not message or system == "R_commit":
                proposals[agent] = (int(state.candidate_index), int(state.tie_cursor))
                agent_updates += 1
                continue
            costs = [
                _candidate_cost(state, index, message, adjacency)
                for index in range(len(state.candidates))
            ]
            current = int(state.candidate_index)
            minimum = min(costs)
            true_correction = costs[current] > minimum
            true_correction_exposures += int(true_correction)
            query_assignment = _candidate_assignment(state)
            query_assignment.update({int(vertex): int(color) for vertex, color in message.items()})
            trigger = True
            for hit_index in range(required_hits):
                observation = detector.observe(
                    instance_id=f"{instance['instance_id']}::agent{agent}",
                    assignment=query_assignment,
                    true_dead=bool(true_correction),
                    query_index=round_index * 16 + hit_index,
                    channel="recurrent_correction",
                )
                detector_queries += 1
                false_positives += int(observation.false_positive)
                false_negatives += int(observation.false_negative)
                if not observation.observed_dead:
                    trigger = False
                    break
            observed_positive_signals += int(trigger)
            if not trigger:
                proposals[agent] = (current, int(state.tie_cursor))
            elif true_correction:
                selected, tie_cursor = _propose(state, message, adjacency, reset_state=False)
                proposals[agent] = (selected, tie_cursor)
                true_corrections_executed += 1
                candidate_corrections += int(selected != current)
            else:
                selected = (current + 1) % len(state.candidates)
                proposals[agent] = (int(selected), int(state.tie_cursor + 1))
                over_corrections += 1
                correct_state_destroyed += int(selected != current)
                candidate_corrections += int(selected != current)
            agent_updates += 1

        for agent, (selected, tie_cursor) in proposals.items():
            state = states[agent]
            if int(selected) != int(state.candidate_index):
                state.state_changes += 1
                state_changes += 1
            state.candidate_index = int(selected)
            state.tie_cursor = int(tie_cursor)

        generated: dict[int, dict[int, int]] = {agent: {} for agent in states}
        for child, parent_agent in parent.items():
            if parent_agent is None:
                continue
            generated[child] = _message_for_child(states[int(parent_agent)], states[child], adjacency)
            messages_generated += 1
        incoming = generated
        delivered = sum(parent_agent is not None for parent_agent in parent.values())
        messages_delivered += int(delivered)
        maximum_message_age = max(maximum_message_age, int(bool(delivered)))

        final_assignment = {
            vertex: color
            for state in states.values()
            for vertex, color in _candidate_assignment(state).items()
        }
        final_cross_conflicts = sum(
            int(final_assignment[int(left)] == final_assignment[int(right)])
            for left, right in instance["edges"]
            if partitions[int(left)] != partitions[int(right)]
        )
        solved = verify_coloring(instance, final_assignment)
        if solved:
            break

    aggregate_work = agent_updates + detector_queries + candidate_corrections
    return {
        "instance_id": str(instance["instance_id"]),
        "partition_diameter": int(instance["partition_diameter"]),
        "system": system,
        "eta_fp": float(eta_fp),
        "eta_fn": float(eta_fn),
        "confirmation_hits": required_hits,
        "round_cap": int(round_cap),
        "solved": bool(solved),
        "status": "SOLVED" if solved else "ROUND_CAP",
        "rounds_executed": rounds_executed,
        "agent_updates": agent_updates,
        "state_changes": state_changes,
        "messages_generated": messages_generated,
        "messages_delivered": messages_delivered,
        "detector_queries": detector_queries,
        "observed_positive_signals": observed_positive_signals,
        "true_correction_exposures": true_correction_exposures,
        "true_corrections_executed": true_corrections_executed,
        "over_corrections": over_corrections,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "candidate_corrections": candidate_corrections,
        "correct_state_destroyed": correct_state_destroyed,
        "aggregate_work": aggregate_work,
        "same_round_cross_agent_reads": same_round_cross_agent_reads,
        "maximum_message_age": maximum_message_age,
        "idealized_parallel_critical_path": rounds_executed,
        "sequential_local_update_critical_path": agent_updates,
        "final_cross_conflicts": final_cross_conflicts,
        "local_candidates_valid": local_candidates_valid,
        "official_verification": bool(solved),
        "planted_assignment_used": False,
        "message_semantics": "full_one_round_delayed",
    }
