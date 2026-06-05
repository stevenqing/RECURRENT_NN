"""Symbolic DPLL-style oracle with branch/propagate/backtrack traces."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
import copy


class TraceAction(str, Enum):
    PROPAGATE = "propagate"
    BRANCH = "branch"
    BACKTRACK = "backtrack"
    CONTRADICTION = "contradiction"
    SOLVED = "solved"


@dataclass
class TraceStep:
    action: TraceAction
    variable: Optional[int] = None
    value: Optional[int] = None
    depth: int = 0
    dead_end: bool = False


@dataclass
class OracleTrace:
    steps: list[TraceStep] = field(default_factory=list)
    solved: bool = False
    solution: Optional[dict[int, int]] = None
    max_backtrack_depth: int = 0
    total_backtracks: int = 0

Constraint = tuple[tuple[int, ...], Callable[[tuple[int, ...]], bool]]


class DPLLOracle:
    def __init__(self):
        self.trace = OracleTrace()

    def solve(self, variables: list[int], domains: dict[int, set[int]], constraints: list[Constraint], assignment: Optional[dict[int, int]] = None, depth: int = 0) -> OracleTrace:
        if assignment is None:
            assignment = {}
            self.trace = OracleTrace()
        domains = copy.deepcopy(domains)
        while True:
            changed = False
            for var in variables:
                if var in assignment:
                    continue
                valid = {value for value in domains[var] if self._consistent({**assignment, var: value}, constraints)}
                if not valid:
                    self.trace.steps.append(TraceStep(TraceAction.CONTRADICTION, depth=depth, dead_end=True))
                    return self.trace
                if valid != domains[var]:
                    domains[var] = valid
                    changed = True
                if len(valid) == 1:
                    value = next(iter(valid))
                    assignment[var] = value
                    self.trace.steps.append(TraceStep(TraceAction.PROPAGATE, var, value, depth))
                    changed = True
            if not changed:
                break
        if all(v in assignment for v in variables):
            self.trace.steps.append(TraceStep(TraceAction.SOLVED, depth=depth))
            self.trace.solved = True
            self.trace.solution = dict(assignment)
            return self.trace
        var = min((v for v in variables if v not in assignment), key=lambda x: len(domains[x]))
        for value in sorted(domains[var]):
            self.trace.steps.append(TraceStep(TraceAction.BRANCH, var, value, depth))
            self.solve(variables, {**domains, var: {value}}, constraints, {**assignment, var: value}, depth + 1)
            if self.trace.solved:
                self.trace.max_backtrack_depth = max(self.trace.max_backtrack_depth, depth + 1)
                return self.trace
            self.trace.steps.append(TraceStep(TraceAction.BACKTRACK, var, value, depth))
            self.trace.total_backtracks += 1
            self.trace.max_backtrack_depth = max(self.trace.max_backtrack_depth, depth + 1)
        return self.trace

    @staticmethod
    def _consistent(assignment: dict[int, int], constraints: list[Constraint]) -> bool:
        for scope, check in constraints:
            if all(v in assignment for v in scope) and not check(tuple(assignment[v] for v in scope)):
                return False
        return True
