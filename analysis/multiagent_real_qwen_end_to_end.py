"""Gated end-to-end real-Qwen multi-agent development run.

This runner executes a branch-source by route-source factorial on the frozen
capacity-coupling preflight manifest. It refuses to start unless the offline
real-Qwen decision gate passed. Model parse/validity failures fail closed and no
oracle fallback is used. Results are checkpointed after every completed episode.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from statistics import mean
from typing import Any

from analysis.multiagent_real_qwen_decision_gate import (
    BRANCH_SCHEMA,
    ROUTE_SCHEMA,
    _branch_prompt,
    _register_view,
    _route_prompt,
)
from experiments.multiagent_capacity_coupling import REPO_ROOT, _adjacency
from experiments.rung1_reasoning_gym_bounded_register import _openai_json_call


SCHEMA_VERSION = "multiagent_real_qwen_end_to_end_dev_v1"
STATUS_COMPLETE = "MULTIAGENT_REAL_QWEN_END_TO_END_DEV_COMPLETE"
STATUS_PARTIAL = "MULTIAGENT_REAL_QWEN_END_TO_END_DEV_PARTIAL"
POLICIES = (
    "symbolic_branch_symbolic_route",
    "qwen_branch_symbolic_route",
    "symbolic_branch_qwen_route",
    "qwen_branch_qwen_route",
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _uses_qwen_branch(policy: str) -> bool:
    return policy.startswith("qwen_branch")


def _uses_qwen_route(policy: str) -> bool:
    return policy.endswith("qwen_route")


def _valid_solution(n: int, k: int, edges: list[tuple[int, int]], assignment: dict[int, int]) -> bool:
    return (
        len(assignment) == int(n)
        and all(int(assignment.get(vertex, 0)) in range(1, int(k) + 1) for vertex in range(int(n)))
        and all(int(assignment[left]) != int(assignment[right]) for left, right in edges)
    )


def _episode_key(cell: str, instance_id: str, policy: str) -> str:
    return f"{cell}::{instance_id}::{policy}"


def _run_episode(
    row: dict[str, Any],
    policy: str,
    base_url: str,
    model: str,
    r_value: int,
    node_cap: int,
    call_cap: int,
    token_cap: int,
    max_new_tokens: int,
) -> dict[str, Any]:
    n = int(row["n_vertices"])
    k = int(row["k"])
    edges = [tuple(map(int, edge)) for edge in row["edges"]]
    partitions = [int(value) for value in row["partitions"]]
    order = [int(value) for value in row["order"]]
    position = {vertex: index for index, vertex in enumerate(order)}
    adjacency = _adjacency(n, edges)
    assignment: dict[int, int] = {}
    next_choice = {vertex: 0 for vertex in order}
    conflict_sets: dict[int, set[int]] = {vertex: set() for vertex in order}
    trail: list[dict[str, int]] = []
    registers: dict[int, list[dict[str, int]]] = defaultdict(list)
    cursor = 0
    steps = 0
    recoveries = 0
    retractions = 0
    cross_block_messages = 0
    boundary_commit_messages = 0
    llm_calls = 0
    branch_calls = 0
    route_calls = 0
    branch_parseable = 0
    branch_valid = 0
    branch_exact = 0
    route_parseable = 0
    route_valid = 0
    route_exact = 0
    prompt_tokens = 0
    output_tokens = 0
    total_tokens = 0
    failure_reason = ""
    trace_samples: list[dict[str, Any]] = []

    def finish(status: str) -> dict[str, Any]:
        solved = status == "SOLVED" and _valid_solution(n, k, edges, assignment)
        final_status = "SOLVED" if solved else ("OFFICIAL_SCORE_FAIL" if status == "SOLVED" else status)
        return {
            "episode_key": _episode_key(str(row["cell"]), str(row["instance_id"]), policy),
            "instance_id": str(row["instance_id"]),
            "cell": str(row["cell"]),
            "capacity": str(row["capacity"]),
            "coupling": str(row["coupling"]),
            "policy": policy,
            "base_url": base_url,
            "model": model,
            "solved": solved,
            "status": final_status,
            "failure_reason": failure_reason,
            "steps": steps,
            "recoveries": recoveries,
            "retractions": retractions,
            "cross_block_messages": cross_block_messages,
            "boundary_commit_messages": boundary_commit_messages,
            "llm_calls": llm_calls,
            "branch_calls": branch_calls,
            "route_calls": route_calls,
            "branch_parse_rate": branch_parseable / max(1, branch_calls if _uses_qwen_branch(policy) else 0),
            "branch_valid_rate": branch_valid / max(1, branch_calls if _uses_qwen_branch(policy) else 0),
            "branch_exact_rate": branch_exact / max(1, branch_calls if _uses_qwen_branch(policy) else 0),
            "route_parse_rate": route_parseable / max(1, route_calls if _uses_qwen_route(policy) else 0),
            "route_valid_rate": route_valid / max(1, route_calls if _uses_qwen_route(policy) else 0),
            "route_exact_rate": route_exact / max(1, route_calls if _uses_qwen_route(policy) else 0),
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "call_cap": int(call_cap),
            "token_cap": int(token_cap),
            "node_cap": int(node_cap),
            "oracle_fallback_used": False,
            "trace_samples": trace_samples,
            "headline_eligible": False,
        }

    def model_call(prompt: str, schema: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal llm_calls, prompt_tokens, output_tokens, total_tokens, failure_reason
        if llm_calls >= int(call_cap):
            failure_reason = "llm_call_cap_reached"
            return None
        try:
            generation = _openai_json_call(base_url, model, prompt, int(max_new_tokens), schema)
        except Exception as exc:
            failure_reason = f"endpoint_error:{type(exc).__name__}:{str(exc)[:160]}"
            return None
        llm_calls += 1
        prompt_tokens += int(generation.get("prompt_tokens", 0))
        output_tokens += int(generation.get("output_tokens", 0))
        total_tokens += int(generation.get("total_tokens", 0))
        if total_tokens > int(token_cap):
            failure_reason = "total_token_cap_exceeded"
            return None
        return generation

    while True:
        if steps >= int(node_cap):
            failure_reason = "node_cap_reached"
            return finish("NODE_CAP")
        if cursor >= len(order):
            return finish("SOLVED")
        vertex = order[cursor]
        if vertex in assignment:
            cursor += 1
            continue
        blocked_colors: dict[int, set[int]] = {}
        valid_colors: list[int] = []
        for color in range(1, k + 1):
            blockers = {neighbor for neighbor in adjacency[vertex] if assignment.get(neighbor) == color}
            if blockers:
                blocked_colors[color] = blockers
                conflict_sets[vertex].update(blockers)
            else:
                valid_colors.append(color)
        steps += 1
        if next_choice[vertex] < len(valid_colors):
            remaining = valid_colors[next_choice[vertex]:]
            reference_color = int(remaining[0])
            chosen_color = reference_color
            agent = partitions[vertex]
            if _uses_qwen_branch(policy):
                _start, bounded = _register_view(registers[agent], int(r_value))
                prompt = _branch_prompt(row, vertex, agent, remaining, assignment, adjacency, partitions, bounded)
                generation = model_call(prompt, BRANCH_SCHEMA)
                branch_calls += 1
                if generation is None:
                    return finish("CALL_OR_TOKEN_CAP" if "cap" in failure_reason else "ENDPOINT_ERROR")
                parsed = generation.get("parsed") or {}
                try:
                    candidate = int(parsed.get("color"))
                    branch_parseable += 1
                except (TypeError, ValueError):
                    failure_reason = "unparseable_branch"
                    return finish("INVALID_BRANCH")
                if candidate not in remaining:
                    failure_reason = "branch_color_not_in_remaining_domain"
                    return finish("INVALID_BRANCH")
                branch_valid += 1
                branch_exact += int(candidate == reference_color)
                chosen_color = candidate
                if len(trace_samples) < 12:
                    trace_samples.append({
                        "event": "branch",
                        "vertex": vertex,
                        "remaining": remaining,
                        "reference": reference_color,
                        "prediction": candidate,
                        "prompt_tokens": int(generation.get("prompt_tokens", 0)),
                        "output_tokens": int(generation.get("output_tokens", 0)),
                    })
            next_choice[vertex] += 1
            assignment[vertex] = int(chosen_color)
            item = {"vertex": int(vertex), "color": int(chosen_color), "agent": int(agent), "order_index": int(cursor)}
            trail.append(item)
            registers[agent].append(item)
            if any(partitions[neighbor] != agent for neighbor in adjacency[vertex]):
                boundary_commit_messages += 1
            cursor += 1
            continue

        blockers = set().union(*blocked_colors.values()) if blocked_colors else set()
        blockers = {item for item in blockers if item in assignment and position[item] < cursor}
        next_choice[vertex] = 0
        if not blockers or not trail:
            failure_reason = "no_conflict_recovery_target"
            return finish("EXHAUSTED")
        cross_block = any(partitions[blocker] != partitions[vertex] for blocker in blockers)
        cross_block_messages += int(cross_block)
        windows: dict[int, list[dict[str, int]]] = {}
        starts: dict[int, int] = {}
        for agent in sorted(set(partitions)):
            start, bounded = _register_view(registers[agent], int(r_value))
            starts[agent] = start
            windows[agent] = bounded
        valid_targets: list[dict[str, int]] = []
        for blocker in sorted(blockers):
            agent = partitions[blocker]
            register = registers[agent]
            absolute_index = max((index for index, item in enumerate(register) if item["vertex"] == blocker), default=-1)
            entry_index = absolute_index - starts[agent]
            if 0 <= entry_index < len(windows[agent]):
                valid_targets.append({
                    "agent": int(agent),
                    "entry_index": int(entry_index),
                    "variable": int(blocker),
                    "order_index": int(position[blocker]),
                })
        if not valid_targets:
            failure_reason = "all_conflict_targets_outside_local_windows"
            return finish("NO_RECOVERY_TARGET")
        reference_vertex = max(blockers, key=lambda item: position[item])
        reference_target = next((target for target in valid_targets if target["variable"] == reference_vertex), None)
        if reference_target is None:
            failure_reason = "deepest_conflict_target_outside_local_window"
            return finish("NO_RECOVERY_TARGET")
        chosen_target = reference_target
        if _uses_qwen_route(policy):
            agent = partitions[vertex]
            prompt = _route_prompt(row, vertex, agent, sorted(blockers), valid_targets, windows)
            generation = model_call(prompt, ROUTE_SCHEMA)
            route_calls += 1
            if generation is None:
                return finish("CALL_OR_TOKEN_CAP" if "cap" in failure_reason else "ENDPOINT_ERROR")
            parsed = generation.get("parsed") or {}
            try:
                predicted_agent = int(parsed.get("agent"))
                predicted_index = int(parsed.get("entry_index"))
                route_parseable += 1
            except (TypeError, ValueError):
                failure_reason = "unparseable_route"
                return finish("INVALID_ROUTE")
            candidate = next(
                (
                    target
                    for target in valid_targets
                    if target["agent"] == predicted_agent and target["entry_index"] == predicted_index
                ),
                None,
            )
            if candidate is None:
                failure_reason = "route_pair_not_in_valid_targets"
                return finish("INVALID_ROUTE")
            route_valid += 1
            route_exact += int(
                candidate["agent"] == reference_target["agent"]
                and candidate["entry_index"] == reference_target["entry_index"]
            )
            chosen_target = candidate
            if len(trace_samples) < 12:
                trace_samples.append({
                    "event": "route",
                    "vertex": vertex,
                    "valid_target_count": len(valid_targets),
                    "reference": reference_target,
                    "prediction": candidate,
                    "prompt_tokens": int(generation.get("prompt_tokens", 0)),
                    "output_tokens": int(generation.get("output_tokens", 0)),
                })
        target_vertex = int(chosen_target["variable"])
        conflict_sets[target_vertex].update(blocker for blocker in blockers if blocker != target_vertex)
        target_trail_index = max(index for index, item in enumerate(trail) if item["vertex"] == target_vertex)
        popped = trail[target_trail_index:]
        popped_vertices = {item["vertex"] for item in popped}
        recoveries += 1
        retractions += len(popped)
        for item in popped:
            assignment.pop(item["vertex"], None)
        trail = trail[:target_trail_index]
        for agent in list(registers):
            registers[agent] = [item for item in registers[agent] if item["vertex"] not in popped_vertices]
        for item in popped[1:]:
            next_choice[item["vertex"]] = 0
            conflict_sets[item["vertex"]].clear()
        conflict_sets[vertex].clear()
        cursor = popped[0]["order_index"]


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for cell, policy in sorted({(row["cell"], row["policy"]) for row in rows}):
        subset = [row for row in rows if row["cell"] == cell and row["policy"] == policy]
        output.append({
            "cell": cell,
            "policy": policy,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_steps": mean(float(row["steps"]) for row in subset),
            "mean_llm_calls": mean(float(row["llm_calls"]) for row in subset),
            "mean_total_tokens": mean(float(row["total_tokens"]) for row in subset),
            "branch_valid_rate": sum(float(row["branch_valid_rate"]) * row["branch_calls"] for row in subset) / max(1, sum(row["branch_calls"] for row in subset)),
            "route_valid_rate": sum(float(row["route_valid_rate"]) * row["route_calls"] for row in subset) / max(1, sum(row["route_calls"] for row in subset)),
            "route_exact_rate": sum(float(row["route_exact_rate"]) * row["route_calls"] for row in subset) / max(1, sum(row["route_calls"] for row in subset)),
            "status_counts": dict(Counter(str(row["status"]) for row in subset)),
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Run gated end-to-end real-Qwen multi-agent development episodes.")
    parser.add_argument("--manifest", type=Path, default=Path("results/multiagent_core_2x2_preflight/instance_manifest.json"))
    parser.add_argument("--decision-gate", type=Path, default=Path("results/multiagent_real_qwen_decision_gate/evaluation.json"))
    parser.add_argument("--output", type=Path, default=Path("results/multiagent_real_qwen_end_to_end/dev_results.json"))
    parser.add_argument("--checkpoint", type=Path, default=Path("results/multiagent_real_qwen_end_to_end/checkpoint.json"))
    parser.add_argument("--instances-per-cell", type=int, default=2)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--node-cap", type=int, default=1500)
    parser.add_argument("--call-cap", type=int, default=160)
    parser.add_argument("--token-cap", type=int, default=80000)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--base-urls", default="http://127.0.0.1:8104/v1,http://127.0.0.1:8105/v1,http://127.0.0.1:8106/v1,http://127.0.0.1:8107/v1")
    parser.add_argument("--model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    decision_gate = json.loads(args.decision_gate.read_text(encoding="utf-8"))
    if decision_gate.get("status") != "MULTIAGENT_REAL_QWEN_DECISION_GATE_PASS" or not decision_gate.get("gates", {}).get("go_end_to_end_dev"):
        raise SystemExit("end-to-end run blocked: real-Qwen decision gate has not passed")
    manifest = list(json.loads(args.manifest.read_text(encoding="utf-8")).get("rows", []))
    selected: list[dict[str, Any]] = []
    for cell in ("under_low", "under_high", "over_low", "over_high"):
        selected.extend(sorted((row for row in manifest if row["cell"] == cell), key=lambda row: row["instance_id"])[: int(args.instances_per_cell)])
    jobs = [(row, policy) for row in selected for policy in POLICIES]
    checkpoint_path = args.checkpoint if args.checkpoint.is_absolute() else REPO_ROOT / args.checkpoint
    completed: list[dict[str, Any]] = []
    if args.resume and checkpoint_path.exists():
        completed = list(json.loads(checkpoint_path.read_text(encoding="utf-8")).get("rows", []))
    done = {str(row["episode_key"]) for row in completed}
    pending = [(row, policy) for row, policy in jobs if _episode_key(str(row["cell"]), str(row["instance_id"]), policy) not in done]
    base_urls = [item.strip() for item in args.base_urls.split(",") if item.strip()]
    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
        futures = {
            executor.submit(
                _run_episode,
                row,
                policy,
                base_urls[index % len(base_urls)],
                args.model,
                args.register,
                args.node_cap,
                args.call_cap,
                args.token_cap,
                args.max_new_tokens,
            ): _episode_key(str(row["cell"]), str(row["instance_id"]), policy)
            for index, (row, policy) in enumerate(pending)
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                completed.append(future.result())
            except Exception as exc:
                cell, instance_id, policy = key.split("::", 2)
                completed.append({
                    "episode_key": key,
                    "cell": cell,
                    "instance_id": instance_id,
                    "policy": policy,
                    "solved": False,
                    "status": "UNHANDLED_EXCEPTION",
                    "failure_reason": f"{type(exc).__name__}:{str(exc)[:300]}",
                    "oracle_fallback_used": False,
                    "headline_eligible": False,
                })
            completed.sort(key=lambda row: row["episode_key"])
            _write_json(checkpoint_path, {"schema": SCHEMA_VERSION + "_checkpoint", "rows": completed})

    expected = len(jobs)
    complete = len(completed) == expected
    summary = _summarize([row for row in completed if "steps" in row])
    payload = {
        "schema": SCHEMA_VERSION,
        "status": STATUS_COMPLETE if complete else STATUS_PARTIAL,
        "decision_gate": str(args.decision_gate),
        "source_manifest": str(args.manifest),
        "config": vars(args) | {
            "manifest": str(args.manifest),
            "decision_gate": str(args.decision_gate),
            "output": str(args.output),
            "checkpoint": str(args.checkpoint),
        },
        "expected_episodes": expected,
        "completed_episodes": len(completed),
        "rows": completed,
        "summary": summary,
        "headline_eligible": False,
        "honesty": {
            "development_only": True,
            "no_oracle_fallback": all(not row.get("oracle_fallback_used", True) for row in completed),
            "does_not_establish": "This small endpoint development run does not establish a multi-agent solve-rate claim. A new independent 50-instance-per-cell confirmatory manifest is required.",
        },
    }
    output_path = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    _write_json(output_path, payload)
    print(json.dumps({"path": str(output_path.relative_to(REPO_ROOT)), "status": payload["status"], "episodes": len(completed)}), flush=True)


if __name__ == "__main__":
    main()
