"""Long-diameter partitioned 3-SAT substrate for recurrent signal replication."""

from __future__ import annotations

from collections import deque
from itertools import combinations, product
import hashlib
import json
import random
from typing import Any, Mapping

from experiments.signal.long_diameter_graph import graph_diameter, partition_tree_edges


def _literal_true(literal: int, assignment: Mapping[int, int]) -> bool:
    value = int(assignment[abs(int(literal))])
    return (value == 1) == (int(literal) > 0)


def clause_satisfied(clause: list[int] | tuple[int, ...], assignment: Mapping[int, int]) -> bool:
    return any(_literal_true(int(literal), assignment) for literal in clause)


def verify_sat(instance: Mapping[str, Any], assignment: Mapping[int, int]) -> bool:
    return len(assignment) == int(instance["n_vars"]) and all(clause_satisfied(clause, assignment) for clause in instance["clauses"])


def _root_parent(n_partitions: int, edges: list[tuple[int, int]], root: int = 0) -> dict[int, int | None]:
    adjacency = [set() for _ in range(int(n_partitions))]
    for left, right in edges:
        adjacency[int(left)].add(int(right))
        adjacency[int(right)].add(int(left))
    parent: dict[int, int | None] = {int(root): None}
    queue = deque([int(root)])
    while queue:
        current = queue.popleft()
        for neighbor in sorted(adjacency[current]):
            if neighbor not in parent:
                parent[neighbor] = current
                queue.append(neighbor)
    return parent


def _local_extendable(variables: list[int], clauses: list[list[int]]) -> bool:
    bit0, bit1, aux0, aux1 = variables
    for left, right in product((0, 1), repeat=2):
        if not any(
            all(clause_satisfied(clause, {bit0: left, bit1: right, aux0: a0, aux1: a1}) for clause in clauses)
            for a0, a1 in product((0, 1), repeat=2)
        ):
            return False
    return True


def _local_clause_pool(variables: list[int], planted: Mapping[int, int]) -> list[list[int]]:
    output = []
    for scope in combinations(variables, 3):
        for signs in product((-1, 1), repeat=3):
            clause = [int(variable) * int(sign) for variable, sign in zip(scope, signs)]
            if sum(int(_literal_true(literal, planted)) for literal in clause) == 1:
                output.append(clause)
    return output


def _equivalence_clauses(parent_var: int, child_var: int, child_aux: int) -> list[list[int]]:
    return [
        [-int(parent_var), int(child_var), int(child_aux)],
        [-int(parent_var), int(child_var), -int(child_aux)],
        [int(parent_var), -int(child_var), int(child_aux)],
        [int(parent_var), -int(child_var), -int(child_aux)],
    ]


