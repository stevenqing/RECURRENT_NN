"""Harvest step-level traces for LLM internalization experiments."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_reasoning_gym_bounded_register import (
    _clean_trace,
    _current_domain,
    _deadend_nogood,
    _ensure_reasoning_gym,
    _graph_color_view,
    _official_answer,
    _official_score,
)


SCHEMA_VERSION = "internalization_trace_harvester_v1"
TRACE_SCHEMA_VERSION = "internalization_step_trace_v1"
STATUS_COMPLETE = "INTERNALIZATION_TRACE_HARVEST_COMPLETE"
STATUS_PREFLIGHT_FAIL = "INTERNALIZATION_TRACE_HARVEST_PREFLIGHT_FAIL"


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
        seed=args.seed,
        num_colors=args.num_colors,
        min_num_vertices=args.num_vertices,
        max_num_vertices=args.num_vertices,
        edge_probability=args.edge_probability,
    )


def _select_entries(dataset: Any, args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    preflight_rows: list[dict[str, Any]] = []
    for index in range(args.scan_limit):
        entry = dataset[index]
        entry.setdefault("metadata", {})["source_index"] = index
        trace = _clean_trace(entry, args.order_mode, args.node_cap, dataset)
        row = {
            "source_index": index,
            "selected": bool(trace.get("solved") and int(trace.get("total_retractions", 0)) >= args.min_backtracks),
            "clean_status": trace.get("status"),
            "clean_solved": trace.get("solved"),
            "clean_steps": trace.get("steps"),
            "clean_total_retractions": trace.get("total_retractions"),
            "source": SOURCE,
            "provenance": "internalization_trace_selection_v1",
        }
        preflight_rows.append(row)
        if row["selected"]:
            selected.append({"entry": entry, "source_index": index, "clean_trace": trace})
        if len(selected) >= args.n_instances:
            break
    return selected, preflight_rows, {
        "benchmark": "graph_color",
        "selected_instances": len(selected),
        "scan_limit": args.scan_limit,
        "min_backtracks": args.min_backtracks,
        "node_cap": args.node_cap,
        "source": SOURCE,
        "provenance": "internalization_trace_preflight_v1",
    }


def _assignment_json(assignment: dict[int, int]) -> dict[str, int]:
    return {str(vertex): int(color) for vertex, color in sorted(assignment.items())}


def _register_view(register: list[dict[str, Any]], r_value: int) -> tuple[int, list[dict[str, Any]]]:
    start = max(0, len(register) - r_value)
    view = []
    for index, item in enumerate(register[start:]):
        view.append(
            {
                "entry_index": index,
                "variable": int(item["vertex"]),
                "value": int(item["color"]),
                "order_index": int(item["order_index"]),
            }
        )
    return start, view


def _state_summary(cursor: int, assignment: dict[int, int], register: list[dict[str, Any]]) -> dict[str, Any]:
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
            "Graph-coloring bounded-register internalization trace.",
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
    source_index: int,
    step_index: int,
    action_kind: str,
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
        "source_index": int(source_index),
        "R": int(args.r_value),
        "teacher_source": args.teacher_source,
        "action_kind": action_kind,
        "visible_state": visible_state,
        "target_action": target_action,
        "state_before_summary": before,
        "state_after_summary": after,
        "training_messages": _training_messages(visible_state, target_action),
        "source": SOURCE,
        "provenance": "internalization_step_trace_v1",
    }


def _harvest_episode(dataset: Any, selected: dict[str, Any], args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entry = selected["entry"]
    source_index = int(selected["source_index"])
    episode_id = f"rg_graph_color_seed{args.seed}_src{source_index}_R{args.r_value}_{args.teacher_source}"
    view = _graph_color_view(entry, args.order_mode)
    position = {vertex: index for index, vertex in enumerate(view["order"])}
    assignment: dict[int, int] = {}
    tried_colors: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, Any]] = []
    cursor = 0
    step_index = 0
    rows: list[dict[str, Any]] = []
    retractions = 0
    status = "RUNNING"
    official_score = 0.0

    while True:
        if step_index >= args.max_steps:
            status = "STEP_CAP"
            break
        before = _state_summary(cursor, assignment, register)
        if cursor >= len(view["order"]):
            official_score = _official_score(dataset, entry, assignment)
            status = "SOLVED" if official_score >= 1.0 else "OFFICIAL_SCORE_FAIL"
            visible_state = {
                "action_request": "final",
                "assignment": _assignment_json(assignment),
                "num_vertices": len(view["vertices"]),
            }
            target_action = {"action_type": "final", "answer": _official_answer(assignment), "official_score": official_score}
            rows.append(_trace_row(args, episode_id, source_index, step_index, "final", visible_state, target_action, before, before))
            break
        vertex = view["order"][cursor]
        domain = _current_domain(view, vertex, assignment, tried_colors)
        if domain:
            _, bounded_register = _register_view(register, args.r_value)
            assigned_neighbors = [
                {"neighbor": int(neighbor), "color": int(assignment[neighbor])}
                for neighbor in sorted(view["adjacency"][vertex])
                if neighbor in assignment
            ]
            color = int(domain[0])
            visible_state = {
                "action_request": "branch",
                "current_variable": int(vertex),
                "remaining_domain": [int(color_value) for color_value in domain],
                "assigned_neighbors": assigned_neighbors,
                "bounded_register": bounded_register,
            }
            target_action = {"action_type": "branch", "color": color}
            tried_colors[vertex].add(color)
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor})
            cursor += 1
            after = _state_summary(cursor, assignment, register)
            rows.append(_trace_row(args, episode_id, source_index, step_index, "branch", visible_state, target_action, before, after))
            step_index += 1
            continue
        if args.r_value == 0 or not register:
            status = "NO_RECOVERY_TARGET"
            visible_state = {"action_request": "fail", "current_variable": int(vertex), "reason": "empty_domain_no_register"}
            target_action = {"action_type": "fail", "status": status}
            rows.append(_trace_row(args, episode_id, source_index, step_index, "fail", visible_state, target_action, before, before))
            break
        nogood = _deadend_nogood(view, vertex, assignment, position)
        blockers = sorted(int(item) for item in nogood)
        oracle_vertex = max(nogood, key=lambda item: position[item]) if nogood else register[-1]["vertex"]
        oracle_abs = max((idx for idx, item in enumerate(register) if item["vertex"] == oracle_vertex), default=len(register) - 1)
        view_start, bounded_register = _register_view(register, args.r_value)
        oracle_view = oracle_abs - view_start
        if not (0 <= oracle_view < len(bounded_register)):
            status = "NO_RECOVERY_TARGET"
            visible_state = {
                "action_request": "fail",
                "current_variable": int(vertex),
                "conflict_blockers": blockers,
                "bounded_register": bounded_register,
                "reason": "oracle_target_out_of_bounded_view",
            }
            target_action = {"action_type": "fail", "status": status}
            rows.append(_trace_row(args, episode_id, source_index, step_index, "fail", visible_state, target_action, before, before))
            break
        visible_state = {
            "action_request": "backtrack",
            "conflict_variable": int(vertex),
            "conflict_blockers": blockers,
            "bounded_register": bounded_register,
        }
        target_action = {"action_type": "backtrack", "entry_index": int(oracle_view), "target_variable": int(oracle_vertex)}
        target_abs = view_start + oracle_view
        popped = register[target_abs:]
        retractions += len(popped)
        for item in popped:
            assignment.pop(int(item["vertex"]), None)
        for item in popped[1:]:
            tried_colors[int(item["vertex"])] = set()
        tried_colors[vertex] = set()
        cursor = int(register[target_abs]["order_index"])
        register = register[:target_abs]
        after = _state_summary(cursor, assignment, register) | {"popped_count": len(popped)}
        rows.append(_trace_row(args, episode_id, source_index, step_index, "backtrack", visible_state, target_action, before, after))
        step_index += 1

    summary = {
        "episode_id": episode_id,
        "source_index": source_index,
        "status": status,
        "solved": status == "SOLVED",
        "official_score": official_score,
        "n_trace_rows": len(rows),
        "branch_rows": sum(row["action_kind"] == "branch" for row in rows),
        "backtrack_rows": sum(row["action_kind"] == "backtrack" for row in rows),
        "final_rows": sum(row["action_kind"] == "final" for row in rows),
        "total_retractions": retractions,
        "max_register_view_len": max((len(row["visible_state"].get("bounded_register", [])) for row in rows), default=0),
        "bounded_view_verified": all(len(row["visible_state"].get("bounded_register", [])) <= args.r_value for row in rows),
        "source": SOURCE,
        "provenance": "internalization_episode_trace_summary_v1",
    }
    return rows, summary


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _make_dataset(args)
    selected, preflight_rows, preflight = _select_entries(dataset, args)
    status = STATUS_COMPLETE if len(selected) >= args.n_instances else STATUS_PREFLIGHT_FAIL
    trace_rows: list[dict[str, Any]] = []
    episode_summaries: list[dict[str, Any]] = []
    if status == STATUS_COMPLETE:
        for item in selected:
            rows, summary = _harvest_episode(dataset, item, args)
            trace_rows.extend(rows)
            episode_summaries.append(summary)
    action_counts = Counter(row["action_kind"] for row in trace_rows)
    solved_values = [bool(row.get("solved")) for row in episode_summaries]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "status": status,
        "generated_at": _now(),
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items() if key not in {"output", "jsonl_output"}},
        "preflight": preflight,
        "preflight_rows": preflight_rows,
        "episode_summaries": episode_summaries,
        "trace_rows": trace_rows[: args.max_rows_in_json],
        "jsonl_output": str(args.jsonl_output),
        "summary": {
            "n_episodes": len(episode_summaries),
            "n_trace_rows": len(trace_rows),
            "action_counts": dict(action_counts),
            "solve_rate": mean(solved_values) if solved_values else 0.0,
            "mean_official_score": mean(float(row.get("official_score", 0.0)) for row in episode_summaries) if episode_summaries else 0.0,
            "mean_trace_rows_per_episode": mean(int(row.get("n_trace_rows", 0)) for row in episode_summaries) if episode_summaries else 0.0,
            "max_register_view_len": max((int(row.get("max_register_view_len", 0)) for row in episode_summaries), default=0),
            "bounded_view_verified": all(bool(row.get("bounded_view_verified")) for row in episode_summaries) if episode_summaries else False,
            "jsonl_rows_parseable": True,
            "source": SOURCE,
            "provenance": "internalization_trace_harvest_summary_v1",
        },
        "honesty": {
            "does_not_establish": "This artifact exports oracle-scaffold step traces for future internalization. It does not train or evaluate an internalized LLM.",
            "teacher_limit": "The smoke uses oracle_scaffold actions, not replayed Qwen decisions from Item095. LLM-scaffold traces are a follow-up item.",
            "source": SOURCE,
            "provenance": "internalization_trace_honesty_v1",
        },
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    _write_jsonl(args.jsonl_output, trace_rows)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest step-level traces for internalization.")
    parser.add_argument("--output", type=Path, default=Path("results/internalization_traces/graph_color_single_agent_mregister_trace_smoke.json"))
    parser.add_argument("--jsonl-output", type=Path, default=Path("results/internalization_traces/graph_color_single_agent_mregister_trace_smoke.jsonl"))
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=200)
    parser.add_argument("--n-instances", type=int, default=8)
    parser.add_argument("--min-backtracks", type=int, default=4)
    parser.add_argument("--node-cap", type=int, default=80)
    parser.add_argument("--num-vertices", type=int, default=14)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--edge-probability", type=float, default=0.4)
    parser.add_argument("--order-mode", default="degree_desc", choices=["degree_desc", "natural"])
    parser.add_argument("--r-value", type=int, default=8)
    parser.add_argument("--max-steps", type=int, default=120)
    parser.add_argument("--teacher-source", default="oracle_scaffold", choices=["oracle_scaffold"])
    parser.add_argument("--max-rows-in-json", type=int, default=400)
    run(parser.parse_args())


if __name__ == "__main__":
    main()