"""Classic 4x4 Sudoku generator by DPLL depth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import random

from tasks.oracle.dpll_oracle import DPLLOracle, OracleTrace


@dataclass
class Sudoku4x4Instance:
    givens: dict[tuple[int, int], int]
    solution: dict[tuple[int, int], int]
    dpll_backtrack_depth: int
    oracle_trace: OracleTrace


def constraints_4x4():
    constraints = []
    units = []
    units += [[r * 4 + c for c in range(4)] for r in range(4)]
    units += [[r * 4 + c for r in range(4)] for c in range(4)]
    units += [[(br * 2 + r) * 4 + (bc * 2 + c) for r in range(2) for c in range(2)] for br in range(2) for bc in range(2)]
    for unit in units:
        for i, a in enumerate(unit):
            for b in unit[i + 1:]:
                constraints.append(((a, b), lambda values: values[0] != values[1]))
    return constraints


def _full_solution(rng: random.Random) -> dict[tuple[int, int], int]:
    base = [[((r * 2 + r // 2 + c) % 4) + 1 for c in range(4)] for r in range(4)]
    rows = [0, 1, 2, 3]
    cols = [0, 1, 2, 3]
    rng.shuffle(rows)
    rng.shuffle(cols)
    return {(r, c): base[rows[r]][cols[c]] for r in range(4) for c in range(4)}


def generate_4x4_by_depth(target_depth: Optional[int] = None, n_instances: int = 20, seed: int = 42) -> list[Sudoku4x4Instance]:
    rng = random.Random(seed)
    out = []
    variables = list(range(16))
    constraints = constraints_4x4()
    for _ in range(n_instances * 100):
        if len(out) >= n_instances:
            break
        solution = _full_solution(rng)
        cells = list(solution.keys())
        rng.shuffle(cells)
        keep = rng.randint(5, 12)
        givens = {cell: solution[cell] for cell in cells[:keep]}
        domains = {v: set(range(1, 5)) for v in variables}
        for (r, c), value in givens.items():
            domains[r * 4 + c] = {value}
        trace = DPLLOracle().solve(variables, domains, constraints)
        depth = trace.max_backtrack_depth
        if trace.solved and (target_depth is None or depth == target_depth):
            out.append(Sudoku4x4Instance(givens, solution, depth, trace))
    return out
