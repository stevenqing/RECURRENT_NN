"""No-LLM multi-agent graph_color solvability and capacity readout."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_multiagent_graphcolor import _partition, _partition_stats, _agent_order
from experiments.rung1_reasoning_gym_bounded_register import _ensure_reasoning_gym, _graph_color_view, _official_answer, _official_score


SCHEMA_VERSION = "rung1_multiagent_solvability_v0"
STATUS_COMPLETE = "RUNG1_MULTIAGENT_SOLVABILITY_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        display_path = _rel(path)
    except ValueError:
        display_path = str(path)
    print(json.dumps({"path": display_path, "status": payload.get("status")}), flush=True)


def _make_dataset(args: argparse.Namespace, size: int, seed: int, n_vertices: int, edge_probability: float) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    return reasoning_gym.create_dataset(
        "graph_color",
        size=size,
        seed=seed,
        num_colors=args.num_colors,
        min_num_vertices=n_vertices,
        max_num_vertices=n_vertices,
        edge_probability=edge_probability,
    )


def _same_owner_domain(view: dict[str, Any], owner: dict[int, int], vertex: int, assignment: dict[int, int]) -> list[int]:
    blocked = {assignment[neighbor] for neighbor in view["adjacency"][vertex] if neighbor in assignment and owner[neighbor] == owner[vertex]}
    return [color for color in view["color_options"] if color not in blocked]


def _same_owner_blockers(view: dict[str, Any], owner: dict[int, int], vertex: int, assignment: dict[int, int]) -> set[int]:
    return {neighbor for neighbor in view["adjacency"][vertex] if neighbor in assignment and owner[neighbor] == owner[vertex]}


def _cross_conflicts(view: dict[str, Any], owner: dict[int, int], assignment: dict[int, int], vertex: int) -> set[int]:
    return {
        neighbor
        for neighbor in view["adjacency"][vertex]
        if neighbor in assignment and owner[neighbor] != owner[vertex] and assignment[neighbor] == assignment[vertex]
    }


def _max_owner_live(assignment: dict[int, int], owner: dict[int, int]) -> int:
    counts = Counter(owner[vertex] for vertex in assignment)
    return max(counts.values(), default=0)


def _block_size_max(owner: dict[int, int]) -> int:
    return max(Counter(owner.values()).values(), default=0)


def _undo_range(
    order: list[int],
    start_idx: int,
    stop_idx: int,
    assignment: dict[int, int],
    next_idx: dict[int, int],
    reset_start: bool,
) -> int:
    undone = 0
    for idx in range(start_idx, stop_idx + 1):
        vertex = order[idx]
        if vertex in assignment:
            undone += 1
            assignment.pop(vertex, None)
        if idx > start_idx or reset_start:
            next_idx[vertex] = 0
    return undone


def _row(
    dataset: Any,
    entry: dict[str, Any],
    view: dict[str, Any],
    owner: dict[int, int],
    arm: str,
    status: str,
    assignment: dict[int, int],
    node_budget: int,
    register_limit: int,
    decisions: int,
    retractions: int,
    recoveries: int,
    distances: list[int],
    conflict_distances: list[int],
    max_live: int,
) -> dict[str, Any]:
    score = _official_score(dataset, entry, assignment)
    return {
        "source_index": int(entry["metadata"].get("source_index", -1)),
        "arm": arm,
        "B": len(set(owner.values())),
        "register_limit": register_limit,
        "node_budget": node_budget,
        "status": status,
        "official_score": score,
        "solved": score >= 1.0,
        "decision_calls": decisions,
        "retractions": retractions,
        "total_work": decisions + retractions,
        "recoveries": recoveries,
        "mean_culprit_distance": mean(distances) if distances else 0.0,
        "max_culprit_distance": max(distances or [0]),
        "n_gt1_culprit_distance": sum(1 for distance in distances if distance > 1),
        "max_conflict_distance": max(conflict_distances or [0]),
        "max_owner_live": max_live,
        "answer": _official_answer(assignment) if score >= 1.0 else None,
        "source": SOURCE,
        "provenance": "complete_chrono_cbj_budgeted_search_v0",
    }


def _budgeted_search(
    dataset: Any,
    entry: dict[str, Any],
    owner: dict[int, int],
    arm: str,
    node_budget: int,
    register_limit: int,
    agent_order: str,
) -> dict[str, Any]:
    view = _graph_color_view(entry, "degree_desc")
    order = _agent_order(view, owner, agent_order)
    position = {vertex: idx for idx, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    next_idx = {vertex: 0 for vertex in order}
    cursor = 0
    decisions = 0
    retractions = 0
    recoveries = 0
    distances: list[int] = []
    conflict_distances: list[int] = []
    max_live = 0

    while True:
        if cursor < 0:
            return _row(dataset, entry, view, owner, arm, "EXHAUSTED", assignment, node_budget, register_limit, decisions, retractions, recoveries, distances, conflict_distances, max_live)
        if cursor >= len(order):
            score = _official_score(dataset, entry, assignment)
            status = "SOLVED" if score >= 1.0 else "OFFICIAL_SCORE_FAIL"
            return _row(dataset, entry, view, owner, arm, status, assignment, node_budget, register_limit, decisions, retractions, recoveries, distances, conflict_distances, max_live)
        if decisions >= node_budget:
            return _row(dataset, entry, view, owner, arm, "NODE_BUDGET", assignment, node_budget, register_limit, decisions, retractions, recoveries, distances, conflict_distances, max_live)

        vertex = order[cursor]
        if vertex in assignment:
            cursor += 1
            continue

        domain = set(_same_owner_domain(view, owner, vertex, assignment))
        chosen = None
        while next_idx[vertex] < len(view["color_options"]):
            color = view["color_options"][next_idx[vertex]]
            next_idx[vertex] += 1
            if color in domain:
                chosen = color
                break

        if chosen is None:
            next_idx[vertex] = 0
            blockers = _same_owner_blockers(view, owner, vertex, assignment)
            if arm == "cbj" and blockers:
                target_idx = max(position[blocker] for blocker in blockers)
            else:
                target_idx = cursor - 1
            if target_idx < 0:
                return _row(dataset, entry, view, owner, arm, "EXHAUSTED", assignment, node_budget, register_limit, decisions, retractions, recoveries, distances, conflict_distances, max_live)
            distance = max(1, cursor - target_idx)
            recoveries += 1
            distances.append(distance if arm == "cbj" else 1)
            undone = _undo_range(order, target_idx, cursor - 1, assignment, next_idx, reset_start=False)
            retractions += undone
            cursor = target_idx
            continue

        assignment[vertex] = chosen
        decisions += 1
        max_live = max(max_live, _max_owner_live(assignment, owner))
        if max_live > register_limit:
            return _row(dataset, entry, view, owner, arm, "REGISTER_LIMIT", assignment, node_budget, register_limit, decisions, retractions, recoveries, distances, conflict_distances, max_live)

        conflicts = _cross_conflicts(view, owner, assignment, vertex)
        if conflicts:
            farthest_conflict_idx = min(position[conflict] for conflict in conflicts)
            latest_conflict_idx = max(position[conflict] for conflict in conflicts)
            conflict_distances.append(cursor - farthest_conflict_idx)
            recoveries += 1
            if arm == "chrono":
                distances.append(1)
                assignment.pop(vertex, None)
                retractions += 1
                continue
            target_idx = latest_conflict_idx
            distance = max(1, cursor - target_idx)
            distances.append(distance)
            undone = _undo_range(order, target_idx, cursor, assignment, next_idx, reset_start=False)
            retractions += undone
            cursor = target_idx
            continue

        cursor += 1


def _summarize_rows(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    summary = []
    key_values = sorted({tuple(row[key] for key in keys) for row in rows})
    for values in key_values:
        subset = [row for row in rows if tuple(row[key] for key in keys) == values]
        item = {key: value for key, value in zip(keys, values)}
        both_solve_work = [row["total_work"] for row in subset if row["solved"]]
        item |= {
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_total_work": mean(row["total_work"] for row in subset),
            "mean_solved_total_work": mean(both_solve_work) if both_solve_work else None,
            "mean_recoveries": mean(row["recoveries"] for row in subset),
            "max_culprit_distance": max(row["max_culprit_distance"] for row in subset),
            "max_conflict_distance": max(row["max_conflict_distance"] for row in subset),
            "status_counts": dict(Counter(row["status"] for row in subset)),
            "source": SOURCE,
            "provenance": "multiagent_solvability_summary_v0",
        }
        summary.append(item)
    return summary


def _chrono_completeness(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _make_dataset(args, args.chrono_small_scan, args.seed + 101, args.chrono_small_vertices, args.chrono_small_edge_probability)
    rows = []
    for index in range(args.chrono_small_scan):
        entry = dataset[index]
        view = _graph_color_view(entry, "degree_desc")
        owner = {vertex: 0 for vertex in view["vertices"]}
        rows.append(_budgeted_search(dataset, entry, owner, "chrono", args.chrono_small_budget, args.chrono_small_vertices, "degree_owner"))
    pass_check = all(row["solved"] and row["status"] == "SOLVED" for row in rows)
    return {
        "verified_on_small_sat": pass_check,
        "n": len(rows),
        "budget": args.chrono_small_budget,
        "n_vertices": args.chrono_small_vertices,
        "edge_probability": args.chrono_small_edge_probability,
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "solve_rate": mean(float(row["solved"]) for row in rows) if rows else 0.0,
        "rows": rows,
        "source": SOURCE,
        "provenance": "chrono_completeness_small_sat_v0",
    }


def _distant_instances(args: argparse.Namespace) -> tuple[Any, list[dict[str, Any]]]:
    dataset = _make_dataset(args, args.claim3_scan, args.seed + 777, args.claim3_vertices, args.claim3_edge_probability)
    selected = []
    for index in range(args.claim3_scan):
        entry = dataset[index]
        view = _graph_color_view(entry, "degree_desc")
        for b_value in args.claim3_b_values:
            owner = _partition(view, b_value, args.balance_weight, args.seed + index)
            probe = _budgeted_search(dataset, entry, owner, "cbj", args.claim3_probe_budget, args.claim3_register, args.agent_order)
            if probe["max_culprit_distance"] > 1 or probe["max_conflict_distance"] > 1:
                selected.append({"source_index": index, "B": b_value, "owner": owner, "probe": probe, "partition": _partition_stats(view, owner)})
        if len(selected) >= args.claim3_min_instances:
            break
    return dataset, selected[: args.claim3_min_instances]


def _claim3_solvability(args: argparse.Namespace, chrono: dict[str, Any]) -> dict[str, Any]:
    dataset, selected = _distant_instances(args)
    rows = []
    pairs = []
    if chrono["verified_on_small_sat"]:
        for item in selected:
            entry = dataset[item["source_index"]]
            for budget in args.claim3_budgets:
                cbj = _budgeted_search(dataset, entry, item["owner"], "cbj", budget, args.claim3_register, args.agent_order)
                chrono_row = _budgeted_search(dataset, entry, item["owner"], "chrono", budget, args.claim3_register, args.agent_order)
                rows.extend([cbj, chrono_row])
                both_solve = cbj["solved"] and chrono_row["solved"]
                pairs.append(
                    {
                        "source_index": item["source_index"],
                        "B": item["B"],
                        "node_budget": budget,
                        "distant_culprit_verified": item["probe"]["max_culprit_distance"] > 1 or item["probe"]["max_conflict_distance"] > 1,
                        "probe_max_culprit_distance": item["probe"]["max_culprit_distance"],
                        "probe_max_conflict_distance": item["probe"]["max_conflict_distance"],
                        "cbj_solved": cbj["solved"],
                        "chrono_solved": chrono_row["solved"],
                        "cbj_status": cbj["status"],
                        "chrono_status": chrono_row["status"],
                        "cbj_total_work": cbj["total_work"],
                        "chrono_total_work": chrono_row["total_work"],
                        "both_solve": both_solve,
                        "both_solve_work_invariant": (cbj["total_work"] <= chrono_row["total_work"]) if both_solve else None,
                        "source": SOURCE,
                        "provenance": "claim3_solvability_pair_v0",
                    }
                )

    budget_summary = []
    for budget in args.claim3_budgets:
        for arm in ["cbj", "chrono"]:
            subset = [row for row in rows if row["node_budget"] == budget and row["arm"] == arm]
            if subset:
                budget_summary.append(
                    {
                        "node_budget": budget,
                        "arm": arm,
                        "n": len(subset),
                        "solve_rate": mean(float(row["solved"]) for row in subset),
                        "mean_total_work": mean(row["total_work"] for row in subset),
                        "status_counts": dict(Counter(row["status"] for row in subset)),
                        "source": SOURCE,
                        "provenance": "claim3_budget_sweep_summary_v0",
                    }
                )
    separation_pairs = [pair for pair in pairs if pair["cbj_solved"] and not pair["chrono_solved"]]
    both_solve_pairs = [pair for pair in pairs if pair["both_solve"]]
    both_solve_invariant_pass = all(pair["both_solve_work_invariant"] for pair in both_solve_pairs) if both_solve_pairs else None
    if not chrono["verified_on_small_sat"]:
        verdict = "chrono_still_incomplete"
    elif separation_pairs:
        verdict = "solvability_positive"
    elif both_solve_pairs:
        verdict = "both_solve_efficiency"
    else:
        verdict = "chrono_still_incomplete"
    return {
        "selected_distant_instances": [
            {
                "source_index": item["source_index"],
                "B": item["B"],
                "probe_status": item["probe"]["status"],
                "probe_solved": item["probe"]["solved"],
                "probe_max_culprit_distance": item["probe"]["max_culprit_distance"],
                "probe_max_conflict_distance": item["probe"]["max_conflict_distance"],
                "partition": item["partition"],
                "source": SOURCE,
                "provenance": "claim3_distant_instance_v0",
            }
            for item in selected
        ],
        "budget_sweep": budget_summary,
        "rows": rows,
        "pairs": pairs,
        "n_separation_pairs": len(separation_pairs),
        "n_both_solve_pairs": len(both_solve_pairs),
        "both_solve_work_invariant_pass": both_solve_invariant_pass,
        "both_solve_efficiency_pass": bool(both_solve_pairs) and bool(both_solve_invariant_pass),
        "claim3_positive": bool(separation_pairs) or (bool(both_solve_pairs) and bool(both_solve_invariant_pass)),
        "claim3_verdict": verdict,
        "source": SOURCE,
        "provenance": "track2_claim3_solve_rate_under_budget_v0",
    }


def _capacity_search(args: argparse.Namespace) -> dict[str, Any]:
    cells = []
    intersection_rows = []
    for n_vertices in args.capacity_vertices:
        dataset = _make_dataset(args, args.capacity_scan, args.seed + n_vertices, n_vertices, args.capacity_edge_probability)
        for register_limit in args.capacity_registers:
            for b_value in args.capacity_b_values:
                rows = []
                for index in range(args.capacity_scan):
                    entry = dataset[index]
                    view = _graph_color_view(entry, "degree_desc")
                    mono_owner = {vertex: 0 for vertex in view["vertices"]}
                    team_owner = _partition(view, b_value, args.balance_weight, args.seed + index)
                    team_feasible = _block_size_max(team_owner) <= register_limit
                    mono = _budgeted_search(dataset, entry, mono_owner, "cbj", args.capacity_node_budget, register_limit, "degree_owner")
                    team = _budgeted_search(dataset, entry, team_owner, "cbj", args.capacity_node_budget, register_limit, args.agent_order) if team_feasible else None
                    in_intersection = (not mono["solved"]) and team_feasible
                    row = {
                        "source_index": index,
                        "n_vertices": n_vertices,
                        "B": b_value,
                        "R": register_limit,
                        "team_static_feasible": team_feasible,
                        "intersection_member": in_intersection,
                        "monolith_solved": mono["solved"],
                        "monolith_status": mono["status"],
                        "monolith_work": mono["total_work"],
                        "team_solved": team["solved"] if team else False,
                        "team_status": team["status"] if team else "STATIC_REGISTER_INFEASIBLE",
                        "team_work": team["total_work"] if team else None,
                        "team_max_owner_live": team["max_owner_live"] if team else None,
                        "source": SOURCE,
                        "provenance": "capacity_intersection_pair_v0",
                    }
                    rows.append(row)
                    if in_intersection:
                        intersection_rows.append(row)
                intersection = [row for row in rows if row["intersection_member"]]
                cells.append(
                    {
                        "n_vertices": n_vertices,
                        "B": b_value,
                        "R": register_limit,
                        "n": len(rows),
                        "team_static_feasible_fraction": mean(float(row["team_static_feasible"]) for row in rows),
                        "monolith_fail_fraction": mean(float(not row["monolith_solved"]) for row in rows),
                        "intersection_n": len(intersection),
                        "intersection_fraction": len(intersection) / max(1, len(rows)),
                        "intersection_team_solve_rate": mean(float(row["team_solved"]) for row in intersection) if intersection else None,
                        "intersection_monolith_solve_rate": mean(float(row["monolith_solved"]) for row in intersection) if intersection else None,
                        "source": SOURCE,
                        "provenance": "capacity_intersection_cell_v0",
                    }
                )
    if intersection_rows:
        team_rate = mean(float(row["team_solved"]) for row in intersection_rows)
        mono_rate = mean(float(row["monolith_solved"]) for row in intersection_rows)
        verdict = "positive" if team_rate > mono_rate else "does_not_manifest"
    else:
        team_rate = None
        mono_rate = None
        verdict = "no_testable_regime"
    return {
        "cells": cells,
        "intersection_rows": intersection_rows[: args.capacity_max_rows],
        "intersection_size": len(intersection_rows),
        "intersection_fraction_max": max([cell["intersection_fraction"] for cell in cells], default=0.0),
        "intersection_team_solve_rate": team_rate,
        "intersection_monolith_solve_rate": mono_rate,
        "claim4_capacity_verdict": verdict,
        "source": SOURCE,
        "provenance": "track1_capacity_intersection_recompute_v0",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.claim3_b_values = [int(item) for item in args.claim3_b_values.split(",") if item]
    args.claim3_budgets = [int(item) for item in args.claim3_budgets.split(",") if item]
    args.capacity_vertices = [int(item) for item in args.capacity_vertices.split(",") if item]
    args.capacity_registers = [int(item) for item in args.capacity_registers.split(",") if item]
    args.capacity_b_values = [int(item) for item in args.capacity_b_values.split(",") if item]

    chrono = _chrono_completeness(args)
    track2 = _claim3_solvability(args, chrono)
    track1 = _capacity_search(args)
    track2_go = chrono["verified_on_small_sat"] and (
        track2["n_separation_pairs"] > 0 or track2["n_both_solve_pairs"] > 0
    ) and track2["claim3_verdict"] in {"solvability_positive", "both_solve_efficiency"}
    track1_go = track1["intersection_size"] > 0 and track1["claim4_capacity_verdict"] in {"positive", "does_not_manifest"}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "chrono_completeness": chrono,
        "track2_claim3": track2,
        "track1_capacity": track1,
        "proceed_gates": {
            "track2_real_llm": "GO" if track2_go else "NO_GO",
            "track2_reason": "chrono completeness verified and claim3 solve-rate verdict resolved" if track2_go else "chrono completeness or claim3 verdict unresolved",
            "track1_real_llm": "GO" if track1_go else "NO_GO",
            "track1_reason": "capacity intersection non-trivial and verdict resolved" if track1_go else "capacity intersection empty or verdict unresolved",
            "source": SOURCE,
            "provenance": "multiagent_solvability_proceed_gates_v0",
        },
        "headline": {
            "track2_claim3_determination": track2["claim3_verdict"],
            "track1_capacity_determination": track1["claim4_capacity_verdict"],
            "single_next_move_track2": "Run real LLM claim3 solve-rate track" if track2_go else "Fix chrono/claim3 no-LLM gate before real LLM",
            "single_next_move_track1": "Run real LLM capacity track" if track1_go else "Search a non-trivial capacity intersection regime",
        },
        "guards": {
            "official_scoring": "dataset.score_answer(answer, entry)",
            "solve_rate_primary": True,
            "work_secondary_only_on_both_solve": True,
            "monolith_same_R_same_instances": True,
            "team_feasible_definition": "static max partition block size <= R",
            "source": SOURCE,
            "provenance": "multiagent_solvability_guards_v0",
        },
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run no-LLM multi-agent solvability and capacity-intersection readout.")
    parser.add_argument("--output", type=Path, default=Path("results/rung1_multiagent_solvability/results.json"))
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--balance-weight", type=float, default=0.05)
    parser.add_argument("--agent-order", default="round_robin")
    parser.add_argument("--chrono-small-vertices", type=int, default=6)
    parser.add_argument("--chrono-small-edge-probability", type=float, default=0.2)
    parser.add_argument("--chrono-small-scan", type=int, default=8)
    parser.add_argument("--chrono-small-budget", type=int, default=5000)
    parser.add_argument("--claim3-vertices", type=int, default=10)
    parser.add_argument("--claim3-edge-probability", type=float, default=0.25)
    parser.add_argument("--claim3-register", type=int, default=8)
    parser.add_argument("--claim3-b-values", default="4,6")
    parser.add_argument("--claim3-scan", type=int, default=48)
    parser.add_argument("--claim3-min-instances", type=int, default=12)
    parser.add_argument("--claim3-probe-budget", type=int, default=800)
    parser.add_argument("--claim3-budgets", default="20,40,80,160,320")
    parser.add_argument("--capacity-vertices", default="10,12,16,20")
    parser.add_argument("--capacity-edge-probability", type=float, default=0.3)
    parser.add_argument("--capacity-registers", default="2,3,4,5,6")
    parser.add_argument("--capacity-b-values", default="4,5,6,8")
    parser.add_argument("--capacity-scan", type=int, default=12)
    parser.add_argument("--capacity-node-budget", type=int, default=800)
    parser.add_argument("--capacity-max-rows", type=int, default=160)
    run(parser.parse_args())


if __name__ == "__main__":
    main()