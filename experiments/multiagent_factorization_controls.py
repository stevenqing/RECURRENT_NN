"""Matched factorization controls for structural confirmation.

The successful proposed arm remains the hash-locked implementation in
``experiments.multiagent_independent_local``. This module supplies a shadow mode
that must reproduce it exactly plus same-order centralized, random-valid, and
no-cross controls. The shadow adds audit-only preservation metrics and a trace
digest; these additions must not change the search trajectory.
"""

from __future__ import annotations

from collections import deque
import hashlib
import json
import random
from typing import Any

from experiments.multiagent_capacity_coupling import _adjacency
from experiments.multiagent_independent_local import (
    AgentState,
    RollbackRequest,
    _make_agents,
    _rollback_local,
    _valid_solution,
)


CONTROL_MODES = (
    "queued_deepest",
    "central_deepest",
    "queued_random_valid",
    "queued_no_cross",
)
ARM_NAMES = {
    "queued_deepest": "independent_local_cbj_shadow",
    "central_deepest": "factorized_central_cbj",
    "queued_random_valid": "independent_local_random_valid",
    "queued_no_cross": "independent_local_no_cross",
}
EQUIVALENCE_FIELDS = (
    "solved",
    "status",
    "failure_reason",
    "activations",
    "parallel_rounds",
    "branch_attempts",
    "recoveries",
    "retractions",
    "requests_sent",
    "requests_executed",
    "acknowledgements",
    "nacks",
    "communication_tokens",
    "boundary_commit_messages",
    "aggregate_work",
    "max_pending_requests",
    "max_local_register",
    "max_local_trail_length",
    "declared_per_agent_window",
    "declared_total_window",
    "cross_agent_direct_mutations",
    "ownership_violations",
    "priority_direction_violations",
    "dependency_invalidations",
    "window_rejections",
    "out_of_window_rollback_executions",
    "protocol_shutdown_acks",
    "request_lifecycle_valid",
    "no_global_trail",
    "independent_agent_state",
    "no_oracle_or_model_fallback",
    "protocol_samples",
)


class TraceDigest:
    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self.events = 0

    def add(self, event: str, *values: Any) -> None:
        payload = json.dumps([event, *values], sort_keys=True, separators=(",", ":"))
        self._digest.update(payload.encode("utf-8") + b"\n")
        self.events += 1

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


def _stable_rng(instance_id: str, mode: str, route_seed: int) -> random.Random:
    payload = f"{int(route_seed)}::{instance_id}::{mode}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return random.Random(seed)


def _target_index(state: AgentState, target_vertex: int) -> int:
    return max(
        (index for index, item in enumerate(state.trail) if int(item["vertex"]) == int(target_vertex)),
        default=-1,
    )


def compare_shadow_to_frozen(
    frozen: dict[str, Any],
    shadow: dict[str, Any],
) -> list[str]:
    """Return fields that differ between the frozen and shadow trajectories."""
    return [field for field in EQUIVALENCE_FIELDS if frozen.get(field) != shadow.get(field)]


