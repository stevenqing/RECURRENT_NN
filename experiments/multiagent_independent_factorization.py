"""Development-only independent-factorization mechanism gate.

This module deliberately leaves the frozen core 2x2 preflight unchanged. It
reuses that already-observed manifest to test whether per-agent local trails,
dependency-local rollback, and queued cross-agent recovery can reduce aggregate
search work under equal total recovery memory.

No result from this module is confirmatory or headline eligible.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any, Iterable

from experiments.multiagent_capacity_coupling import REPO_ROOT, _adjacency, _run_search


SCHEMA_VERSION = "multiagent_independent_factorization_dev_v1"
STATUS_GO = "MULTIAGENT_INDEPENDENT_FACTORIZATION_DEV_GO"
STATUS_PARTIAL = "MULTIAGENT_INDEPENDENT_FACTORIZATION_DEV_PARTIAL_GO"
STATUS_NO_GO = "MULTIAGENT_INDEPENDENT_FACTORIZATION_DEV_NO_GO"

BASELINE_ARMS = (
    "monolith_R",
    "monolith_MR",
    "global_trail_team_cbj",
    "centralized_sharded_MR",
)
FACTORIZED_ARMS = (
    "factorized_central_deepest",
    "independent_local_deepest",
    "independent_local_random_valid",
    "independent_local_no_cross",
)
ARMS = BASELINE_ARMS + FACTORIZED_ARMS
CELLS = ("under_low", "under_high", "over_low", "over_high")


@dataclass
class LocalEntry:
    vertex: int
    color: int
    local_order_index: int
    global_order_index: int
    commit_epoch: int


@dataclass
class LocalAgentState:
    agent_id: int
    order: list[int]
    trail: list[LocalEntry] = field(default_factory=list)
    next_choice: dict[int, int] = field(default_factory=dict)
    conflict_sets: dict[int, set[int]] = field(default_factory=dict)
    inbox: list[dict[str, Any]] = field(default_factory=list)
    waiting_request_id: int | None = None
    waiting_vertex: int | None = None


@dataclass
class SearchMetrics:
    decision_work: int = 0
    coordination_work: int = 0
    critical_path_rounds: int = 0
    recoveries: int = 0
    local_recoveries: int = 0
    cross_agent_recoveries: int = 0
    retractions: int = 0
    preserved_unrelated_assignments: int = 0
    recovery_request_messages: int = 0
    recovery_ack_messages: int = 0
    stale_recovery_requests: int = 0
    boundary_commit_messages: int = 0
    boundary_retract_messages: int = 0
    communication_tokens: int = 0
    max_local_recovery_distance: int = 0
    max_preserved_per_recovery: int = 0
    max_inbox_depth: int = 0
    out_of_window_blockers: int = 0
    capacity_access_violations: int = 0
    invariant_checks: int = 0
    invariant_failures: int = 0
    route_events: int = 0
    cross_agent_route_events: int = 0
    random_route_events: int = 0
    peak_total_recoverable_entries: int = 0
    peak_recoverable_entries_per_agent: int = 0
    peak_total_audit_entries: int = 0

    @property
    def aggregate_work(self) -> int:
        return self.decision_work + self.coordination_work


class TraceDigest:
    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self.count = 0

    def add(self, event: str, *values: Any) -> None:
        payload = json.dumps([event, *values], separators=(",", ":"), sort_keys=True)
        self._digest.update(payload.encode("utf-8") + b"\n")
        self.count += 1

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _valid_solution(n: int, k: int, edges: list[tuple[int, int]], assignment: dict[int, int]) -> bool:
    return (
        len(assignment) == int(n)
        and all(int(assignment.get(vertex, 0)) in range(1, int(k) + 1) for vertex in range(int(n)))
        and all(int(assignment[left]) != int(assignment[right]) for left, right in edges)
    )


def _stable_rng(seed: int, instance_id: str, arm: str) -> random.Random:
    payload = f"{int(seed)}::{instance_id}::{arm}".encode("utf-8")
    value = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return random.Random(value)


def _is_boundary_vertex(vertex: int, owner: list[int], adjacency: list[set[int]]) -> bool:
    return any(owner[neighbor] != owner[vertex] for neighbor in adjacency[vertex])


def _neighbor_agents(vertex: int, owner: list[int], adjacency: list[set[int]]) -> set[int]:
    return {owner[neighbor] for neighbor in adjacency[vertex] if owner[neighbor] != owner[vertex]}


def _find_entry(state: LocalAgentState, vertex: int) -> tuple[int, LocalEntry] | None:
    for index in range(len(state.trail) - 1, -1, -1):
        entry = state.trail[index]
        if entry.vertex == int(vertex):
            return index, entry
    return None


def _row_identity(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["cell"]), str(row["instance_id"])


def _run_factorized(
    row: dict[str, Any],
    arm: str,
    m_agents: int,
    r_value: int,
    work_cap: int,
    route_seed: int,
) -> dict[str, Any]:
    if arm not in FACTORIZED_ARMS:
        raise ValueError(f"unsupported factorized arm: {arm}")
    centralized = arm == "factorized_central_deepest"
    route_mode = {
        "factorized_central_deepest": "deepest",
        "independent_local_deepest": "deepest",
        "independent_local_random_valid": "random_valid",
        "independent_local_no_cross": "no_cross",
    }[arm]

    n = int(row["n_vertices"])
    k = int(row["k"])
    edges = [tuple(map(int, edge)) for edge in row["edges"]]
    owner = [int(value) for value in row["partitions"]]
    if len(set(owner)) != int(m_agents):
        raise ValueError(f"manifest has {len(set(owner))} agents, expected {m_agents}")
    global_order = [int(value) for value in row["order"]]
    global_position = {vertex: index for index, vertex in enumerate(global_order)}
    adjacency = _adjacency(n, edges)
    boundary_vertices = {
        vertex for vertex in range(n) if _is_boundary_vertex(vertex, owner, adjacency)
    }
    local_orders = {
        agent: [vertex for vertex in global_order if owner[vertex] == agent]
        for agent in range(int(m_agents))
    }
    states = {
        agent: LocalAgentState(
            agent_id=agent,
            order=list(local_orders[agent]),
            next_choice={vertex: 0 for vertex in local_orders[agent]},
            conflict_sets={vertex: set() for vertex in local_orders[agent]},
        )
        for agent in range(int(m_agents))
    }
    assignment: dict[int, int] = {}
    boundary_blackboard: dict[int, int] = {}
    metrics = SearchMetrics()
    trace = TraceDigest()
    rng = _stable_rng(route_seed, str(row["instance_id"]), arm)
    commit_epoch = 0
    request_counter = 0
    terminal_status: str | None = None
    failure_reason = ""
    invariant_failure_details: list[str] = []

    def visible_color(agent: int, neighbor: int) -> int | None:
        if owner[neighbor] == int(agent):
            return assignment.get(neighbor)
        return boundary_blackboard.get(neighbor)

    def update_memory_peaks() -> None:
        recoverable = [min(len(state.trail), int(r_value)) for state in states.values()]
        metrics.peak_total_recoverable_entries = max(
            metrics.peak_total_recoverable_entries, sum(recoverable)
        )
        metrics.peak_recoverable_entries_per_agent = max(
            metrics.peak_recoverable_entries_per_agent, max(recoverable, default=0)
        )
        metrics.peak_total_audit_entries = max(
            metrics.peak_total_audit_entries, sum(len(state.trail) for state in states.values())
        )
        metrics.max_inbox_depth = max(
            metrics.max_inbox_depth, max((len(state.inbox) for state in states.values()), default=0)
        )

    def check_invariants() -> list[str]:
        problems: list[str] = []
        trail_vertices: list[int] = []
        for agent, state in states.items():
            local_positions = [entry.local_order_index for entry in state.trail]
            if local_positions != sorted(local_positions) or len(local_positions) != len(set(local_positions)):
                problems.append(f"agent_{agent}_trail_not_strict_local_order")
            for entry in state.trail:
                trail_vertices.append(entry.vertex)
                if owner[entry.vertex] != agent:
                    problems.append(f"agent_{agent}_owns_wrong_vertex_{entry.vertex}")
                if assignment.get(entry.vertex) != entry.color:
                    problems.append(f"trail_assignment_mismatch_{entry.vertex}")
        if len(trail_vertices) != len(set(trail_vertices)):
            problems.append("duplicate_vertex_across_local_trails")
        if set(trail_vertices) != set(assignment):
            problems.append("assignment_not_union_of_local_trails")
        expected_blackboard = {
            vertex: color for vertex, color in assignment.items() if vertex in boundary_vertices
        }
        if boundary_blackboard != expected_blackboard:
            problems.append("boundary_blackboard_mismatch")
        for left, right in edges:
            if left in assignment and right in assignment and assignment[left] == assignment[right]:
                problems.append(f"constraint_violation_{left}_{right}")
                break
        for state in states.values():
            if state.waiting_request_id is None and state.waiting_vertex is not None:
                problems.append(f"agent_{state.agent_id}_waiting_vertex_without_request")
            if state.waiting_request_id is not None and state.waiting_vertex is None:
                problems.append(f"agent_{state.agent_id}_request_without_waiting_vertex")
        return problems

    def enforce_invariants() -> bool:
        nonlocal terminal_status, failure_reason
        metrics.invariant_checks += 1
        problems = check_invariants()
        if not problems:
            return True
        metrics.invariant_failures += len(problems)
        invariant_failure_details.extend(problems[:8])
        terminal_status = "INVARIANT_FAILURE"
        failure_reason = problems[0]
        return False

    def publish_assignment(agent: int, vertex: int, color: int) -> None:
        if vertex not in boundary_vertices:
            return
        boundary_blackboard[vertex] = int(color)
        recipients = _neighbor_agents(vertex, owner, adjacency)
        metrics.boundary_commit_messages += len(recipients)
        metrics.communication_tokens += 4 * len(recipients)
        trace.add("boundary_commit", agent, vertex, color, sorted(recipients))

    def retract_assignment(agent: int, vertex: int) -> None:
        if vertex not in boundary_vertices:
            return
        boundary_blackboard.pop(vertex, None)
        recipients = _neighbor_agents(vertex, owner, adjacency)
        metrics.boundary_retract_messages += len(recipients)
        metrics.communication_tokens += 4 * len(recipients)
        trace.add("boundary_retract", agent, vertex, sorted(recipients))

    def reset_source(source_agent: int, source_vertex: int) -> None:
        source = states[int(source_agent)]
        source.next_choice[int(source_vertex)] = 0
        source.conflict_sets[int(source_vertex)].clear()

    def local_rollback(
        target_agent: int,
        target_vertex: int,
        source_agent: int,
        source_vertex: int,
        blockers: list[int],
        *,
        via_message: bool,
    ) -> str:
        target = states[int(target_agent)]
        found = _find_entry(target, int(target_vertex))
        if found is None:
            metrics.stale_recovery_requests += 1
            reset_source(source_agent, source_vertex)
            trace.add(
                "stale_recovery",
                target_agent,
                target_vertex,
                source_agent,
                source_vertex,
                blockers,
            )
            return "stale"
        target_index, target_entry = found
        local_distance = len(target.trail) - target_index
        if local_distance > int(r_value):
            metrics.capacity_access_violations += 1
            trace.add("capacity_violation", target_agent, target_vertex, local_distance, r_value)
            return "outside_window"
        popped = target.trail[target_index:]
        popped_vertices = {entry.vertex for entry in popped}
        preserved = sum(
            1
            for other_agent, other_state in states.items()
            if other_agent != int(target_agent)
            for entry in other_state.trail
            if entry.commit_epoch > target_entry.commit_epoch and entry.vertex not in popped_vertices
        )
        metrics.recoveries += 1
        metrics.local_recoveries += int(int(target_agent) == int(source_agent))
        metrics.cross_agent_recoveries += int(int(target_agent) != int(source_agent))
        metrics.retractions += len(popped)
        metrics.preserved_unrelated_assignments += preserved
        metrics.max_preserved_per_recovery = max(metrics.max_preserved_per_recovery, preserved)
        metrics.max_local_recovery_distance = max(metrics.max_local_recovery_distance, local_distance)
        for entry in popped:
            assignment.pop(entry.vertex, None)
            retract_assignment(int(target_agent), entry.vertex)
        target.trail = target.trail[:target_index]
        for entry in popped[1:]:
            target.next_choice[entry.vertex] = 0
            target.conflict_sets[entry.vertex].clear()
        reset_source(source_agent, source_vertex)
        trace.add(
            "local_rollback",
            target_agent,
            target_vertex,
            source_agent,
            source_vertex,
            [entry.vertex for entry in popped],
            preserved,
            via_message,
        )
        update_memory_peaks()
        return "rolled_back"

    def valid_targets(blockers: Iterable[int]) -> list[dict[str, int]]:
        targets: list[dict[str, int]] = []
        for blocker in sorted(set(map(int, blockers))):
            agent = owner[blocker]
            found = _find_entry(states[agent], blocker)
            if found is None:
                continue
            index, entry = found
            distance = len(states[agent].trail) - index
            if distance > int(r_value):
                metrics.out_of_window_blockers += 1
                continue
            targets.append(
                {
                    "agent": int(agent),
                    "vertex": int(blocker),
                    "distance": int(distance),
                    "global_order_index": int(global_position[blocker]),
                    "commit_epoch": int(entry.commit_epoch),
                }
            )
        return targets

    def choose_target(source_agent: int, targets: list[dict[str, int]]) -> dict[str, int] | None:
        candidates = list(targets)
        if route_mode == "no_cross":
            candidates = [target for target in candidates if target["agent"] == int(source_agent)]
        if not candidates:
            return None
        if route_mode == "random_valid":
            metrics.random_route_events += 1
            return rng.choice(sorted(candidates, key=lambda target: (target["agent"], target["vertex"])))
        return max(
            candidates,
            key=lambda target: (
                target["global_order_index"],
                target["commit_epoch"],
                -target["agent"],
            ),
        )

    def queue_ack(request: dict[str, Any], outcome: str) -> None:
        source = states[int(request["source_agent"])]
        ack = {
            "type": "recovery_ack",
            "request_id": int(request["request_id"]),
            "source_agent": int(request["source_agent"]),
            "source_vertex": int(request["source_vertex"]),
            "target_agent": int(request["target_agent"]),
            "target_vertex": int(request["target_vertex"]),
            "outcome": str(outcome),
        }
        source.inbox.append(ack)
        metrics.recovery_ack_messages += 1
        metrics.communication_tokens += 4
        trace.add("queue_ack", ack)
        update_memory_peaks()

    def process_message(agent: int) -> bool:
        nonlocal terminal_status, failure_reason
        state = states[int(agent)]
        if not state.inbox:
            return False
        message = state.inbox.pop(0)
        metrics.coordination_work += 1
        trace.add("process_message", agent, message)
        if message["type"] == "rollback_request":
            outcome = local_rollback(
                int(message["target_agent"]),
                int(message["target_vertex"]),
                int(message["source_agent"]),
                int(message["source_vertex"]),
                [int(value) for value in message["blockers"]],
                via_message=True,
            )
            if outcome == "outside_window":
                terminal_status = "NO_RECOVERY_TARGET"
                failure_reason = "queued_target_outside_local_window"
                return True
            queue_ack(message, outcome)
        elif message["type"] == "recovery_ack":
            if state.waiting_request_id == int(message["request_id"]):
                state.waiting_request_id = None
                state.waiting_vertex = None
            reset_source(int(message["source_agent"]), int(message["source_vertex"]))
            trace.add("ack_applied", agent, message["request_id"], message["outcome"])
        else:
            terminal_status = "INVALID_MESSAGE"
            failure_reason = f"unknown_message_type:{message.get('type')}"
        update_memory_peaks()
        enforce_invariants()
        return True

    def next_unassigned(state: LocalAgentState) -> tuple[int, int] | None:
        for local_index, vertex in enumerate(state.order):
            if vertex not in assignment:
                return local_index, vertex
        return None

    def agent_decision(agent: int) -> bool:
        nonlocal commit_epoch, request_counter, terminal_status, failure_reason
        state = states[int(agent)]
        if state.waiting_request_id is not None:
            return False
        pending = next_unassigned(state)
        if pending is None:
            return False
        local_index, vertex = pending
        metrics.decision_work += 1
        chosen_color: int | None = None
        while state.next_choice[vertex] < k:
            color = state.next_choice[vertex] + 1
            state.next_choice[vertex] += 1
            blockers = {
                neighbor
                for neighbor in adjacency[vertex]
                if visible_color(agent, neighbor) == color
            }
            if blockers:
                state.conflict_sets[vertex].update(blockers)
                continue
            chosen_color = int(color)
            break
        if chosen_color is not None:
            commit_epoch += 1
            assignment[vertex] = chosen_color
            entry = LocalEntry(
                vertex=int(vertex),
                color=chosen_color,
                local_order_index=int(local_index),
                global_order_index=int(global_position[vertex]),
                commit_epoch=int(commit_epoch),
            )
            state.trail.append(entry)
            publish_assignment(agent, vertex, chosen_color)
            trace.add("assign", agent, vertex, chosen_color, local_index, commit_epoch)
            update_memory_peaks()
            enforce_invariants()
            return True

        blockers = {
            blocker
            for blocker in state.conflict_sets[vertex]
            if blocker in assignment
            and visible_color(agent, blocker) == assignment.get(blocker)
        }
        state.next_choice[vertex] = 0
        if not blockers:
            terminal_status = "EXHAUSTED"
            failure_reason = "dead_end_without_live_blocker"
            trace.add("exhausted", agent, vertex)
            return True
        targets = valid_targets(blockers)
        chosen = choose_target(agent, targets)
        cross_blockers = [blocker for blocker in blockers if owner[blocker] != int(agent)]
        if chosen is None:
            if route_mode == "no_cross" and cross_blockers:
                terminal_status = "NO_CROSS_RECOVERY"
                failure_reason = "cross_agent_recovery_disabled"
            else:
                terminal_status = "NO_RECOVERY_TARGET"
                failure_reason = "no_blocker_in_declared_local_windows"
            trace.add(
                "no_target",
                agent,
                vertex,
                sorted(blockers),
                route_mode,
                len(targets),
            )
            return True
        metrics.route_events += 1
        is_cross = int(chosen["agent"]) != int(agent)
        metrics.cross_agent_route_events += int(is_cross)
        trace.add("route", agent, vertex, chosen, sorted(blockers), route_mode)
        if not is_cross or centralized:
            outcome = local_rollback(
                int(chosen["agent"]),
                int(chosen["vertex"]),
                int(agent),
                int(vertex),
                sorted(blockers),
                via_message=False,
            )
            if outcome == "outside_window":
                terminal_status = "NO_RECOVERY_TARGET"
                failure_reason = "direct_target_outside_local_window"
            enforce_invariants()
            return True

        request_counter += 1
        request = {
            "type": "rollback_request",
            "request_id": int(request_counter),
            "source_agent": int(agent),
            "source_vertex": int(vertex),
            "target_agent": int(chosen["agent"]),
            "target_vertex": int(chosen["vertex"]),
            "blockers": sorted(map(int, blockers)),
        }
        states[int(chosen["agent"])].inbox.append(request)
        state.waiting_request_id = int(request_counter)
        state.waiting_vertex = int(vertex)
        metrics.recovery_request_messages += 1
        metrics.communication_tokens += 4 + 2 * len(blockers)
        trace.add("queue_request", request)
        update_memory_peaks()
        enforce_invariants()
        return True

    def finish(status: str) -> dict[str, Any]:
        problems = check_invariants()
        if problems:
            metrics.invariant_failures += len(problems)
            invariant_failure_details.extend(problems[:8])
            status = "INVARIANT_FAILURE"
        solved = status == "SOLVED" and _valid_solution(n, k, edges, assignment)
        if status == "SOLVED" and not solved:
            status = "OFFICIAL_SCORE_FAIL"
        return {
            "instance_id": str(row["instance_id"]),
            "cell": str(row["cell"]),
            "capacity": str(row["capacity"]),
            "coupling": str(row["coupling"]),
            "arm": arm,
            "solved": bool(solved),
            "solution_valid": bool(solved) if status == "SOLVED" else None,
            "status": "SOLVED" if solved else status,
            "failure_reason": "" if solved else failure_reason,
            "decision_work": metrics.decision_work,
            "coordination_work": metrics.coordination_work,
            "aggregate_work": metrics.aggregate_work,
            "penalized_work": metrics.aggregate_work if solved else int(work_cap),
            "critical_path_rounds": metrics.critical_path_rounds,
            "recoveries": metrics.recoveries,
            "local_recoveries": metrics.local_recoveries,
            "cross_agent_recoveries": metrics.cross_agent_recoveries,
            "retractions": metrics.retractions,
            "preserved_unrelated_assignments": metrics.preserved_unrelated_assignments,
            "recovery_request_messages": metrics.recovery_request_messages,
            "recovery_ack_messages": metrics.recovery_ack_messages,
            "stale_recovery_requests": metrics.stale_recovery_requests,
            "boundary_commit_messages": metrics.boundary_commit_messages,
            "boundary_retract_messages": metrics.boundary_retract_messages,
            "communication_tokens": metrics.communication_tokens,
            "max_local_recovery_distance": metrics.max_local_recovery_distance,
            "max_preserved_per_recovery": metrics.max_preserved_per_recovery,
            "max_inbox_depth": metrics.max_inbox_depth,
            "out_of_window_blockers": metrics.out_of_window_blockers,
            "capacity_access_violations": metrics.capacity_access_violations,
            "invariant_checks": metrics.invariant_checks,
            "invariant_failures": metrics.invariant_failures,
            "invariant_failure_details": invariant_failure_details[:8],
            "route_events": metrics.route_events,
            "cross_agent_route_events": metrics.cross_agent_route_events,
            "random_route_events": metrics.random_route_events,
            "cross_route_fraction_of_decision_work": (
                metrics.recovery_request_messages / metrics.decision_work
                if metrics.decision_work
                else 0.0
            ),
            "peak_total_recoverable_entries": metrics.peak_total_recoverable_entries,
            "peak_recoverable_entries_per_agent": metrics.peak_recoverable_entries_per_agent,
            "peak_total_audit_entries": metrics.peak_total_audit_entries,
            "declared_window_per_agent": int(r_value),
            "declared_total_window": int(m_agents) * int(r_value),
            "aggregate_work_cap": int(work_cap),
            "scheduler": "deterministic_round_robin",
            "route_mode": route_mode,
            "centralized_recovery": centralized,
            "oracle_fallback_used": False,
            "trace_sha256": trace.hexdigest(),
            "trace_event_count": trace.count,
            "evaluation_mode": "symbolic_independent_factorization_development_v1",
            "headline_eligible": False,
        }

    update_memory_peaks()
    enforce_invariants()
    while terminal_status is None:
        if len(assignment) == n:
            terminal_status = "SOLVED"
            break
        if metrics.aggregate_work >= int(work_cap):
            terminal_status = "WORK_CAP"
            failure_reason = "aggregate_work_cap_reached"
            break
        metrics.critical_path_rounds += 1
        actions_this_round = 0
        for agent in range(int(m_agents)):
            if terminal_status is not None:
                break
            if metrics.aggregate_work >= int(work_cap):
                terminal_status = "WORK_CAP"
                failure_reason = "aggregate_work_cap_reached"
                break
            if process_message(agent):
                actions_this_round += 1
                continue
            if agent_decision(agent):
                actions_this_round += 1
        if terminal_status is not None:
            break
        if len(assignment) == n:
            terminal_status = "SOLVED"
            break
        if actions_this_round == 0:
            terminal_status = "DEADLOCK"
            failure_reason = "no_agent_action_with_incomplete_assignment"
            break
    return finish(str(terminal_status))


def _run_baseline(
    row: dict[str, Any],
    arm: str,
    m_agents: int,
    r_value: int,
    work_cap: int,
) -> dict[str, Any]:
    source_arm = {
        "monolith_R": "monolith_R",
        "monolith_MR": "monolith_MR",
        "global_trail_team_cbj": "team_cbj",
        "centralized_sharded_MR": "centralized_sharded_MR",
    }[arm]
    result = _run_search(
        row,
        source_arm,
        int(m_agents),
        int(r_value),
        int(work_cap),
        enforce_window=True,
    )
    solved = bool(result["solved"])
    steps = int(result["steps"])
    return {
        **result,
        "arm": arm,
        "solution_valid": solved if result["status"] == "SOLVED" else None,
        "decision_work": steps,
        "coordination_work": 0,
        "aggregate_work": steps,
        "penalized_work": steps if solved else int(work_cap),
        "critical_path_rounds": steps,
        "local_recoveries": None,
        "cross_agent_recoveries": None,
        "preserved_unrelated_assignments": 0,
        "recovery_request_messages": 0,
        "recovery_ack_messages": 0,
        "stale_recovery_requests": 0,
        "boundary_retract_messages": 0,
        "max_preserved_per_recovery": 0,
        "max_inbox_depth": 0,
        "out_of_window_blockers": None,
        "capacity_access_violations": 0,
        "invariant_checks": 0,
        "invariant_failures": 0,
        "invariant_failure_details": [],
        "route_events": int(result["recoveries"]),
        "cross_agent_route_events": int(result["cross_block_messages"]),
        "random_route_events": 0,
        "cross_route_fraction_of_decision_work": (
            int(result["cross_block_messages"]) / steps if steps else 0.0
        ),
        "peak_total_recoverable_entries": min(
            int(result["total_register_entries_peak_proxy"]), int(m_agents) * int(r_value)
        ),
        "peak_recoverable_entries_per_agent": min(
            int(result["max_register_length_per_agent"]),
            int(m_agents) * int(r_value) if arm.startswith("monolith") else int(r_value),
        ),
        "peak_total_audit_entries": int(result["total_register_entries_peak_proxy"]),
        "aggregate_work_cap": int(work_cap),
        "scheduler": "single_global_cursor",
        "route_mode": "deepest_global_cbj",
        "centralized_recovery": True,
        "oracle_fallback_used": False,
        "trace_sha256": None,
        "trace_event_count": None,
        "evaluation_mode": "symbolic_independent_factorization_development_v1",
        "headline_eligible": False,
    }


def _summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for cell in CELLS:
        for arm in ARMS:
            subset = [row for row in rows if row["cell"] == cell and row["arm"] == arm]
            if not subset:
                continue
            decision_total = sum(int(row["decision_work"]) for row in subset)
            output.append(
                {
                    "cell": cell,
                    "capacity": subset[0]["capacity"],
                    "coupling": subset[0]["coupling"],
                    "arm": arm,
                    "n": len(subset),
                    "solve_rate": mean(float(row["solved"]) for row in subset),
                    "mean_aggregate_work": mean(float(row["aggregate_work"]) for row in subset),
                    "mean_penalized_work": mean(float(row["penalized_work"]) for row in subset),
                    "mean_decision_work": mean(float(row["decision_work"]) for row in subset),
                    "mean_coordination_work": mean(float(row["coordination_work"]) for row in subset),
                    "mean_critical_path_rounds": mean(float(row["critical_path_rounds"]) for row in subset),
                    "mean_retractions": mean(float(row["retractions"]) for row in subset),
                    "mean_recoveries": mean(float(row["recoveries"]) for row in subset),
                    "mean_preserved_unrelated_assignments": mean(
                        float(row["preserved_unrelated_assignments"]) for row in subset
                    ),
                    "mean_recovery_request_messages": mean(
                        float(row["recovery_request_messages"]) for row in subset
                    ),
                    "mean_communication_tokens": mean(
                        float(row["communication_tokens"]) for row in subset
                    ),
                    "cross_route_fraction_of_decision_work": (
                        sum(int(row["recovery_request_messages"]) for row in subset) / decision_total
                        if decision_total
                        else 0.0
                    ),
                    "status_counts": dict(Counter(str(row["status"]) for row in subset)),
                }
            )
    return output


def _summary_lookup(summary: list[dict[str, Any]], cell: str, arm: str) -> dict[str, Any]:
    return next(row for row in summary if row["cell"] == cell and row["arm"] == arm)


def _contrast(
    rows: list[dict[str, Any]],
    left_arm: str,
    right_arm: str,
    cells: Iterable[str],
) -> dict[str, Any]:
    selected_cells = set(cells)
    left = {
        _row_identity(row): row
        for row in rows
        if row["arm"] == left_arm and row["cell"] in selected_cells
    }
    right = {
        _row_identity(row): row
        for row in rows
        if row["arm"] == right_arm and row["cell"] in selected_cells
    }
    keys = sorted(set(left) & set(right))
    jointly_solved = [key for key in keys if left[key]["solved"] and right[key]["solved"]]
    left_penalized = mean(float(left[key]["penalized_work"]) for key in keys) if keys else None
    right_penalized = mean(float(right[key]["penalized_work"]) for key in keys) if keys else None
    left_joint = mean(float(left[key]["aggregate_work"]) for key in jointly_solved) if jointly_solved else None
    right_joint = mean(float(right[key]["aggregate_work"]) for key in jointly_solved) if jointly_solved else None
    return {
        "cells": sorted(selected_cells),
        "left_arm": left_arm,
        "right_arm": right_arm,
        "n_pairs": len(keys),
        "left_solve_rate": mean(float(left[key]["solved"]) for key in keys) if keys else None,
        "right_solve_rate": mean(float(right[key]["solved"]) for key in keys) if keys else None,
        "solve_rate_difference": (
            mean(float(left[key]["solved"]) - float(right[key]["solved"]) for key in keys)
            if keys
            else None
        ),
        "left_only_solves": sum(bool(left[key]["solved"]) and not bool(right[key]["solved"]) for key in keys),
        "right_only_solves": sum(bool(right[key]["solved"]) and not bool(left[key]["solved"]) for key in keys),
        "mean_left_penalized_work": left_penalized,
        "mean_right_penalized_work": right_penalized,
        "penalized_work_ratio_left_over_right": (
            left_penalized / right_penalized if left_penalized is not None and right_penalized else None
        ),
        "jointly_solved_pairs": len(jointly_solved),
        "mean_left_work_jointly_solved": left_joint,
        "mean_right_work_jointly_solved": right_joint,
        "joint_work_ratio_left_over_right": (
            left_joint / right_joint if left_joint is not None and right_joint else None
        ),
        "confirmatory": False,
    }


def _reproducibility_check(
    manifest: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    m_agents: int,
    r_value: int,
    work_cap: int,
    route_seed: int,
) -> dict[str, Any]:
    expected = {
        (_row_identity(row), str(row["arm"])): row
        for row in rows
        if row["arm"] in FACTORIZED_ARMS
    }
    compared_fields = (
        "solved",
        "status",
        "failure_reason",
        "decision_work",
        "coordination_work",
        "aggregate_work",
        "critical_path_rounds",
        "retractions",
        "preserved_unrelated_assignments",
        "communication_tokens",
        "trace_sha256",
        "trace_event_count",
    )
    mismatches: list[dict[str, Any]] = []
    for manifest_row in manifest:
        for arm in FACTORIZED_ARMS:
            rerun = _run_factorized(
                manifest_row,
                arm,
                int(m_agents),
                int(r_value),
                int(work_cap),
                int(route_seed),
            )
            original = expected[(_row_identity(manifest_row), arm)]
            different = [field for field in compared_fields if original.get(field) != rerun.get(field)]
            if different:
                mismatches.append(
                    {
                        "cell": manifest_row["cell"],
                        "instance_id": manifest_row["instance_id"],
                        "arm": arm,
                        "fields": different,
                    }
                )
    return {
        "deterministic": not mismatches,
        "rerun_count": len(manifest) * len(FACTORIZED_ARMS),
        "compared_fields": list(compared_fields),
        "mismatches": mismatches[:20],
    }


def _gates(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    contrasts: list[dict[str, Any]],
    reproducibility: dict[str, Any],
) -> dict[str, Any]:
    def contrast(left: str, right: str, cells: Iterable[str]) -> dict[str, Any]:
        target_cells = sorted(set(cells))
        return next(
            item
            for item in contrasts
            if item["left_arm"] == left
            and item["right_arm"] == right
            and item["cells"] == target_cells
        )

    factor_over_low = contrast("independent_local_deepest", "monolith_MR", ("over_low",))
    async_all = contrast(
        "independent_local_deepest", "factorized_central_deepest", CELLS
    )
    global_all = contrast(
        "independent_local_deepest", "global_trail_team_cbj", CELLS
    )
    route_by_cell = {
        cell: contrast(
            "independent_local_deepest", "independent_local_random_valid", (cell,)
        )
        for cell in ("over_low", "over_high")
    }
    no_cross_by_cell = {
        cell: contrast(
            "independent_local_deepest", "independent_local_no_cross", (cell,)
        )
        for cell in ("over_low", "over_high")
    }

    factorized_rows = [row for row in rows if row["arm"] in FACTORIZED_ARMS]
    solved_invalid = [
        row for row in factorized_rows if row["solved"] and row.get("solution_valid") is not True
    ]
    invariant_failures = sum(int(row["invariant_failures"]) for row in factorized_rows)
    capacity_violations = sum(int(row["capacity_access_violations"]) for row in factorized_rows)
    oracle_fallbacks = sum(bool(row["oracle_fallback_used"]) for row in rows)
    baseline_equivalent = all(
        left["solved"] == right["solved"] and left["status"] == right["status"]
        for key in sorted({_row_identity(row) for row in rows})
        for left in [
            next(
                row
                for row in rows
                if _row_identity(row) == key and row["arm"] == "global_trail_team_cbj"
            )
        ]
        for right in [
            next(
                row
                for row in rows
                if _row_identity(row) == key and row["arm"] == "centralized_sharded_MR"
            )
        ]
    )
    d0 = (
        not solved_invalid
        and invariant_failures == 0
        and capacity_violations == 0
        and oracle_fallbacks == 0
        and bool(reproducibility["deterministic"])
        and baseline_equivalent
    )

    independent_rows = [row for row in rows if row["arm"] == "independent_local_deepest"]
    recovery_episodes = [row for row in independent_rows if int(row["recoveries"]) > 0]
    preserved_fraction = (
        mean(float(int(row["preserved_unrelated_assignments"]) > 0) for row in recovery_episodes)
        if recovery_episodes
        else 0.0
    )
    non_equivalent = (
        abs(float(global_all["solve_rate_difference"] or 0.0)) > 0.0
        or any(
            row["aggregate_work"]
            != next(
                other["aggregate_work"]
                for other in rows
                if _row_identity(other) == _row_identity(row)
                and other["arm"] == "global_trail_team_cbj"
            )
            for row in independent_rows
        )
    )
    d1 = preserved_fraction >= 0.25 and non_equivalent

    d2_over_low = float(factor_over_low["solve_rate_difference"] or 0.0) >= -0.10
    d2_async = float(async_all["solve_rate_difference"] or 0.0) >= -0.10
    d2 = d2_over_low and d2_async

    factor_ratio = factor_over_low["penalized_work_ratio_left_over_right"]
    d3 = factor_ratio is not None and float(factor_ratio) <= 0.85

    async_ratio = async_all["joint_work_ratio_left_over_right"]
    compensating_solve_gain = float(async_all["solve_rate_difference"] or 0.0) >= 0.05
    d4 = (async_ratio is not None and float(async_ratio) <= 1.10) or compensating_solve_gain

    route_observations: dict[str, dict[str, Any]] = {}
    route_identifiable = False
    for cell, item in route_by_cell.items():
        solve_difference = abs(float(item["solve_rate_difference"] or 0.0))
        work_ratio = item["joint_work_ratio_left_over_right"]
        work_difference = abs(float(work_ratio) - 1.0) if work_ratio is not None else 0.0
        cell_identifiable = solve_difference >= 0.10 or work_difference >= 0.15
        route_identifiable = route_identifiable or cell_identifiable
        route_observations[cell] = {
            "absolute_solve_difference": solve_difference,
            "joint_work_ratio_deepest_over_random": work_ratio,
            "absolute_relative_work_difference": work_difference,
            "identifiable": cell_identifiable,
        }
    d5 = route_identifiable

    no_cross_failures = {
        cell: sum(
            row["status"] == "NO_CROSS_RECOVERY"
            for row in rows
            if row["arm"] == "independent_local_no_cross" and row["cell"] == cell
        )
        for cell in ("over_low", "over_high")
    }
    no_cross_ns = {
        cell: sum(
            row["arm"] == "independent_local_no_cross" and row["cell"] == cell
            for row in rows
        )
        for cell in ("over_low", "over_high")
    }
    paired_cross_necessity = any(
        float(item["solve_rate_difference"] or 0.0) >= 0.20
        for item in no_cross_by_cell.values()
    )
    separated_failure = any(
        no_cross_ns[cell] > 0 and no_cross_failures[cell] / no_cross_ns[cell] >= 0.25
        for cell in no_cross_failures
    )
    d6 = paired_cross_necessity or separated_failure

    sparsity = {
        cell: float(
            _summary_lookup(summary, cell, "independent_local_deepest")[
                "cross_route_fraction_of_decision_work"
            ]
        )
        for cell in ("over_low", "over_high")
    }
    d7 = all(value <= 0.20 for value in sparsity.values())

    named = {
        "D0_correctness_reproducibility": d0,
        "D1_mechanism_engagement": d1,
        "D2_equal_resource_solve_retention": d2,
        "D3_aggregate_work_factorization": d3,
        "D4_bounded_decentralization_tax": d4,
        "D5_route_identifiability": d5,
        "D6_coordination_necessity": d6,
        "D7_event_sparsity": d7,
    }
    factorization_go = all(named[key] for key in (
        "D0_correctness_reproducibility",
        "D1_mechanism_engagement",
        "D2_equal_resource_solve_retention",
        "D3_aggregate_work_factorization",
        "D4_bounded_decentralization_tax",
    ))
    sparse_routing_go = all(named[key] for key in (
        "D0_correctness_reproducibility",
        "D2_equal_resource_solve_retention",
        "D5_route_identifiability",
        "D6_coordination_necessity",
        "D7_event_sparsity",
    ))
    return {
        **named,
        "factorization_go": factorization_go,
        "sparse_routing_go": sparse_routing_go,
        "full_research_go": factorization_go and sparse_routing_go,
        "observed": {
            "solved_invalid_rows": len(solved_invalid),
            "invariant_failures": invariant_failures,
            "capacity_access_violations": capacity_violations,
            "oracle_fallbacks": oracle_fallbacks,
            "global_team_centralized_sharded_rowwise_equivalent": baseline_equivalent,
            "recovery_episodes": len(recovery_episodes),
            "fraction_recovery_episodes_preserving_unrelated_assignments": preserved_fraction,
            "independent_non_equivalent_to_global_trail": non_equivalent,
            "over_low_independent_minus_monolith_MR_solve": factor_over_low[
                "solve_rate_difference"
            ],
            "overall_independent_minus_factorized_central_solve": async_all[
                "solve_rate_difference"
            ],
            "over_low_penalized_work_ratio_independent_over_monolith_MR": factor_ratio,
            "overall_joint_work_ratio_independent_over_factorized_central": async_ratio,
            "route_identifiability": route_observations,
            "no_cross_failure_counts": no_cross_failures,
            "event_sparsity_by_over_cell": sparsity,
        },
    }


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    gates = payload["gates"]
    lines = [
        "# Independent Factorization Mechanism — Development Result",
        "",
        f"- Status: **`{payload['status']}`**",
        "- Evidence tier: symbolic development on an already-observed pool",
        "- Headline eligible: **No**",
        "- GPU/LLM use: none",
        "- Preregistration: [Development Contract](../../specs/multiagent_independent_factorization_development_v1.md)",
        "- Contribution boundary: [Research Contribution Contract](../../specs/multiagent_contribution_contract_v1.md)",
        "",
        "## Executive decision",
        "",
        f"- Factorization gate: **{_fmt(gates['factorization_go'])}**",
        f"- Sparse-routing identifiability gate: **{_fmt(gates['sparse_routing_go'])}**",
        f"- Full research gate: **{_fmt(gates['full_research_go'])}**",
        "",
        "A full GO would authorize only a fresh confirmatory manifest; it would not itself establish a paper claim.",
        "",
        "## Solve and resource table",
        "",
        "| Cell | Arm | Solve | Penalized work | Aggregate work | Critical rounds | Retractions | Recovery requests | Preserved unrelated |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in CELLS:
        for arm in ARMS:
            row = _summary_lookup(summary, cell, arm)
            lines.append(
                "| "
                + " | ".join(
                    [
                        cell,
                        arm,
                        _fmt(row["solve_rate"]),
                        _fmt(row["mean_penalized_work"], 1),
                        _fmt(row["mean_aggregate_work"], 1),
                        _fmt(row["mean_critical_path_rounds"], 1),
                        _fmt(row["mean_retractions"], 1),
                        _fmt(row["mean_recovery_request_messages"], 1),
                        _fmt(row["mean_preserved_unrelated_assignments"], 1),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Frozen development gates",
            "",
            "| Gate | Result |",
            "|---|---|",
        ]
    )
    for key in (
        "D0_correctness_reproducibility",
        "D1_mechanism_engagement",
        "D2_equal_resource_solve_retention",
        "D3_aggregate_work_factorization",
        "D4_bounded_decentralization_tax",
        "D5_route_identifiability",
        "D6_coordination_necessity",
        "D7_event_sparsity",
    ):
        lines.append(f"| `{key}` | **{_fmt(gates[key])}** |")
    observed = gates["observed"]
    lines.extend(
        [
            "",
            "## Mechanism diagnostics",
            "",
            f"- Recovery episodes preserving unrelated assignments: `{_fmt(observed['fraction_recovery_episodes_preserving_unrelated_assignments'])}`.",
            f"- Over/low solve difference, independent minus monolith-MR: `{_fmt(observed['over_low_independent_minus_monolith_MR_solve'])}`.",
            f"- Over/low cap-penalized work ratio, independent / monolith-MR: `{_fmt(observed['over_low_penalized_work_ratio_independent_over_monolith_MR'])}`.",
            f"- Overall jointly-solved work ratio, independent / centralized factorized: `{_fmt(observed['overall_joint_work_ratio_independent_over_factorized_central'])}`.",
            f"- Event sparsity in over/low and over/high: `{json.dumps(observed['event_sparsity_by_over_cell'], sort_keys=True)}`.",
            f"- Invariant failures: `{observed['invariant_failures']}`; capacity access violations: `{observed['capacity_access_violations']}`; oracle fallbacks: `{observed['oracle_fallbacks']}`.",
            "",
            "## Research interpretation",
            "",
        ]
    )
    if gates["full_research_go"]:
        lines.extend(
            [
                "The mechanism passes all frozen development criteria: equal-total-window local factorization retains solve, reduces cap-penalized aggregate work, preserves dependency-unrelated assignments, and exposes a sparse route-sensitive coordination channel.",
                "",
                "This is a **development mechanism result**, not a confirmatory multi-agent advantage. The next permissible step is to freeze the implementation and generate a new 50-instance-per-cell confirmatory manifest with deterministic, random-valid, no-cross, and oracle route controls before spending any LLM budget.",
            ]
        )
    else:
        failed = [key for key, value in gates.items() if key.startswith("D") and value is False]
        lines.extend(
            [
                f"The full mechanism does not clear development. Failed gates: `{', '.join(failed)}`.",
                "",
                "No strong free-lunch or LLM-routing contribution is authorized. Interpretation must be reduced to the subset of gates that passed, and the failed mechanism must be repaired or abandoned before a fresh confirmatory manifest is generated.",
            ]
        )
    lines.extend(
        [
            "",
            "## Explicit non-claims",
            "",
            "- This run does not establish that multi-agent systems beat equal-resource monoliths.",
            "- This run does not test or establish a Qwen routing advantage.",
            "- Simulated critical-path rounds are not wall-clock parallel speedup.",
            "- The components are not claimed novel without a separate literature audit.",
            "- The observed-pool development statistics are not confirmatory p-values.",
            "",
            "## Artifacts",
            "",
            "- [Full results](results.json)",
            "- [Compact summary](summary.json)",
            "- [Development contract](../../specs/multiagent_independent_factorization_development_v1.md)",
            "- [Implementation](../../experiments/multiagent_independent_factorization.py)",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = list(manifest_payload.get("rows", []))
    selected: list[dict[str, Any]] = []
    for cell in CELLS:
        cell_rows = sorted(
            (row for row in manifest if row["cell"] == cell),
            key=lambda row: str(row["instance_id"]),
        )
        if args.instances_per_cell is not None:
            cell_rows = cell_rows[: int(args.instances_per_cell)]
        selected.extend(cell_rows)
    if not selected:
        raise ValueError("empty source manifest")

    rows: list[dict[str, Any]] = []
    for manifest_row in selected:
        for arm in BASELINE_ARMS:
            rows.append(
                _run_baseline(
                    manifest_row,
                    arm,
                    int(args.agents),
                    int(args.register),
                    int(args.work_cap),
                )
            )
        for arm in FACTORIZED_ARMS:
            rows.append(
                _run_factorized(
                    manifest_row,
                    arm,
                    int(args.agents),
                    int(args.register),
                    int(args.work_cap),
                    int(args.route_seed),
                )
            )

    summary = _summaries(rows)
    contrast_specs = [
        ("independent_local_deepest", "monolith_MR", ("over_low",)),
        ("independent_local_deepest", "factorized_central_deepest", CELLS),
        ("independent_local_deepest", "global_trail_team_cbj", CELLS),
        ("independent_local_deepest", "independent_local_random_valid", ("over_low",)),
        ("independent_local_deepest", "independent_local_random_valid", ("over_high",)),
        ("independent_local_deepest", "independent_local_no_cross", ("over_low",)),
        ("independent_local_deepest", "independent_local_no_cross", ("over_high",)),
    ]
    contrasts = [_contrast(rows, left, right, cells) for left, right, cells in contrast_specs]
    reproducibility = _reproducibility_check(
        selected,
        rows,
        int(args.agents),
        int(args.register),
        int(args.work_cap),
        int(args.route_seed),
    )
    gates = _gates(rows, summary, contrasts, reproducibility)
    if gates["full_research_go"]:
        status = STATUS_GO
    elif gates["factorization_go"] or gates["sparse_routing_go"]:
        status = STATUS_PARTIAL
    else:
        status = STATUS_NO_GO
    return {
        "schema": SCHEMA_VERSION,
        "status": status,
        "evaluation_mode": "symbolic_independent_factorization_development_v1",
        "headline_eligible": False,
        "preregistration": "specs/multiagent_independent_factorization_development_v1.json",
        "config": {
            "manifest": str(args.manifest),
            "output_dir": str(args.output_dir),
            "instances_per_cell": args.instances_per_cell,
            "agents": int(args.agents),
            "register": int(args.register),
            "declared_total_window": int(args.agents) * int(args.register),
            "work_cap": int(args.work_cap),
            "route_seed": int(args.route_seed),
        },
        "manifest_counts": dict(Counter(str(row["cell"]) for row in selected)),
        "arms": list(ARMS),
        "rows": rows,
        "summary": summary,
        "contrasts": contrasts,
        "reproducibility": reproducibility,
        "gates": gates,
        "honesty": {
            "development_only": True,
            "already_observed_pool": True,
            "no_llm": True,
            "no_oracle_fallback": all(not row["oracle_fallback_used"] for row in rows),
            "does_not_establish": "This observed-pool symbolic development run establishes no paper-grade equal-resource or frozen-Qwen claim. It only decides whether the mechanism is ready for a fresh confirmatory manifest.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the development-only independent-factorization mechanism gate."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("results/multiagent_core_2x2_preflight/instance_manifest.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/multiagent_independent_factorization_dev"),
    )
    parser.add_argument("--instances-per-cell", type=int, default=None)
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--work-cap", type=int, default=5000)
    parser.add_argument("--route-seed", type=int, default=17011)
    args = parser.parse_args()

    payload = run(args)
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    _write_json(output_dir / "results.json", payload)
    compact = {key: value for key, value in payload.items() if key != "rows"}
    _write_json(output_dir / "summary.json", compact)
    (output_dir / "SUMMARY.md").write_text(_render_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "path": str(output_dir.relative_to(REPO_ROOT)),
                "status": payload["status"],
                "factorization_go": payload["gates"]["factorization_go"],
                "sparse_routing_go": payload["gates"]["sparse_routing_go"],
                "full_research_go": payload["gates"]["full_research_go"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
