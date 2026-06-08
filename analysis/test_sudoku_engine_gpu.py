"""Equivalence checks for the batched 6x6 Sudoku candidate engine."""

from __future__ import annotations

import json
import random
from pathlib import Path

import torch

from llm_operator.symbolic_filter import CSPTask, forced_moves, propagation_fixpoint, status as scalar_status
from sudoku_engine_gpu import contradiction, forced_set, from_assignments, propagate, status, to_assignments
from tasks.sudoku.generator_6x6 import _full_solution, constraints_6x6


def _task() -> CSPTask:
    variables = list(range(36))
    domains = {cell: set(range(1, 7)) for cell in variables}
    return CSPTask("sudoku_6x6_equivalence", "sudoku_6x6", {}, variables, domains, constraints_6x6(), None, 0)


def _random_assignments(n_boards: int, seed: int) -> list[dict[int, int]]:
    rng = random.Random(seed)
    rows = []
    for index in range(n_boards):
        solution = _full_solution(rng)
        keep_probability = rng.uniform(0.05, 0.85)
        assignment = {row * 6 + col: value for (row, col), value in solution.items() if rng.random() < keep_probability}
        if index % 10 == 0:
            row = rng.randrange(6)
            col_a, col_b = rng.sample(range(6), 2)
            value = rng.randrange(1, 7)
            assignment[row * 6 + col_a] = value
            assignment[row * 6 + col_b] = value
        rows.append(assignment)
    return rows


def run(n_boards: int = 1000, seed: int = 20260608, device: str | None = None) -> dict:
    if device is None:
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    task = _task()
    assignments = _random_assignments(n_boards, seed)
    batch = from_assignments(assignments, device=device)
    initial_contradiction = contradiction(batch).detach().cpu()
    forced = forced_set(batch).detach().cpu()
    propagated = propagate(batch)
    gpu_status = status(propagated)
    gpu_assignments = to_assignments(propagated)
    mismatches = []
    for index, assignment in enumerate(assignments):
        scalar_initial_status = scalar_status(task, assignment)
        gpu_initial_contradiction = bool(initial_contradiction[index].item())
        if gpu_initial_contradiction != (scalar_initial_status == "CONTRADICTION"):
            mismatches.append({"index": index, "kind": "initial_contradiction", "expected": scalar_initial_status == "CONTRADICTION", "actual": gpu_initial_contradiction})
            continue
        scalar_forced = forced_moves(task, assignment)
        gpu_forced = {cell: int(forced[index, cell].item()) for cell in range(36) if int(forced[index, cell].item()) > 0}
        scalar_fixpoint, _, scalar_fixpoint_status = propagation_fixpoint(task, assignment)
        expected_status = scalar_status(task, scalar_fixpoint)
        if expected_status != scalar_fixpoint_status:
            mismatches.append({"index": index, "kind": "scalar_status_internal", "expected": expected_status, "actual": scalar_fixpoint_status})
            continue
        if gpu_forced != scalar_forced:
            mismatches.append({"index": index, "kind": "forced_set", "expected": scalar_forced, "actual": gpu_forced})
            continue
        if gpu_status[index] != scalar_fixpoint_status:
            mismatches.append({"index": index, "kind": "status", "expected": scalar_fixpoint_status, "actual": gpu_status[index]})
            continue
        if gpu_status[index] != "CONTRADICTION" and gpu_assignments[index] != scalar_fixpoint:
            mismatches.append({"index": index, "kind": "propagation_fixpoint", "expected": scalar_fixpoint, "actual": gpu_assignments[index]})
            continue
    result = {
        "name": "sudoku_engine_gpu_equivalence",
        "n_boards": n_boards,
        "seed": seed,
        "device": device,
        "passed": not mismatches,
        "mismatches": mismatches[:10],
        "n_mismatches": len(mismatches),
    }
    output_path = Path("results/sudoku_engine_gpu/equivalence_1000.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    payload = run()
    if not payload["passed"]:
        raise SystemExit(1)