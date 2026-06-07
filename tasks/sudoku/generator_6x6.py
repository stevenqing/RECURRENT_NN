"""6x6 banded Sudoku generator for Stage A G1 diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import random

from tasks.oracle.dpll_oracle import DPLLOracle, OracleTrace


@dataclass
class Sudoku6x6Instance:
    givens: dict[tuple[int, int], int]
    solution: dict[tuple[int, int], int]
    dpll_backtrack_depth: int
    oracle_trace: OracleTrace


def constraints_6x6():
    constraints = []
    units = []
    units += [[row * 6 + col for col in range(6)] for row in range(6)]
    units += [[row * 6 + col for row in range(6)] for col in range(6)]
    units += [[(box_row * 2 + row) * 6 + (box_col * 3 + col) for row in range(2) for col in range(3)] for box_row in range(3) for box_col in range(2)]
    for unit in units:
        for index, left in enumerate(unit):
            for right in unit[index + 1:]:
                constraints.append(((left, right), lambda values: values[0] != values[1]))
    return constraints


def _full_solution(rng: random.Random) -> dict[tuple[int, int], int]:
    base = [[((row * 3 + row // 2 + col) % 6) + 1 for col in range(6)] for row in range(6)]
    row_bands = [[0, 1], [2, 3], [4, 5]]
    col_bands = [[0, 1, 2], [3, 4, 5]]
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
    digits = list(range(1, 7))
    shuffled = digits[:]
    rng.shuffle(shuffled)
    digit_map = dict(zip(digits, shuffled))
    return {(row, col): digit_map[base[rows[row]][cols[col]]] for row in range(6) for col in range(6)}


def generate_6x6_by_depth_band(min_depth: int = 1, max_depth: int = 2, n_instances: int = 32, seed: int = 42) -> list[Sudoku6x6Instance]:
    rng = random.Random(seed)
    out = []
    variables = list(range(36))
    constraints = constraints_6x6()
    attempts = max(200, n_instances * 250)
    for _ in range(attempts):
        if len(out) >= n_instances:
            break
        solution = _full_solution(rng)
        cells = list(solution.keys())
        rng.shuffle(cells)
        keep = rng.randint(10, 24)
        givens = {cell: solution[cell] for cell in cells[:keep]}
        domains = {var: set(range(1, 7)) for var in variables}
        for (row, col), value in givens.items():
            domains[row * 6 + col] = {value}
        trace = DPLLOracle().solve(variables, domains, constraints)
        depth = trace.max_backtrack_depth
        if trace.solved and min_depth <= depth <= max_depth:
            out.append(Sudoku6x6Instance(givens, solution, depth, trace))
    return out


def generate_6x6_by_depth(target_depth: Optional[int] = None, n_instances: int = 32, seed: int = 42) -> list[Sudoku6x6Instance]:
    if target_depth is None:
        return generate_6x6_by_depth_band(0, 8, n_instances, seed)
    return generate_6x6_by_depth_band(target_depth, target_depth, n_instances, seed)
