"""Matched global and owner-local solvers for community-structured 3-SAT."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
import hashlib
import json
import random
from statistics import mean
from typing import Any

from tasks.sat.community import (
    clause_falsified,
    generate_community_sat_candidate,
    verify_sat_assignment,
)


FACTOR_MODES = (
    "queued_deepest",
    "central_deepest",
    "queued_random_valid",
    "queued_no_cross",
)
FACTOR_ARM_NAMES = {
    "queued_deepest": "independent_local_cbj_sat",
    "central_deepest": "factorized_central_cbj_sat",
    "queued_random_valid": "independent_local_random_valid_sat",
    "queued_no_cross": "independent_local_no_cross_sat",
}
GLOBAL_ARMS = (
    "global_trail_cbj_sat",
    "centralized_sharded_MR_sat",
    "monolith_MR_sat",
    "monolith_R_sat",
)
ALL_ARMS = tuple(FACTOR_ARM_NAMES.values()) + GLOBAL_ARMS


@dataclass
class SATRollbackRequest:
    request_id: int
    source_agent: int
    target_agent: int
    target_variable: int
    target_timestamp: int
    deadend_variable: int
    blockers: tuple[int, ...]
    reason: str


@dataclass
class SATAgentState:
    agent_id: int
    order: list[int]
    cursor: int = 0
    next_choice: dict[int, int] = field(default_factory=dict)
    conflict_sets: dict[int, set[int]] = field(default_factory=dict)
    rejected_targets: dict[int, set[int]] = field(default_factory=dict)
    trail: list[dict[str, int]] = field(default_factory=list)
    pending: deque[SATRollbackRequest] = field(default_factory=deque)
    waiting_request_id: int | None = None
    waiting_variable: int | None = None
    done: bool = False
    exhausted: bool = False


def _owner(instance: dict[str, Any], variable: int) -> int:
    return int(instance["partitions"][int(variable) - 1])


def _position(instance: dict[str, Any]) -> dict[int, int]:
    return {int(variable): index for index, variable in enumerate(instance["order"])}


def _clause_index(instance: dict[str, Any]) -> tuple[dict[int, list[tuple[int, ...]]], set[int], list[set[int]]]:
    position = _position(instance)
    by_latest: dict[int, list[tuple[int, ...]]] = defaultdict(list)
    boundary_variables: set[int] = set()
    cooccurrence = [set() for _ in range(int(instance["n_vars"]) + 1)]
    for raw_clause in instance["clauses"]:
        clause = tuple(int(literal) for literal in raw_clause)
        variables = [abs(literal) for literal in clause]
        latest = max(variables, key=lambda variable: position[variable])
        by_latest[latest].append(clause)
        owners = {_owner(instance, variable) for variable in variables}
        if len(owners) > 1:
            boundary_variables.update(variables)
        for left in variables:
            cooccurrence[left].update(variable for variable in variables if variable != left)
    return dict(by_latest), boundary_variables, cooccurrence


def _literal_false(literal: int, value: int) -> bool:
    return not ((int(value) == 1) == (int(literal) > 0))


def _value_blockers(
    variable: int,
    value: int,
    assignment: dict[int, int],
    clauses_by_latest: dict[int, list[tuple[int, ...]]],
) -> set[int]:
    blockers: set[int] = set()
    for clause in clauses_by_latest.get(int(variable), []):
        values: dict[int, int] = {}
        complete = True
        for literal in clause:
            item = abs(int(literal))
            if item == int(variable):
                values[item] = int(value)
            elif item in assignment:
                values[item] = int(assignment[item])
            else:
                complete = False
                break
        if complete and all(_literal_false(literal, values[abs(literal)]) for literal in clause):
            blockers.update(abs(literal) for literal in clause if abs(literal) != int(variable))
    return blockers


def _invalidating_blockers(
    variable: int,
    assignment: dict[int, int],
    clauses_by_latest: dict[int, list[tuple[int, ...]]],
) -> set[int]:
    blockers: set[int] = set()
    for clause in clauses_by_latest.get(int(variable), []):
        if clause_falsified(clause, assignment):
            blockers.update(abs(literal) for literal in clause if abs(literal) != int(variable))
    return blockers


def _make_agents(instance: dict[str, Any]) -> dict[int, SATAgentState]:
    agents: dict[int, SATAgentState] = {}
    for agent_id in sorted(set(map(int, instance["partitions"]))):
        order = [int(variable) for variable in instance["order"] if _owner(instance, int(variable)) == agent_id]
        agents[agent_id] = SATAgentState(
            agent_id=agent_id,
            order=order,
            next_choice={variable: 0 for variable in order},
            conflict_sets={variable: set() for variable in order},
            rejected_targets={variable: set() for variable in order},
        )
    return agents


def _rollback_local(
    state: SATAgentState,
    target_variable: int,
    assignment: dict[int, int],
    assignment_meta: dict[int, dict[str, int]],
    instance: dict[str, Any],
    r_value: int,
) -> tuple[list[dict[str, int]] | None, str | None]:
    target_index = max(
        (index for index, item in enumerate(state.trail) if int(item["variable"]) == int(target_variable)),
        default=-1,
    )
    if target_index < 0:
        return None, "target_not_in_owner_trail"
    if target_index < max(0, len(state.trail) - int(r_value)):
        return None, "target_outside_owner_window"
    popped = state.trail[target_index:]
    if any(_owner(instance, int(item["variable"])) != int(state.agent_id) for item in popped):
        return None, "ownership_violation_in_local_trail"
    for item in popped:
        variable = int(item["variable"])
        assignment.pop(variable, None)
        assignment_meta.pop(variable, None)
    state.trail = state.trail[:target_index]
    for item in popped[1:]:
        variable = int(item["variable"])
        state.next_choice[variable] = 0
        state.conflict_sets[variable].clear()
        state.rejected_targets[variable].clear()
    state.rejected_targets[int(target_variable)].clear()
    state.cursor = int(popped[0]["local_index"])
    state.done = False
    state.exhausted = False
    return popped, None


def _global_config(
    instance: dict[str, Any],
    arm: str,
    m_agents: int,
    r_value: int,
) -> tuple[list[int], dict[int, int], bool]:
    original = [int(value) for value in instance["partitions"]]
    if arm == "monolith_R_sat":
        return [0] * len(original), {0: int(r_value)}, False
    if arm == "monolith_MR_sat":
        return [0] * len(original), {0: int(m_agents) * int(r_value)}, False
    if arm == "global_trail_cbj_sat":
        return original, {agent: int(r_value) for agent in range(int(m_agents))}, True
    if arm == "centralized_sharded_MR_sat":
        return original, {agent: int(r_value) for agent in range(int(m_agents))}, False
    raise ValueError(arm)


def run_global_sat(
    instance: dict[str, Any],
    arm: str,
    m_agents: int,
    r_value: int,
    node_cap: int,
    *,
    enforce_window: bool = True,
) -> dict[str, Any]:
    if arm not in GLOBAL_ARMS:
        raise ValueError(arm)
    n = int(instance["n_vars"])
    position = _position(instance)
    clauses_by_latest, boundary_variables, _cooccurrence = _clause_index(instance)
    partitions, windows, count_communication = _global_config(instance, arm, m_agents, r_value)
    order = [int(variable) for variable in instance["order"]]
    assignment: dict[int, int] = {}
    next_choice = {variable: 0 for variable in order}
    conflict_sets: dict[int, set[int]] = {variable: set() for variable in order}
    trail: list[dict[str, int]] = []
    registers: dict[int, list[dict[str, int]]] = defaultdict(list)
    cursor = 0
    branch_attempts = 0
    recoveries = 0
    retractions = 0
    cross_block_messages = 0
    boundary_commit_messages = 0
    communication_tokens = 0
    max_global_recovery_distance = 0
    max_local_recovery_distance = 0
    max_register_length = 0
    peak_total_register_entries = 0

    def owner(variable: int) -> int:
        return int(partitions[int(variable) - 1])

    def finish(status: str) -> dict[str, Any]:
        solved = status == "SOLVED" and verify_sat_assignment(instance, assignment)
        final_status = "SOLVED" if solved else ("OFFICIAL_SCORE_FAIL" if status == "SOLVED" else status)
        aggregate_work = branch_attempts + retractions + cross_block_messages
        return {
            "instance_id": str(instance["instance_id"]),
            "cell": str(instance.get("cell", "reference")),
            "capacity": str(instance.get("capacity", "reference")),
            "coupling": str(instance["coupling"]),
            "arm": arm,
            "solved": solved,
            "status": final_status,
            "branch_attempts": branch_attempts,
            "activations": branch_attempts,
            "parallel_rounds": branch_attempts,
            "recoveries": recoveries,
            "retractions": retractions,
            "cross_block_messages": cross_block_messages,
            "requests_sent": cross_block_messages,
            "requests_executed": cross_block_messages,
            "acknowledgements": cross_block_messages,
            "nacks": 0,
            "boundary_commit_messages": boundary_commit_messages,
            "communication_tokens": communication_tokens,
            "aggregate_work": aggregate_work,
            "penalized_work": aggregate_work if solved else max(aggregate_work, int(node_cap)),
            "max_global_recovery_distance": max_global_recovery_distance,
            "max_local_recovery_distance": max_local_recovery_distance,
            "max_pending_requests": 0,
            "max_local_register": min(max_register_length, max(windows.values(), default=0)),
            "max_local_trail_length": max_register_length,
            "total_register_entries_peak": peak_total_register_entries,
            "declared_per_agent_window": max(windows.values(), default=0),
            "declared_total_window": sum(windows.values()),
            "cross_agent_direct_mutations": 0,
            "ownership_violations": 0,
            "priority_direction_violations": 0,
            "window_rejections": int(final_status == "NO_RECOVERY_TARGET"),
            "out_of_window_rollback_executions": 0,
            "request_lifecycle_valid": True,
            "no_global_trail": False,
            "independent_agent_state": False,
            "no_oracle_or_model_fallback": True,
            "official_full_clause_verification": bool(solved),
            "evaluation_mode": "community_sat_global_v1",
            "headline_eligible": False,
        }

    while True:
        if branch_attempts >= int(node_cap):
            return finish("ACTIVATION_CAP")
        if cursor >= len(order):
            return finish("SOLVED")
        variable = order[cursor]
        if variable in assignment:
            cursor += 1
            continue
        chosen_value: int | None = None
        while next_choice[variable] < 2:
            value = next_choice[variable]
            next_choice[variable] += 1
            blockers = _value_blockers(variable, value, assignment, clauses_by_latest)
            if not blockers:
                chosen_value = value
                break
            conflict_sets[variable].update(blockers)
        branch_attempts += 1
        if chosen_value is not None:
            assignment[variable] = int(chosen_value)
            agent = owner(variable)
            item = {"variable": variable, "agent": agent, "order_index": cursor}
            trail.append(item)
            registers[agent].append(item)
            max_register_length = max(max_register_length, len(registers[agent]))
            peak_total_register_entries = max(peak_total_register_entries, sum(len(value) for value in registers.values()))
            if count_communication and variable in boundary_variables:
                boundary_commit_messages += 1
                communication_tokens += 4
            cursor += 1
            continue
        blockers = {
            blocker for blocker in conflict_sets[variable]
            if blocker in assignment and position[blocker] < position[variable]
        }
        next_choice[variable] = 0
        if not blockers or not trail:
            return finish("EXHAUSTED")
        cross_block = any(owner(blocker) != owner(variable) for blocker in blockers)
        if count_communication and cross_block:
            cross_block_messages += 1
            communication_tokens += 2 + 2 * len(blockers)
        target_variable = max(blockers, key=lambda item: position[item])
        target_agent = owner(target_variable)
        target_register = registers[target_agent]
        absolute_index = max(
            (index for index, item in enumerate(target_register) if int(item["variable"]) == target_variable),
            default=-1,
        )
        if absolute_index < 0:
            return finish("NO_RECOVERY_TARGET")
        local_distance = len(target_register) - absolute_index
        target_trail_index = max(
            index for index, item in enumerate(trail) if int(item["variable"]) == target_variable
        )
        global_distance = len(trail) - target_trail_index
        max_local_recovery_distance = max(max_local_recovery_distance, local_distance)
        max_global_recovery_distance = max(max_global_recovery_distance, global_distance)
        if enforce_window and absolute_index < max(0, len(target_register) - int(windows[target_agent])):
            return finish("NO_RECOVERY_TARGET")
        conflict_sets[target_variable].update(
            blocker for blocker in blockers if position[blocker] < position[target_variable]
        )
        popped = trail[target_trail_index:]
        popped_variables = {int(item["variable"]) for item in popped}
        recoveries += 1
        retractions += len(popped)
        for item in popped:
            assignment.pop(int(item["variable"]), None)
        trail = trail[:target_trail_index]
        for agent in list(registers):
            registers[agent] = [item for item in registers[agent] if int(item["variable"]) not in popped_variables]
        for item in popped[1:]:
            item_variable = int(item["variable"])
            next_choice[item_variable] = 0
            conflict_sets[item_variable].clear()
        conflict_sets[variable].clear()
        cursor = int(popped[0]["order_index"])


def reference_metrics(instance: dict[str, Any], m_agents: int = 4, r_value: int = 8, node_cap: int = 100000) -> dict[str, Any] | None:
    global_row = run_global_sat(
        instance,
        "monolith_MR_sat",
        int(m_agents),
        max(int(instance["n_vars"]), int(r_value)),
        int(node_cap),
        enforce_window=False,
    )
    local_row = run_global_sat(
        instance,
        "centralized_sharded_MR_sat",
        int(m_agents),
        max(int(instance["n_vars"]), int(r_value)),
        int(node_cap),
        enforce_window=False,
    )
    if not global_row["solved"] or not local_row["solved"]:
        return None
    return {
        "reference_solved": True,
        "reference_steps": int(global_row["branch_attempts"]),
        "reference_recoveries": int(global_row["recoveries"]),
        "reference_retractions": int(global_row["retractions"]),
        "global_recovery_distance": int(global_row["max_global_recovery_distance"]),
        "local_recovery_distance": int(local_row["max_local_recovery_distance"]),
    }


def _target_index(state: SATAgentState, target_variable: int) -> int:
    return max(
        (index for index, item in enumerate(state.trail) if int(item["variable"]) == int(target_variable)),
        default=-1,
    )


def _stable_rng(instance_id: str, mode: str, route_seed: int) -> random.Random:
    payload = f"community_sat_route::{int(route_seed)}::{instance_id}::{mode}".encode("utf-8")
    return random.Random(int.from_bytes(hashlib.sha256(payload).digest()[:8], "big"))


def run_factorized_sat(
    instance: dict[str, Any],
    mode: str,
    r_value: int,
    activation_cap: int,
    channel_cap: int,
    route_seed: int,
) -> dict[str, Any]:
    if mode not in FACTOR_MODES:
        raise ValueError(mode)
    n = int(instance["n_vars"])
    position = _position(instance)
    clauses_by_latest, boundary_variables, cooccurrence = _clause_index(instance)
    agents = _make_agents(instance)
    assignment: dict[int, int] = {}
    assignment_meta: dict[int, dict[str, int]] = {}
    timestamp = 0
    next_request_id = 0
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
    rng = _stable_rng(str(instance["instance_id"]), mode, int(route_seed))

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
                    source_state.waiting_variable = None
        solved = status == "SOLVED" and verify_sat_assignment(instance, assignment)
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
            "instance_id": str(instance["instance_id"]),
            "cell": str(instance.get("cell", "development")),
            "capacity": str(instance.get("capacity", "development")),
            "coupling": str(instance["coupling"]),
            "arm": FACTOR_ARM_NAMES[mode],
            "control_mode": mode,
            "solved": solved,
            "status": final_status,
            "failure_reason": failure_reason,
            "branch_attempts": branch_attempts,
            "activations": activations,
            "parallel_rounds": parallel_rounds,
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
            "official_full_clause_verification": bool(solved),
            "preserved_global_suffix_assignments": preserved_global_suffix_assignments,
            "preserved_dependency_unrelated_assignments": preserved_dependency_unrelated_assignments,
            "rollback_events_with_global_preservation": rollback_events_with_global_preservation,
            "rollback_events_with_unrelated_preservation": rollback_events_with_unrelated_preservation,
            "cross_agent_rollback_events": cross_agent_rollback_events,
            "local_rollback_events": local_rollback_events,
            "no_cross_failures": no_cross_failures,
            "route_mode": "random_valid" if mode == "queued_random_valid" else "no_cross" if mode == "queued_no_cross" else "deepest_cbj",
            "delivery_mode": "immediate_target_callback" if mode == "central_deepest" else "queued_target_activation",
            "evaluation_mode": "community_sat_factorized_v1",
            "headline_eligible": False,
        }

    def execute_local_rollback(
        state: SATAgentState,
        target_variable: int,
        expected_timestamp: int,
        source_agent: int,
    ) -> tuple[bool, str | None, int]:
        nonlocal cross_agent_rollback_events, local_rollback_events
        nonlocal max_local_register, max_local_trail_length
        nonlocal out_of_window_rollback_executions, ownership_violations
        nonlocal preserved_dependency_unrelated_assignments, preserved_global_suffix_assignments
        nonlocal recoveries, retractions, rollback_events_with_global_preservation
        nonlocal rollback_events_with_unrelated_preservation, window_rejections
        current_meta = assignment_meta.get(int(target_variable))
        if current_meta is None or int(current_meta["timestamp"]) != int(expected_timestamp):
            return True, "stale_assignment_already_retracted", 0
        index = _target_index(state, int(target_variable))
        outside_window = index >= 0 and index < max(0, len(state.trail) - int(r_value))
        metadata_before = {variable: dict(meta) for variable, meta in assignment_meta.items()}
        popped, error = _rollback_local(
            state,
            int(target_variable),
            assignment,
            assignment_meta,
            instance,
            int(r_value),
        )
        if error:
            ownership_violations += int(error == "ownership_violation_in_local_trail")
            window_rejections += int(error == "target_outside_owner_window")
            return False, error, 0
        popped_variables = {int(item["variable"]) for item in (popped or [])}
        suffix = {
            variable for variable, meta in metadata_before.items()
            if int(meta["timestamp"]) >= int(expected_timestamp)
        }
        preserved = suffix - popped_variables
        unrelated = {
            variable for variable in preserved
            if _owner(instance, variable) != int(state.agent_id)
            and all(variable not in cooccurrence[popped_variable] for popped_variable in popped_variables)
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
        return True, None, len(popped or [])

    def process_request(target_state: SATAgentState, request: SATRollbackRequest) -> None:
        nonlocal acknowledgements, communication_tokens, nacks
        nonlocal ownership_violations, priority_direction_violations, requests_executed
        if (
            int(request.target_agent) != int(target_state.agent_id)
            or _owner(instance, int(request.target_variable)) != int(target_state.agent_id)
        ):
            ownership_violations += 1
            success, error, popped_count = False, "request_target_ownership_violation", 0
        elif position[int(request.target_variable)] >= position[int(request.deadend_variable)]:
            priority_direction_violations += 1
            success, error, popped_count = False, "non_decreasing_priority_request", 0
        else:
            success, error, popped_count = execute_local_rollback(
                target_state,
                int(request.target_variable),
                int(request.target_timestamp),
                int(request.source_agent),
            )
        source_state = agents[int(request.source_agent)]
        if success:
            if popped_count:
                target_state.conflict_sets[int(request.target_variable)].update(
                    blocker for blocker in request.blockers
                    if position[int(blocker)] < position[int(request.target_variable)]
                )
            requests_executed += 1
            acknowledgements += 1
            communication_tokens += 2
            source_state.waiting_request_id = None
            if source_state.waiting_variable is not None and request.reason == "deadend":
                source_state.next_choice[int(source_state.waiting_variable)] = 0
                source_state.conflict_sets[int(source_state.waiting_variable)].clear()
            source_state.waiting_variable = None
            source_state.done = False
        else:
            nacks += 1
            acknowledgements += 1
            source_state.waiting_request_id = None
            if source_state.waiting_variable is not None:
                source_state.rejected_targets[int(source_state.waiting_variable)].add(int(request.target_variable))
            source_state.waiting_variable = None

    def target_window_valid(variable: int) -> bool:
        state = agents[_owner(instance, int(variable))]
        index = _target_index(state, int(variable))
        return index >= 0 and index >= max(0, len(state.trail) - int(r_value))

    def choose_target(candidates: set[int], source_agent: int, rejected: set[int]) -> int:
        available = set(candidates) - set(rejected)
        if mode == "queued_no_cross":
            available = {variable for variable in available if _owner(instance, variable) == int(source_agent)}
        if mode == "queued_random_valid":
            available = {variable for variable in available if target_window_valid(variable)}
        if not available:
            return -1
        ordered = sorted(available, key=lambda variable: (position[variable], variable))
        if mode == "queued_random_valid":
            return int(ordered[rng.randrange(len(ordered))])
        return int(ordered[-1])

    def dispatch_request(
        source_state: SATAgentState,
        target_agent: int,
        target_variable: int,
        target_timestamp: int,
        source_variable: int,
        blockers: set[int],
        reason: str,
    ) -> bool:
        nonlocal communication_tokens, max_pending_requests, next_request_id, requests_sent
        pending_count = sum(len(state.pending) for state in agents.values())
        if mode != "central_deepest" and pending_count >= int(channel_cap):
            return False
        request = SATRollbackRequest(
            request_id=next_request_id,
            source_agent=int(source_state.agent_id),
            target_agent=int(target_agent),
            target_variable=int(target_variable),
            target_timestamp=int(target_timestamp),
            deadend_variable=int(source_variable),
            blockers=tuple(sorted(map(int, blockers))),
            reason=str(reason),
        )
        next_request_id += 1
        source_state.waiting_request_id = int(request.request_id)
        source_state.waiting_variable = int(source_variable)
        requests_sent += 1
        communication_tokens += 2 + 2 * len(blockers)
        if mode == "central_deepest":
            max_pending_requests = max(max_pending_requests, 1)
            process_request(agents[int(target_agent)], request)
        else:
            agents[int(target_agent)].pending.append(request)
            max_pending_requests = max(max_pending_requests, sum(len(state.pending) for state in agents.values()))
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
                process_request(state, state.pending.popleft())
                progress = True
                continue
            if state.waiting_request_id is not None or state.exhausted:
                continue

            invalidated: tuple[int, set[int], int] | None = None
            for item in state.trail:
                variable = int(item["variable"])
                blockers = _invalidating_blockers(variable, assignment, clauses_by_latest)
                if blockers:
                    invalidated = (variable, blockers, int(item["timestamp"]))
                    break
            if invalidated is not None:
                variable, blockers, expected_timestamp = invalidated
                success, error, popped_count = execute_local_rollback(
                    state, variable, expected_timestamp, agent_id
                )
                if not success:
                    target = choose_target(blockers, agent_id, state.rejected_targets[variable])
                    if target < 0:
                        state.exhausted = True
                        if mode == "queued_no_cross" and any(_owner(instance, item) != agent_id for item in blockers):
                            no_cross_failures += 1
                            failure_reason = "dependency_invalidation_no_cross_recovery"
                        else:
                            failure_reason = f"dependency_invalidation_no_route_after_{error}"
                    else:
                        target_agent = _owner(instance, target)
                        target_timestamp = int(assignment_meta[target]["timestamp"])
                        if target_agent == agent_id:
                            routed, route_error, routed_count = execute_local_rollback(
                                state, target, target_timestamp, agent_id
                            )
                            if not routed:
                                state.rejected_targets[variable].add(target)
                            else:
                                dependency_invalidations += 1
                                if routed_count:
                                    state.conflict_sets[target].update(
                                        blocker for blocker in blockers if position[blocker] < position[target]
                                    )
                                if routed_count <= 0:
                                    state.exhausted = True
                                    failure_reason = f"dependency_invalidation_{route_error}"
                        elif not dispatch_request(
                            state, target_agent, target, target_timestamp, variable, blockers, "dependency_invalidation"
                        ):
                            failure_reason = "request_channel_capacity_exceeded"
                            return finish("COMM_CAP")
                else:
                    dependency_invalidations += 1
                    state.next_choice[variable] = 0
                    state.conflict_sets[variable].clear()
                    state.rejected_targets[variable].clear()
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
            variable = int(state.order[state.cursor])
            if _owner(instance, variable) != agent_id:
                ownership_violations += 1
                failure_reason = "agent_cursor_ownership_violation"
                return finish("PROTOCOL_VIOLATION")
            chosen_value: int | None = None
            while state.next_choice[variable] < 2:
                value = int(state.next_choice[variable])
                state.next_choice[variable] += 1
                blockers = _value_blockers(variable, value, assignment, clauses_by_latest)
                if not blockers:
                    chosen_value = value
                    break
                state.conflict_sets[variable].update(blockers)
            branch_attempts += 1
            progress = True
            if chosen_value is not None:
                timestamp += 1
                assignment[variable] = int(chosen_value)
                assignment_meta[variable] = {
                    "agent": int(agent_id),
                    "timestamp": int(timestamp),
                    "value": int(chosen_value),
                }
                state.trail.append({
                    "variable": variable,
                    "value": int(chosen_value),
                    "local_index": int(state.cursor),
                    "timestamp": int(timestamp),
                })
                max_local_trail_length = max(max_local_trail_length, len(state.trail))
                max_local_register = max(max_local_register, min(len(state.trail), int(r_value)))
                state.rejected_targets[variable].clear()
                if variable in boundary_variables:
                    boundary_commit_messages += 1
                    communication_tokens += 4
                state.cursor += 1
                state.done = False
                continue
            blockers = {
                blocker for blocker in state.conflict_sets[variable]
                if blocker in assignment_meta and position[blocker] < position[variable]
            }
            rejected = state.rejected_targets[variable]
            state.next_choice[variable] = 0
            target = choose_target(blockers, agent_id, rejected)
            if target < 0:
                state.exhausted = True
                if mode == "queued_no_cross" and any(_owner(instance, item) != agent_id for item in blockers - rejected):
                    no_cross_failures += 1
                    failure_reason = "no_cross_recovery_disabled"
                else:
                    failure_reason = "no_unrejected_assignment_to_rollback"
                continue
            target_agent = _owner(instance, target)
            target_timestamp = int(assignment_meta[target]["timestamp"])
            if target_agent == agent_id:
                success, _error, popped_count = execute_local_rollback(
                    state, target, target_timestamp, agent_id
                )
                if not success:
                    state.rejected_targets[variable].add(target)
                elif popped_count:
                    state.conflict_sets[target].update(
                        blocker for blocker in blockers if position[blocker] < position[target]
                    )
                state.conflict_sets[variable].clear()
                continue
            if not dispatch_request(
                state, target_agent, target, target_timestamp, variable, blockers, "deadend"
            ):
                failure_reason = "request_channel_capacity_exceeded"
                return finish("COMM_CAP")

        if verify_sat_assignment(instance, assignment):
            return finish("SOLVED")
        if any(state.exhausted for state in agents.values()):
            return finish("NO_CROSS_RECOVERY" if no_cross_failures else "EXHAUSTED")
        if not progress:
            failure_reason = "scheduler_deadlock_no_progress"
            return finish("DEADLOCK")
    failure_reason = "activation_cap_reached"
    return finish("ACTIVATION_CAP")


def run_sat_arm(
    instance: dict[str, Any],
    arm: str,
    *,
    m_agents: int = 4,
    r_value: int = 8,
    activation_cap: int = 20000,
    channel_cap: int = 16,
    route_seed: int = 20260712,
) -> dict[str, Any]:
    if arm in GLOBAL_ARMS:
        return run_global_sat(instance, arm, m_agents, r_value, activation_cap, enforce_window=True)
    reverse = {value: key for key, value in FACTOR_ARM_NAMES.items()}
    if arm not in reverse:
        raise ValueError(arm)
    return run_factorized_sat(instance, reverse[arm], r_value, activation_cap, channel_cap, route_seed)


def classify_capacity(metrics: dict[str, Any], r_value: int) -> str | None:
    global_distance = int(metrics["global_recovery_distance"])
    local_distance = int(metrics["local_recovery_distance"])
    if global_distance <= int(r_value):
        return "under"
    if global_distance > int(r_value) and local_distance <= int(r_value):
        return "over_local_fit"
    return None


def generate_structural_pool(
    *,
    split: str,
    base_seed: int,
    max_candidates_per_coupling: int,
    instances_per_cell: int,
    r_value: int = 8,
    reference_cap: int = 100000,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accepted: dict[tuple[str, str], list[dict[str, Any]]] = {
        (capacity, coupling): []
        for capacity in ("under", "over_local_fit")
        for coupling in ("low", "high")
    }
    counters: dict[str, Counter[str]] = {coupling: Counter() for coupling in ("low", "high")}
    for coupling in ("low", "high"):
        for candidate_index in range(int(max_candidates_per_coupling)):
            if all(len(accepted[(capacity, coupling)]) >= int(instances_per_cell) for capacity in ("under", "over_local_fit")):
                break
            counters[coupling]["generated"] += 1
            candidate = generate_community_sat_candidate(
                base_seed=int(base_seed),
                candidate_index=int(candidate_index),
                coupling=coupling,
                split=split,
            )
            planted = {int(variable): int(value) for variable, value in candidate["planted_assignment"].items()}
            if not verify_sat_assignment(candidate, planted):
                counters[coupling]["planted_invalid"] += 1
                continue
            metrics = reference_metrics(candidate, r_value=int(r_value), node_cap=int(reference_cap))
            if metrics is None:
                counters[coupling]["reference_failed"] += 1
                continue
            counters[coupling]["reference_solved"] += 1
            capacity = classify_capacity(metrics, int(r_value))
            if capacity is None:
                counters[coupling]["outside_strata"] += 1
                continue
            key = (capacity, coupling)
            if len(accepted[key]) >= int(instances_per_cell):
                counters[coupling][f"extra_{capacity}"] += 1
                continue
            row = {key_name: value for key_name, value in candidate.items() if key_name != "planted_assignment"}
            row.update(metrics)
            row["capacity"] = capacity
            row["cell"] = ("under" if capacity == "under" else "over") + f"_{coupling}"
            row["selection_rule"] = "reference_recovery_stratum_only_no_evaluated_arm_outcomes"
            row["planted_assignment_removed"] = True
            accepted[key].append(row)
            counters[coupling][f"accepted_{capacity}"] += 1
    rows = [
        row
        for capacity in ("under", "over_local_fit")
        for coupling in ("low", "high")
        for row in accepted[(capacity, coupling)]
    ]
    generation = {
        "schema": "community_sat_pool_generation_v1",
        "split": split,
        "base_seed": int(base_seed),
        "max_candidates_per_coupling": int(max_candidates_per_coupling),
        "instances_per_cell": int(instances_per_cell),
        "cell_counts": dict(Counter(str(row["cell"]) for row in rows)),
        "counters": {coupling: dict(counter) for coupling, counter in counters.items()},
        "complete": all(len(accepted[key]) == int(instances_per_cell) for key in accepted),
        "evaluated_arm_outcomes_used": False,
    }
    return rows, generation


def summarize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for cell, arm in sorted({(str(row["cell"]), str(row["arm"])) for row in rows}):
        subset = [row for row in rows if row["cell"] == cell and row["arm"] == arm]
        output.append({
            "cell": cell,
            "arm": arm,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_aggregate_work": mean(float(row["aggregate_work"]) for row in subset),
            "mean_penalized_work": mean(float(row["penalized_work"]) for row in subset),
            "mean_parallel_rounds": mean(float(row["parallel_rounds"]) for row in subset),
            "mean_retractions": mean(float(row["retractions"]) for row in subset),
            "mean_requests": mean(float(row.get("requests_sent", 0)) for row in subset),
            "status_counts": dict(Counter(str(row["status"]) for row in subset)),
        })
    return output
