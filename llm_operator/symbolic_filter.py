"""Answer-free CSP utilities for M2 operator probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import random

from tasks.graph_coloring.generator import generate_graph_coloring
from tasks.logic_grid.generator import generate_logic_grid
from tasks.oracle.dpll_oracle import Constraint
from tasks.oracle.trace_generator import trace_to_examples
from tasks.sat.generators import generate_general_sat, generate_horn_sat
from tasks.sudoku.generator_4x4 import constraints_4x4, generate_4x4_by_depth


@dataclass(frozen=True)
class CSPTask:
    task_id: str
    task_type: str
    givens: dict[str, Any]
    variables: list[int]
    domains: dict[int, set[int]]
    constraints: list[Constraint]
    oracle_trace: Any
    dpll_backtrack_depth: int


@dataclass(frozen=True)
class ProbeNode:
    task: CSPTask
    partial_assignment: dict[int, int]
    depth: int
    oracle_action: str
    oracle_dead_end: bool


def sat_constraints(clauses: list[list[int]]) -> list[Constraint]:
    constraints = []
    for clause in clauses:
        scope = tuple(abs(lit) for lit in clause)
        signs = tuple(lit > 0 for lit in clause)

        def check(values: tuple[int, ...], signs: tuple[bool, ...] = signs) -> bool:
            return any((value == 1) == sign for value, sign in zip(values, signs))

        constraints.append((scope, check))
    return constraints


def graph_constraints(edges: list[tuple[int, int]]) -> list[Constraint]:
    return [((u, v), lambda values: values[0] != values[1]) for u, v in edges]


def is_consistent(assignment: dict[int, int], constraints: list[Constraint]) -> bool:
    for scope, check in constraints:
        if all(var in assignment for var in scope) and not check(tuple(assignment[var] for var in scope)):
            return False
    return True


def valid_values(task: CSPTask, assignment: dict[int, int], var: int) -> set[int]:
    if var in assignment:
        return {assignment[var]} if is_consistent(assignment, task.constraints) else set()
    return {value for value in task.domains[var] if is_consistent({**assignment, var: value}, task.constraints)}


def status(task: CSPTask, assignment: dict[int, int]) -> str:
    if not is_consistent(assignment, task.constraints):
        return "CONTRADICTION"
    for var in task.variables:
        if var not in assignment and not valid_values(task, assignment, var):
            return "CONTRADICTION"
    if all(var in assignment for var in task.variables):
        return "SOLVED"
    return "OPEN"


def forced_moves(task: CSPTask, assignment: dict[int, int]) -> dict[int, int]:
    if status(task, assignment) == "CONTRADICTION":
        return {}
    forced: dict[int, int] = {}
    for var in task.variables:
        if var in assignment:
            continue
        values = valid_values(task, assignment, var)
        if len(values) == 1:
            forced[var] = next(iter(values))
    return forced


def propagation_fixpoint(task: CSPTask, assignment: dict[int, int]) -> tuple[dict[int, int], int, str]:
    current = dict(assignment)
    rounds = 0
    while True:
        current_status = status(task, current)
        if current_status != "OPEN":
            return current, rounds, current_status
        moves = forced_moves(task, current)
        new_moves = {var: value for var, value in moves.items() if var not in current}
        if not new_moves:
            return current, rounds, "OPEN"
        current.update(new_moves)
        rounds += 1


def mrv_guess(task: CSPTask, assignment: dict[int, int]) -> tuple[int, int] | None:
    candidates = []
    for var in task.variables:
        if var in assignment:
            continue
        values = sorted(valid_values(task, assignment, var))
        if values:
            candidates.append((len(values), var, values[0]))
    if not candidates:
        return None
    _, var, value = min(candidates)
    return var, value


def random_guess(task: CSPTask, assignment: dict[int, int], rng: random.Random) -> tuple[int, int] | None:
    candidates = []
    for var in task.variables:
        if var in assignment:
            continue
        for value in sorted(valid_values(task, assignment, var)):
            candidates.append((var, value))
    return rng.choice(candidates) if candidates else None


def build_tasks(task_types: list[str], n_instances: int, seed: int) -> list[CSPTask]:
    tasks: list[CSPTask] = []
    if "horn_sat" in task_types:
        for index, task in enumerate(generate_horn_sat(n_instances=n_instances, seed=seed)):
            variables = list(range(1, task.n_vars + 1))
            tasks.append(CSPTask(f"horn_sat_{index}", "horn_sat", {"n_vars": task.n_vars, "clauses": task.clauses}, variables, {var: {0, 1} for var in variables}, sat_constraints(task.clauses), task.oracle_trace, task.dpll_backtrack_depth))
    if "general_sat" in task_types:
        for index, task in enumerate(generate_general_sat(n_instances=n_instances, min_depth=1, seed=seed)):
            variables = list(range(1, task.n_vars + 1))
            tasks.append(CSPTask(f"general_sat_{index}", "general_sat", {"n_vars": task.n_vars, "clauses": task.clauses}, variables, {var: {0, 1} for var in variables}, sat_constraints(task.clauses), task.oracle_trace, task.dpll_backtrack_depth))
    if "graph_coloring" in task_types:
        for index, task in enumerate(generate_graph_coloring(n_instances=n_instances, seed=seed)):
            variables = list(range(task.n))
            tasks.append(CSPTask(f"graph_coloring_{index}", "graph_coloring", {"n": task.n, "k": task.k, "edges": task.edges}, variables, {var: set(range(1, task.k + 1)) for var in variables}, graph_constraints(task.edges), task.oracle_trace, task.dpll_backtrack_depth))
    if "sudoku_4x4" in task_types:
        for index, task in enumerate(generate_4x4_by_depth(n_instances=n_instances, seed=seed)):
            variables = list(range(16))
            domains = {var: set(range(1, 5)) for var in variables}
            for (row, col), value in task.givens.items():
                domains[row * 4 + col] = {value}
            givens = {f"{row},{col}": value for (row, col), value in task.givens.items()}
            tasks.append(CSPTask(f"sudoku_4x4_{index}", "sudoku_4x4", givens, variables, domains, constraints_4x4(), task.oracle_trace, task.dpll_backtrack_depth))
    if "logic_grid" in task_types:
        for index, task in enumerate(generate_logic_grid(n_instances=n_instances, seed=seed)):
            variables = list(range(8))
            domains = {var: set(range(1, 5)) for var in variables}
            givens = {"categories": task.categories, "clues": task.clues}
            tasks.append(CSPTask(f"logic_grid_{index}", "logic_grid", givens, variables, domains, task.constraints, task.oracle_trace, task.dpll_backtrack_depth))
    return tasks


def sample_probe_nodes(tasks: list[CSPTask], max_nodes_per_task: int, seed: int) -> list[ProbeNode]:
    rng = random.Random(seed)
    nodes: list[ProbeNode] = []
    for task in tasks:
        examples = trace_to_examples(task.oracle_trace, task.givens, task.task_type)
        rng.shuffle(examples)
        for example in examples[:max_nodes_per_task]:
            nodes.append(ProbeNode(task, dict(example.partial_assignment), example.depth, example.target_action, example.is_dead_end))
    return nodes