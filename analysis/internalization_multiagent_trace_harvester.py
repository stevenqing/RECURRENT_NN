"""Harvest multi-agent step-level traces for LLM internalization."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_multiagent_graphcolor import _agent_order, _cross_conflict, _local_domain, _partition, _partition_stats
from experiments.rung1_reasoning_gym_bounded_register import _current_domain, _deadend_nogood, _ensure_reasoning_gym, _graph_color_view, _official_answer, _official_score


SCHEMA_VERSION = "internalization_multiagent_trace_harvester_v1"
TRACE_SCHEMA_VERSION = "internalization_multiagent_step_trace_v1"
STATUS_COMPLETE = "INTERNALIZATION_MULTIAGENT_TRACE_HARVEST_COMPLETE"
STATUS_PREFLIGHT_FAIL = "INTERNALIZATION_MULTIAGENT_TRACE_HARVEST_PREFLIGHT_FAIL"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": f"rows={len(rows)}"}), flush=True)


def _make_dataset(args: argparse.Namespace) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    return reasoning_gym.create_dataset(
        "graph_color",
        size=args.scan_limit,
        seed=args.seed + 1000 * args.k_value,
        num_colors=args.num_colors,
        min_num_vertices=args.k_value * args.block_size,
        max_num_vertices=args.k_value * args.block_size,
        edge_probability=args.edge_probability,
    )


def _assignment_json(assignment: dict[int, int]) -> dict[str, int]:
    return {str(vertex): int(color) for vertex, color in sorted(assignment.items())}


def _register_view(register: list[dict[str, Any]], r_value: int) -> tuple[int, list[dict[str, Any]]]:
    start = max(0, len(register) - r_value)
    view = []
    for index, item in enumerate(register[start:]):
        row = {"entry_index": index, "variable": int(item["vertex"]), "value": int(item["color"]), "order_index": int(item["order_index"])}
        if "agent" in item:
            row["agent_id"] = int(item["agent"])
        view.append(row)
    return start, view


def _team_state_summary(cursor: int, assignment: dict[int, int], trail: list[dict[str, Any]], registers: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "cursor": int(cursor),
        "assignment_size": len(assignment),
        "assignment": _assignment_json(assignment),
        "trail_len": len(trail),
        "trail_tail": [
            {"variable": int(item["vertex"]), "value": int(item["color"]), "agent_id": int(item["agent"]), "order_index": int(item["order_index"])}
            for item in trail[-8:]
        ],
        "per_agent_register_len": {str(agent): len(register) for agent, register in sorted(registers.items())},
    }


def _monolith_state_summary(cursor: int, assignment: dict[int, int], register: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cursor": int(cursor),
        "assignment_size": len(assignment),
        "assignment": _assignment_json(assignment),
        "register_len": len(register),
        "register_tail": [
            {"variable": int(item["vertex"]), "value": int(item["color"]), "order_index": int(item["order_index"])}
            for item in register[-8:]
        ],
    }


def _training_messages(visible_state: dict[str, Any], target_action: dict[str, Any]) -> list[dict[str, str]]:
    prompt = "\n".join(
        [
            "Multi-agent graph-coloring internalization trace.",
            "Given VISIBLE_STATE, return exactly TARGET_ACTION as JSON.",
            "VISIBLE_STATE=" + json.dumps(visible_state, sort_keys=True),
        ]
    )
    return [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": json.dumps(target_action, sort_keys=True)},
    ]


def _trace_row(
    args: argparse.Namespace,
    episode_id: str,
    arm: str,
    source_index: int,
    step_index: int,
    action_kind: str,
    agent_id: int | None,
    r_value: int,
    visible_state: dict[str, Any],
    target_action: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    return {
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "trace_id": f"{episode_id}_step{step_index:04d}",
        "episode_id": episode_id,
        "step_index": int(step_index),
        "benchmark": "graph_color",
        "arm": arm,
        "source_index": int(source_index),
        "K": int(args.k_value),
        "R": int(r_value),
        "agent_id": None if agent_id is None else int(agent_id),
        "teacher_source": args.teacher_source,
        "action_kind": action_kind,
        "visible_state": visible_state,
        "target_action": target_action,
        "state_before_summary": before,
        "state_after_summary": after,
        "training_messages": _training_messages(visible_state, target_action),
        "source": SOURCE,
        "provenance": "internalization_multiagent_step_trace_v1",
    }


def _block_context(view: dict[str, Any], owner: dict[int, int], agent: int, assignment: dict[int, int]) -> dict[str, Any]:
    block_nodes = sorted(node for node, block in owner.items() if block == agent)
    boundary_nodes = sorted({neighbor for node in block_nodes for neighbor in view["adjacency"][node] if owner[neighbor] != agent})
    return {
        "block_nodes": block_nodes,
        "local_assignment": {str(node): assignment[node] for node in block_nodes if node in assignment},
        "boundary_nodes": boundary_nodes,
        "boundary_assignment": {str(node): assignment[node] for node in boundary_nodes if node in assignment},
    }


def _apply_team_rollback(
    position: dict[int, int],
    assignment: dict[int, int],
    tried: dict[int, set[int]],
    trail: list[dict[str, Any]],
    registers: dict[int, list[dict[str, Any]]],
    target_vertex: int,
) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
    target_indices = [idx for idx, item in enumerate(trail) if item["vertex"] == target_vertex]
    if not target_indices:
        return -1, [], trail
    target_index = target_indices[-1]
    popped = trail[target_index:]
    for item in popped:
        assignment.pop(int(item["vertex"]), None)
    popped_vertices = {int(item["vertex"]) for item in popped}
    trail = [item for item in trail if int(item["vertex"]) not in popped_vertices]
    for new_index, item in enumerate(trail):
        item["trail_index"] = new_index
    for agent in list(registers):
        registers[agent] = [item for item in registers[agent] if int(item["vertex"]) not in popped_vertices]
    for item in popped[1:]:
        tried[int(item["vertex"])] = set()
    cursor = min(position[int(item["vertex"])] for item in popped) if popped else -1
    return cursor, popped, trail


def _harvest_team_episode(dataset: Any, selected: dict[str, Any], args: argparse.Namespace, keep_rows: bool = True) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entry = selected["entry"]
    source_index = int(selected["source_index"])
    view = _graph_color_view(entry, args.order_mode)
    owner = selected["owner"]
    order = _agent_order(view, owner, args.agent_order)
    position = {vertex: index for index, vertex in enumerate(order)}
    episode_id = f"rg_graph_color_seed{args.seed}_K{args.k_value}_src{source_index}_team_{args.teacher_source}"
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    trail: list[dict[str, Any]] = []
    registers: dict[int, list[dict[str, Any]]] = defaultdict(list)
    cursor = 0
    step_index = 0
    rows: list[dict[str, Any]] = []
    stats = Counter()
    status = "RUNNING"
    official_score = 0.0
    max_register_view_len = 0

    def append(action_kind: str, agent_id: int | None, visible_state: dict[str, Any], target_action: dict[str, Any], before: dict[str, Any], after: dict[str, Any]) -> None:
        nonlocal step_index, max_register_view_len
        max_register_view_len = max(max_register_view_len, len(visible_state.get("bounded_register", [])))
        if keep_rows:
            rows.append(_trace_row(args, episode_id, "team", source_index, step_index, action_kind, agent_id, args.register_limit, visible_state, target_action, before, after))
        step_index += 1
        stats[action_kind] += 1

    while True:
        if step_index >= args.max_steps:
            status = "STEP_CAP"
            break
        before = _team_state_summary(cursor, assignment, trail, registers)
        conflict = _cross_conflict(view, owner, assignment)
        if conflict is not None:
            earlier_vertex = min(conflict, key=lambda vertex: position[vertex])
            later_vertex = max(conflict, key=lambda vertex: position[vertex])
            target_agent = owner[earlier_vertex]
            agent_register = registers[target_agent]
            register_start, bounded = _register_view(agent_register, args.register_limit)
            local_indices = [idx for idx, item in enumerate(agent_register) if int(item["vertex"]) == int(earlier_vertex)]
            latest_index = trail[-1]["trail_index"] if trail else 0
            culprit_index = max((item["trail_index"] for item in trail if int(item["vertex"]) == int(earlier_vertex)), default=latest_index)
            culprit_distance = max(0, latest_index - culprit_index)
            visible_state = {
                "action_request": "cross_block_conflict",
                "conflict_edge": [int(conflict[0]), int(conflict[1])],
                "candidate_agents": sorted({int(owner[conflict[0]]), int(owner[conflict[1]])}),
                "earlier_vertex": int(earlier_vertex),
                "later_vertex": int(later_vertex),
                "target_agent": int(target_agent),
                "bounded_register": bounded,
            }
            target_action = {"action_type": "route_conflict", "target_agent": int(target_agent), "target_variable": int(earlier_vertex), "culprit_distance": int(culprit_distance)}
            append("cross_block_conflict", None, visible_state, target_action, before, before)
            append("message", int(target_agent), {"action_request": "message", **visible_state}, {"action_type": "message", "to_agent": int(target_agent), "content": target_action}, before, before)
            if not local_indices or local_indices[-1] < register_start:
                status = "NO_RECOVERY_TARGET"
                break
            rollback_before = _team_state_summary(cursor, assignment, trail, registers)
            cursor, popped, trail = _apply_team_rollback(position, assignment, tried, trail, registers, int(earlier_vertex))
            if cursor < 0:
                status = "NO_RECOVERY_TARGET"
                break
            stats["total_retractions"] += len(popped)
            stats["cross_block_recoveries"] += 1
            rollback_after = _team_state_summary(cursor, assignment, trail, registers) | {"popped_count": len(popped)}
            append(
                "rollback",
                int(target_agent),
                {"action_request": "rollback", "target_variable": int(earlier_vertex), "popped": [{"variable": int(item["vertex"]), "agent_id": int(item["agent"])} for item in popped], "bounded_register": bounded},
                {"action_type": "rollback", "target_variable": int(earlier_vertex), "popped_count": len(popped)},
                rollback_before,
                rollback_after,
            )
            continue
        if cursor >= len(order):
            official_score = _official_score(dataset, entry, assignment)
            status = "SOLVED" if official_score >= 1.0 else "OFFICIAL_SCORE_FAIL"
            visible_state = {"action_request": "final", "assignment": _assignment_json(assignment), "num_vertices": len(view["vertices"])}
            target_action = {"action_type": "final", "answer": _official_answer(assignment), "official_score": official_score}
            append("final", None, visible_state, target_action, before, before)
            break
        vertex = order[cursor]
        if vertex in assignment:
            cursor += 1
            continue
        domain = _local_domain(view, owner, vertex, assignment, tried)
        agent = int(owner[vertex])
        if not domain:
            blockers = sorted(neighbor for neighbor in view["adjacency"][vertex] if neighbor in assignment and owner[neighbor] == agent)
            if not blockers:
                status = "NO_RECOVERY_TARGET"
                break
            oracle_vertex = max(blockers, key=lambda item: position[item])
            register_start, bounded = _register_view(registers[agent], args.register_limit)
            local_indices = [idx for idx, item in enumerate(registers[agent]) if int(item["vertex"]) == int(oracle_vertex)]
            if not local_indices or local_indices[-1] < register_start:
                status = "NO_RECOVERY_TARGET"
                break
            chosen_view = local_indices[-1] - register_start
            append(
                "local_backtrack",
                agent,
                {"action_request": "local_backtrack", "agent_id": agent, "conflict_variable": int(vertex), "local_blockers": [int(item) for item in blockers], "bounded_register": bounded},
                {"action_type": "local_backtrack", "entry_index": int(chosen_view), "target_variable": int(oracle_vertex)},
                before,
                before,
            )
            rollback_before = _team_state_summary(cursor, assignment, trail, registers)
            cursor, popped, trail = _apply_team_rollback(position, assignment, tried, trail, registers, int(oracle_vertex))
            if cursor < 0:
                status = "NO_RECOVERY_TARGET"
                break
            stats["total_retractions"] += len(popped)
            stats["local_recoveries"] += 1
            rollback_after = _team_state_summary(cursor, assignment, trail, registers) | {"popped_count": len(popped)}
            append("rollback", agent, {"action_request": "rollback", "target_variable": int(oracle_vertex), "popped": [{"variable": int(item["vertex"]), "agent_id": int(item["agent"])} for item in popped], "bounded_register": bounded}, {"action_type": "rollback", "target_variable": int(oracle_vertex), "popped_count": len(popped)}, rollback_before, rollback_after)
            continue
        _, bounded = _register_view(registers[agent], args.register_limit)
        context = _block_context(view, owner, agent, assignment)
        color = int(domain[0])
        visible_state = {"action_request": "branch", "agent_id": agent, "current_variable": int(vertex), "remaining_domain": [int(item) for item in domain], "bounded_register": bounded, **context}
        target_action = {"action_type": "branch", "color": color}
        tried[vertex].add(color)
        assignment[vertex] = color
        item = {"vertex": int(vertex), "color": color, "agent": agent, "order_index": int(cursor), "trail_index": len(trail)}
        trail.append(item)
        registers[agent].append(item)
        cursor += 1
        append("branch", agent, visible_state, target_action, before, _team_state_summary(cursor, assignment, trail, registers))

    summary = {
        "episode_id": episode_id,
        "arm": "team",
        "source_index": source_index,
        "K": int(args.k_value),
        "R": int(args.register_limit),
        "status": status,
        "solved": status == "SOLVED",
        "official_score": official_score,
        "n_trace_rows": step_index,
        "action_counts": {key: int(value) for key, value in stats.items() if key not in {"total_retractions", "cross_block_recoveries", "local_recoveries"}},
        "cross_block_recoveries": int(stats["cross_block_recoveries"]),
        "local_recoveries": int(stats["local_recoveries"]),
        "total_retractions": int(stats["total_retractions"]),
        "max_register_view_len": int(max_register_view_len),
        "bounded_view_verified": max_register_view_len <= args.register_limit,
        "partition": selected["partition"],
        "source": SOURCE,
        "provenance": "internalization_multiagent_episode_trace_summary_v1",
    }
    return rows, summary


def _harvest_monolith_episode(dataset: Any, selected: dict[str, Any], args: argparse.Namespace, arm: str, r_value: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entry = selected["entry"]
    source_index = int(selected["source_index"])
    view = _graph_color_view(entry, args.order_mode)
    position = {vertex: index for index, vertex in enumerate(view["order"])}
    episode_id = f"rg_graph_color_seed{args.seed}_K{args.k_value}_src{source_index}_{arm}_{args.teacher_source}"
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, Any]] = []
    cursor = 0
    step_index = 0
    rows: list[dict[str, Any]] = []
    stats = Counter()
    status = "RUNNING"
    official_score = 0.0
    max_register_view_len = 0

    def append(action_kind: str, visible_state: dict[str, Any], target_action: dict[str, Any], before: dict[str, Any], after: dict[str, Any]) -> None:
        nonlocal step_index, max_register_view_len
        max_register_view_len = max(max_register_view_len, len(visible_state.get("bounded_register", [])))
        rows.append(_trace_row(args, episode_id, arm, source_index, step_index, action_kind, None, r_value, visible_state, target_action, before, after))
        step_index += 1
        stats[action_kind] += 1

    while True:
        if step_index >= args.max_steps:
            status = "STEP_CAP"
            break
        before = _monolith_state_summary(cursor, assignment, register)
        if cursor >= len(view["order"]):
            official_score = _official_score(dataset, entry, assignment)
            status = "SOLVED" if official_score >= 1.0 else "OFFICIAL_SCORE_FAIL"
            visible_state = {"action_request": "final", "assignment": _assignment_json(assignment), "num_vertices": len(view["vertices"])}
            target_action = {"action_type": "final", "answer": _official_answer(assignment), "official_score": official_score}
            append("final", visible_state, target_action, before, before)
            break
        vertex = view["order"][cursor]
        domain = _current_domain(view, vertex, assignment, tried)
        if domain:
            _, bounded = _register_view(register, r_value)
            assigned_neighbors = [{"neighbor": int(neighbor), "color": int(assignment[neighbor])} for neighbor in sorted(view["adjacency"][vertex]) if neighbor in assignment]
            color = int(domain[0])
            visible_state = {"action_request": "branch", "current_variable": int(vertex), "remaining_domain": [int(item) for item in domain], "assigned_neighbors": assigned_neighbors, "bounded_register": bounded}
            target_action = {"action_type": "branch", "color": color}
            tried[vertex].add(color)
            assignment[vertex] = color
            register.append({"vertex": int(vertex), "color": color, "order_index": int(cursor)})
            cursor += 1
            append("branch", visible_state, target_action, before, _monolith_state_summary(cursor, assignment, register))
            continue
        if not register:
            status = "NO_RECOVERY_TARGET"
            append("fail", {"action_request": "fail", "current_variable": int(vertex), "reason": "empty_domain_no_register"}, {"action_type": "fail", "status": status}, before, before)
            break
        nogood = _deadend_nogood(view, vertex, assignment, position)
        oracle_vertex = max(nogood, key=lambda item: position[item]) if nogood else register[-1]["vertex"]
        oracle_abs = max((index for index, item in enumerate(register) if int(item["vertex"]) == int(oracle_vertex)), default=len(register) - 1)
        view_start, bounded = _register_view(register, r_value)
        oracle_view = oracle_abs - view_start
        if not (0 <= oracle_view < len(bounded)):
            status = "NO_RECOVERY_TARGET"
            append("fail", {"action_request": "fail", "current_variable": int(vertex), "bounded_register": bounded, "reason": "oracle_target_out_of_bounded_view"}, {"action_type": "fail", "status": status}, before, before)
            break
        append("backtrack", {"action_request": "backtrack", "conflict_variable": int(vertex), "conflict_blockers": [int(item) for item in sorted(nogood)], "bounded_register": bounded}, {"action_type": "backtrack", "entry_index": int(oracle_view), "target_variable": int(oracle_vertex)}, before, before)
        rollback_before = _monolith_state_summary(cursor, assignment, register)
        target_abs = view_start + oracle_view
        popped = register[target_abs:]
        stats["total_retractions"] += len(popped)
        for item in popped:
            assignment.pop(int(item["vertex"]), None)
        for item in popped[1:]:
            tried[int(item["vertex"])] = set()
        tried[vertex] = set()
        cursor = int(register[target_abs]["order_index"])
        register = register[:target_abs]
        append("rollback", {"action_request": "rollback", "target_variable": int(oracle_vertex), "popped": [{"variable": int(item["vertex"])} for item in popped], "bounded_register": bounded}, {"action_type": "rollback", "target_variable": int(oracle_vertex), "popped_count": len(popped)}, rollback_before, _monolith_state_summary(cursor, assignment, register) | {"popped_count": len(popped)})

    summary = {
        "episode_id": episode_id,
        "arm": arm,
        "source_index": source_index,
        "K": int(args.k_value),
        "R": int(r_value),
        "status": status,
        "solved": status == "SOLVED",
        "official_score": official_score,
        "n_trace_rows": len(rows),
        "action_counts": {key: int(value) for key, value in stats.items() if key != "total_retractions"},
        "total_retractions": int(stats["total_retractions"]),
        "max_register_view_len": int(max_register_view_len),
        "bounded_view_verified": max_register_view_len <= r_value,
        "source": SOURCE,
        "provenance": "internalization_multiagent_episode_trace_summary_v1",
    }
    return rows, summary


def _select_entries(dataset: Any, args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    preflight_rows: list[dict[str, Any]] = []
    for index in range(args.scan_limit):
        entry = dataset[index]
        entry.setdefault("metadata", {})["source_index"] = index
        view = _graph_color_view(entry, args.order_mode)
        owner = _partition(view, args.k_value, args.balance_weight, args.seed + index + 100 * args.k_value)
        partition = _partition_stats(view, owner)
        candidate = {"entry": entry, "source_index": index, "owner": owner, "partition": partition}
        _, summary = _harvest_team_episode(dataset, candidate, args, keep_rows=False)
        recoveries = int(summary["cross_block_recoveries"]) + int(summary["local_recoveries"])
        block_fits = max(partition["block_sizes"].values(), default=0) <= args.block_size and max(partition["block_sizes"].values(), default=0) <= args.register_limit
        ok = bool(summary["solved"] and recoveries >= args.min_recoveries and block_fits)
        preflight_rows.append({"source_index": index, "selected": ok, "team_oracle_status": summary["status"], "team_oracle_recoveries": recoveries, "partition": partition, "source": SOURCE, "provenance": "internalization_multiagent_trace_selection_v1"})
        if ok:
            selected.append(candidate)
        if len(selected) >= args.n_instances:
            break
    return selected, preflight_rows, {"selected_instances": len(selected), "scan_limit": args.scan_limit, "K": args.k_value, "block_size": args.block_size, "min_recoveries": args.min_recoveries, "source": SOURCE, "provenance": "internalization_multiagent_trace_preflight_v1"}


def _summary_by_arm(episode_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for arm in sorted({row["arm"] for row in episode_summaries}):
        subset = [row for row in episode_summaries if row["arm"] == arm]
        counts = Counter()
        for row in subset:
            counts.update(row.get("action_counts", {}))
        out.append({"arm": arm, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "mean_official_score": mean(float(row["official_score"]) for row in subset), "mean_trace_rows": mean(int(row["n_trace_rows"]) for row in subset), "status_counts": dict(Counter(row["status"] for row in subset)), "action_counts": dict(counts), "max_register_view_len": max(int(row["max_register_view_len"]) for row in subset), "bounded_view_verified": all(bool(row["bounded_view_verified"]) for row in subset), "source": SOURCE, "provenance": "internalization_multiagent_trace_arm_summary_v1"})
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _make_dataset(args)
    selected, preflight_rows, preflight = _select_entries(dataset, args)
    status = STATUS_COMPLETE if len(selected) >= args.n_instances else STATUS_PREFLIGHT_FAIL
    trace_rows: list[dict[str, Any]] = []
    episode_summaries: list[dict[str, Any]] = []
    if status == STATUS_COMPLETE:
        for item in selected:
            rows, summary = _harvest_team_episode(dataset, item, args, keep_rows=True)
            trace_rows.extend(rows)
            episode_summaries.append(summary)
            for arm, r_value in [("monolith_R", args.register_limit), ("monolith_KR", args.register_limit * args.k_value)]:
                rows, summary = _harvest_monolith_episode(dataset, item, args, arm, r_value)
                trace_rows.extend(rows)
                episode_summaries.append(summary)
    action_counts = Counter(row["action_kind"] for row in trace_rows)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "status": status,
        "generated_at": _now(),
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items() if key not in {"output", "jsonl_output"}},
        "preflight": preflight,
        "preflight_rows": preflight_rows,
        "episode_summaries": episode_summaries,
        "summary_by_arm": _summary_by_arm(episode_summaries),
        "trace_rows": trace_rows[: args.max_rows_in_json],
        "jsonl_output": str(args.jsonl_output),
        "summary": {"n_episodes": len(episode_summaries), "n_trace_rows": len(trace_rows), "action_counts": dict(action_counts), "jsonl_rows_parseable": True, "bounded_view_verified": all(bool(row.get("bounded_view_verified")) for row in episode_summaries) if episode_summaries else False, "source": SOURCE, "provenance": "internalization_multiagent_trace_harvest_summary_v1"},
        "honesty": {"does_not_establish": "This artifact exports oracle-scaffold multi-agent and monolith traces. It does not train or evaluate internalized agents.", "teacher_limit": "The trace teacher is oracle_scaffold, not Qwen replay. LLM-scaffold traces remain a later item.", "source": SOURCE, "provenance": "internalization_multiagent_trace_honesty_v1"},
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    _write_jsonl(args.jsonl_output, trace_rows)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest multi-agent graph_color traces for internalization.")
    parser.add_argument("--output", type=Path, default=Path("results/internalization_traces/graph_color_multiagent_trace_pilot.json"))
    parser.add_argument("--jsonl-output", type=Path, default=Path("results/internalization_traces/graph_color_multiagent_trace_pilot.jsonl"))
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=200)
    parser.add_argument("--n-instances", type=int, default=4)
    parser.add_argument("--k-value", type=int, default=2)
    parser.add_argument("--block-size", type=int, default=8)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--edge-probability", type=float, default=0.35)
    parser.add_argument("--order-mode", default="degree_desc")
    parser.add_argument("--agent-order", default="round_robin", choices=["degree_owner", "round_robin", "agent_blocks"])
    parser.add_argument("--register-limit", type=int, default=8)
    parser.add_argument("--min-recoveries", type=int, default=1)
    parser.add_argument("--balance-weight", type=float, default=0.05)
    parser.add_argument("--max-steps", type=int, default=240)
    parser.add_argument("--teacher-source", default="oracle_scaffold", choices=["oracle_scaffold"])
    parser.add_argument("--max-rows-in-json", type=int, default=800)
    run(parser.parse_args())


if __name__ == "__main__":
    main()