"""No-LLM power calibration for externalization validation."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any, Callable

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_reasoning_gym_bounded_register import _ensure_reasoning_gym


SCHEMA_VERSION = "externalization_power_calibration_v0"
STATUS_COMPLETE = "EXTERNALIZATION_POWER_CALIBRATION_COMPLETE"


@dataclass
class CSPView:
    variables: list[int]
    domains: dict[int, list[int]]
    neighbors: dict[int, set[int]]
    givens: dict[int, int]
    answer: Callable[[dict[int, int]], str]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _unit(*parts: Any) -> float:
    digest = hashlib.blake2b("::".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(2**64)


def _graph_color_view(entry: dict[str, Any]) -> CSPView:
    puzzle = entry["metadata"]["puzzle"]
    variables = [int(vertex) for vertex in puzzle["vertices"]]
    neighbors = {variable: set() for variable in variables}
    for left, right in puzzle["edges"]:
        left = int(left)
        right = int(right)
        neighbors[left].add(right)
        neighbors[right].add(left)
    domains = {variable: [int(color) for color in puzzle["color_options"]] for variable in variables}

    def answer(assignment: dict[int, int]) -> str:
        return json.dumps({str(variable): int(assignment[variable]) for variable in sorted(variables)}, sort_keys=True)

    return CSPView(variables=variables, domains=domains, neighbors=neighbors, givens={}, answer=answer)


def _sudoku_view(entry: dict[str, Any]) -> CSPView:
    puzzle = entry["metadata"]["puzzle"]
    variables = list(range(81))
    givens = {9 * row + col: int(puzzle[row][col]) for row in range(9) for col in range(9) if int(puzzle[row][col]) != 0}
    neighbors = {variable: set() for variable in variables}
    for row in range(9):
        row_vars = [9 * row + col for col in range(9)]
        for variable in row_vars:
            neighbors[variable].update(other for other in row_vars if other != variable)
    for col in range(9):
        col_vars = [9 * row + col for row in range(9)]
        for variable in col_vars:
            neighbors[variable].update(other for other in col_vars if other != variable)
    for box_row in range(0, 9, 3):
        for box_col in range(0, 9, 3):
            box_vars = [9 * row + col for row in range(box_row, box_row + 3) for col in range(box_col, box_col + 3)]
            for variable in box_vars:
                neighbors[variable].update(other for other in box_vars if other != variable)
    domains = {variable: [givens[variable]] if variable in givens else list(range(1, 10)) for variable in variables}

    def answer(assignment: dict[int, int]) -> str:
        return "\n".join(" ".join(str(assignment[9 * row + col]) for col in range(9)) for row in range(9))

    return CSPView(variables=variables, domains=domains, neighbors=neighbors, givens=givens, answer=answer)


def _domain(view: CSPView, assignment: dict[int, int], variable: int) -> list[int]:
    blocked = {assignment[neighbor] for neighbor in view.neighbors[variable] if neighbor in assignment}
    return [value for value in view.domains[variable] if value not in blocked]


def _select_variable(view: CSPView, assignment: dict[int, int], arm: str, rng: random.Random) -> int | None:
    unassigned = [variable for variable in view.variables if variable not in assignment]
    if not unassigned:
        return None
    if arm == "random":
        return rng.choice(unassigned)
    return min(unassigned, key=lambda variable: (len(_domain(view, assignment, variable)), -len(view.neighbors[variable]), variable))


def _ordered_values(view: CSPView, assignment: dict[int, int], variable: int, arm: str, rng: random.Random) -> list[int]:
    values = _domain(view, assignment, variable)
    if arm == "random":
        values = list(values)
        rng.shuffle(values)
    return values


def _solve_budgeted(dataset: Any, entry: dict[str, Any], view: CSPView, arm: str, node_budget: int, seed_parts: tuple[Any, ...]) -> dict[str, Any]:
    rng = random.Random(int(_unit(*seed_parts, arm) * (2**32)))
    assignment = dict(view.givens)
    nodes = 0
    retractions = 0
    max_depth = len(assignment)

    def dfs() -> bool:
        nonlocal nodes, retractions, max_depth
        if nodes >= node_budget:
            return False
        variable = _select_variable(view, assignment, arm, rng)
        if variable is None:
            return True
        for value in _ordered_values(view, assignment, variable, arm, rng):
            if nodes >= node_budget:
                return False
            nodes += 1
            assignment[variable] = value
            max_depth = max(max_depth, len(assignment))
            if dfs():
                return True
            assignment.pop(variable, None)
            retractions += 1
        return False

    solved = dfs()
    score = 0.0
    status = "NODE_BUDGET"
    if solved:
        try:
            score = float(dataset.score_answer(view.answer(assignment), entry))
        except Exception:
            score = 0.0
        status = "SOLVED" if score >= 1.0 else "OFFICIAL_SCORE_FAIL"
    return {
        "arm": f"L0-symbolic-{arm}",
        "node_budget": node_budget,
        "status": status,
        "solved": score >= 1.0,
        "official_score": score,
        "nodes_visited": nodes,
        "retractions": retractions,
        "max_depth": max_depth,
        "source": SOURCE,
        "provenance": "externalization_l0_budgeted_csp_episode_v0",
    }


def _make_dataset(reasoning_gym: Any, benchmark: str, size: int, seed: int, config: dict[str, Any]) -> Any:
    if benchmark == "graph_color":
        return reasoning_gym.create_dataset("graph_color", size=size, seed=seed, num_colors=3, min_num_vertices=config["n_vertices"], max_num_vertices=config["n_vertices"], edge_probability=config["edge_probability"])
    if benchmark == "sudoku":
        return reasoning_gym.create_dataset("sudoku", size=size, seed=seed, min_empty=config["empty"], max_empty=config["empty"])
    if benchmark == "zebra_puzzles":
        return reasoning_gym.create_dataset("zebra_puzzles", size=size, seed=seed, num_people=config["num_people"], num_characteristics=config["num_characteristics"])
    raise ValueError(f"unknown benchmark {benchmark}")


def _view_for(benchmark: str, entry: dict[str, Any]) -> CSPView:
    if benchmark == "graph_color":
        return _graph_color_view(entry)
    if benchmark == "sudoku":
        return _sudoku_view(entry)
    raise NotImplementedError(f"{benchmark} adapter is not implemented in v0")


def _configs(args: argparse.Namespace) -> dict[str, list[dict[str, Any]]]:
    graph = []
    for n_vertices in args.graph_vertices:
        for edge_probability in args.graph_edge_probabilities:
            graph.append({"n_vertices": n_vertices, "edge_probability": edge_probability})
    return {
        "graph_color": graph,
        "sudoku": [{"empty": empty} for empty in args.sudoku_empty_values],
        "zebra_puzzles": [{"num_people": people, "num_characteristics": chars} for people in args.zebra_people for chars in args.zebra_characteristics],
    }


def _summarize_cell(rows: list[dict[str, Any]], benchmark: str, config: dict[str, Any], node_budget: int) -> list[dict[str, Any]]:
    out = []
    for arm in ["L0-symbolic-heuristic", "L0-symbolic-random"]:
        subset = [row for row in rows if row["arm"] == arm]
        out.append({
            "benchmark": benchmark,
            "config": config,
            "node_budget": node_budget,
            "arm": arm,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset) if subset else None,
            "mean_nodes_visited": mean(row["nodes_visited"] for row in subset) if subset else None,
            "mean_retractions": mean(row["retractions"] for row in subset) if subset else None,
            "status_counts": dict(Counter(row["status"] for row in subset)),
            "source": SOURCE,
            "provenance": "externalization_l0_power_cell_summary_v0",
        })
    return out


def _calibrate_benchmark(reasoning_gym: Any, benchmark: str, args: argparse.Namespace) -> dict[str, Any]:
    if benchmark == "zebra_puzzles":
        rows = []
        for config in _configs(args)[benchmark]:
            dataset = _make_dataset(reasoning_gym, benchmark, 2, args.seed, config)
            entry = dataset[0]
            rows.append({"benchmark": benchmark, "config": config, "status": "ADAPTER_PENDING", "score_answer_usable": float(dataset.score_answer(entry["answer"], entry)) >= 1.0, "reason": "RG zebra metadata does not expose structural constraints; v0 needs a generator-structure adapter or question parser before L0 power calibration.", "source": SOURCE, "provenance": "externalization_zebra_adapter_pending_v0"})
        return {"benchmark": benchmark, "status": "ADAPTER_PENDING", "adapter_rows": rows, "power_gate_pass": False, "source": SOURCE, "provenance": "externalization_l0_power_benchmark_v0"}

    summary_rows = []
    episode_rows = []
    for config_index, config in enumerate(_configs(args)[benchmark]):
        dataset = _make_dataset(reasoning_gym, benchmark, args.instances_per_cell, args.seed + 1000 * config_index, config)
        for node_budget in args.node_budgets:
            cell_rows = []
            for index in range(args.instances_per_cell):
                entry = dataset[index]
                view = _view_for(benchmark, entry)
                for arm in ["heuristic", "random"]:
                    row = _solve_budgeted(dataset, entry, view, arm, node_budget, (benchmark, config_index, index, node_budget, args.seed))
                    row |= {"benchmark": benchmark, "config": config, "source_index": index}
                    cell_rows.append(row)
            episode_rows.extend(cell_rows)
            summary_rows.extend(_summarize_cell(cell_rows, benchmark, config, node_budget))
    random_rows = [row for row in summary_rows if row["arm"] == "L0-symbolic-random"]
    passing = [row for row in random_rows if row.get("solve_rate") is not None and row["solve_rate"] < args.power_threshold]
    hardest = min(passing, key=lambda row: (row["solve_rate"], -row["node_budget"])) if passing else None
    return {
        "benchmark": benchmark,
        "status": "CALIBRATED" if hardest else "NO_POWER_BIN_FOUND",
        "power_gate_pass": hardest is not None,
        "power_threshold": args.power_threshold,
        "selected_hard_bin": hardest,
        "summary_rows": summary_rows,
        "episode_rows": episode_rows[: args.max_episode_rows],
        "source": SOURCE,
        "provenance": "externalization_l0_power_benchmark_v0",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.node_budgets = [int(item) for item in args.node_budgets.split(",") if item]
    args.graph_vertices = [int(item) for item in args.graph_vertices.split(",") if item]
    args.graph_edge_probabilities = [float(item) for item in args.graph_edge_probabilities.split(",") if item]
    args.sudoku_empty_values = [int(item) for item in args.sudoku_empty_values.split(",") if item]
    args.zebra_people = [int(item) for item in args.zebra_people.split(",") if item]
    args.zebra_characteristics = [int(item) for item in args.zebra_characteristics.split(",") if item]
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    benchmarks = [item for item in args.benchmarks.split(",") if item]
    results = [_calibrate_benchmark(reasoning_gym, benchmark, args) for benchmark in benchmarks]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "matched_node_budgets": args.node_budgets,
        "power_threshold": args.power_threshold,
        "benchmarks": results,
        "power_gates": {row["benchmark"]: {"gate": "PASS" if row["power_gate_pass"] else "NO_GO", "status": row["status"], "selected_hard_bin": row.get("selected_hard_bin")} for row in results},
        "headline": {
            "benchmarks_with_power_bins": [row["benchmark"] for row in results if row["power_gate_pass"]],
            "benchmarks_pending_adapters": [row["benchmark"] for row in results if row["status"] == "ADAPTER_PENDING"],
            "single_next_move": "Run LLM arms only for benchmarks with PASS power gates; implement zebra structural adapter before zebra LLM arms.",
        },
        "honesty": {
            "does_not_establish": "This is no-LLM power calibration only. It does not run M-register or L1 LLM arms and banks no externalization claim result.",
            "zebra_limit": "zebra_puzzles official scoring is available, but structural constraints are not exposed in RG metadata; L0 calibration is adapter-pending in this v0 artifact.",
            "source": SOURCE,
            "provenance": "externalization_power_calibration_honesty_v0",
        },
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run no-LLM Tier-1 power calibration.")
    parser.add_argument("--output", type=Path, default=Path("results/externalization_validation_v0/power_calibration.json"))
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--benchmarks", default="graph_color,sudoku,zebra_puzzles")
    parser.add_argument("--node-budgets", default="20,40,80,160,320")
    parser.add_argument("--instances-per-cell", type=int, default=12)
    parser.add_argument("--power-threshold", type=float, default=0.7)
    parser.add_argument("--graph-vertices", default="10,14,18")
    parser.add_argument("--graph-edge-probabilities", default="0.3,0.45,0.6")
    parser.add_argument("--sudoku-empty-values", default="35,45,55,60")
    parser.add_argument("--zebra-people", default="4,5,6")
    parser.add_argument("--zebra-characteristics", default="4,5,6")
    parser.add_argument("--max-episode-rows", type=int, default=240)
    run(parser.parse_args())


if __name__ == "__main__":
    main()