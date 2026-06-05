"""Build symbolic-oracle supervision examples for Stage D controllers."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import os
from typing import Any

from tasks.graph_coloring.generator import generate_graph_coloring
from tasks.logic_grid.generator import generate_logic_grid
from tasks.oracle.trace_generator import trace_to_examples
from tasks.sat.generators import generate_general_sat, generate_horn_sat
from tasks.sudoku.generator_4x4 import generate_4x4_by_depth


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _sat_givens(task: Any) -> dict[str, Any]:
    return {"n_vars": task.n_vars, "clauses": task.clauses}


def _sudoku_givens(task: Any) -> dict[str, Any]:
    return {f"{row},{col}": value for (row, col), value in task.givens.items()}


def _graph_givens(task: Any) -> dict[str, Any]:
    return {"n": task.n, "k": task.k, "edges": task.edges}


def _logic_grid_givens(task: Any) -> dict[str, Any]:
    return {"categories": task.categories, "clues": task.clues}


def _collect_tasks(seed: int) -> list[tuple[str, dict[str, Any], Any]]:
    tasks: list[tuple[str, dict[str, Any], Any]] = []
    tasks.extend(("horn_sat", _sat_givens(task), task) for task in generate_horn_sat(n_instances=8, seed=seed))
    tasks.extend(("general_sat", _sat_givens(task), task) for task in generate_general_sat(min_depth=1, n_instances=8, seed=seed))
    tasks.extend(("sudoku_4x4", _sudoku_givens(task), task) for task in generate_4x4_by_depth(n_instances=8, seed=seed))
    tasks.extend(("graph_coloring", _graph_givens(task), task) for task in generate_graph_coloring(n_instances=8, seed=seed))
    tasks.extend(("logic_grid", _logic_grid_givens(task), task) for task in generate_logic_grid(n_instances=8, seed=seed))
    return tasks


def build_oracle_dataset(output_dir: str = "results/oracle_dataset", seeds: list[int] | None = None) -> dict[str, Any]:
    if seeds is None:
        seeds = [42, 137, 256, 314, 999]
    os.makedirs(output_dir, exist_ok=True)
    jsonl_path = os.path.join(output_dir, "examples.jsonl")
    summary: dict[str, Any] = {
        "seeds": seeds,
        "n_tasks": 0,
        "n_examples": 0,
        "task_types": {},
        "max_backtrack_depth": 0,
        "supervision": "symbolic_oracle_trace",
    }
    with open(jsonl_path, "w", encoding="utf-8") as handle:
        for seed in seeds:
            for task_type, givens, task in _collect_tasks(seed):
                summary["n_tasks"] += 1
                summary["task_types"].setdefault(task_type, {"tasks": 0, "examples": 0})
                summary["task_types"][task_type]["tasks"] += 1
                summary["max_backtrack_depth"] = max(summary["max_backtrack_depth"], int(task.dpll_backtrack_depth))
                examples = trace_to_examples(task.oracle_trace, givens, task_type)
                for example_index, example in enumerate(examples):
                    row = _jsonable(example)
                    row["seed"] = seed
                    row["example_index"] = example_index
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
                summary["n_examples"] += len(examples)
                summary["task_types"][task_type]["examples"] += len(examples)
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
    return {"examples": jsonl_path, "summary": summary_path, **summary}


if __name__ == "__main__":
    print(json.dumps(build_oracle_dataset(), indent=2, sort_keys=True))