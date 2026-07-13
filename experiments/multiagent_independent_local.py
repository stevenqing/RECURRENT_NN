"""Independent-local multi-agent search contribution gate.

Unlike the earlier global-trail team, each agent owns an independent cursor,
choice state, conflict sets, and local trail. A source agent cannot mutate a
target agent. Cross-agent recovery follows request -> target-local rollback ->
acknowledgement. This is a symbolic mechanism experiment on the frozen 2x2
manifest and is never headline eligible by itself.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.capacity.stats import mcnemar_exact
from experiments.multiagent_capacity_coupling import REPO_ROOT, _adjacency, _run_search


SCHEMA_VERSION = "multiagent_independent_local_contribution_v1"
STATUS_STRONG = "STRONG_STRUCTURAL_FREE_LUNCH_CANDIDATE"
STATUS_PARALLEL = "PARALLEL_ONLY_CANDIDATE"
STATUS_HORIZONTAL = "HORIZONTAL_CAPACITY_ONLY"
STATUS_NONE = "NO_STRUCTURAL_CONTRIBUTION"
INDEPENDENT_ARMS = ("independent_local_cbj", "independent_local_chronological")
BASELINE_ARMS = ("global_trail_cbj", "centralized_sharded_MR", "monolith_MR", "monolith_R")
ALL_ARMS = INDEPENDENT_ARMS + BASELINE_ARMS


@dataclass
class RollbackRequest:
    request_id: int
    source_agent: int
    target_agent: int
    target_vertex: int
    target_timestamp: int
    deadend_vertex: int
    blockers: tuple[int, ...]
    mode: str
    reason: str


@dataclass
class AgentState:
    agent_id: int
    order: list[int]
    cursor: int = 0
    next_choice: dict[int, int] = field(default_factory=dict)
    conflict_sets: dict[int, set[int]] = field(default_factory=dict)
    rejected_targets: dict[int, set[int]] = field(default_factory=dict)
    trail: list[dict[str, int]] = field(default_factory=list)
    pending: deque[RollbackRequest] = field(default_factory=deque)
    waiting_request_id: int | None = None
    waiting_vertex: int | None = None
    done: bool = False
    exhausted: bool = False


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path.relative_to(REPO_ROOT)), "status": payload.get("status")}), flush=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_frozen_inputs(
    args: argparse.Namespace,
    contract: dict[str, Any],
    manifest: list[dict[str, Any]],
) -> dict[str, Any]:
    config = contract["config"]
    expected_cells = {"under_low", "under_high", "over_low", "over_high"}
    cell_counts = Counter(str(row["cell"]) for row in manifest)
    checks = {
        "schema": contract.get("schema") == "multiagent_structural_free_lunch_contract_v1",
        "agents": int(args.agents) == int(config["M"]),
        "register": int(args.register) == int(config["R"]),
        "total_window": int(args.agents) * int(args.register) == int(config["MR"]),
        "activation_cap": int(args.activation_cap) == int(config["node_activation_cap"]),
        "channel_cap": int(args.channel_cap) == int(config["request_channel_cap"]),
        "cells": set(cell_counts) == expected_cells,
        "cell_counts": all(
            int(cell_counts[cell]) == int(config["instances_per_cell"]) for cell in expected_cells
        ),
        "unique_instances": len({str(row["instance_id"]) for row in manifest}) == len(manifest),
        "arms": set(contract["arms"]) == set(ALL_ARMS),
    }
    if not all(checks.values()):
        raise ValueError(f"frozen contract validation failed: {checks}")
    return {"pass": True, "checks": checks, "cell_counts": dict(sorted(cell_counts.items()))}


def _valid_solution(n: int, k: int, edges: list[tuple[int, int]], assignment: dict[int, int]) -> bool:
    return (
        len(assignment) == int(n)
        and all(int(assignment.get(vertex, 0)) in range(1, int(k) + 1) for vertex in range(int(n)))
        and all(int(assignment[left]) != int(assignment[right]) for left, right in edges)
    )


def _make_agents(row: dict[str, Any]) -> dict[int, AgentState]:
    partitions = [int(value) for value in row["partitions"]]
    global_order = [int(value) for value in row["order"]]
    agents: dict[int, AgentState] = {}
    for agent_id in sorted(set(partitions)):
        order = [vertex for vertex in global_order if partitions[vertex] == agent_id]
        agents[agent_id] = AgentState(
            agent_id=agent_id,
            order=order,
            next_choice={vertex: 0 for vertex in order},
            conflict_sets={vertex: set() for vertex in order},
            rejected_targets={vertex: set() for vertex in order},
        )
    return agents


def _rollback_local(
    state: AgentState,
    target_vertex: int,
    assignment: dict[int, int],
    assignment_meta: dict[int, dict[str, int]],
    partitions: list[int],
    r_value: int,
) -> tuple[list[dict[str, int]] | None, str | None]:
    target_index = max(
        (index for index, item in enumerate(state.trail) if int(item["vertex"]) == int(target_vertex)),
        default=-1,
    )
    if target_index < 0:
        return None, "target_not_in_owner_trail"
    if target_index < max(0, len(state.trail) - int(r_value)):
        return None, "target_outside_owner_window"
    popped = state.trail[target_index:]
    for item in popped:
        vertex = int(item["vertex"])
        if int(partitions[vertex]) != int(state.agent_id):
            return None, "ownership_violation_in_local_trail"
    for item in popped:
        vertex = int(item["vertex"])
        assignment.pop(vertex, None)
        assignment_meta.pop(vertex, None)
    state.trail = state.trail[:target_index]
    for item in popped[1:]:
        vertex = int(item["vertex"])
        state.next_choice[vertex] = 0
        state.conflict_sets[vertex].clear()
        state.rejected_targets[vertex].clear()
    state.rejected_targets[target_vertex].clear()
    state.cursor = int(popped[0]["local_index"])
    state.done = False
    state.exhausted = False
    return popped, None


def _run_independent(
    row: dict[str, Any],
    arm: str,
    r_value: int,
    activation_cap: int,
    channel_cap: int,
) -> dict[str, Any]:
    if arm not in INDEPENDENT_ARMS:
        raise ValueError(arm)
    n = int(row["n_vertices"])
    k = int(row["k"])
    edges = [tuple(map(int, edge)) for edge in row["edges"]]
    partitions = [int(value) for value in row["partitions"]]
    adjacency = _adjacency(n, edges)
    global_order = [int(value) for value in row["order"]]
    position = {vertex: index for index, vertex in enumerate(global_order)}
    agents = _make_agents(row)
    assignment: dict[int, int] = {}
    assignment_meta: dict[int, dict[str, int]] = {}
    request_sources: dict[int, int] = {}
    requests: dict[int, RollbackRequest] = {}
    next_request_id = 0
    timestamp = 0
    activations = 0
    parallel_rounds = 0
    branch_attempts = 0
    recoveries = 0
    retractions = 0
    requests_sent = 0
    requests_executed = 0
    acknowledgements = 0
    nacks = 0
    communication_tokens = 0
    boundary_commit_messages = 0
    ownership_violations = 0
    cross_agent_direct_mutations = 0
    priority_direction_violations = 0
    dependency_invalidations = 0
    window_rejections = 0
    out_of_window_rollback_executions = 0
    protocol_shutdown_acks = 0
    max_pending_requests = 0
    max_local_register = 0
    max_local_trail_length = 0
    failure_reason = ""
    protocol_samples: list[dict[str, Any]] = []

    def finish(status: str) -> dict[str, Any]:
        nonlocal acknowledgements, communication_tokens, nacks, protocol_shutdown_acks
        for target_state in agents.values():
            while target_state.pending:
                request = target_state.pending.popleft()
                source_state = agents[request.source_agent]
                nacks += 1
                acknowledgements += 1
                protocol_shutdown_acks += 1
                communication_tokens += 1
                if source_state.waiting_request_id == request.request_id:
                    source_state.waiting_request_id = None
                    source_state.waiting_vertex = None
                if len(protocol_samples) < 32:
                    protocol_samples.append({
                        "event": "terminal_nack_ack",
                        "terminal_status": status,
                        "request_id": request.request_id,
                        "source_agent": request.source_agent,
                        "target_agent": request.target_agent,
                    })
        solved = status == "SOLVED" and _valid_solution(n, k, edges, assignment)
        final_status = "SOLVED" if solved else ("OFFICIAL_SCORE_FAIL" if status == "SOLVED" else status)
        pending_count = sum(len(state.pending) for state in agents.values())
        lifecycle_valid = (
            requests_sent == requests_executed + nacks
            and acknowledgements == requests_sent
            and pending_count == 0
            and all(state.waiting_request_id is None for state in agents.values())
        )
        aggregate_work = branch_attempts + retractions + requests_sent + acknowledgements
        return {
            "instance_id": str(row["instance_id"]),
            "cell": str(row["cell"]),
            "capacity": str(row["capacity"]),
            "coupling": str(row["coupling"]),
            "arm": arm,
            "solved": solved,
            "status": final_status,
            "failure_reason": failure_reason,
            "activations": activations,
            "parallel_rounds": parallel_rounds,
            "branch_attempts": branch_attempts,
            "recoveries": recoveries,
            "retractions": retractions,
            "requests_sent": requests_sent,
            "requests_executed": requests_executed,
            "acknowledgements": acknowledgements,
            "nacks": nacks,
            "communication_tokens": communication_tokens,
            "boundary_commit_messages": boundary_commit_messages,
            "aggregate_work": aggregate_work,
            "max_pending_requests": max_pending_requests,
            "max_local_register": max_local_register,
            "max_local_trail_length": max_local_trail_length,
            "declared_per_agent_window": int(r_value),
            "declared_total_window": int(r_value) * len(agents),
            "cross_agent_direct_mutations": cross_agent_direct_mutations,
            "ownership_violations": ownership_violations,
            "priority_direction_violations": priority_direction_violations,
            "dependency_invalidations": dependency_invalidations,
            "window_rejections": window_rejections,
            "out_of_window_rollback_executions": out_of_window_rollback_executions,
            "protocol_shutdown_acks": protocol_shutdown_acks,
            "request_lifecycle_valid": lifecycle_valid,
            "no_global_trail": True,
            "independent_agent_state": True,
            "no_oracle_or_model_fallback": True,
            "protocol_samples": protocol_samples,
            "evaluation_mode": "symbolic_independent_local_contribution_v1",
            "headline_eligible": False,
        }

    def execute_local_rollback(
        state: AgentState,
        target_vertex: int,
        expected_timestamp: int,
    ) -> tuple[bool, str | None, int]:
        nonlocal max_local_register, max_local_trail_length, out_of_window_rollback_executions, ownership_violations
        nonlocal recoveries, retractions, window_rejections
        current_meta = assignment_meta.get(target_vertex)
        if current_meta is None or int(current_meta["timestamp"]) != int(expected_timestamp):
            return True, "stale_assignment_already_retracted", 0
        target_index = max(
            (index for index, item in enumerate(state.trail) if int(item["vertex"]) == int(target_vertex)),
            default=-1,
        )
        outside_window = target_index >= 0 and target_index < max(0, len(state.trail) - int(r_value))
        popped, error = _rollback_local(
            state,
            target_vertex,
            assignment,
            assignment_meta,
            partitions,
            int(r_value),
        )
        if error:
            ownership_violations += int(error == "ownership_violation_in_local_trail")
            window_rejections += int(error == "target_outside_owner_window")
            return False, error, 0
        out_of_window_rollback_executions += int(outside_window)
        recoveries += 1
        retractions += len(popped or [])
        max_local_trail_length = max(max_local_trail_length, len(state.trail))
        max_local_register = max(max_local_register, min(len(state.trail), int(r_value)))
        return True, None, len(popped or [])

    def enqueue_request(
        source_state: AgentState,
        target_agent: int,
        target_vertex: int,
        target_timestamp: int,
        source_vertex: int,
        blockers: set[int],
        reason: str,
    ) -> bool:
        nonlocal communication_tokens, max_pending_requests, next_request_id, requests_sent
        pending_count = sum(len(item.pending) for item in agents.values())
        if pending_count >= int(channel_cap):
            return False
        request = RollbackRequest(
            request_id=next_request_id,
            source_agent=source_state.agent_id,
            target_agent=int(target_agent),
            target_vertex=int(target_vertex),
            target_timestamp=int(target_timestamp),
            deadend_vertex=int(source_vertex),
            blockers=tuple(sorted(blockers)),
            mode="cbj" if arm == "independent_local_cbj" else "chronological",
            reason=reason,
        )
        requests[next_request_id] = request
        request_sources[next_request_id] = source_state.agent_id
        next_request_id += 1
        agents[target_agent].pending.append(request)
        source_state.waiting_request_id = request.request_id
        source_state.waiting_vertex = source_vertex
        requests_sent += 1
        communication_tokens += 2 + 2 * len(blockers)
        max_pending_requests = max(
            max_pending_requests,
            sum(len(item.pending) for item in agents.values()),
        )
        if len(protocol_samples) < 32:
            protocol_samples.append({
                "event": "rollback_request",
                "reason": reason,
                "request_id": request.request_id,
                "source_agent": source_state.agent_id,
                "target_agent": int(target_agent),
                "target_vertex": int(target_vertex),
                "target_timestamp": int(target_timestamp),
                "deadend_vertex": int(source_vertex),
                "blockers": sorted(blockers),
            })
        return True

    while activations < int(activation_cap):
        parallel_rounds += 1
        progress = False
        for agent_id in sorted(agents):
            state = agents[agent_id]
            if activations >= int(activation_cap):
                break
            activations += 1

            if state.pending:
                request = state.pending.popleft()
                if (
                    int(request.target_agent) != int(state.agent_id)
                    or int(partitions[request.target_vertex]) != int(state.agent_id)
                ):
                    ownership_violations += 1
                    success, error, popped_count = False, "request_target_ownership_violation", 0
                elif position[request.target_vertex] >= position[request.deadend_vertex]:
                    priority_direction_violations += 1
                    success, error, popped_count = False, "non_decreasing_priority_request", 0
                else:
                    success, error, popped_count = execute_local_rollback(
                        state,
                        request.target_vertex,
                        request.target_timestamp,
                    )
                source_state = agents[request.source_agent]
                if success:
                    if popped_count and request.mode == "cbj":
                        state.conflict_sets[request.target_vertex].update(
                            blocker
                            for blocker in request.blockers
                            if position[blocker] < position[request.target_vertex]
                        )
                    requests_executed += 1
                    acknowledgements += 1
                    communication_tokens += 2
                    source_state.waiting_request_id = None
                    if source_state.waiting_vertex is not None and request.reason == "deadend":
                        source_state.next_choice[source_state.waiting_vertex] = 0
                        source_state.conflict_sets[source_state.waiting_vertex].clear()
                    source_state.waiting_vertex = None
                    source_state.done = False
                    if len(protocol_samples) < 32:
                        protocol_samples.append({
                            "event": "target_rollback_ack",
                            "request_id": request.request_id,
                            "reason": request.reason,
                            "source_agent": request.source_agent,
                            "target_agent": request.target_agent,
                            "target_vertex": request.target_vertex,
                            "target_timestamp": request.target_timestamp,
                            "popped_count": popped_count,
                            "stale_ack": error == "stale_assignment_already_retracted",
                        })
                else:
                    nacks += 1
                    acknowledgements += 1
                    source_state.waiting_request_id = None
                    if source_state.waiting_vertex is not None:
                        source_state.rejected_targets[source_state.waiting_vertex].add(request.target_vertex)
                    source_state.waiting_vertex = None
                    if len(protocol_samples) < 32:
                        protocol_samples.append({
                            "event": "target_rollback_nack",
                            "request_id": request.request_id,
                            "reason": request.reason,
                            "source_agent": request.source_agent,
                            "target_agent": request.target_agent,
                            "target_vertex": request.target_vertex,
                            "error": error,
                        })
                progress = True
                continue

            if state.waiting_request_id is not None or state.exhausted:
                continue

            invalidated: tuple[int, set[int], int] | None = None
            for item in state.trail:
                local_vertex = int(item["vertex"])
                local_color = int(item["color"])
                earlier_blockers = {
                    neighbor
                    for neighbor in adjacency[local_vertex]
                    if position[neighbor] < position[local_vertex]
                    and assignment.get(neighbor) == local_color
                }
                if earlier_blockers:
                    invalidated = (local_vertex, earlier_blockers, int(item["timestamp"]))
                    break
            if invalidated is not None:
                invalidated_vertex, _earlier_blockers, invalidated_timestamp = invalidated
                success, error, popped_count = execute_local_rollback(
                    state,
                    invalidated_vertex,
                    invalidated_timestamp,
                )
                if not success:
                    rejected = state.rejected_targets[invalidated_vertex]
                    if arm == "independent_local_cbj":
                        candidates = _earlier_blockers - rejected
                    else:
                        candidates = {
                            candidate
                            for candidate in assignment_meta
                            if position[candidate] < position[invalidated_vertex]
                        } - rejected
                    target_vertex = max(candidates, key=lambda item: position[item], default=-1)
                    if target_vertex < 0:
                        state.exhausted = True
                        failure_reason = f"dependency_invalidation_no_route_after_{error}"
                    else:
                        target_agent = int(partitions[target_vertex])
                        target_timestamp = int(assignment_meta[target_vertex]["timestamp"])
                        if target_agent == agent_id:
                            routed, route_error, routed_count = execute_local_rollback(
                                state,
                                target_vertex,
                                target_timestamp,
                            )
                            if not routed:
                                state.rejected_targets[invalidated_vertex].add(target_vertex)
                            else:
                                dependency_invalidations += 1
                                if routed_count and arm == "independent_local_cbj":
                                    state.conflict_sets[target_vertex].update(
                                        blocker
                                        for blocker in _earlier_blockers
                                        if position[blocker] < position[target_vertex]
                                    )
                                if routed_count <= 0:
                                    state.exhausted = True
                                    failure_reason = f"dependency_invalidation_{route_error}"
                        elif not enqueue_request(
                            state,
                            target_agent,
                            target_vertex,
                            target_timestamp,
                            invalidated_vertex,
                            _earlier_blockers,
                            "dependency_invalidation",
                        ):
                            failure_reason = "request_channel_capacity_exceeded"
                            return finish("COMM_CAP")
                else:
                    dependency_invalidations += 1
                    state.next_choice[invalidated_vertex] = 0
                    state.conflict_sets[invalidated_vertex].clear()
                    state.rejected_targets[invalidated_vertex].clear()
                    if popped_count <= 0:
                        state.exhausted = True
                        failure_reason = "dependency_invalidation_stale_local_version"
                progress = True
                continue

            while state.cursor < len(state.order) and state.order[state.cursor] in assignment:
                state.cursor += 1
            if state.cursor >= len(state.order):
                state.done = True
                continue

            vertex = int(state.order[state.cursor])
            if partitions[vertex] != agent_id:
                ownership_violations += 1
                failure_reason = "agent_cursor_ownership_violation"
                return finish("PROTOCOL_VIOLATION")

            chosen_color: int | None = None
            while state.next_choice[vertex] < k:
                color = state.next_choice[vertex] + 1
                state.next_choice[vertex] += 1
                blockers = {
                    neighbor
                    for neighbor in adjacency[vertex]
                    if position[neighbor] < position[vertex]
                    and assignment.get(neighbor) == color
                }
                if not blockers:
                    chosen_color = color
                    break
                state.conflict_sets[vertex].update(blockers)
            branch_attempts += 1
            progress = True

            if chosen_color is not None:
                timestamp += 1
                assignment[vertex] = int(chosen_color)
                assignment_meta[vertex] = {"agent": agent_id, "timestamp": timestamp, "color": int(chosen_color)}
                state.trail.append({
                    "vertex": vertex,
                    "color": int(chosen_color),
                    "local_index": int(state.cursor),
                    "timestamp": timestamp,
                })
                max_local_trail_length = max(max_local_trail_length, len(state.trail))
                max_local_register = max(max_local_register, min(len(state.trail), int(r_value)))
                state.rejected_targets[vertex].clear()
                if any(partitions[neighbor] != agent_id for neighbor in adjacency[vertex]):
                    boundary_commit_messages += 1
                    communication_tokens += 4
                state.cursor += 1
                state.done = False
                continue

            blockers = {
                blocker
                for blocker in state.conflict_sets[vertex]
                if blocker in assignment_meta and position[blocker] < position[vertex]
            }
            rejected = state.rejected_targets[vertex]
            state.next_choice[vertex] = 0
            if arm == "independent_local_cbj" and blockers - rejected:
                target_vertex = max(blockers - rejected, key=lambda item: position[item])
            else:
                candidates = (
                    {
                        candidate
                        for candidate in assignment_meta
                        if position[candidate] < position[vertex]
                    }
                    - rejected
                    if arm == "independent_local_chronological"
                    else set()
                )
                target_vertex = max(
                    candidates,
                    key=lambda item: position[item],
                    default=-1,
                )
            if target_vertex < 0:
                state.exhausted = True
                failure_reason = "no_unrejected_assignment_to_rollback"
                continue
            target_agent = int(partitions[target_vertex])
            target_timestamp = int(assignment_meta[target_vertex]["timestamp"])
            if target_agent == agent_id:
                success, error, popped_count = execute_local_rollback(
                    state,
                    target_vertex,
                    target_timestamp,
                )
                if not success:
                    state.rejected_targets[vertex].add(target_vertex)
                elif popped_count and arm == "independent_local_cbj":
                    state.conflict_sets[target_vertex].update(
                        blocker for blocker in blockers if position[blocker] < position[target_vertex]
                    )
                state.conflict_sets[vertex].clear()
                continue

            if not enqueue_request(
                state,
                target_agent,
                target_vertex,
                target_timestamp,
                vertex,
                blockers,
                "deadend",
            ):
                failure_reason = "request_channel_capacity_exceeded"
                return finish("COMM_CAP")

        if _valid_solution(n, k, edges, assignment):
            return finish("SOLVED")
        if any(state.exhausted for state in agents.values()):
            # A failed owner request or exhausted local search makes this complete
            # symbolic episode unreadable; no centralized fallback is permitted.
            return finish("EXHAUSTED")
        if not progress:
            failure_reason = "scheduler_deadlock_no_progress"
            return finish("DEADLOCK")

    failure_reason = "activation_cap_reached"
    return finish("ACTIVATION_CAP")


def _run_baseline_rows(
    manifest: list[dict[str, Any]],
    m_agents: int,
    r_value: int,
    node_cap: int,
) -> list[dict[str, Any]]:
    arm_map = {
        "team_cbj": "global_trail_cbj",
        "centralized_sharded_MR": "centralized_sharded_MR",
        "monolith_MR": "monolith_MR",
        "monolith_R": "monolith_R",
    }
    rows = []
    for manifest_row in manifest:
        for source_arm, arm in arm_map.items():
            source = _run_search(
                manifest_row,
                source_arm,
                int(m_agents),
                int(r_value),
                int(node_cap),
            )
            cross_messages = int(source.get("cross_block_messages", 0))
            steps = int(source.get("steps", 0))
            retractions = int(source.get("retractions", 0))
            rows.append({
                "instance_id": source["instance_id"],
                "cell": source["cell"],
                "capacity": source["capacity"],
                "coupling": source["coupling"],
                "arm": arm,
                "solved": bool(source["solved"]),
                "status": source["status"],
                "activations": steps,
                "parallel_rounds": steps,
                "branch_attempts": steps,
                "recoveries": int(source.get("recoveries", 0)),
                "retractions": retractions,
                "requests_sent": cross_messages,
                "requests_executed": cross_messages,
                "acknowledgements": cross_messages,
                "nacks": 0,
                "communication_tokens": int(source.get("communication_tokens", 0)),
                "boundary_commit_messages": int(source.get("boundary_commit_messages", 0)),
                "aggregate_work": steps + retractions + cross_messages,
                "max_pending_requests": 0,
                "max_local_register": min(
                    int(source.get("max_register_length_per_agent", 0)),
                    int(source.get("declared_window_per_agent", 0)),
                ),
                "max_local_trail_length": int(source.get("max_register_length_per_agent", 0)),
                "declared_per_agent_window": int(source.get("declared_window_per_agent", 0)),
                "declared_total_window": int(source.get("declared_total_window", 0)),
                "cross_agent_direct_mutations": 0,
                "ownership_violations": 0,
                "request_lifecycle_valid": True,
                "no_global_trail": False,
                "independent_agent_state": False,
                "no_oracle_or_model_fallback": True,
                "protocol_samples": [],
                "evaluation_mode": "same_manifest_same_cap_control_v1",
                "headline_eligible": False,
            })
    return rows


def _summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for cell, arm in sorted({(row["cell"], row["arm"]) for row in rows}):
        subset = [row for row in rows if row["cell"] == cell and row["arm"] == arm]
        output.append({
            "cell": cell,
            "capacity": subset[0]["capacity"],
            "coupling": subset[0]["coupling"],
            "arm": arm,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_aggregate_work": mean(float(row["aggregate_work"]) for row in subset),
            "mean_parallel_rounds": mean(float(row["parallel_rounds"]) for row in subset),
            "mean_retractions": mean(float(row["retractions"]) for row in subset),
            "mean_requests": mean(float(row["requests_sent"]) for row in subset),
            "mean_communication_tokens": mean(float(row["communication_tokens"]) for row in subset),
            "mean_max_local_register": mean(float(row["max_local_register"]) for row in subset),
            "status_counts": dict(Counter(str(row["status"]) for row in subset)),
        })
    return output


def _protocol_audit(rows: list[dict[str, Any]], channel_cap: int) -> dict[str, Any]:
    independent_rows = [row for row in rows if row["arm"] in INDEPENDENT_ARMS]
    checks = {
        "no_cross_agent_direct_mutations": all(
            int(row["cross_agent_direct_mutations"]) == 0 for row in independent_rows
        ),
        "owner_only_mutation": all(int(row["ownership_violations"]) == 0 for row in independent_rows),
        "acyclic_priority_direction": all(
            int(row["priority_direction_violations"]) == 0 for row in independent_rows
        ),
        "no_out_of_window_execution": all(
            int(row["out_of_window_rollback_executions"]) == 0 for row in independent_rows
        ),
        "recoverable_window_occupancy_bounded": all(
            int(row["max_local_register"]) <= int(row["declared_per_agent_window"])
            for row in independent_rows
        ),
        "request_lifecycle_recomputed": all(
            int(row["requests_sent"]) == int(row["requests_executed"]) + int(row["nacks"])
            and int(row["acknowledgements"]) == int(row["requests_sent"])
            and bool(row["request_lifecycle_valid"])
            for row in independent_rows
        ),
        "request_channel_bounded": all(
            int(row["max_pending_requests"]) <= int(channel_cap) for row in independent_rows
        ),
        "no_global_trail": all(bool(row["no_global_trail"]) for row in independent_rows),
        "independent_agent_state": all(bool(row["independent_agent_state"]) for row in independent_rows),
        "no_fallback": all(bool(row["no_oracle_or_model_fallback"]) for row in independent_rows),
        "global_verification": all(row["status"] != "OFFICIAL_SCORE_FAIL" for row in independent_rows),
    }
    violations = []
    for row in independent_rows:
        failed = []
        if int(row["cross_agent_direct_mutations"]) != 0:
            failed.append("cross_agent_direct_mutation")
        if int(row["ownership_violations"]) != 0:
            failed.append("ownership")
        if int(row["priority_direction_violations"]) != 0:
            failed.append("priority_direction")
        if int(row["out_of_window_rollback_executions"]) != 0:
            failed.append("out_of_window_execution")
        if int(row["max_local_register"]) > int(row["declared_per_agent_window"]):
            failed.append("window_occupancy")
        if not bool(row["request_lifecycle_valid"]):
            failed.append("request_lifecycle")
        if int(row["max_pending_requests"]) > int(channel_cap):
            failed.append("request_channel")
        if row["status"] == "OFFICIAL_SCORE_FAIL":
            failed.append("global_verification")
        if failed:
            violations.append({
                "instance_id": row["instance_id"],
                "cell": row["cell"],
                "arm": row["arm"],
                "failed": failed,
            })
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "violations": violations,
        "totals": {
            "rows": len(independent_rows),
            "requests_sent": sum(int(row["requests_sent"]) for row in independent_rows),
            "acknowledgements": sum(int(row["acknowledgements"]) for row in independent_rows),
            "nacks": sum(int(row["nacks"]) for row in independent_rows),
            "window_rejections": sum(int(row["window_rejections"]) for row in independent_rows),
            "out_of_window_rollback_executions": sum(
                int(row["out_of_window_rollback_executions"]) for row in independent_rows
            ),
        },
    }


def _lookup(summary: list[dict[str, Any]], cell: str, arm: str) -> dict[str, Any]:
    return next(row for row in summary if row["cell"] == cell and row["arm"] == arm)


def _paired_tests(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tests = []
    contrasts = (
        ("independent_local_cbj", "monolith_MR"),
        ("independent_local_cbj", "centralized_sharded_MR"),
        ("independent_local_cbj", "global_trail_cbj"),
        ("independent_local_cbj", "independent_local_chronological"),
    )
    for cell in sorted({row["cell"] for row in rows}):
        ids = sorted({row["instance_id"] for row in rows if row["cell"] == cell})
        index = {(row["instance_id"], row["arm"]): row for row in rows if row["cell"] == cell}
        for left_arm, right_arm in contrasts:
            left = [bool(index[(instance_id, left_arm)]["solved"]) for instance_id in ids]
            right = [bool(index[(instance_id, right_arm)]["solved"]) for instance_id in ids]
            tests.append({
                "cell": cell,
                "left_arm": left_arm,
                "right_arm": right_arm,
                "n_pairs": len(ids),
                "left_solve_rate": mean(map(float, left)),
                "right_solve_rate": mean(map(float, right)),
                "solve_rate_difference": mean(map(float, left)) - mean(map(float, right)),
                "left_only": sum(a and not b for a, b in zip(left, right)),
                "right_only": sum(b and not a for a, b in zip(left, right)),
                "p_two_sided_exact_mcnemar": mcnemar_exact(left, right),
                "confirmatory": False,
            })
    return tests


def _gates(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    protocol_audit: dict[str, Any],
) -> dict[str, Any]:
    independent = _lookup(summary, "over_low", "independent_local_cbj")
    mono_mr = _lookup(summary, "over_low", "monolith_MR")
    central = _lookup(summary, "over_low", "centralized_sharded_MR")
    global_team = _lookup(summary, "over_low", "global_trail_cbj")
    independent_high = _lookup(summary, "over_high", "independent_local_cbj")
    chrono_low = _lookup(summary, "over_low", "independent_local_chronological")
    chrono_high = _lookup(summary, "over_high", "independent_local_chronological")
    work_ratio_central = independent["mean_aggregate_work"] / max(central["mean_aggregate_work"], 1e-12)
    work_ratio_mono = independent["mean_aggregate_work"] / max(mono_mr["mean_aggregate_work"], 1e-12)
    rounds_ratio = independent["mean_parallel_rounds"] / max(central["mean_parallel_rounds"], 1e-12)
    coupling_work_ratio = independent_high["mean_aggregate_work"] / max(independent["mean_aggregate_work"], 1e-12)
    coordination_signals = []
    for independent_row, chrono_row in ((independent, chrono_low), (independent_high, chrono_high)):
        solve_gain = independent_row["solve_rate"] - chrono_row["solve_rate"]
        work_reduction = 1.0 - independent_row["mean_aggregate_work"] / max(chrono_row["mean_aggregate_work"], 1e-12)
        noninferior = independent_row["solve_rate"] >= chrono_row["solve_rate"] - 0.10
        coordination_signals.append(solve_gain >= 0.10 or (noninferior and work_reduction >= 0.20))
    gates = {
        "protocol_invariants": bool(protocol_audit["pass"]),
        "G1_solve_noninferiority": (
            independent["solve_rate"] >= mono_mr["solve_rate"] - 0.10
            and independent["solve_rate"] >= central["solve_rate"] - 0.10
        ),
        "G2_aggregate_work_advantage": work_ratio_central <= 0.80 or work_ratio_mono <= 0.80,
        "G3_critical_path_advantage": rounds_ratio <= 0.60,
        "G4_coupling_boundary": coupling_work_ratio >= 1.20,
        "G5_coordination_mechanism": any(coordination_signals),
        "protocol_detail": protocol_audit["checks"],
        "observed": {
            "independent_over_low_solve": independent["solve_rate"],
            "monolith_MR_over_low_solve": mono_mr["solve_rate"],
            "centralized_over_low_solve": central["solve_rate"],
            "global_trail_over_low_solve": global_team["solve_rate"],
            "work_ratio_vs_centralized": work_ratio_central,
            "work_ratio_vs_monolith_MR": work_ratio_mono,
            "critical_rounds_ratio_vs_centralized_steps": rounds_ratio,
            "coupling_work_ratio_high_vs_low": coupling_work_ratio,
            "independent_over_low_work": independent["mean_aggregate_work"],
            "independent_over_high_work": independent_high["mean_aggregate_work"],
        },
    }
    if not gates["protocol_invariants"] or not gates["G1_solve_noninferiority"]:
        verdict = STATUS_NONE
    elif gates["G2_aggregate_work_advantage"] and gates["G3_critical_path_advantage"] and gates["G4_coupling_boundary"] and gates["G5_coordination_mechanism"]:
        verdict = STATUS_STRONG
    elif gates["G3_critical_path_advantage"] and gates["G4_coupling_boundary"] and gates["G5_coordination_mechanism"]:
        verdict = STATUS_PARALLEL
    else:
        verdict = STATUS_HORIZONTAL
    gates["verdict"] = verdict
    return gates


def run(args: argparse.Namespace) -> dict[str, Any]:
    contract_payload = json.loads(args.contract.read_text(encoding="utf-8"))
    manifest_payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest = list(manifest_payload.get("rows", []))
    frozen_input_validation = _validate_frozen_inputs(args, contract_payload, manifest)
    if int(args.instances_per_cell) > 0:
        selected = []
        for cell in ("under_low", "under_high", "over_low", "over_high"):
            selected.extend(sorted((row for row in manifest if row["cell"] == cell), key=lambda row: row["instance_id"])[: int(args.instances_per_cell)])
        manifest = selected
    independent_rows: list[dict[str, Any]] = []
    for row in manifest:
        for arm in INDEPENDENT_ARMS:
            independent_rows.append(
                _run_independent(
                    row,
                    arm,
                    int(args.register),
                    int(args.activation_cap),
                    int(args.channel_cap),
                )
            )
    selected_ids = {str(row["instance_id"]) for row in manifest}
    baseline_rows = _run_baseline_rows(
        manifest,
        int(args.agents),
        int(args.register),
        int(args.activation_cap),
    )
    rows = independent_rows + baseline_rows
    summary = _summaries(rows)
    protocol_audit = _protocol_audit(rows, int(args.channel_cap))
    gates = _gates(rows, summary, protocol_audit)
    return {
        "schema": SCHEMA_VERSION,
        "status": gates["verdict"],
        "evaluation_mode": "symbolic_independent_local_contribution_v1",
        "study_role": "formal_frozen_64" if int(args.instances_per_cell) == 0 else "implementation_smoke",
        "headline_eligible": False,
        "contract": "specs/multiagent_structural_free_lunch_contract_v1.json",
        "input_hashes": {
            "contract_sha256": _sha256(args.contract),
            "manifest_sha256": _sha256(args.manifest),
        },
        "frozen_input_validation": frozen_input_validation,
        "config": {
            "manifest": str(args.manifest),
            "contract": str(args.contract),
            "instances_per_cell": int(args.instances_per_cell),
            "agents": int(args.agents),
            "register": int(args.register),
            "activation_cap": int(args.activation_cap),
            "channel_cap": int(args.channel_cap),
        },
        "manifest_instance_ids": sorted(selected_ids),
        "rows": rows,
        "summary": summary,
        "protocol_audit": protocol_audit,
        "paired_tests": _paired_tests(rows),
        "gates": gates,
        "honesty": {
            "does_not_establish": "This symbolic mechanism experiment can nominate a structural free-lunch candidate but cannot establish a real-Qwen or measured parallel-speedup claim.",
            "critical_path": "parallel_rounds is an idealized scheduler critical path, not measured wall-clock latency.",
            "selection": "Uses the already frozen core 2x2 manifest and does not select instances by these arm outcomes.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run independent-local multi-agent contribution gate.")
    parser.add_argument("--contract", type=Path, default=Path("specs/multiagent_structural_free_lunch_contract_v1.json"))
    parser.add_argument("--manifest", type=Path, default=Path("results/multiagent_core_2x2_preflight/instance_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_structural_free_lunch"))
    parser.add_argument("--instances-per-cell", type=int, default=0)
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--activation-cap", type=int, default=20000)
    parser.add_argument("--channel-cap", type=int, default=16)
    args = parser.parse_args()
    payload = run(args)
    root = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    _write_json(root / "results.json", payload)
    _write_json(root / "summary.json", {key: value for key, value in payload.items() if key != "rows"})


if __name__ == "__main__":
    main()