def generate_long_diameter_sat(
    *,
    base_seed: int,
    candidate_index: int,
    diameter: int,
    n_partitions: int = 17,
    variables_per_partition: int = 4,
    local_clauses_per_partition: int = 8,
    split: str = "development",
) -> dict[str, Any]:
    if int(variables_per_partition) != 4:
        raise ValueError("long-diameter SAT is frozen to four variables per partition")
    rng = random.Random(int(base_seed) * 1_000_003 + int(candidate_index) * 10_007 + int(diameter) * 101)
    tree_edges = partition_tree_edges(int(n_partitions), int(diameter))
    parent = _root_parent(int(n_partitions), tree_edges)
    n_vars = int(n_partitions) * int(variables_per_partition)
    partitions = [block for block in range(int(n_partitions)) for _ in range(int(variables_per_partition))]

    global_bits = (rng.randrange(2), rng.randrange(2))
    planted: dict[int, int] = {}
    local_clauses: list[list[int]] = []
    for agent in range(int(n_partitions)):
        variables = [agent * int(variables_per_partition) + offset + 1 for offset in range(int(variables_per_partition))]
        planted[variables[0]] = global_bits[0]
        planted[variables[1]] = global_bits[1]
        planted[variables[2]] = rng.randrange(2)
        planted[variables[3]] = rng.randrange(2)
        pool = _local_clause_pool(variables, planted)
        rng.shuffle(pool)
        selected: list[list[int]] = []
        for clause in pool:
            if len(selected) >= int(local_clauses_per_partition):
                break
            proposal = selected + [clause]
            if _local_extendable(variables, proposal):
                selected.append(clause)
        if len(selected) != int(local_clauses_per_partition):
            raise RuntimeError("could not construct extendable local SAT gadget")
        local_clauses.extend(selected)

    cross_clauses: list[list[int]] = []
    for child, parent_agent in sorted(parent.items()):
        if parent_agent is None:
            continue
        parent_vars = [int(parent_agent) * int(variables_per_partition) + offset + 1 for offset in range(int(variables_per_partition))]
        child_vars = [int(child) * int(variables_per_partition) + offset + 1 for offset in range(int(variables_per_partition))]
        cross_clauses.extend(_equivalence_clauses(parent_vars[0], child_vars[0], child_vars[2]))
        cross_clauses.extend(_equivalence_clauses(parent_vars[1], child_vars[1], child_vars[3]))

    clauses = local_clauses + cross_clauses
    instance_id = f"sat_rpd_{split}_s{int(base_seed)}_d{int(diameter)}_{int(candidate_index):06d}"
    initial_pair_codes = {str(agent): int(agent % 4) for agent in range(int(n_partitions))}
    payload = {
        "schema": "recurrent_signal_long_diameter_sat_v1",
        "instance_id": instance_id,
        "split": str(split),
        "base_seed": int(base_seed),
        "candidate_index": int(candidate_index),
        "n_partitions": int(n_partitions),
        "variables_per_partition": int(variables_per_partition),
        "n_vars": n_vars,
        "partitions": partitions,
        "partition_tree_edges": [list(edge) for edge in tree_edges],
        "partition_diameter": graph_diameter(int(n_partitions), tree_edges),
        "clauses": clauses,
        "n_clauses": len(clauses),
        "n_local_clauses": len(local_clauses),
        "n_cross_clauses": len(cross_clauses),
        "initial_pair_codes": initial_pair_codes,
        "planted_assignment": {str(key): int(value) for key, value in planted.items()},
    }
    if not verify_sat(payload, planted):
        raise AssertionError("planted SAT assignment invalid")
    return payload


def public_instance(instance: Mapping[str, Any]) -> dict[str, Any]:
    output = {key: value for key, value in instance.items() if key != "planted_assignment"}
    output["planted_assignment_removed"] = True
    return output


def clause_hash(instance: Mapping[str, Any]) -> str:
    payload = {"n_vars": int(instance["n_vars"]), "partitions": instance["partitions"], "tree": instance["partition_tree_edges"], "clauses": instance["clauses"], "initial_pair_codes": instance["initial_pair_codes"]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def local_pair_extendability(instance: Mapping[str, Any]) -> dict[int, bool]:
    output = {}
    for agent in range(int(instance["n_partitions"])):
        variables = [agent * int(instance["variables_per_partition"]) + offset + 1 for offset in range(int(instance["variables_per_partition"]))]
        clauses = [clause for clause in instance["clauses"] if all(int(instance["partitions"][abs(int(literal)) - 1]) == agent for literal in clause)]
        output[agent] = _local_extendable(variables, clauses)
    return output


def initial_parent_child_mismatches(instance: Mapping[str, Any]) -> int:
    parent = _root_parent(int(instance["n_partitions"]), [tuple(map(int, edge)) for edge in instance["partition_tree_edges"]])
    codes = {int(agent): int(code) for agent, code in instance["initial_pair_codes"].items()}
    return sum(int(codes[child] != codes[int(parent_agent)]) for child, parent_agent in parent.items() if parent_agent is not None)
