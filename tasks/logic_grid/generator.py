"""Synthetic logic-grid CSP generator with symbolic oracle traces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import random

from tasks.oracle.dpll_oracle import Constraint, DPLLOracle, OracleTrace


@dataclass
class LogicGridInstance:
    categories: list[str]
    clues: list[str]
    dpll_backtrack_depth: int
    oracle_trace: OracleTrace


def _not_equal(scope: tuple[int, int]) -> Constraint:
    return (scope, lambda values: values[0] != values[1])


def _allowed(var: int, values: set[int]) -> Constraint:
    return ((var,), lambda assignment, values=values: assignment[0] in values)


def _implies(left_value: int, right_value: int) -> Constraint:
    return ((0, 1), lambda values, left_value=left_value, right_value=right_value: values[0] != left_value or values[1] == right_value)


def _renumber_constraint(constraint: Constraint, scope: tuple[int, ...]) -> Constraint:
    _old_scope, check = constraint
    return (scope, check)


def _constraints(n_people: int, rng: random.Random) -> tuple[list[Constraint], list[str]]:
    color_vars = list(range(n_people))
    pet_vars = list(range(n_people, n_people * 2))
    constraints: list[Constraint] = []
    clues: list[str] = []

    for variables, label in [(color_vars, "color"), (pet_vars, "pet")]:
        for index, left in enumerate(variables):
            for right in variables[index + 1:]:
                constraints.append(_not_equal((left, right)))
        clues.append(f"Each person has a unique {label}.")

    for person in range(n_people):
        true_color = rng.randint(1, n_people)
        true_pet = rng.randint(1, n_people)
        forbidden_color = 1 if true_color != 1 else n_people
        forbidden_pet = 1 if true_pet != 1 else n_people
        allowed_colors = set(range(1, n_people + 1)) - {forbidden_color}
        allowed_pets = set(range(1, n_people + 1)) - {forbidden_pet}
        constraints.append(_allowed(color_vars[person], allowed_colors))
        constraints.append(_allowed(pet_vars[person], allowed_pets))
        clues.append(f"person_{person} is not color_{forbidden_color}.")
        clues.append(f"person_{person} does not have pet_{forbidden_pet}.")

    links = list(range(1, n_people + 1))
    rng.shuffle(links)
    for color, pet in enumerate(links, start=1):
        constraints.append(_renumber_constraint(_implies(color, pet), (color_vars[rng.randrange(n_people)], pet_vars[rng.randrange(n_people)])))
        clues.append(f"A color_{color} assignment implies pet_{pet} for one clue row.")

    return constraints, clues


def generate_logic_grid(target_depth: Optional[int] = None, n_instances: int = 20, seed: int = 42) -> list[LogicGridInstance]:
    rng = random.Random(seed)
    out: list[LogicGridInstance] = []
    n_people = 4
    variables = list(range(n_people * 2))
    domains = {var: set(range(1, n_people + 1)) for var in variables}
    for _ in range(n_instances * 100):
        if len(out) >= n_instances:
            break
        constraints, clues = _constraints(n_people, rng)
        trace = DPLLOracle().solve(variables, domains, constraints)
        depth = trace.max_backtrack_depth
        if trace.solved and (target_depth is None or depth == target_depth):
            out.append(LogicGridInstance(["person", "color", "pet"], clues, depth, trace))
    return out
