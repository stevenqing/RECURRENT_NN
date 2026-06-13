"""Part-1 multi-agent real-LLM graph_color capacity-ratio runner.

This runner is intentionally LLM-first: it reuses established graph_color
official scoring and bounded-register mechanics, and does not create new L0
calibration artifacts.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_multiagent_graphcolor import _agent_order, _partition, _partition_stats
from experiments.rung1_reasoning_gym_bounded_register import (
    BACKTRACK_SCHEMA,
    BRANCH_SCHEMA,
    _ensure_reasoning_gym,
    _graph_color_view,
    _official_answer,
    _official_score,
    _openai_json_call,
    _run_episode,
)
from experiments.rung1_separator_llm_inloop import DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL


SCHEMA_VERSION = "externalization_multiagent_real_llm_v1"
STATUS_COMPLETE = "EXTERNALIZATION_MULTIAGENT_REAL_LLM_V1_COMPLETE"
STATUS_PREFLIGHT_FAIL = "EXTERNALIZATION_MULTIAGENT_REAL_LLM_V1_PREFLIGHT_FAIL"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = payload.get("status") if isinstance(payload, dict) else f"rows={len(payload)}"
    print(json.dumps({"path": _rel(path), "status": status}), flush=True)


def _read_json(path: Path) -> Any:
    path = path if path.is_absolute() else REPO_ROOT / path
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _checkpoint_path(args: argparse.Namespace) -> Path:
    return args.checkpoint_path if args.checkpoint_path.is_absolute() else REPO_ROOT / args.checkpoint_path


def _row_key(row: dict[str, Any]) -> tuple[int, int, str]:
    return (int(row.get("K", -1)), int(row.get("source_index", -1)), str(row.get("arm", "")))


def _make_dataset(args: argparse.Namespace, k_value: int, size: int) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    n_vertices = int(k_value * args.block_size)
    return reasoning_gym.create_dataset(
        "graph_color",
        size=size,
        seed=args.seed + 1000 * k_value,
        num_colors=args.num_colors,
        min_num_vertices=n_vertices,
        max_num_vertices=n_vertices,
        edge_probability=args.edge_probability,
    )


def _local_domain(view: dict[str, Any], owner: dict[int, int], vertex: int, assignment: dict[int, int], tried: dict[int, set[int]]) -> list[int]:
    agent = owner[vertex]
    blocked = {assignment[neighbor] for neighbor in view["adjacency"][vertex] if neighbor in assignment and owner[neighbor] == agent}
    return [color for color in view["color_options"] if color not in blocked and color not in tried[vertex]]


def _cross_conflict(view: dict[str, Any], owner: dict[int, int], assignment: dict[int, int]) -> tuple[int, int] | None:
    for left, right in view["edges"]:
        if owner[left] != owner[right] and left in assignment and right in assignment and assignment[left] == assignment[right]:
            return left, right
    return None


def _branch_prompt(entry: dict[str, Any], view: dict[str, Any], owner: dict[int, int], vertex: int, domain: list[int], assignment: dict[int, int], register_view: list[dict[str, Any]]) -> str:
    agent = owner[vertex]
    block_nodes = sorted(node for node, block in owner.items() if block == agent)
    boundary_nodes = sorted({neighbor for node in block_nodes for neighbor in view["adjacency"][node] if owner[neighbor] != agent})
    local_assignment = {node: assignment[node] for node in block_nodes if node in assignment}
    boundary_assignment = {node: assignment[node] for node in boundary_nodes if node in assignment}
    return "\n".join(
        [
            "Multi-agent graph_color bounded-register branch decision. Return JSON only.",
            "Choose one color from remaining_domain for current_variable.",
            "The symbolic scaffold owns state, propagation, conflict detection, CBJ routing, and final score_answer validation.",
            "Use only this block-local bounded view.",
            "Schema: {\"color\": int, \"reason\": str}",
            f"source_index={entry['metadata'].get('source_index')}; agent={agent}; current_variable={vertex}",
            f"remaining_domain={domain}",
            f"block_nodes={block_nodes}",
            f"local_assignment={local_assignment}",
            f"boundary_nodes={boundary_nodes}",
            f"boundary_assignment={boundary_assignment}",
            f"bounded_register={register_view}",
        ]
    )


def _local_backtrack_prompt(entry: dict[str, Any], agent: int, conflict_vertex: int, blockers: list[int], register_view: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "Multi-agent graph_color block-local backtrack decision. Return JSON only.",
            "Pick which bounded register entry to retract by entry_index.",
            "The symbolic scaffold will undo that entry and all newer dependent entries, then continue search.",
            "Use only this agent's bounded register view.",
            "Schema: {\"entry_index\": int, \"reason\": str}",
            f"source_index={entry['metadata'].get('source_index')}; agent={agent}; conflict_variable={conflict_vertex}; local_blockers={blockers}",
            f"bounded_register={register_view}",
        ]
    )


def _register_view(register: list[dict[str, Any]], r_value: int) -> tuple[int, list[dict[str, Any]]]:
    start = max(0, len(register) - r_value)
    view = [
        {"entry_index": index - start, "variable": int(item["vertex"]), "value": int(item["color"]), "order_index": int(item["order_index"])}
        for index, item in enumerate(register[start:])
    ]
    return start, view


def _token_zero() -> dict[str, int]:
    return {"output_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}


def _run_team_episode(dataset: Any, selected: dict[str, Any], k_value: int, args: argparse.Namespace, use_llm: bool) -> dict[str, Any]:
    entry = selected["entry"]
    view = _graph_color_view(entry, args.order_mode)
    owner = selected["owner"]
    order = _agent_order(view, owner, args.agent_order)
    position = {vertex: idx for idx, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    trail: list[dict[str, Any]] = []
    registers: dict[int, list[dict[str, Any]]] = defaultdict(list)
    cursor = 0
    stats: dict[str, Any] = {
        "decision_calls": 0,
        "llm_calls": 0,
        "branch_calls": 0,
        "backtrack_calls": 0,
        "parseable_decisions": 0,
        "valid_decisions": 0,
        "branch_accuracy_vs_oracle": 0,
        "backtrack_accuracy_vs_oracle": 0,
        "cross_block_recoveries": 0,
        "local_recoveries": 0,
        "total_retractions": 0,
        "max_register_view_len": 0,
        "max_prompt_chars": 0,
        "max_culprit_distance": 0,
        "culprit_distance_gt1": 0,
        "output_tokens": 0,
        "prompt_tokens": 0,
        "total_tokens": 0,
        "cache_effective": False,
        "failure_reason": "",
    }

    def add_usage(generation: dict[str, Any]) -> None:
        stats["output_tokens"] += int(generation.get("output_tokens", 0))
        stats["prompt_tokens"] += int(generation.get("prompt_tokens", 0))
        stats["total_tokens"] += int(generation.get("total_tokens", 0))

    def finish(status: str) -> dict[str, Any]:
        score = _official_score(dataset, entry, assignment)
        branch_calls = max(1, int(stats["branch_calls"]))
        backtrack_calls = max(1, int(stats["backtrack_calls"]))
        llm_calls = max(1, int(stats["llm_calls"]))
        return {
            "source_index": int(selected["source_index"]),
            "K": int(k_value),
            "block_size": int(args.block_size),
            "R": int(args.register_limit),
            "arm": "team",
            "status": status,
            "failure_reason": stats["failure_reason"],
            "official_score": score,
            "solved": score >= 1.0,
            "answer": _official_answer(assignment) if score >= 1.0 else None,
            "partition": selected["partition"],
            **stats,
            "branch_accuracy_vs_oracle": stats["branch_accuracy_vs_oracle"] / branch_calls,
            "backtrack_accuracy_vs_oracle": stats["backtrack_accuracy_vs_oracle"] / backtrack_calls,
            "parseable_rate": stats["parseable_decisions"] / llm_calls,
            "valid_decision_rate": stats["valid_decisions"] / llm_calls,
            "source": SOURCE,
            "provenance": "externalization_multiagent_real_llm_team_episode_v1",
        }

    while True:
        if stats["decision_calls"] >= args.call_cap:
            stats["failure_reason"] = "call_cap_reached"
            return finish("CALL_CAP")
        conflict = _cross_conflict(view, owner, assignment)
        if conflict is not None:
            stats["cross_block_recoveries"] += 1
            earlier_vertex = min(conflict, key=lambda vertex: position[vertex])
            earlier_agent = owner[earlier_vertex]
            agent_register = registers[earlier_agent]
            register_start, bounded = _register_view(agent_register, args.register_limit)
            stats["max_register_view_len"] = max(stats["max_register_view_len"], len(bounded))
            local_indices = [idx for idx, item in enumerate(agent_register) if item["vertex"] == earlier_vertex]
            if not local_indices or local_indices[-1] < register_start:
                stats["failure_reason"] = "cross_block_culprit_out_of_agent_register_view"
                return finish("NO_RECOVERY_TARGET")
            latest_index = trail[-1]["trail_index"] if trail else 0
            culprit_index = max((item["trail_index"] for item in trail if item["vertex"] == earlier_vertex), default=latest_index)
            distance = max(0, latest_index - culprit_index)
            stats["max_culprit_distance"] = max(stats["max_culprit_distance"], distance)
            stats["culprit_distance_gt1"] += int(distance > 1)
            target_vertex = earlier_vertex
        elif cursor >= len(order):
            return finish("SOLVED" if _official_score(dataset, entry, assignment) >= 1.0 else "OFFICIAL_SCORE_FAIL")
        else:
            vertex = order[cursor]
            if vertex in assignment:
                cursor += 1
                continue
            domain = _local_domain(view, owner, vertex, assignment, tried)
            if not domain:
                agent = owner[vertex]
                blockers = sorted(neighbor for neighbor in view["adjacency"][vertex] if neighbor in assignment and owner[neighbor] == agent)
                if not blockers:
                    stats["failure_reason"] = "local_deadend_without_same_agent_blockers"
                    return finish("NO_RECOVERY_TARGET")
                oracle_vertex = max(blockers, key=lambda item: position[item])
                agent_register = registers[agent]
                register_start, bounded = _register_view(agent_register, args.register_limit)
                stats["max_register_view_len"] = max(stats["max_register_view_len"], len(bounded))
                oracle_local_indices = [idx for idx, item in enumerate(agent_register) if item["vertex"] == oracle_vertex]
                if not oracle_local_indices or oracle_local_indices[-1] < register_start:
                    stats["failure_reason"] = "local_culprit_out_of_agent_register_view"
                    return finish("NO_RECOVERY_TARGET")
                chosen_view = oracle_local_indices[-1] - register_start
                generation = _token_zero()
                if use_llm:
                    prompt = _local_backtrack_prompt(entry, agent, vertex, blockers, bounded)
                    stats["max_prompt_chars"] = max(stats["max_prompt_chars"], len(prompt))
                    generation = _openai_json_call(args.openai_base_url, args.openai_model, prompt, args.max_new_tokens, BACKTRACK_SCHEMA)
                    try:
                        candidate = int(generation["parsed"].get("entry_index"))
                        stats["parseable_decisions"] += 1
                    except (TypeError, ValueError):
                        candidate = chosen_view
                    if 0 <= candidate < len(bounded):
                        chosen_view = candidate
                        stats["valid_decisions"] += 1
                    stats["llm_calls"] += 1
                stats["decision_calls"] += 1
                stats["backtrack_calls"] += 1
                add_usage(generation)
                stats["backtrack_accuracy_vs_oracle"] += int(bounded[chosen_view]["variable"] == oracle_vertex)
                target_vertex = int(bounded[chosen_view]["variable"])
                stats["local_recoveries"] += 1
            else:
                agent = owner[vertex]
                register_start, bounded = _register_view(registers[agent], args.register_limit)
                del register_start
                stats["max_register_view_len"] = max(stats["max_register_view_len"], len(bounded))
                oracle_color = domain[0]
                color = oracle_color
                generation = _token_zero()
                if use_llm:
                    prompt = _branch_prompt(entry, view, owner, vertex, domain, assignment, bounded)
                    stats["max_prompt_chars"] = max(stats["max_prompt_chars"], len(prompt))
                    generation = _openai_json_call(args.openai_base_url, args.openai_model, prompt, args.max_new_tokens, BRANCH_SCHEMA)
                    try:
                        candidate = int(generation["parsed"].get("color"))
                        stats["parseable_decisions"] += 1
                    except (TypeError, ValueError):
                        candidate = oracle_color
                    if candidate in domain:
                        color = candidate
                        stats["valid_decisions"] += 1
                    stats["llm_calls"] += 1
                stats["decision_calls"] += 1
                stats["branch_calls"] += 1
                add_usage(generation)
                stats["branch_accuracy_vs_oracle"] += int(color == oracle_color)
                tried[vertex].add(color)
                assignment[vertex] = color
                item = {"vertex": vertex, "color": color, "agent": agent, "order_index": cursor, "trail_index": len(trail)}
                trail.append(item)
                registers[agent].append(item)
                cursor += 1
                continue

        target_indices = [idx for idx, item in enumerate(trail) if item["vertex"] == target_vertex]
        if not target_indices:
            stats["failure_reason"] = "chosen_target_not_in_global_trail"
            return finish("NO_RECOVERY_TARGET")
        target_index = target_indices[-1]
        popped = trail[target_index:]
        stats["total_retractions"] += len(popped)
        for item in popped:
            assignment.pop(item["vertex"], None)
        popped_vertices = {item["vertex"] for item in popped}
        trail = [item for item in trail if item["vertex"] not in popped_vertices]
        for new_index, item in enumerate(trail):
            item["trail_index"] = new_index
        for agent in list(registers):
            registers[agent] = [item for item in registers[agent] if item["vertex"] not in popped_vertices]
        for item in popped[1:]:
            tried[item["vertex"]] = set()
        cursor = min(position[item["vertex"]] for item in popped)


def _run_monolith_episode(dataset: Any, selected: dict[str, Any], k_value: int, r_value: int, arm: str, args: argparse.Namespace, use_llm: bool) -> dict[str, Any]:
    selected_single = {"entry": selected["entry"], "source_index": selected["source_index"], "trace": {}}
    ns = argparse.Namespace(**vars(args))
    ns.dataset = "graph_color"
    ns.no_llm = not use_llm
    row = _run_episode(dataset, selected_single, r_value, "llm", ns)
    return {
        "source_index": int(selected["source_index"]),
        "K": int(k_value),
        "block_size": int(args.block_size),
        "R": int(r_value),
        "arm": arm,
        "official_score": row["official_score"],
        "solved": row["solved"],
        "status": row["status"],
        "decision_calls": row.get("decision_calls", 0),
        "llm_calls": row.get("llm_calls", 0),
        "branch_calls": row.get("branch_calls", 0),
        "backtrack_calls": row.get("backtrack_calls", 0),
        "parseable_rate": row.get("parseable_rate", 0.0),
        "valid_decision_rate": row.get("valid_decision_rate", 0.0),
        "branch_accuracy_vs_oracle": row.get("branch_accuracy_vs_oracle", 0.0),
        "backtrack_accuracy_vs_oracle": row.get("backtrack_accuracy_vs_oracle", 0.0),
        "max_register_view_len": row.get("max_register_view_len", 0),
        "max_prompt_chars": row.get("max_prompt_chars", 0),
        "output_tokens": row.get("output_tokens", 0),
        "prompt_tokens": row.get("prompt_tokens", 0),
        "total_tokens": row.get("total_tokens", 0),
        "cache_effective": False,
        "answer": row.get("answer"),
        "source": SOURCE,
        "provenance": "externalization_multiagent_real_llm_monolith_episode_v1",
    }


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for key in sorted({(int(row["K"]), row["arm"]) for row in rows}):
        k_value, arm = key
        subset = [row for row in rows if (int(row["K"]), row["arm"]) == key]
        out.append(
            {
                "K": k_value,
                "arm": arm,
                "n": len(subset),
                "solve_rate": mean(float(row["solved"]) for row in subset),
                "mean_official_score": mean(float(row["official_score"]) for row in subset),
                "mean_total_tokens": mean(float(row.get("total_tokens", 0)) for row in subset),
                "mean_prompt_tokens": mean(float(row.get("prompt_tokens", 0)) for row in subset),
                "mean_output_tokens": mean(float(row.get("output_tokens", 0)) for row in subset),
                "mean_llm_calls": mean(float(row.get("llm_calls", 0)) for row in subset),
                "mean_decision_calls": mean(float(row.get("decision_calls", 0)) for row in subset),
                "status_counts": dict(Counter(row["status"] for row in subset)),
                "source": SOURCE,
                "provenance": "externalization_multiagent_real_llm_summary_v1",
            }
        )
    return out


def _select_entries(dataset: Any, args: argparse.Namespace, k_value: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = []
    preflight_rows = []
    for index in range(args.scan_limit):
        entry = dataset[index]
        entry["metadata"]["source_index"] = index
        view = _graph_color_view(entry, args.order_mode)
        owner = _partition(view, k_value, args.balance_weight, args.seed + index + 100 * k_value)
        partition = _partition_stats(view, owner)
        dry_selected = {"entry": entry, "source_index": index, "owner": owner, "partition": partition}
        oracle = _run_team_episode(dataset, dry_selected, k_value, args, use_llm=False)
        forward_required = oracle["cross_block_recoveries"] + oracle["local_recoveries"] >= args.min_recoveries
        block_fits = max(partition["block_sizes"].values(), default=0) <= args.block_size and max(partition["block_sizes"].values(), default=0) <= args.register_limit
        ok = bool(oracle["solved"] and forward_required and block_fits)
        preflight_rows.append(
            {
                "source_index": index,
                "K": k_value,
                "selected": ok,
                "oracle_team_status": oracle["status"],
                "oracle_team_solved": oracle["solved"],
                "oracle_team_recoveries": oracle["cross_block_recoveries"] + oracle["local_recoveries"],
                "partition": partition,
                "selection_does_not_condition_on_monolith": True,
                "source": SOURCE,
                "provenance": "externalization_multiagent_real_llm_selection_v1",
            }
        )
        if ok:
            selected.append(dry_selected)
        if len(selected) >= args.n_instances:
            break
    return selected, preflight_rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    k_values = [int(item) for item in args.k_values.split(",") if item.strip()]
    requested_arms = [item.strip() for item in args.arms.split(",") if item.strip()]
    requested_sources = {int(item) for item in args.source_indices.split(",") if item.strip()} if args.source_indices else set()
    checkpoint_path = _checkpoint_path(args)
    all_rows: list[dict[str, Any]] = _read_json(checkpoint_path) if args.resume else []
    completed_keys = {_row_key(row) for row in all_rows}
    new_rows_written = 0
    all_preflight: list[dict[str, Any]] = []
    status = STATUS_COMPLETE
    use_llm = not args.no_llm
    for k_value in k_values:
        dataset = _make_dataset(args, k_value, args.scan_limit)
        selected, preflight = _select_entries(dataset, args, k_value)
        all_preflight.extend(preflight[: args.max_preflight_rows_per_k])
        if len(selected) < args.n_instances:
            status = STATUS_PREFLIGHT_FAIL
            continue
        tasks = []
        for item in selected:
            if requested_sources and int(item["source_index"]) not in requested_sources:
                continue
            for arm, r_value in [("team", args.register_limit), ("monolith_R", args.register_limit), ("monolith_KR", args.register_limit * k_value)]:
                if arm not in requested_arms:
                    continue
                key = (int(k_value), int(item["source_index"]), arm)
                if key not in completed_keys:
                    tasks.append((arm, dataset, item, k_value, r_value))
        if args.max_new_rows > 0:
            remaining = max(0, args.max_new_rows - new_rows_written)
            tasks = tasks[:remaining]
        task_batch_size = args.task_batch_size if args.task_batch_size > 0 else len(tasks)
        if use_llm:
            for start in range(0, len(tasks), max(1, task_batch_size)):
                batch = tasks[start : start + max(1, task_batch_size)]
                with ThreadPoolExecutor(max_workers=max(1, min(args.batch_size, len(batch)))) as pool:
                    futures = {}
                    for arm, dataset_item, selected_item, k_item, r_item in batch:
                        if arm == "team":
                            futures[pool.submit(_run_team_episode, dataset_item, selected_item, k_item, args, True)] = arm
                        else:
                            futures[pool.submit(_run_monolith_episode, dataset_item, selected_item, k_item, r_item, arm, args, True)] = arm
                    for future in as_completed(futures):
                        row = future.result()
                        all_rows.append(row)
                        completed_keys.add(_row_key(row))
                        new_rows_written += 1
                        _write_json(checkpoint_path, all_rows)
                if args.max_new_rows > 0 and new_rows_written >= args.max_new_rows:
                    break
        else:
            for arm, dataset_item, selected_item, k_item, r_item in tasks:
                if arm == "team":
                    row = _run_team_episode(dataset_item, selected_item, k_item, args, False)
                else:
                    row = _run_monolith_episode(dataset_item, selected_item, k_item, r_item, arm, args, False)
                all_rows.append(row)
                completed_keys.add(_row_key(row))
                new_rows_written += 1
                _write_json(checkpoint_path, all_rows)
                if args.max_new_rows > 0 and new_rows_written >= args.max_new_rows:
                    break
        if args.max_new_rows > 0 and new_rows_written >= args.max_new_rows:
            break
    summary = _summarize(all_rows)
    k6_rows = []
    for k_value in k_values:
        team = next((row for row in summary if row["K"] == k_value and row["arm"] == "team"), None)
        mono_r = next((row for row in summary if row["K"] == k_value and row["arm"] == "monolith_R"), None)
        mono_kr = next((row for row in summary if row["K"] == k_value and row["arm"] == "monolith_KR"), None)
        if team and mono_r and mono_kr:
            k6_rows.append(
                {
                    "K": k_value,
                    "team_solve_rate": team["solve_rate"],
                    "monolith_R_solve_rate": mono_r["solve_rate"],
                    "monolith_KR_solve_rate": mono_kr["solve_rate"],
                    "team_minus_monolith_R": team["solve_rate"] - mono_r["solve_rate"],
                    "team_minus_monolith_KR": team["solve_rate"] - mono_kr["solve_rate"],
                    "source": SOURCE,
                    "provenance": "externalization_multiagent_real_llm_k6_row_v1",
                }
            )
    capacity_positive = bool(k6_rows) and any(row["team_minus_monolith_R"] > 0 for row in k6_rows)
    kr_match = bool(k6_rows) and all(row["team_minus_monolith_KR"] >= -args.noise_margin for row in k6_rows)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "generated_at": _now(),
        "program_reweight_policy": {
            "l0_frozen": True,
            "new_compute_route": "LLM axes first; this artifact executes Part 1 multi-agent real-LLM harness/pilot.",
            "does_not_expand_calibration": True,
            "source": SOURCE,
            "provenance": "program_reweight_policy_v1",
        },
        "dataset_config": {
            "dataset": "graph_color",
            "official_instance_source": "reasoning_gym.create_dataset",
            "official_scoring": "dataset.score_answer(answer, entry)",
            "seed": args.seed,
            "k_values": k_values,
            "block_size": args.block_size,
            "num_colors": args.num_colors,
            "edge_probability": args.edge_probability,
            "source": SOURCE,
            "provenance": "externalization_multiagent_real_llm_dataset_config_v1",
        },
        "preflight": {
            "selection_does_not_condition_on_monolith": True,
            "selected_by": "team oracle solves and requires at least min_recoveries within per-block R; monolith outcomes are never used for selection",
            "min_recoveries": args.min_recoveries,
            "rows": all_preflight,
            "source": SOURCE,
            "provenance": "externalization_multiagent_real_llm_preflight_v1",
        },
        "budget_ledger": [
            {
                "n_instances_per_K": args.n_instances,
                "K_values": k_values,
                "arms": requested_arms,
                "source_indices_filter": sorted(requested_sources),
                "per_agent_R": args.register_limit,
                "call_cap": args.call_cap,
                "batch_size": args.batch_size,
                "task_batch_size": args.task_batch_size,
                "max_new_rows": args.max_new_rows,
                "resume": args.resume,
                "max_new_tokens": args.max_new_tokens,
                "max_episode_runs": len(k_values) * args.n_instances * 3,
                "source": SOURCE,
                "provenance": "externalization_multiagent_real_llm_budget_v1",
            }
        ],
        "summary_by_K_arm": summary,
        "k6_capacity_read": {
            "rows": k6_rows,
            "capacity_positive_vs_monolith_R": capacity_positive,
            "team_matches_monolith_KR_within_noise": kr_match,
            "noise_margin": args.noise_margin,
            "verdict": "pilot_or_underpowered" if args.n_instances < 30 else ("capacity_positive" if capacity_positive else "no_real_llm_capacity_effect"),
            "source": SOURCE,
            "provenance": "externalization_multiagent_real_llm_k6_v1",
        },
        "episode_rows": all_rows,
        "gold_trace_manifest": {
            "trace_role": "externalized bounded-CBJ gold traces for downstream LoRA internalization only after Part 1 full run lands",
            "contains_branch_and_backtrack_decisions": True,
            "external_controller_present": True,
            "internalization_not_started": True,
            "source": SOURCE,
            "provenance": "externalization_to_internalization_trace_manifest_v1",
        },
        "honesty": {
            "does_not_establish": "A run with n<30 is a harness/endpoint pilot only and does not establish claim 4b. Full K6 requires K={2,3,4,6}, n>=30 per K, and the monolith-KR control.",
            "l0_limit": "This runner does not expand no-LLM calibration; dry selection is a harness feasibility screen and is not a new L0 result.",
            "agentsnet_limit": "This artifact covers Substrate A graph_color only. AgentsNet Substrate B remains a follow-up using direct Coloring.get_score formula.",
            "internalization_limit": "LoRA internalization is not started here; this only creates the scaffold/trace source that Part 4 depends on.",
        },
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Part-1 multi-agent real-LLM graph_color capacity-ratio sweep/pilot.")
    parser.add_argument("--output", type=Path, default=Path("results/externalization_validation_v0/multiagent_real_llm_v1.json"))
    parser.add_argument("--checkpoint-path", type=Path, default=Path("results/externalization_validation_v0/multiagent_real_llm_v1_checkpoint.json"))
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--k-values", default="2,3,4,6")
    parser.add_argument("--arms", default="team,monolith_R,monolith_KR")
    parser.add_argument("--source-indices", default="")
    parser.add_argument("--block-size", type=int, default=8)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--edge-probability", type=float, default=0.35)
    parser.add_argument("--scan-limit", type=int, default=500)
    parser.add_argument("--n-instances", type=int, default=30)
    parser.add_argument("--max-preflight-rows-per-k", type=int, default=40)
    parser.add_argument("--min-recoveries", type=int, default=1)
    parser.add_argument("--order-mode", default="degree_desc")
    parser.add_argument("--agent-order", default="round_robin", choices=["degree_owner", "round_robin", "agent_blocks"])
    parser.add_argument("--register-limit", type=int, default=8)
    parser.add_argument("--call-cap", type=int, default=80)
    parser.add_argument("--balance-weight", type=float, default=0.05)
    parser.add_argument("--noise-margin", type=float, default=0.1)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--task-batch-size", type=int, default=0)
    parser.add_argument("--max-new-rows", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.set_defaults(resume=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
