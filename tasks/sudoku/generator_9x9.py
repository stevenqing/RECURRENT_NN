"""9x9 Sudoku external anchor generator.

The 9x9 anchor is not the core Stage D proof, but the generator must still be a
real object: it creates solved grids, removes givens, and grades candidates with
the same DPLL oracle used by the smaller controlled tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import random

from tasks.oracle.dpll_oracle import DPLLOracle, OracleTrace


@dataclass
class Sudoku9x9Instance:
    givens: dict[tuple[int, int], int]
    solution: dict[tuple[int, int], int]
    dpll_backtrack_depth: int
    oracle_trace: OracleTrace


def constraints_9x9():
    constraints = []
    units = []
    units += [[row * 9 + col for col in range(9)] for row in range(9)]
    units += [[row * 9 + col for row in range(9)] for col in range(9)]
    units += [[(box_row * 3 + row) * 9 + (box_col * 3 + col) for row in range(3) for col in range(3)] for box_row in range(3) for box_col in range(3)]
    for unit in units:
        for index, left in enumerate(unit):
            for right in unit[index + 1:]:
                constraints.append(((left, right), lambda values: values[0] != values[1]))
    return constraints


def _full_solution(rng: random.Random) -> dict[tuple[int, int], int]:
    base = [[((row * 3 + row // 3 + col) % 9) + 1 for col in range(9)] for row in range(9)]
    row_bands = [[0, 1, 2], [3, 4, 5], [6, 7, 8]]
    col_bands = [[0, 1, 2], [3, 4, 5], [6, 7, 8]]
    rng.shuffle(row_bands)
    rng.shuffle(col_bands)
    rows = []
    for band in row_bands:
        band = list(band)
        rng.shuffle(band)
        rows.extend(band)
    cols = []
    for band in col_bands:
        band = list(band)
        rng.shuffle(band)
        cols.extend(band)
    digits = list(range(1, 10))
    shuffled = digits[:]
    rng.shuffle(shuffled)
    digit_map = dict(zip(digits, shuffled))
    return {(row, col): digit_map[base[rows[row]][cols[col]]] for row in range(9) for col in range(9)}


def generate_9x9_by_depth_band(min_depth: int = 0, max_depth: int = 1, n_instances: int = 8, seed: int = 42) -> list[Sudoku9x9Instance]:
    rng = random.Random(seed)
    out = []
    variables = list(range(81))
    constraints = constraints_9x9()
    attempts = max(100, n_instances * 120)
    for _ in range(attempts):
        if len(out) >= n_instances:
            break
        solution = _full_solution(rng)
        cells = list(solution.keys())
        rng.shuffle(cells)
        keep = rng.randint(42, 64)
        givens = {cell: solution[cell] for cell in cells[:keep]}
        domains = {var: set(range(1, 10)) for var in variables}
        for (row, col), value in givens.items():
            domains[row * 9 + col] = {value}
        trace = DPLLOracle().solve(variables, domains, constraints)
        depth = trace.max_backtrack_depth
        if trace.solved and min_depth <= depth <= max_depth:
            out.append(Sudoku9x9Instance(givens, solution, depth, trace))
    return out


def generate_9x9_by_depth(target_depth: Optional[int] = None, n_instances: int = 8, seed: int = 42) -> list[Sudoku9x9Instance]:
    if target_depth is None:
        return generate_9x9_by_depth_band(0, 8, n_instances, seed)
    return generate_9x9_by_depth_band(target_depth, target_depth, n_instances, seed)
