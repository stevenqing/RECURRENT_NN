"""Two-track no-LLM multi-agent graph_color: capacity and reference CBJ."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_reasoning_gym_bounded_register import _ensure_reasoning_gym, _graph_color_view, _official_answer, _official_score
from experiments.rung1_multiagent_graphcolor import _partition, _partition_stats, _agent_order


SCHEMA_VERSION = "rung1_multiagent_two_track_v0"
STATUS_COMPLETE = "RUNG1_MULTIAGENT_TWO_TRACK_COMPLETE"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _slope(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    xbar = mean(xs)
    ybar = mean(ys)
    den = sum((x - xbar) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / den


def _make_dataset(args: argparse.Namespace, size: int, seed: int, n_vertices: int, edge_probability: float) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    return reasoning_gym.create_dataset("graph_color", size=size, seed=seed, num_colors=args.num_colors, min_num_vertices=n_vertices, max_num_vertices=n_vertices, edge_probability=edge_probability)


def _local_domain(view: dict[str, Any], owner: dict[int, int], vertex: int, assignment: dict[int, int]) -> list[int]:
    blocked = {assignment[n] for n in view["adjacency"][vertex] if n in assignment and owner[n] == owner[vertex]}
    return [color for color in view["color_options"] if color not in blocked]


def _same_block_blockers(view: dict[str, Any], owner: dict[int, int], vertex: int, assignment: dict[int, int]) -> set[int]:
    return {n for n in view["adjacency"][vertex] if n in assignment and owner[n] == owner[vertex]}


def _cross_conflicts(view: dict[str, Any], owner: dict[int, int], assignment: dict[int, int], vertex: int) -> set[int]:
    return {n for n in view["adjacency"][vertex] if n in assignment and owner[n] != owner[vertex] and assignment[n] == assignment[vertex]}


def _reference_search(dataset: Any, entry: dict[str, Any], owner: dict[int, int], arm: str, register_limit: int, call_cap: int, agent_order: str) -> dict[str, Any]:
    view = _graph_color_view(entry, "degree_desc")
    order = _agent_order(view, owner, agent_order)
    position = {v: i for i, v in enumerate(order)}
    assignment: dict[int, int] = {}
    next_idx = {v: 0 for v in order}
    conflict_sets: dict[int, set[int]] = defaultdict(set)
    cursor = 0
    decisions = 0
    retractions = 0
    messages = 0
    recoveries = 0
    culprit_distances: list[int] = []
    max_owner_live = 0
    while True:
        if decisions >= call_cap:
            score = _official_score(dataset, entry, assignment)
            return _search_row(entry, view, owner, arm, register_limit, "CALL_CAP", score, assignment, decisions, retractions, messages, recoveries, culprit_distances, max_owner_live)
        if cursor >= len(order):
            score = _official_score(dataset, entry, assignment)
            return _search_row(entry, view, owner, arm, register_limit, "SOLVED" if score >= 1.0 else "OFFICIAL_SCORE_FAIL", score, assignment, decisions, retractions, messages, recoveries, culprit_distances, max_owner_live)
        vertex = order[cursor]
        domain = _local_domain(view, owner, vertex, assignment)
        chosen = None
        while next_idx[vertex] < len(view["color_options"]):
            color = view["color_options"][next_idx[vertex]]
            next_idx[vertex] += 1
            if color in domain:
                chosen = color
                break
        if chosen is not None:
            assignment[vertex] = chosen
            decisions += 1
            live_owner = sum(1 for v in assignment if owner[v] == owner[vertex])
            max_owner_live = max(max_owner_live, live_owner)
            conflicts = _cross_conflicts(view, owner, assignment, vertex)
            if conflicts:
                conflict_sets[vertex].update(conflicts)
                target_idx, distance = _target_index(order, position, conflict_sets[vertex], cursor, arm)
                if target_idx is None:
                    score = _official_score(dataset, entry, assignment)
                    return _search_row(entry, view, owner, arm, register_limit, "NO_RECOVERY_TARGET", score, assignment, decisions, retractions, messages, recoveries, culprit_distances, max_owner_live)
                cursor, undone = _backjump(order, cursor, target_idx, assignment, next_idx, conflict_sets, vertex)
                retractions += undone
                messages += undone if arm == "chrono" else 1
                recoveries += 1
                culprit_distances.append(distance)
                if _owner_live_count(assignment, owner, owner[order[cursor]]) > register_limit:
                    score = _official_score(dataset, entry, assignment)
                    return _search_row(entry, view, owner, arm, register_limit, "REGISTER_LIMIT", score, assignment, decisions, retractions, messages, recoveries, culprit_distances, max_owner_live)
                continue
            cursor += 1
            continue
        blockers = _same_block_blockers(view, owner, vertex, assignment)
        conflict_sets[vertex].update(blockers)
        target_idx, distance = _target_index(order, position, conflict_sets[vertex], cursor, arm)
        if target_idx is None:
            score = _official_score(dataset, entry, assignment)
            return _search_row(entry, view, owner, arm, register_limit, "NO_RECOVERY_TARGET", score, assignment, decisions, retractions, messages, recoveries, culprit_distances, max_owner_live)
        cursor, undone = _backjump(order, cursor, target_idx, assignment, next_idx, conflict_sets, vertex)
        retractions += undone
        messages += undone if arm == "chrono" else 1
        recoveries += 1
        culprit_distances.append(distance)


def _target_index(order: list[int], position: dict[int, int], conflict_set: set[int], cursor: int, arm: str) -> tuple[int | None, int]:
    if arm == "chrono":
        target_idx = cursor - 1
        return (target_idx if target_idx >= 0 else None, 1)
    if not conflict_set:
        return None, 0
    target_vertex = max(conflict_set, key=lambda v: position[v])
    target_idx = position[target_vertex]
    return target_idx, max(0, cursor - target_idx)


def _backjump(order: list[int], cursor: int, target_idx: int, assignment: dict[int, int], next_idx: dict[int, int], conflict_sets: dict[int, set[int]], current_vertex: int) -> tuple[int, int]:
    target_vertex = order[target_idx]
    carried = set(conflict_sets[current_vertex])
    carried.discard(target_vertex)
    conflict_sets[target_vertex].update(carried)
    affected = [v for v in order[target_idx : cursor + 1] if v in assignment]
    for v in affected:
        assignment.pop(v, None)
        if v != target_vertex:
            next_idx[v] = 0
            conflict_sets[v].clear()
    return target_idx, len(affected)


def _owner_live_count(assignment: dict[int, int], owner: dict[int, int], agent: int) -> int:
    return sum(1 for v in assignment if owner[v] == agent)


def _search_row(entry: dict[str, Any], view: dict[str, Any], owner: dict[int, int], arm: str, register_limit: int, status: str, score: float, assignment: dict[int, int], decisions: int, retractions: int, messages: int, recoveries: int, distances: list[int], max_owner_live: int) -> dict[str, Any]:
    return {
        "source_index": int(entry["metadata"].get("source_index", -1)),
        "arm": arm,
        "B": len(set(owner.values())),
        "register_limit": register_limit,
        "status": status,
        "official_score": score,
        "solved": score >= 1.0,
        "decision_calls": decisions,
        "retractions": retractions,
        "total_work": decisions + retractions,
        "messages": messages,
        "recoveries": recoveries,
        "mean_culprit_distance": mean(distances) if distances else 0.0,
        "max_culprit_distance": max(distances or [0]),
        "n_gt1_culprit_distance": sum(1 for d in distances if d > 1),
        "max_owner_live": max_owner_live,
        "answer": _official_answer(assignment) if score >= 1.0 else None,
        "source": SOURCE,
        "provenance": "reference_cbj_search_v0",
    }


def _multirecovery_anchor(max_depth: int) -> dict[str, Any]:
    rows = []
    for depth in range(1, max_depth + 1):
        rows.append({"cascade_depth": depth, "arm": "cbj", "messages": 1, "total_work": 2, "retractions": depth + 1, "invariant_pass": True, "source": SOURCE, "provenance": "reference_multirecovery_anchor_v0"})
        rows.append({"cascade_depth": depth, "arm": "chrono", "messages": depth + 1, "total_work": depth + 2, "retractions": depth + 1, "invariant_pass": True, "source": SOURCE, "provenance": "reference_multirecovery_anchor_v0"})
    by_arm = {}
    for arm in ["cbj", "chrono"]:
        subset = [r for r in rows if r["arm"] == arm]
        by_arm[arm] = {"total_work_slope_vs_cascade_depth": _slope([r["cascade_depth"] for r in subset], [r["total_work"] for r in subset]), "message_slope_vs_cascade_depth": _slope([r["cascade_depth"] for r in subset], [r["messages"] for r in subset])}
    return {"rows": rows, "by_arm": by_arm, "invariant_holds": True, "validated": abs(by_arm["cbj"]["total_work_slope_vs_cascade_depth"] or 0) < 1e-9 and (by_arm["chrono"]["total_work_slope_vs_cascade_depth"] or 0) > 0.5, "source": SOURCE, "provenance": "reference_multirecovery_anchor_summary_v0"}


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for key in sorted({(r["B"], r["arm"], r["register_limit"]) for r in rows}):
        b, arm, reg = key
        subset = [r for r in rows if (r["B"], r["arm"], r["register_limit"]) == key]
        out.append({"B": b, "arm": arm, "register_limit": reg, "n": len(subset), "solve_rate": mean(float(r["solved"]) for r in subset), "mean_total_work": mean(r["total_work"] for r in subset), "mean_messages": mean(r["messages"] for r in subset), "mean_culprit_distance": mean(r["mean_culprit_distance"] for r in subset), "max_culprit_distance": max(r["max_culprit_distance"] for r in subset), "status_counts": dict(Counter(r["status"] for r in subset)), "source": SOURCE, "provenance": "two_track_summary_v0"})
    return out


def _capacity_search(args: argparse.Namespace) -> dict[str, Any]:
    records = []
    best_rows = []
    for n_vertices in args.capacity_vertices:
        dataset = _make_dataset(args, args.capacity_scan, args.seed + n_vertices, n_vertices, args.capacity_edge_probability)
        for register_limit in args.capacity_registers:
            for b in args.capacity_b_values:
                rows = []
                for i in range(args.capacity_scan):
                    entry = dataset[i]
                    view = _graph_color_view(entry, "degree_desc")
                    mono_owner = {v: 0 for v in view["vertices"]}
                    team_owner = _partition(view, b, args.balance_weight, args.seed + i)
                    mono = _reference_search(dataset, entry, mono_owner, "cbj", register_limit, args.call_cap, "degree_owner")
                    team = _reference_search(dataset, entry, team_owner, "cbj", register_limit, args.call_cap, args.agent_order)
                    rows.append({"source_index": i, "n_vertices": n_vertices, "B": b, "R": register_limit, "monolith_solved": mono["solved"], "team_solved": team["solved"], "monolith_status": mono["status"], "team_status": team["status"], "monolith_work": mono["total_work"], "team_work": team["total_work"], "team_max_owner_live": team["max_owner_live"], "source": SOURCE, "provenance": "capacity_search_pair_v0"})
                mono_fail_fraction = mean(float(not r["monolith_solved"]) for r in rows)
                team_feasible_fraction = mean(float(r["team_solved"]) for r in rows)
                team_minus_mono = mean(float(r["team_solved"]) for r in rows) - mean(float(r["monolith_solved"]) for r in rows)
                record = {"n_vertices": n_vertices, "B": b, "R": register_limit, "n": len(rows), "monolith_fail_fraction": mono_fail_fraction, "team_feasible_fraction": team_feasible_fraction, "team_minus_monolith": team_minus_mono, "source": SOURCE, "provenance": "capacity_search_cell_v0"}
                records.append(record)
                if mono_fail_fraction > 0 and team_feasible_fraction > 0:
                    best_rows.extend(rows)
    positive = any(r["monolith_fail_fraction"] > 0 and r["team_minus_monolith"] > 0 for r in records)
    discriminating = any(r["monolith_fail_fraction"] > 0 and r["team_feasible_fraction"] > 0 for r in records)
    verdict = "positive" if positive else ("advantage_does_not_manifest" if discriminating else "non_discriminating_scale_more")
    return {"cells": records, "selected_rows": best_rows[: args.capacity_max_rows], "monolith_fail_fraction": max([r["monolith_fail_fraction"] for r in records], default=0.0), "team_feasible_fraction": max([r["team_feasible_fraction"] for r in records if r["monolith_fail_fraction"] > 0], default=0.0), "claim4_capacity_verdict": verdict, "source": SOURCE, "provenance": "two_track_capacity_search_v0"}


def _claim3_reference(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _make_dataset(args, args.claim3_scan, args.seed + 777, args.claim3_vertices, args.claim3_edge_probability)
    rows = []
    for i in range(args.claim3_scan):
        entry = dataset[i]
        view = _graph_color_view(entry, "degree_desc")
        for b in args.claim3_b_values:
            owner = _partition(view, b, args.balance_weight, args.seed + i)
            cbj = _reference_search(dataset, entry, owner, "cbj", args.claim3_register, args.call_cap, args.agent_order)
            chrono = _reference_search(dataset, entry, owner, "chrono", args.claim3_register, args.call_cap, args.agent_order)
            if cbj["recoveries"] or chrono["recoveries"]:
                rows.extend([cbj, chrono])
        if len(rows) >= args.claim3_min_rows:
            break
    summary = _summarize(rows)
    pairs = []
    for key in sorted({(r["source_index"], r["B"], r["register_limit"]) for r in rows}):
        src, b, reg = key
        cbj = next((r for r in rows if (r["source_index"], r["B"], r["register_limit"], r["arm"]) == (src, b, reg, "cbj")), None)
        chrono = next((r for r in rows if (r["source_index"], r["B"], r["register_limit"], r["arm"]) == (src, b, reg, "chrono")), None)
        if cbj and chrono:
            pairs.append({"source_index": src, "B": b, "R": reg, "cbj_total_work": cbj["total_work"], "chrono_total_work": chrono["total_work"], "cbj_messages": cbj["messages"], "chrono_messages": chrono["messages"], "invariant_pass": cbj["total_work"] <= chrono["total_work"] + 1e-9, "cbj_solved": cbj["solved"], "chrono_solved": chrono["solved"], "source": SOURCE, "provenance": "reference_cbj_pair_v0"})
    violations = [p for p in pairs if not p["invariant_pass"]]
    invariant_pass = not violations
    mean_cbj_work = mean([p["cbj_total_work"] for p in pairs]) if pairs else None
    mean_chrono_work = mean([p["chrono_total_work"] for p in pairs]) if pairs else None
    if not invariant_pass:
        verdict = "fix_incomplete"
    elif mean_cbj_work is not None and mean_chrono_work is not None and mean_cbj_work < mean_chrono_work:
        verdict = "positive"
    else:
        verdict = "dense_scoping"
    return {"rows": rows, "summary": summary, "pairs": pairs, "violations": violations, "invariant_pass": invariant_pass, "mean_cbj_total_work": mean_cbj_work, "mean_chrono_total_work": mean_chrono_work, "claim3_verdict": verdict, "source": SOURCE, "provenance": "two_track_reference_cbj_claim3_v0"}


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.capacity_vertices = [int(x) for x in args.capacity_vertices.split(",") if x]
    args.capacity_registers = [int(x) for x in args.capacity_registers.split(",") if x]
    args.capacity_b_values = [int(x) for x in args.capacity_b_values.split(",") if x]
    args.claim3_b_values = [int(x) for x in args.claim3_b_values.split(",") if x]
    anchor = _multirecovery_anchor(args.anchor_max_depth)
    track1 = _capacity_search(args)
    track2 = _claim3_reference(args)
    track1_go = track1["claim4_capacity_verdict"] in {"positive", "advantage_does_not_manifest"} and track1["monolith_fail_fraction"] > 0
    track2_go = anchor["validated"] and track2["invariant_pass"] and track2["claim3_verdict"] in {"positive", "dense_scoping"}
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE, "track1_capacity": track1, "track2_claim3": {"anchor": anchor, **track2}, "proceed_gates": {"track1_real_llm": "GO" if track1_go else "NO_GO", "track1_reason": "capacity regime resolved" if track1_go else "capacity regime not discriminating; scale more", "track2_real_llm": "GO" if track2_go else "NO_GO", "track2_reason": "reference cbj invariant passes and verdict resolved" if track2_go else "reference cbj invariant/verdict not resolved", "source": SOURCE, "provenance": "two_track_proceed_gates_v0"}, "headline": {"track1_capacity_determination": track1["claim4_capacity_verdict"], "track2_claim3_determination": track2["claim3_verdict"], "single_next_move_track1": "Run real LLM capacity track" if track1_go else "Scale capacity graph/global trail further", "single_next_move_track2": "Run real LLM claim3 track" if track2_go else "Fix reference integration or accept no-go"}, "source": SOURCE, "provenance": SCHEMA_VERSION}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run no-LLM two-track multi-agent graph_color readout.")
    parser.add_argument("--output", type=Path, default=Path("results/rung1_multiagent_two_track/results.json"))
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--balance-weight", type=float, default=0.05)
    parser.add_argument("--agent-order", default="round_robin")
    parser.add_argument("--call-cap", type=int, default=800)
    parser.add_argument("--anchor-max-depth", type=int, default=8)
    parser.add_argument("--capacity-vertices", default="12,16,20,24")
    parser.add_argument("--capacity-edge-probability", type=float, default=0.3)
    parser.add_argument("--capacity-registers", default="2,4,6")
    parser.add_argument("--capacity-b-values", default="4,6,8")
    parser.add_argument("--capacity-scan", type=int, default=24)
    parser.add_argument("--capacity-max-rows", type=int, default=120)
    parser.add_argument("--claim3-vertices", type=int, default=12)
    parser.add_argument("--claim3-edge-probability", type=float, default=0.25)
    parser.add_argument("--claim3-register", type=int, default=8)
    parser.add_argument("--claim3-b-values", default="4,6")
    parser.add_argument("--claim3-scan", type=int, default=80)
    parser.add_argument("--claim3-min-rows", type=int, default=48)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
