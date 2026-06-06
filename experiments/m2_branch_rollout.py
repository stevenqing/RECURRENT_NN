"""M2.0 branch heuristic rollout with symbolic propagation."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any

from llm_operator.qwen_operator import QwenGenerativeOperator
from llm_operator.symbolic_filter import build_tasks, mrv_guess, propagation_fixpoint, random_guess, status, valid_values


TASK_TYPES = ["horn_sat", "general_sat", "graph_coloring", "sudoku_4x4"]


def _valid_guess(task: Any, assignment: dict[int, int], guess: tuple[int, int] | None) -> tuple[int, int] | None:
    if guess is None:
        return None
    var, value = guess
    if var not in task.variables or var in assignment:
        return None
    return guess if value in valid_values(task, assignment, var) else None


def _search(task: Any, chooser: str, operator: QwenGenerativeOperator | None, cap_nodes: int, seed: int, batch_size: int) -> dict[str, Any]:
    rng = random.Random(seed)
    stack: list[dict[int, int]] = [{}]
    nodes = 0
    parse_failures = 0
    invalid_guesses = 0
    while stack and nodes < cap_nodes:
        assignment = stack.pop()
        assignment, _, node_status = propagation_fixpoint(task, assignment)
        nodes += 1
        if node_status == "SOLVED":
            return {"solved": True, "nodes": nodes, "parse_failures": parse_failures, "invalid_guesses": invalid_guesses}
        if node_status == "CONTRADICTION":
            continue
        if chooser == "mrv":
            guess = mrv_guess(task, assignment)
        elif chooser == "random":
            guess = random_guess(task, assignment, rng)
        else:
            assert operator is not None
            prediction = operator.predict(task, assignment, batch_size=batch_size)
            if not prediction.parse_success:
                parse_failures += 1
            guess = _valid_guess(task, assignment, prediction.guess)
            if guess is None:
                invalid_guesses += 1
                guess = mrv_guess(task, assignment)
        if guess is None:
            continue
        var, preferred = guess
        values = sorted(valid_values(task, assignment, var))
        ordered = [preferred] + [value for value in values if value != preferred]
        for value in reversed(ordered):
            stack.append({**assignment, var: value})
    return {"solved": False, "nodes": cap_nodes, "parse_failures": parse_failures, "invalid_guesses": invalid_guesses}


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_task[row["task_type"]].append(row)

    def subset_summary(subset: list[dict[str, Any]]) -> dict[str, Any]:
        out = {}
        for chooser in ["qwen_guess", "mrv", "random"]:
            chosen = [row for row in subset if row["chooser"] == chooser]
            out[chooser] = {
                "n": len(chosen),
                "solve_rate": sum(1 for row in chosen if row["solved"]) / len(chosen) if chosen else None,
                "mean_nodes_to_solve_or_cap": mean(row["nodes"] for row in chosen) if chosen else None,
                "parse_failures": sum(row["parse_failures"] for row in chosen),
                "invalid_guesses": sum(row["invalid_guesses"] for row in chosen),
            }
        return out

    return {"overall": subset_summary(rows), "by_task": {task: subset_summary(subset) for task, subset in sorted(by_task.items())}}


def run_rollout(output_dir: str, model_id: str, device: str, n_instances: int, seed: int, cap_nodes: int, batch_size: int) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(TASK_TYPES, n_instances=n_instances, seed=seed)
    operator = QwenGenerativeOperator(model_id=model_id, device=device)
    rows = []
    for task_index, task in enumerate(tasks):
        for chooser in ["qwen_guess", "mrv", "random"]:
            result = _search(task, chooser, operator if chooser == "qwen_guess" else None, cap_nodes, seed + task_index * 1009, batch_size)
            row = {"task_id": task.task_id, "task_type": task.task_type, "chooser": chooser, "cap_nodes": cap_nodes, **result}
            rows.append(row)
            print(json.dumps({"event": "m2_branch_rollout", **row}), flush=True)
    payload = {"module": "m2_branch_rollout", "model_id": model_id, "device": device, "task_types": TASK_TYPES, "n_instances": n_instances, "cap_nodes": cap_nodes, "rows": rows, "summary": _summarize(rows)}
    (out / "branch_rollout.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="results/m2_operator_probe")
    parser.add_argument("--model-id", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--n-instances", type=int, default=2)
    parser.add_argument("--seed", type=int, default=314)
    parser.add_argument("--cap-nodes", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(run_rollout(args.output_dir, args.model_id, args.device, args.n_instances, args.seed, args.cap_nodes, args.batch_size), indent=2, sort_keys=True))