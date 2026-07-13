"""Planted fixed-density community-structured 3-SAT instances."""

from __future__ import annotations

from functools import lru_cache
import hashlib
from itertools import combinations
import json
import random
from typing import Any


@lru_cache(maxsize=None)
def _descriptor_pools(
    n_vars: int,
    communities: int,
    community_size: int,
) -> tuple[tuple[tuple[tuple[int, int, int], int], ...], tuple[tuple[tuple[int, int, int], int], ...]]:
    if int(n_vars) != int(communities) * int(community_size):
        raise ValueError("n_vars must equal communities * community_size")
    intra: list[tuple[tuple[int, int, int], int]] = []
    cross: list[tuple[tuple[int, int, int], int]] = []
    for triple in combinations(range(1, int(n_vars) + 1), 3):
        owners = {(variable - 1) // int(community_size) for variable in triple}
        target = intra if len(owners) == 1 else cross
        target.extend((triple, true_variable) for true_variable in triple)
    return tuple(intra), tuple(cross)


def literal_satisfied(literal: int, value: int) -> bool:
    return (int(value) == 1) == (int(literal) > 0)


def clause_satisfied(clause: list[int] | tuple[int, ...], assignment: dict[int, int]) -> bool:
    return any(
        abs(int(literal)) in assignment
        and literal_satisfied(int(literal), int(assignment[abs(int(literal))]))
        for literal in clause
    )


def clause_falsified(clause: list[int] | tuple[int, ...], assignment: dict[int, int]) -> bool:
    return all(abs(int(literal)) in assignment for literal in clause) and not clause_satisfied(clause, assignment)


def verify_sat_assignment(instance: dict[str, Any], assignment: dict[int, int]) -> bool:
    n_vars = int(instance["n_vars"])
    if set(map(int, assignment)) != set(range(1, n_vars + 1)):
        return False
    if any(int(value) not in {0, 1} for value in assignment.values()):
        return False
    return all(clause_satisfied(clause, assignment) for clause in instance["clauses"])


def clause_hash(clauses: list[list[int]]) -> str:
    payload = json.dumps(clauses, separators=(",", ":"), sort_keys=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_community_sat_candidate(
    *,
    base_seed: int,
    candidate_index: int,
    coupling: str,
    n_vars: int = 48,
    communities: int = 4,
    community_size: int = 12,
    n_clauses: int = 192,
    cross_clauses_low: int = 19,
    cross_clauses_high: int = 77,
    split: str = "development",
) -> dict[str, Any]:
    """Generate one planted 3-CNF with exact clause count and coupling."""
    if coupling not in {"low", "high"}:
        raise ValueError("coupling must be low or high")
    cross_count = int(cross_clauses_low if coupling == "low" else cross_clauses_high)
    intra_count = int(n_clauses) - cross_count
    if intra_count < 0:
        raise ValueError("cross clause count exceeds total clauses")
    rng = random.Random(f"community_sat_v1::{int(base_seed)}::{coupling}::{int(candidate_index)}")
    planted = {variable: rng.randrange(2) for variable in range(1, int(n_vars) + 1)}
    order = list(range(1, int(n_vars) + 1))
    rng.shuffle(order)
    partitions = [(variable - 1) // int(community_size) for variable in range(1, int(n_vars) + 1)]
    intra_pool, cross_pool = _descriptor_pools(int(n_vars), int(communities), int(community_size))
    if intra_count > len(intra_pool) or cross_count > len(cross_pool):
        raise ValueError("requested clause count exceeds unique planted descriptor pool")
    descriptors = rng.sample(intra_pool, intra_count) + rng.sample(cross_pool, cross_count)
    rng.shuffle(descriptors)
    clauses: list[list[int]] = []
    for variables, true_variable in descriptors:
        clause = []
        for variable in variables:
            makes_true = int(variable) == int(true_variable)
            planted_value = int(planted[int(variable)])
            positive = (planted_value == 1) if makes_true else (planted_value == 0)
            clause.append(int(variable) if positive else -int(variable))
        clauses.append(clause)
    canonical = {tuple(clause) for clause in clauses}
    if len(canonical) != int(n_clauses):
        raise RuntimeError("duplicate planted clauses generated")
    instance = {
        "schema": "community_sat_instance_v1",
        "instance_id": f"community_sat_{split}_s{int(base_seed)}_{coupling}_{int(candidate_index):06d}",
        "split": str(split),
        "base_seed": int(base_seed),
        "candidate_index": int(candidate_index),
        "n_vars": int(n_vars),
        "n_communities": int(communities),
        "community_size": int(community_size),
        "n_clauses": int(n_clauses),
        "clause_size": 3,
        "cross_clause_count": int(cross_count),
        "intra_clause_count": int(intra_count),
        "coupling": coupling,
        "rho_actual": int(cross_count) / max(int(n_clauses), 1),
        "partitions": partitions,
        "order": order,
        "clauses": clauses,
        "planted_assignment": {str(variable): int(value) for variable, value in planted.items()},
        "clause_sha256": clause_hash(clauses),
        "selection_rule": "unselected_candidate_no_evaluated_arm_outcomes",
        "headline_eligible": False,
    }
    if not verify_sat_assignment(instance, planted):
        raise RuntimeError("planted assignment did not satisfy generated CNF")
    return instance
