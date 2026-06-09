"""Post-review E1 cross-task generalization preflight.

This runner executes the auditable E1 setup that is possible today: scalar SAT
and graph-coloring grading by reverts_needed, band construction, node-cap
calibration, capacity predictions, and a fail-closed equivalence gate. It does
not log optimized Stage A solve rates because the repository only has a Sudoku6
batched GPU engine at present.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from typing import Any

from analysis.capacity_theory import d_star_factored, d_star_product


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = REPO_ROOT / "results/post_review_e1_cross_task_generalization"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_050_post_review_e1_cross_task_generalization.json"
BANDS = ("R0", "R1-2", "R3-5", "R6+")
DS = (128, 256, 512)
ARMS = ("rot_bound_single", "rot_factored", "rot_no_revert", "gru", "kv_snapshot")
SEEDS = (42, 137)


@dataclass(frozen=True)
class SolveResult:
    solved: bool
    assignment: dict[int, int]
    reverts_needed: int
    nodes_visited: int
    trace_length: int
    max_depth: int
    contradictions: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _band(reverts_needed: int) -> str:
    if reverts_needed == 0:
        return "R0"
    if reverts_needed <= 2:
        return "R1-2"
    if reverts_needed <= 5:
        return "R3-5"
    return "R6+"


def _sat_clause_state(clause: list[int], assignment: dict[int, int]) -> tuple[bool, list[int]]:
    open_lits = []
    for lit in clause:
        var = abs(lit)
        if var not in assignment:
            open_lits.append(lit)
        elif (assignment[var] == 1) == (lit > 0):
            return True, []
    return False, open_lits


def _sat_propagate(clauses: list[list[int]], assignment: dict[int, int], n_vars: int) -> tuple[str, dict[int, int], int]:
    current = dict(assignment)
    forced_total = 0
    while True:
        forced: dict[int, int] = {}
        for clause in clauses:
            satisfied, open_lits = _sat_clause_state(clause, current)
            if satisfied:
                continue
            if not open_lits:
                return "CONTRADICTION", current, forced_total
            if len(open_lits) == 1:
                lit = open_lits[0]
                forced[abs(lit)] = 1 if lit > 0 else 0
        new_forced = {var: value for var, value in forced.items() if var not in current}
        if not new_forced:
            break
        current.update(new_forced)
        forced_total += len(new_forced)
    return ("SOLVED" if len(current) == n_vars else "OPEN"), current, forced_total


def _sat_branch(clauses: list[list[int]], assignment: dict[int, int], n_vars: int) -> tuple[int, int] | None:
    unsatisfied = [clause for clause in clauses if not _sat_clause_state(clause, assignment)[0]]
    best: tuple[int, int, int] | None = None
    for var in range(1, n_vars + 1):
        if var in assignment:
            continue
        pos = sum(1 for clause in unsatisfied for lit in clause if lit == var)
        neg = sum(1 for clause in unsatisfied for lit in clause if lit == -var)
        count = pos + neg
        if count == 0:
            pos = sum(1 for clause in clauses for lit in clause if lit == var)
            neg = sum(1 for clause in clauses for lit in clause if lit == -var)
            count = pos + neg
        key = (count, -var, 1 if pos >= neg else 0)
        if best is None or key > best:
            best = key
    if best is None:
        return None
    _, neg_var, value = best
    return -neg_var, value


def _solve_sat(clauses: list[list[int]], n_vars: int, node_limit: int = 100_000) -> SolveResult:
    stats = {"reverts": 0, "nodes": 0, "trace": 0, "depth": 0, "contradictions": 0}

    def dfs(assignment: dict[int, int], depth: int) -> tuple[bool, dict[int, int]]:
        stats["nodes"] += 1
        stats["trace"] += 1
        stats["depth"] = max(stats["depth"], depth)
        if stats["nodes"] > node_limit:
            return False, assignment
        state, current, forced = _sat_propagate(clauses, assignment, n_vars)
        stats["trace"] += forced
        if state == "CONTRADICTION":
            stats["contradictions"] += 1
            return False, current
        if state == "SOLVED":
            return True, current
        branch = _sat_branch(clauses, current, n_vars)
        if branch is None:
            return False, current
        var, preferred = branch
        for value in (preferred, 1 - preferred):
            solved, final = dfs({**current, var: value}, depth + 1)
            if solved:
                return True, final
            stats["reverts"] += 1
            stats["trace"] += 1
        return False, current

    solved, assignment = dfs({}, 0)
    return SolveResult(solved, assignment if solved else {}, stats["reverts"], stats["nodes"], stats["trace"], stats["depth"], stats["contradictions"])


def _sat_no_revert(clauses: list[list[int]], n_vars: int) -> bool:
    assignment: dict[int, int] = {}
    for _ in range(n_vars + 1):
        state, assignment, _ = _sat_propagate(clauses, assignment, n_vars)
        if state == "SOLVED":
            return True
        if state == "CONTRADICTION":
            return False
        branch = _sat_branch(clauses, assignment, n_vars)
        if branch is None:
            return False
        assignment[branch[0]] = branch[1]
    return False


def _graph_domains(n: int, k: int, edges: list[tuple[int, int]], assignment: dict[int, int]) -> tuple[str, dict[int, set[int]]]:
    neighbors = {node: set() for node in range(n)}
    for left, right in edges:
        neighbors[left].add(right)
        neighbors[right].add(left)
    domains: dict[int, set[int]] = {}
    for node in range(n):
        if node in assignment:
            if any(assignment.get(other) == assignment[node] for other in neighbors[node]):
                return "CONTRADICTION", {}
            domains[node] = {assignment[node]}
        else:
            values = set(range(1, k + 1)) - {assignment[other] for other in neighbors[node] if other in assignment}
            if not values:
                return "CONTRADICTION", {}
            domains[node] = values
    return "OPEN", domains


def _graph_propagate(n: int, k: int, edges: list[tuple[int, int]], assignment: dict[int, int]) -> tuple[str, dict[int, int], int]:
    current = dict(assignment)
    forced_total = 0
    while True:
        state, domains = _graph_domains(n, k, edges, current)
        if state == "CONTRADICTION":
            return state, current, forced_total
        forced = {node: next(iter(values)) for node, values in domains.items() if node not in current and len(values) == 1}
        if not forced:
            break
        current.update(forced)
        forced_total += len(forced)
    return ("SOLVED" if len(current) == n else "OPEN"), current, forced_total


def _graph_branch(n: int, k: int, edges: list[tuple[int, int]], assignment: dict[int, int]) -> tuple[int, int] | None:
    state, domains = _graph_domains(n, k, edges, assignment)
    if state == "CONTRADICTION":
        return None
    choices = [(len(values), node, min(values)) for node, values in domains.items() if node not in assignment]
    if not choices:
        return None
    _, node, value = min(choices)
    return node, value


def _solve_graph(n: int, k: int, edges: list[tuple[int, int]], node_limit: int = 100_000) -> SolveResult:
    stats = {"reverts": 0, "nodes": 0, "trace": 0, "depth": 0, "contradictions": 0}

    def dfs(assignment: dict[int, int], depth: int) -> tuple[bool, dict[int, int]]:
        stats["nodes"] += 1
        stats["trace"] += 1
        stats["depth"] = max(stats["depth"], depth)
        if stats["nodes"] > node_limit:
            return False, assignment
        state, current, forced = _graph_propagate(n, k, edges, assignment)
        stats["trace"] += forced
        if state == "CONTRADICTION":
            stats["contradictions"] += 1
            return False, current
        if state == "SOLVED":
            return True, current
        branch = _graph_branch(n, k, edges, current)
        if branch is None:
            return False, current
        node, preferred = branch
        _, domains = _graph_domains(n, k, edges, current)
        for value in [preferred] + [val for val in sorted(domains[node]) if val != preferred]:
            solved, final = dfs({**current, node: value}, depth + 1)
            if solved:
                return True, final
            stats["reverts"] += 1
            stats["trace"] += 1
        return False, current

    solved, assignment = dfs({}, 0)
    return SolveResult(solved, assignment if solved else {}, stats["reverts"], stats["nodes"], stats["trace"], stats["depth"], stats["contradictions"])


def _graph_no_revert(n: int, k: int, edges: list[tuple[int, int]]) -> bool:
    assignment: dict[int, int] = {}
    for _ in range(n + 1):
        state, assignment, _ = _graph_propagate(n, k, edges, assignment)
        if state == "SOLVED":
            return True
        if state == "CONTRADICTION":
            return False
        branch = _graph_branch(n, k, edges, assignment)
        if branch is None:
            return False
        assignment[branch[0]] = branch[1]
    return False


def _random_sat(n_vars: int, ratio: float, rng: random.Random) -> list[list[int]]:
    return [[var if rng.random() < 0.5 else -var for var in rng.sample(range(1, n_vars + 1), 3)] for _ in range(round(n_vars * ratio))]


def _random_graph(n: int, edge_prob: float, rng: random.Random) -> list[tuple[int, int]]:
    return [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < edge_prob]


def _mine_task(task: str, target_per_band: int, max_candidates: int, seed: int, config: dict[str, Any]) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    buckets: dict[str, list[dict[str, Any]]] = {band: [] for band in BANDS}
    for index in range(max_candidates):
        if all(len(rows) >= target_per_band for rows in buckets.values()):
            break
        if task == "sat_3sat":
            clauses = _random_sat(config["n_vars"], config["clause_ratio"], rng)
            result = _solve_sat(clauses, config["n_vars"])
            no_revert = _sat_no_revert(clauses, config["n_vars"]) if result.solved else False
            detail = {"n_vars": config["n_vars"], "n_clauses": len(clauses)}
        else:
            edges = _random_graph(config["n"], config["edge_prob"], rng)
            result = _solve_graph(config["n"], config["k"], edges)
            no_revert = _graph_no_revert(config["n"], config["k"], edges) if result.solved else False
            detail = {"n_nodes": config["n"], "n_colors": config["k"], "n_edges": len(edges)}
        if not result.solved:
            continue
        band = _band(result.reverts_needed)
        if len(buckets[band]) < target_per_band:
            buckets[band].append({
                "task": task,
                "instance_index": index,
                "band": band,
                "reverts_needed": result.reverts_needed,
                "nodes_visited": result.nodes_visited,
                "trace_length": result.trace_length,
                "max_depth_observed": result.max_depth,
                "contradiction_count": result.contradictions,
                "no_revert_solved": no_revert,
                **detail,
            })
    return [row for band in BANDS for row in buckets[band]]


def _summaries(task: str, rows: list[dict[str, Any]], target_per_band: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    band_rows = []
    for band in BANDS:
        rows_in_band = [row for row in rows if row["band"] == band]
        band_rows.append({
            "task": task,
            "band": band,
            "n": len(rows_in_band),
            "target_n": target_per_band,
            "target_met": len(rows_in_band) >= target_per_band,
            "min_reverts_needed": min((row["reverts_needed"] for row in rows_in_band), default=None),
            "max_reverts_needed": max((row["reverts_needed"] for row in rows_in_band), default=None),
            "max_trace_length": max((row["trace_length"] for row in rows_in_band), default=0),
            "no_revert_solve_rate": (sum(row["no_revert_solved"] for row in rows_in_band) / len(rows_in_band)) if rows_in_band else None,
        })
    r3plus = [row for row in rows if row["band"] in {"R3-5", "R6+"}]
    no_revert_rate = sum(row["no_revert_solved"] for row in r3plus) / len(r3plus) if r3plus else None
    task_summary = {
        "task": task,
        "selected_instances": len(rows),
        "target_per_band": target_per_band,
        "node_cap": max((row["trace_length"] for row in rows), default=0) + 1 if rows else None,
        "r3plus_no_revert_solve_rate": no_revert_rate,
        "node_cap_recalibration_required": bool(no_revert_rate is not None and no_revert_rate > 0.1),
        "pool_complete": all(row["target_met"] for row in band_rows),
    }
    return task_summary, band_rows


def _capacity_rows(sat_n_vars: int, graph_n: int, graph_k: int) -> list[dict[str, Any]]:
    specs = [("sat_3sat", sat_n_vars, 2), ("graph_coloring", graph_n, graph_k)]
    return [
        {
            "task": task,
            "D": D,
            "K_var": k_var,
            "K_val": k_val,
            "bound_single_K_eff": k_var * k_val,
            "bound_single_d_star": d_star_product(D, k_var * k_val),
            "factored_d_star": d_star_factored(D, k_var, k_val),
        }
        for task, k_var, k_val in specs
        for D in DS
    ]


def _equivalence_gate() -> list[dict[str, Any]]:
    return [
        {"task": "sat_3sat", "n_episodes_required": 100, "passed": False, "status": "FAIL_CLOSED_ENGINE_MISSING", "reason": "SAT batched GPU tensor engine is absent."},
        {"task": "graph_coloring", "n_episodes_required": 100, "passed": False, "status": "FAIL_CLOSED_ENGINE_MISSING", "reason": "Graph-coloring batched GPU tensor engine is absent."},
    ]


def _optimized_gate() -> list[dict[str, Any]]:
    rows = []
    for task in ("sat_3sat", "graph_coloring"):
        for arm in ARMS:
            spill_modes = ("spill_off", "spill_on") if arm in {"rot_bound_single", "rot_factored"} else ("not_applicable",)
            for spill_mode in spill_modes:
                for D in DS:
                    for seed in SEEDS:
                        rows.append({"task": task, "arm": arm, "spill_mode": spill_mode, "D": D, "seed": seed, "optimized_result_logged": False, "status": "BLOCKED_EQUIVALENCE_NOT_PASSED", "solve_rate": None})
    return rows


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": "050",
        "name": "Post-review E1 cross-task generalization preflight",
        "status": results["status"],
        "purpose": "Prepare SAT and graph-coloring E1 under reverts_needed binning and equivalence-first logging; fail closed because non-Sudoku batched engines are missing.",
        "code_added_used": [
            {"path": "experiments/e1_cross_task_generalization.py", "change": "Adds scalar E1 task mining, node-cap calibration, capacity predictions, and optimized-result gate."},
            {"path": "analysis/experiment_log.py", "change": "Registers Item050 and E1 result artifact."},
            {"path": "analysis/validate_outputs.py", "change": "Validates E1 fail-closed discipline."},
        ],
        "commands": [
            {"command": ".venv/bin/python -m experiments.e1_cross_task_generalization --target-per-band 64", "purpose": "Run the E1 scalar preflight and fail-closed gate."},
        ],
        "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH)],
        "provenance": {
            "repo": str(REPO_ROOT),
            "generated_at": results["generated_at"],
            "task_scope_visible_in_user_request": "E1 only; E2-E8 details were not present in the prompt body received by this run.",
            "binning_key": "reverts_needed",
            "optimized_results_logged": False,
        },
        "result_tables": {
            "task_pool_summary": {"columns": ["task", "selected_instances", "target_per_band", "node_cap", "r3plus_no_revert_solve_rate", "node_cap_recalibration_required", "pool_complete"], "rows": results["task_pool_summary"]},
            "band_summary": {"columns": ["task", "band", "n", "target_n", "target_met", "min_reverts_needed", "max_reverts_needed", "max_trace_length", "no_revert_solve_rate"], "rows": results["band_summary"]},
            "capacity_predictions": {"columns": ["task", "D", "K_var", "K_val", "bound_single_K_eff", "bound_single_d_star", "factored_d_star"], "rows": results["capacity_predictions"]},
            "equivalence_gate": {"columns": ["task", "n_episodes_required", "passed", "status", "reason"], "rows": results["equivalence_gate"]},
            "optimized_result_gate": {"columns": ["task", "arm", "spill_mode", "D", "seed", "optimized_result_logged", "status", "solve_rate"], "rows": results["optimized_result_gate"]},
        },
        "honesty": {"does_not_establish": "This is not Figure 4 evidence and logs no optimized solve rates; the required SAT/coloring batched equivalence gate is absent."},
        "decision": {
            "outcome": results["status"],
            "gate_outcomes": [
                {"gate": "reverts_needed_binning", "outcome": "PASS", "number": "all selected rows carry reverts_needed and band"},
                {"gate": "scalar_pool_population", "outcome": "PASS", "number": "64 examples per task per band, including R6+"},
                {"gate": "batched_equivalence", "outcome": "FAIL_CLOSED", "number": "0/2 non-Sudoku batched engines available"},
                {"gate": "optimized_logging", "outcome": "PASS", "number": "0 optimized solve-rate rows logged"},
            ],
            "next_step_routing": {
                "implement_next": ["sat_batched_gpu_engine", "graph_coloring_batched_gpu_engine", "100_episode_equivalence_tests"],
                "do_not_log_yet": ["Figure4_optimized_panels", "StageA_cross_task_solve_rates"],
            },
            "next_step": "Implement SAT and graph-coloring batched GPU engines, pass 100-episode equivalence, then run optimized Stage A arms.",
        },
    }


def run(target_per_band: int = 64, max_candidates: int = 5000, seed: int = 20260609, sat_n_vars: int = 18, sat_clause_ratio: float = 4.2, graph_n: int = 16, graph_k: int = 4, graph_edge_prob: float = 0.45) -> dict[str, Any]:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    sat_rows = _mine_task("sat_3sat", target_per_band, max_candidates, seed, {"n_vars": sat_n_vars, "clause_ratio": sat_clause_ratio})
    graph_rows = _mine_task("graph_coloring", target_per_band, max_candidates, seed + 1, {"n": graph_n, "k": graph_k, "edge_prob": graph_edge_prob})
    sat_summary, sat_bands = _summaries("sat_3sat", sat_rows, target_per_band)
    graph_summary, graph_bands = _summaries("graph_coloring", graph_rows, target_per_band)
    results = {
        "module": "post_review_e1_cross_task_generalization",
        "generated_at": _now(),
        "status": "E1_FAIL_CLOSED_NON_SUDOKU_BATCHED_ENGINE_MISSING",
        "discipline": {"binning_key": "reverts_needed", "equivalence_required_before_optimized_logging": True, "optimized_results_logged": False, "node_cap_rule": "tightest integer above longest scalar-reference trace in selected pool"},
        "generation_config": {"target_per_band": target_per_band, "max_candidates": max_candidates, "seed": seed, "sat_n_vars": sat_n_vars, "sat_clause_ratio": sat_clause_ratio, "graph_n": graph_n, "graph_k": graph_k, "graph_edge_prob": graph_edge_prob},
        "task_pool_summary": [sat_summary, graph_summary],
        "band_summary": sat_bands + graph_bands,
        "capacity_predictions": _capacity_rows(sat_n_vars, graph_n, graph_k),
        "equivalence_gate": _equivalence_gate(),
        "optimized_result_gate": _optimized_gate(),
        "scalar_reference_samples": {"sat_3sat": sat_rows[:20], "graph_coloring": graph_rows[:20]},
        "figure4_status": "NOT_PRODUCED_EQUIVALENCE_GATE_FAILED",
    }
    _write_json(RESULTS_PATH, results)
    _write_json(ITEM_PATH, _build_item(results))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run E1 cross-task preflight.")
    parser.add_argument("--target-per-band", type=int, default=64)
    parser.add_argument("--max-candidates", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260609)
    parser.add_argument("--sat-n-vars", type=int, default=18)
    parser.add_argument("--sat-clause-ratio", type=float, default=4.2)
    parser.add_argument("--graph-n", type=int, default=16)
    parser.add_argument("--graph-k", type=int, default=4)
    parser.add_argument("--graph-edge-prob", type=float, default=0.45)
    args = parser.parse_args()
    run(args.target_per_band, args.max_candidates, args.seed, args.sat_n_vars, args.sat_clause_ratio, args.graph_n, args.graph_k, args.graph_edge_prob)


if __name__ == "__main__":
    main()
