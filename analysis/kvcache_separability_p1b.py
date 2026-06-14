"""P1-B planted separability multi-agent graph_color test."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE
from experiments.rung1_reasoning_gym_bounded_register import _ensure_reasoning_gym, _official_answer


SCHEMA_VERSION = "kvcache_separability_p1b_v0"
STATUS_COMPLETE = "KVCACHE_SEPARABILITY_P1B_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path.relative_to(REPO_ROOT)), "status": payload.get("status")}), flush=True)


def _score_dataset(args: argparse.Namespace) -> Any:
    return _ensure_reasoning_gym(args.reasoning_gym_repo).create_dataset("graph_color", size=1, seed=args.seed, min_num_vertices=10, max_num_vertices=10, num_colors=args.num_colors, edge_probability=0.1)


def _generate_entry(args: argparse.Namespace, p_out: float, source_index: int) -> tuple[dict[str, Any], dict[int, int], dict[int, int]]:
    rng = random.Random(f"{args.seed}:{p_out}:{source_index}")
    n = int(args.k_value) * int(args.block_size)
    vertices = list(range(n))
    owner = {v: v // int(args.block_size) for v in vertices}
    planted = {v: (v + owner[v]) % int(args.num_colors) + 1 for v in vertices}
    edges = []
    for left in vertices:
        for right in range(left + 1, n):
            if planted[left] == planted[right]:
                continue
            prob = float(args.p_in) if owner[left] == owner[right] else float(p_out)
            if rng.random() < prob:
                edges.append([left, right])
    puzzle = {"vertices": vertices, "edges": edges, "num_colors": int(args.num_colors), "color_options": list(range(1, int(args.num_colors) + 1))}
    question = f"Please color the planted SBM graph. Vertices: {vertices}\nEdges: {edges}\nPossible colors: {puzzle['color_options']}"
    entry = {"question": question, "answer": None, "metadata": {"source_dataset": "planted_sbm_graph_color", "source_index": int(source_index), "possible_answer": {str(k): int(v) for k, v in planted.items()}, "puzzle": puzzle, "num_vertices": n, "difficulty": {"p_out": float(p_out), "p_in": float(args.p_in), "K": int(args.k_value), "block_size": int(args.block_size)}}}
    return entry, owner, planted


def _adjacency(entry: dict[str, Any]) -> dict[int, set[int]]:
    vertices = [int(v) for v in entry["metadata"]["puzzle"]["vertices"]]
    adj = {v: set() for v in vertices}
    for left, right in entry["metadata"]["puzzle"]["edges"]:
        adj[int(left)].add(int(right))
        adj[int(right)].add(int(left))
    return adj


def _order(entry: dict[str, Any], owner: dict[int, int], mode: str) -> list[int]:
    adj = _adjacency(entry)
    per_agent: dict[int, list[int]] = {}
    for agent in sorted(set(owner.values())):
        per_agent[agent] = sorted([v for v, a in owner.items() if a == agent], key=lambda v: (-len(adj[v]), v))
    if mode == "agent_blocks":
        return [v for agent in sorted(per_agent) for v in per_agent[agent]]
    order = []
    while any(per_agent.values()):
        for agent in sorted(per_agent):
            if per_agent[agent]:
                order.append(per_agent[agent].pop(0))
    return order


def _blockers(adj: dict[int, set[int]], vertex: int, color: int, assignment: dict[int, int], owner: dict[int, int], include_cross: bool) -> set[int]:
    return {n for n in adj[vertex] if n in assignment and assignment[n] == color and (include_cross or owner[n] == owner[vertex])}


def _target_in_window(registers: dict[int, list[dict[str, Any]]], owner: dict[int, int], vertex: int, r_value: int) -> bool:
    reg = registers.get(owner[vertex], [])
    start = max(0, len(reg) - int(r_value))
    return any(item["vertex"] == vertex for item in reg[start:])


def _rollback_suffix(assignment: dict[int, int], next_idx: dict[int, int], conflict_sets: dict[int, set[int]], trail: list[dict[str, Any]], registers: dict[int, list[dict[str, Any]]], target_vertex: int, dead_vertex: int, carry: set[int] | None) -> tuple[int, list[dict[str, Any]]]:
    indices = [idx for idx, item in enumerate(trail) if item["vertex"] == target_vertex]
    if not indices:
        return -1, []
    target_index = indices[-1]
    popped = trail[target_index:]
    popped_vertices = {item["vertex"] for item in popped}
    for item in popped:
        assignment.pop(item["vertex"], None)
    trail[:] = [item for item in trail if item["vertex"] not in popped_vertices]
    for agent in list(registers):
        registers[agent] = [item for item in registers[agent] if item["vertex"] not in popped_vertices]
    for item in popped[1:]:
        next_idx[item["vertex"]] = 0
        conflict_sets[item["vertex"]].clear()
    next_idx[dead_vertex] = 0
    conflict_sets[dead_vertex].clear()
    if carry is not None:
        conflict_sets[target_vertex].update(v for v in carry if v != target_vertex)
    return int(popped[0]["order_index"]), popped


def _rollback_broadcast(assignment: dict[int, int], next_idx: dict[int, int], conflict_sets: dict[int, set[int]], trail: list[dict[str, Any]], registers: dict[int, list[dict[str, Any]]], dead_vertex: int) -> tuple[int, list[dict[str, Any]]]:
    latest = [reg[-1] for reg in registers.values() if reg]
    if not latest:
        return -1, []
    start_order = min(item["order_index"] for item in latest)
    popped = [item for item in trail if item["order_index"] >= start_order]
    popped_vertices = {item["vertex"] for item in popped}
    for item in popped:
        assignment.pop(item["vertex"], None)
        next_idx[item["vertex"]] = 0
        conflict_sets[item["vertex"]].clear()
    trail[:] = [item for item in trail if item["vertex"] not in popped_vertices]
    for agent in list(registers):
        registers[agent] = [item for item in registers[agent] if item["vertex"] not in popped_vertices]
    next_idx[dead_vertex] = 0
    conflict_sets[dead_vertex].clear()
    return start_order, popped


def _run_team(dataset: Any, entry: dict[str, Any], owner: dict[int, int], r_value: int, arm: str, args: argparse.Namespace) -> dict[str, Any]:
    adj = _adjacency(entry)
    order = _order(entry, owner, args.agent_order)
    position = {v: idx for idx, v in enumerate(order)}
    colors = list(entry["metadata"]["puzzle"]["color_options"])
    assignment: dict[int, int] = {}
    next_idx = {v: 0 for v in order}
    conflict_sets = {v: set() for v in order}
    registers = {agent: [] for agent in sorted(set(owner.values()))}
    trail: list[dict[str, Any]] = []
    cursor = 0
    stats = Counter()
    status = "RUNNING"
    while True:
        if int(stats["steps"]) >= int(args.node_cap):
            status = "NODE_CAP"
            break
        if len(assignment) == len(order):
            status = "SOLVED"
            break
        while cursor < len(order) and order[cursor] in assignment:
            cursor += 1
        if cursor >= len(order):
            remaining = [position[v] for v in order if v not in assignment]
            if not remaining:
                status = "SOLVED"
                break
            cursor = min(remaining)
        vertex = order[cursor]
        include_cross = arm != "no_coordination"
        chosen = None
        while next_idx[vertex] < len(colors):
            color = int(colors[next_idx[vertex]])
            next_idx[vertex] += 1
            blockers = _blockers(adj, vertex, color, assignment, owner, include_cross)
            if not blockers:
                chosen = color
                break
            conflict_sets[vertex].update(blockers)
        stats["steps"] += 1
        if chosen is not None:
            assignment[vertex] = chosen
            item = {"vertex": vertex, "color": chosen, "agent": owner[vertex], "order_index": cursor}
            trail.append(item)
            registers[owner[vertex]].append(item)
            stats["branches"] += 1
            cursor += 1
            continue
        blockers = {b for b in conflict_sets[vertex] if position.get(b, 10**9) < cursor}
        if not blockers:
            status = "EXHAUSTED"
            break
        stats["deadends"] += 1
        target = None
        carry = None
        if arm == "cbj_cross_block":
            target = max(blockers, key=lambda b: position[b])
            carry = set(blockers)
        elif arm == "chronological_cross_block":
            target = trail[-1]["vertex"] if trail else None
        elif arm == "broadcast":
            target = None
        elif arm == "no_coordination":
            target = max(blockers, key=lambda b: position[b])
            carry = set(blockers)
        if arm == "broadcast":
            new_cursor, popped = _rollback_broadcast(assignment, next_idx, conflict_sets, trail, registers, vertex)
            stats["cross_block_messages"] += len(registers)
        else:
            if target is None or not _target_in_window(registers, owner, target, int(r_value)):
                status = "NO_RECOVERY_TARGET"
                break
            stats["cross_block_backjumps"] += int(owner[target] != owner[vertex])
            stats["cross_block_messages"] += int(owner[target] != owner[vertex])
            new_cursor, popped = _rollback_suffix(assignment, next_idx, conflict_sets, trail, registers, target, vertex, carry if arm == "cbj_cross_block" else None)
        if new_cursor < 0:
            status = "NO_RECOVERY_TARGET"
            break
        popped_agents = {item["agent"] for item in popped}
        stats["recoveries"] += 1
        stats["retractions"] += len(popped)
        stats["cascade_sum"] += len(popped_agents)
        stats["cascade_max"] = max(int(stats["cascade_max"]), len(popped_agents))
        cursor = max(0, new_cursor)
    answer = _official_answer(assignment) if len(assignment) == len(order) else "{}"
    score = float(dataset.score_answer(answer, entry)) if len(assignment) == len(order) else 0.0
    if score >= 1.0:
        status = "SOLVED"
    return {"status": status, "solved": score >= 1.0, "official_score": score, "branches": int(stats["branches"]), "deadends": int(stats["deadends"]), "recoveries": int(stats["recoveries"]), "retractions": int(stats["retractions"]), "cross_block_messages": int(stats["cross_block_messages"]), "cross_block_backjumps": int(stats["cross_block_backjumps"]), "mean_cascade_depth": float(stats["cascade_sum"]) / max(1, int(stats["recoveries"])), "max_cascade_depth": int(stats["cascade_max"]), "source": SOURCE, "provenance": "kvcache_separability_team_row_v0"}


def _run_monolith(dataset: Any, entry: dict[str, Any], r_value: int, args: argparse.Namespace) -> dict[str, Any]:
    owner = {int(v): 0 for v in entry["metadata"]["puzzle"]["vertices"]}
    return _run_team(dataset, entry, owner, r_value, "cbj_cross_block", args)


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    keys = sorted({(row["p_out"], row["R"], row["table"], row["arm"]) for row in rows})
    for p_out, r_value, table, arm in keys:
        subset = [row for row in rows if row["p_out"] == p_out and row["R"] == r_value and row["table"] == table and row["arm"] == arm]
        out.append({"p_out": p_out, "R": r_value, "table": table, "arm": arm, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "mean_official_score": mean(float(row["official_score"]) for row in subset), "mean_cross_block_messages": mean(float(row.get("cross_block_messages", 0)) for row in subset), "mean_retractions": mean(float(row.get("retractions", 0)) for row in subset), "mean_cascade_depth": mean(float(row.get("mean_cascade_depth", 0)) for row in subset), "status_counts": dict(Counter(row["status"] for row in subset)), "source": SOURCE, "provenance": "kvcache_separability_summary_v0"})
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _score_dataset(args)
    rows = []
    for p_out in [float(x) for x in args.p_out_values.split(",") if x.strip()]:
        for source_index in range(int(args.n_instances)):
            entry, owner, _planted = _generate_entry(args, p_out, source_index)
            for r_value in [int(x) for x in args.r_values.split(",") if x.strip()]:
                for arm in ["cbj_cross_block", "chronological_cross_block", "broadcast", "no_coordination"]:
                    row = _run_team(dataset, entry, owner, r_value, arm, args)
                    rows.append({"p_out": p_out, "R": r_value, "table": "ma1", "arm": arm, "source_index": source_index, **row})
                team = _run_team(dataset, entry, owner, r_value, "cbj_cross_block", args)
                rows.append({"p_out": p_out, "R": r_value, "table": "ma2", "arm": "team_cbj", "source_index": source_index, **team})
                mono_r = _run_monolith(dataset, entry, r_value, args)
                rows.append({"p_out": p_out, "R": r_value, "table": "ma2", "arm": "monolith_R", "source_index": source_index, **mono_r})
                mono_kr = _run_monolith(dataset, entry, int(r_value) * int(args.k_value), args)
                rows.append({"p_out": p_out, "R": r_value, "table": "ma2", "arm": "monolith_KR", "source_index": source_index, **mono_kr})
    summary = _summarize(rows)
    def find(p, r, t, a):
        return next((row for row in summary if row["p_out"] == p and row["R"] == r and row["table"] == t and row["arm"] == a), None)
    low_p = min(float(x) for x in args.p_out_values.split(",") if x.strip())
    low_r = min(int(x) for x in args.r_values.split(",") if x.strip())
    cbj = find(low_p, low_r, "ma1", "cbj_cross_block")
    chrono = find(low_p, low_r, "ma1", "chronological_cross_block")
    team = find(low_p, low_r, "ma2", "team_cbj")
    monokr = find(low_p, low_r, "ma2", "monolith_KR")
    h1 = (cbj["solve_rate"] - chrono["solve_rate"]) if cbj and chrono else None
    h3 = (team["solve_rate"] - monokr["solve_rate"]) if team and monokr else None
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE, "generated_at": _now(), "config": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}, "summary": summary, "hypotheses": {"lowest_p_out": low_p, "lowest_R": low_r, "H1_cbj_minus_chrono": h1, "H1_pass_threshold_0p10": h1 is not None and h1 >= 0.10, "H3_team_minus_monolith_KR": h3, "H3_pass_threshold_0p10": h3 is not None and h3 >= 0.10}, "rows": rows, "source": SOURCE, "provenance": "kvcache_separability_p1b_v0"}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P1-B planted separability graph_color test.")
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--output", type=Path, default=Path("results/kvcache_overnight_v0/p1b_separability/results.json"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-instances", type=int, default=24)
    parser.add_argument("--k-value", type=int, default=3)
    parser.add_argument("--block-size", type=int, default=8)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--p-in", type=float, default=0.45)
    parser.add_argument("--p-out-values", default="0.02,0.08,0.15")
    parser.add_argument("--r-values", default="4,8")
    parser.add_argument("--node-cap", type=int, default=1200)
    parser.add_argument("--agent-order", choices=["round_robin", "agent_blocks"], default="round_robin")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