def run_factorized_control(
    row: dict[str, Any],
    mode: str,
    r_value: int,
    activation_cap: int,
    channel_cap: int,
    route_seed: int,
) -> dict[str, Any]:
    if mode not in CONTROL_MODES:
        raise ValueError(f"unknown factorization control mode: {mode}")
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
    requests: dict[int, RollbackRequest] = {}
    request_sources: dict[int, int] = {}
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
    preserved_global_suffix_assignments = 0
    preserved_dependency_unrelated_assignments = 0
    rollback_events_with_global_preservation = 0
    rollback_events_with_unrelated_preservation = 0
    cross_agent_rollback_events = 0
    local_rollback_events = 0
    no_cross_failures = 0
    failure_reason = ""
    protocol_samples: list[dict[str, Any]] = []
    trace = TraceDigest()
    generator = _stable_rng(str(row["instance_id"]), mode, int(route_seed))

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
                trace.add("terminal_nack_ack", status, request.request_id)
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
            "arm": ARM_NAMES[mode],
            "control_mode": mode,
            "delivery_mode": "immediate_target_callback" if mode == "central_deepest" else "queued_target_activation",
            "route_mode": (
                "random_valid" if mode == "queued_random_valid"
                else "no_cross" if mode == "queued_no_cross"
                else "deepest_cbj"
            ),
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
            "penalized_work": aggregate_work if solved else max(aggregate_work, int(activation_cap)),
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
            "preserved_global_suffix_assignments": preserved_global_suffix_assignments,
            "preserved_dependency_unrelated_assignments": preserved_dependency_unrelated_assignments,
            "rollback_events_with_global_preservation": rollback_events_with_global_preservation,
            "rollback_events_with_unrelated_preservation": rollback_events_with_unrelated_preservation,
            "cross_agent_rollback_events": cross_agent_rollback_events,
            "local_rollback_events": local_rollback_events,
            "no_cross_failures": no_cross_failures,
            "trace_sha256": trace.hexdigest(),
            "trace_event_count": trace.events,
            "protocol_samples": protocol_samples,
            "evaluation_mode": "symbolic_factorization_confirmatory_control_v1",
            "headline_eligible": False,
        }

    def execute_local_rollback(
        state: AgentState,
        target_vertex: int,
        expected_timestamp: int,
        source_agent: int,
    ) -> tuple[bool, str | None, int]:
        nonlocal cross_agent_rollback_events, local_rollback_events
        nonlocal max_local_register, max_local_trail_length
        nonlocal out_of_window_rollback_executions, ownership_violations
        nonlocal preserved_dependency_unrelated_assignments, preserved_global_suffix_assignments
        nonlocal recoveries, retractions, rollback_events_with_global_preservation
        nonlocal rollback_events_with_unrelated_preservation, window_rejections
        current_meta = assignment_meta.get(target_vertex)
        if current_meta is None or int(current_meta["timestamp"]) != int(expected_timestamp):
            return True, "stale_assignment_already_retracted", 0
        target_index = _target_index(state, target_vertex)
        outside_window = target_index >= 0 and target_index < max(0, len(state.trail) - int(r_value))
        metadata_before = {vertex: dict(meta) for vertex, meta in assignment_meta.items()}
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
            trace.add("rollback_rejected", state.agent_id, target_vertex, expected_timestamp, error)
            return False, error, 0
        popped_vertices = {int(item["vertex"]) for item in (popped or [])}
        hypothetical_suffix = {
            vertex
            for vertex, meta in metadata_before.items()
            if int(meta["timestamp"]) >= int(expected_timestamp)
        }
        preserved = hypothetical_suffix - popped_vertices
        unrelated = {
            vertex
            for vertex in preserved
            if int(partitions[vertex]) != int(state.agent_id)
            and all(vertex not in adjacency[popped_vertex] for popped_vertex in popped_vertices)
        }
        preserved_global_suffix_assignments += len(preserved)
        preserved_dependency_unrelated_assignments += len(unrelated)
        rollback_events_with_global_preservation += int(bool(preserved))
        rollback_events_with_unrelated_preservation += int(bool(unrelated))
        out_of_window_rollback_executions += int(outside_window)
        recoveries += 1
        retractions += len(popped or [])
        cross_agent_rollback_events += int(int(source_agent) != int(state.agent_id))
        local_rollback_events += int(int(source_agent) == int(state.agent_id))
        max_local_trail_length = max(max_local_trail_length, len(state.trail))
        max_local_register = max(max_local_register, min(len(state.trail), int(r_value)))
        trace.add(
            "rollback",
            source_agent,
            state.agent_id,
            target_vertex,
            expected_timestamp,
            [int(item["vertex"]) for item in (popped or [])],
            sorted(preserved),
            sorted(unrelated),
        )
        return True, None, len(popped or [])

    def process_request(target_state: AgentState, request: RollbackRequest) -> None:
        nonlocal acknowledgements, communication_tokens, nacks
        nonlocal ownership_violations, priority_direction_violations, requests_executed
        if (
            int(request.target_agent) != int(target_state.agent_id)
            or int(partitions[request.target_vertex]) != int(target_state.agent_id)
        ):
            ownership_violations += 1
            success, error, popped_count = False, "request_target_ownership_violation", 0
        elif position[request.target_vertex] >= position[request.deadend_vertex]:
            priority_direction_violations += 1
            success, error, popped_count = False, "non_decreasing_priority_request", 0
        else:
            success, error, popped_count = execute_local_rollback(
                target_state,
                request.target_vertex,
                request.target_timestamp,
                request.source_agent,
            )
        source_state = agents[request.source_agent]
        if success:
            if popped_count and request.mode == "cbj":
                target_state.conflict_sets[request.target_vertex].update(
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
            trace.add("request_ack", request.request_id, popped_count, error)
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
            trace.add("request_nack", request.request_id, error)
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

    def target_is_window_valid(target_vertex: int) -> bool:
        state = agents[int(partitions[target_vertex])]
        index = _target_index(state, target_vertex)
        return index >= max(0, len(state.trail) - int(r_value)) and index >= 0

    def choose_target(
        candidates: set[int],
        source_agent: int,
        rejected: set[int],
    ) -> int:
        available = set(candidates) - set(rejected)
        if mode == "queued_no_cross":
            available = {vertex for vertex in available if int(partitions[vertex]) == int(source_agent)}
        if mode == "queued_random_valid":
            available = {vertex for vertex in available if target_is_window_valid(vertex)}
        if not available:
            return -1
        ordered = sorted(available, key=lambda vertex: (position[vertex], vertex))
        if mode == "queued_random_valid":
            return int(ordered[generator.randrange(len(ordered))])
        return int(ordered[-1])

    def dispatch_request(
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
        if mode != "central_deepest" and pending_count >= int(channel_cap):
            return False
        request = RollbackRequest(
            request_id=next_request_id,
            source_agent=source_state.agent_id,
            target_agent=int(target_agent),
            target_vertex=int(target_vertex),
            target_timestamp=int(target_timestamp),
            deadend_vertex=int(source_vertex),
            blockers=tuple(sorted(blockers)),
            mode="cbj",
            reason=reason,
        )
        requests[next_request_id] = request
        request_sources[next_request_id] = source_state.agent_id
        next_request_id += 1
        source_state.waiting_request_id = request.request_id
        source_state.waiting_vertex = source_vertex
        requests_sent += 1
        communication_tokens += 2 + 2 * len(blockers)
        trace.add(
            "request",
            reason,
            request.request_id,
            source_state.agent_id,
            target_agent,
            target_vertex,
            target_timestamp,
            sorted(blockers),
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
        if mode == "central_deepest":
            max_pending_requests = max(max_pending_requests, 1)
            process_request(agents[int(target_agent)], request)
        else:
            agents[int(target_agent)].pending.append(request)
            max_pending_requests = max(
                max_pending_requests,
                sum(len(item.pending) for item in agents.values()),
            )
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
                process_request(state, request)
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
                invalidated_vertex, earlier_blockers, invalidated_timestamp = invalidated
                success, error, popped_count = execute_local_rollback(
                    state,
                    invalidated_vertex,
                    invalidated_timestamp,
                    agent_id,
                )
                if not success:
                    rejected = state.rejected_targets[invalidated_vertex]
                    target_vertex = choose_target(earlier_blockers, agent_id, rejected)
                    if target_vertex < 0:
                        state.exhausted = True
                        if mode == "queued_no_cross" and any(
                            int(partitions[vertex]) != int(agent_id) for vertex in earlier_blockers - rejected
                        ):
                            no_cross_failures += 1
                            failure_reason = "dependency_invalidation_no_cross_recovery"
                        else:
                            failure_reason = f"dependency_invalidation_no_route_after_{error}"
                    else:
                        target_agent = int(partitions[target_vertex])
                        target_timestamp = int(assignment_meta[target_vertex]["timestamp"])
                        if target_agent == agent_id:
                            routed, route_error, routed_count = execute_local_rollback(
                                state,
                                target_vertex,
                                target_timestamp,
                                agent_id,
                            )
                            if not routed:
                                state.rejected_targets[invalidated_vertex].add(target_vertex)
                            else:
                                dependency_invalidations += 1
                                if routed_count:
                                    state.conflict_sets[target_vertex].update(
                                        blocker
                                        for blocker in earlier_blockers
                                        if position[blocker] < position[target_vertex]
                                    )
                                if routed_count <= 0:
                                    state.exhausted = True
                                    failure_reason = f"dependency_invalidation_{route_error}"
                        elif not dispatch_request(
                            state,
                            target_agent,
                            target_vertex,
                            target_timestamp,
                            invalidated_vertex,
                            earlier_blockers,
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
                assignment_meta[vertex] = {
                    "agent": agent_id,
                    "timestamp": timestamp,
                    "color": int(chosen_color),
                }
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
                trace.add("assign", agent_id, vertex, chosen_color, timestamp)
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
            target_vertex = choose_target(blockers, agent_id, rejected)
            if target_vertex < 0:
                state.exhausted = True
                if mode == "queued_no_cross" and any(
                    int(partitions[candidate]) != int(agent_id) for candidate in blockers - rejected
                ):
                    no_cross_failures += 1
                    failure_reason = "no_cross_recovery_disabled"
                else:
                    failure_reason = "no_unrejected_assignment_to_rollback"
                continue
            target_agent = int(partitions[target_vertex])
            target_timestamp = int(assignment_meta[target_vertex]["timestamp"])
            if target_agent == agent_id:
                success, _error, popped_count = execute_local_rollback(
                    state,
                    target_vertex,
                    target_timestamp,
                    agent_id,
                )
                if not success:
                    state.rejected_targets[vertex].add(target_vertex)
                elif popped_count:
                    state.conflict_sets[target_vertex].update(
                        blocker for blocker in blockers if position[blocker] < position[target_vertex]
                    )
                state.conflict_sets[vertex].clear()
                continue

            if not dispatch_request(
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
            return finish("NO_CROSS_RECOVERY" if no_cross_failures else "EXHAUSTED")
        if not progress:
            failure_reason = "scheduler_deadlock_no_progress"
            return finish("DEADLOCK")

    failure_reason = "activation_cap_reached"
    return finish("ACTIVATION_CAP")
