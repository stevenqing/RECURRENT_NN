"""Equivalence checks for register.batched_ops Sudoku6 helpers."""

from __future__ import annotations

import json
from pathlib import Path

import torch

from llm_operator.symbolic_filter import CSPTask, forced_moves, propagation_fixpoint, status as scalar_status
from register.batched_ops import batched_apply_commits, batched_forced_values, batched_propagation_fixpoint
from tasks.sudoku.generator_6x6 import constraints_6x6, generate_6x6_by_depth_band


def _task() -> CSPTask:
    variables = list(range(36))
    domains = {cell: set(range(1, 7)) for cell in variables}
    return CSPTask("sudoku_6x6_batched_ops_equivalence", "sudoku_6x6", {}, variables, domains, constraints_6x6(), None, 0)


def _assignments(n_episodes: int, seed: int) -> list[dict[int, int]]:
    instances = generate_6x6_by_depth_band(min_depth=1, max_depth=2, n_instances=n_episodes, seed=seed)
    return [{row * 6 + col: value for (row, col), value in instance.givens.items()} for instance in instances]


def run(n_episodes: int = 100, seed: int = 20260608, device: str | None = None) -> dict:
    if device is None:
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    task = _task()
    assignments = _assignments(n_episodes, seed)
    forced_result = batched_forced_values(assignments, device=device)
    fixpoint_result = batched_propagation_fixpoint(assignments, device=device)
    scalar_forced = [forced_moves(task, assignment) for assignment in assignments]
    scalar_fixpoints = []
    scalar_statuses = []
    for assignment in assignments:
        fixpoint, _, fixpoint_status = propagation_fixpoint(task, assignment)
        scalar_fixpoints.append(fixpoint)
        scalar_statuses.append(fixpoint_status)
    scalar_one_step_commits = [{next(iter(row)): row[next(iter(row))]} if row else {} for row in scalar_forced]
    applied_commits = batched_apply_commits(assignments, scalar_one_step_commits, device=device)
    expected_after_commit = [{**assignment, **commit} for assignment, commit in zip(assignments, scalar_one_step_commits)]
    mismatches = []
    for index in range(len(assignments)):
        initial_status = scalar_status(task, assignments[index])
        if forced_result.statuses[index] != initial_status:
            mismatches.append({"index": index, "kind": "initial_status", "expected": initial_status, "actual": forced_result.statuses[index]})
            continue
        if forced_result.forced_values[index] != scalar_forced[index]:
            mismatches.append({"index": index, "kind": "forced_values", "expected": scalar_forced[index], "actual": forced_result.forced_values[index]})
            continue
        if fixpoint_result.statuses[index] != scalar_statuses[index]:
            mismatches.append({"index": index, "kind": "fixpoint_status", "expected": scalar_statuses[index], "actual": fixpoint_result.statuses[index]})
            continue
        if fixpoint_result.assignments[index] != scalar_fixpoints[index]:
            mismatches.append({"index": index, "kind": "fixpoint_assignment", "expected": scalar_fixpoints[index], "actual": fixpoint_result.assignments[index]})
            continue
        if applied_commits[index] != expected_after_commit[index]:
            mismatches.append({"index": index, "kind": "apply_commits", "expected": expected_after_commit[index], "actual": applied_commits[index]})
            continue
    result = {
        "name": "register_batched_ops_equivalence",
        "n_episodes_requested": n_episodes,
        "n_episodes_generated": len(assignments),
        "seed": seed,
        "device": device,
        "passed": not mismatches and len(assignments) == n_episodes,
        "n_mismatches": len(mismatches),
        "mismatches": mismatches[:10],
        "checks": ["forced_values", "initial_status", "propagation_fixpoint", "apply_commits"],
    }
    output_path = Path("results/batched_ops/equivalence_100.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    payload = run()
    if not payload["passed"]:
        raise SystemExit(1)