"""Horn-SAT and general SAT generators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import random

from tasks.oracle.dpll_oracle import DPLLOracle, OracleTrace


@dataclass
class SATInstance:
    n_vars: int
    clauses: list[list[int]]
    kind: str
    dpll_backtrack_depth: int
    oracle_trace: OracleTrace


def _constraints(clauses: list[list[int]]):
    constraints = []
    for clause in clauses:
        scope = tuple(abs(lit) for lit in clause)
        signs = tuple(lit > 0 for lit in clause)
        def check(values, signs=signs):
            return any((value == 1) == sign for value, sign in zip(values, signs))
        constraints.append((scope, check))
    return constraints


def generate_horn_sat(n_vars: int = 8, n_clauses: int = 16, n_instances: int = 20, seed: int = 42) -> list[SATInstance]:
    rng = random.Random(seed)
    out = []
    for _ in range(n_instances * 20):
        if len(out) >= n_instances:
            break
        clauses = []
        for _ in range(n_clauses):
            vars_ = rng.sample(range(1, n_vars + 1), rng.randint(1, min(3, n_vars)))
            positives = rng.sample(range(len(vars_)), rng.randint(0, 1))
            clauses.append([v if i in positives else -v for i, v in enumerate(vars_)])
        variables = list(range(1, n_vars + 1))
        trace = DPLLOracle().solve(variables, {v: {0, 1} for v in variables}, _constraints(clauses))
        if trace.solved and trace.max_backtrack_depth == 0:
            out.append(SATInstance(n_vars, clauses, "horn_sat", 0, trace))
    return out


def generate_general_sat(n_vars: int = 8, clause_ratio: float = 4.0, target_depth: Optional[int] = None, min_depth: int = 1, n_instances: int = 20, seed: int = 42) -> list[SATInstance]:
    rng = random.Random(seed)
    out = []
    n_clauses = max(1, int(n_vars * clause_ratio))
    for _ in range(n_instances * 100):
        if len(out) >= n_instances:
            break
        clauses = []
        for _ in range(n_clauses):
            vars_ = rng.sample(range(1, n_vars + 1), min(3, n_vars))
            clauses.append([v if rng.random() > 0.5 else -v for v in vars_])
        variables = list(range(1, n_vars + 1))
        trace = DPLLOracle().solve(variables, {v: {0, 1} for v in variables}, _constraints(clauses))
        depth = trace.max_backtrack_depth
        if trace.solved and depth >= min_depth and (target_depth is None or depth == target_depth):
            out.append(SATInstance(n_vars, clauses, "general_sat", depth, trace))
    return out
