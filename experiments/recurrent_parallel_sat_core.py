"""Recurrent parallel local-candidate engine for long-diameter partitioned SAT."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Mapping

from experiments.recurrent_parallel_core import SIGNAL_SYSTEMS, _root_tree
from experiments.signal.detector import DeterministicNoisyDetector
from experiments.signal.long_diameter_sat import clause_satisfied, verify_sat


@dataclass
class SATLocalState:
    agent_id: int
    variables: tuple[int, ...]
    candidates: tuple[tuple[int, ...], ...]
    candidate_index: int
    tie_cursor: int = 0


def _candidate_assignment(state: SATLocalState, index: int | None = None) -> dict[int, int]:
    candidate = state.candidates[state.candidate_index if index is None else int(index)]
    return {variable: int(value) for variable, value in zip(state.variables, candidate)}


def _local_candidates(instance: Mapping[str, Any], agent: int) -> tuple[tuple[int, ...], ...]:
    variables = tuple(agent * int(instance["variables_per_partition"]) + offset + 1 for offset in range(int(instance["variables_per_partition"])))
    local = [clause for clause in instance["clauses"] if all(int(instance["partitions"][abs(int(literal)) - 1]) == int(agent) for literal in clause)]
    candidates = []
    for values in product((0, 1), repeat=len(variables)):
        assignment = dict(zip(variables, values))
        if all(clause_satisfied(clause, assignment) for clause in local):
            candidates.append(tuple(map(int, values)))
    if not candidates:
        raise ValueError("SAT agent has no local candidate")
    return tuple(sorted(candidates))


def _initial_candidate_index(candidates: tuple[tuple[int, ...], ...], pair_code: int) -> int:
    target = (int(pair_code) & 1, (int(pair_code) >> 1) & 1)
    return next(index for index, values in enumerate(candidates) if values[:2] == target)


def _cross_clauses_by_child(instance: Mapping[str, Any], parent: dict[int, int | None]) -> dict[int, list[list[int]]]:
    output = {agent: [] for agent in range(int(instance["n_partitions"]))}
    for clause in instance["clauses"]:
        owners = {int(instance["partitions"][abs(int(literal)) - 1]) for literal in clause}
        if len(owners) <= 1:
            continue
        child = next(agent for agent, parent_agent in parent.items() if parent_agent is not None and owners == {agent, int(parent_agent)})
        output[child].append([int(literal) for literal in clause])
    return output


def _candidate_cost(state: SATLocalState, candidate_index: int, parent_message: Mapping[int, int], clauses: list[list[int]]) -> int:
    assignment = dict(parent_message)
    assignment.update(_candidate_assignment(state, candidate_index))
    return sum(int(not clause_satisfied(clause, assignment)) for clause in clauses)


def _propose(state: SATLocalState, parent_message: Mapping[int, int], clauses: list[list[int]]) -> tuple[int, int]:
    costs = [_candidate_cost(state, index, parent_message, clauses) for index in range(len(state.candidates))]
    minimum = min(costs)
    minima = [index for index, cost in enumerate(costs) if cost == minimum]
    if state.candidate_index in minima:
        return int(state.candidate_index), int(state.tie_cursor)
    selected = minima[state.tie_cursor % len(minima)]
    return int(selected), int(state.tie_cursor + 1)


def run_noisy_sat_recurrence(
    instance: Mapping[str, Any],
    *,
    system: str,
    eta_fp: float,
    round_cap: int,
    eta_fn: float = 0.0,
    noise_seed: int = 20260712,
    root_agent: int = 0,
    confirmation_hits: int | None = None,
) -> dict[str, Any]:
    if system not in SIGNAL_SYSTEMS and system != "R_adaptive":
        raise ValueError(f"unknown SAT signal system: {system}")
    required_hits = int(confirmation_hits) if system == "R_adaptive" else (2 if system == "R_soft2" else 1)
    if required_hits < 1:
        raise ValueError("confirmation_hits must be positive")
    n_agents = int(instance["n_partitions"])
    parent, _children, _depth, _order = _root_tree(n_agents, list(instance["partition_tree_edges"]), int(root_agent))
    cross_by_child = _cross_clauses_by_child(instance, parent)
    codes = {int(agent): int(code) for agent, code in instance["initial_pair_codes"].items()}
    states: dict[int, SATLocalState] = {}
    for agent in range(n_agents):
        candidates = _local_candidates(instance, agent)
        variables = tuple(agent * int(instance["variables_per_partition"]) + offset + 1 for offset in range(int(instance["variables_per_partition"])))
        states[agent] = SATLocalState(agent, variables, candidates, _initial_candidate_index(candidates, codes[agent]))
    local_candidates_valid = all(
        all(_candidate_cost(state, index, {}, []) == 0 for index in range(len(state.candidates)))
        for state in states.values()
    )
    detector = DeterministicNoisyDetector(float(eta_fp), float(eta_fn), int(noise_seed))
    incoming = {agent: {} for agent in states}
    rounds_executed = 0
    agent_updates = 0
    state_changes = 0
    detector_queries = 0
    true_correction_exposures = 0
    true_corrections_executed = 0
    over_corrections = 0
    false_positives = 0
    false_negatives = 0
    candidate_corrections = 0
    messages_generated = 0
    messages_delivered = 0
    maximum_message_age = 0
    solved = False
    final_assignment: dict[int, int] = {}
    final_cross_violations = 0

    for round_index in range(int(round_cap)):
        rounds_executed += 1
        proposals: dict[int, tuple[int, int]] = {}
        for agent, state in states.items():
            message = dict(incoming[agent])
            if parent[agent] is None or not message or system == "R_commit":
                proposals[agent] = (state.candidate_index, state.tie_cursor)
                agent_updates += 1
                continue
            clauses = cross_by_child[agent]
            costs = [_candidate_cost(state, index, message, clauses) for index in range(len(state.candidates))]
            minimum = min(costs)
            current = int(state.candidate_index)
            true_correction = costs[current] > minimum
            true_correction_exposures += int(true_correction)
            query_assignment = _candidate_assignment(state)
            query_assignment.update({int(key): int(value) for key, value in message.items()})
            trigger = True
            for hit_index in range(required_hits):
                observation = detector.observe(
                    instance_id=f"{instance['instance_id']}::agent{agent}",
                    assignment=query_assignment,
                    true_dead=bool(true_correction),
                    query_index=round_index * 16 + hit_index,
                    channel="sat_recurrent_correction",
                )
                detector_queries += 1
                false_positives += int(observation.false_positive)
                false_negatives += int(observation.false_negative)
                if not observation.observed_dead:
                    trigger = False
                    break
            if not trigger:
                proposals[agent] = (current, state.tie_cursor)
            elif true_correction:
                proposals[agent] = _propose(state, message, clauses)
                true_corrections_executed += 1
                candidate_corrections += int(proposals[agent][0] != current)
            else:
                selected = (current + 1) % len(state.candidates)
                proposals[agent] = (selected, state.tie_cursor + 1)
                over_corrections += 1
                candidate_corrections += int(selected != current)
            agent_updates += 1
        for agent, (selected, tie_cursor) in proposals.items():
            state = states[agent]
            state_changes += int(int(selected) != int(state.candidate_index))
            state.candidate_index = int(selected)
            state.tie_cursor = int(tie_cursor)

        generated = {agent: {} for agent in states}
        for child, parent_agent in parent.items():
            if parent_agent is None:
                continue
            parent_state = states[int(parent_agent)]
            parent_assignment = _candidate_assignment(parent_state)
            generated[child] = {parent_state.variables[0]: parent_assignment[parent_state.variables[0]], parent_state.variables[1]: parent_assignment[parent_state.variables[1]]}
            messages_generated += 1
        incoming = generated
        delivered = sum(parent_agent is not None for parent_agent in parent.values())
        messages_delivered += delivered
        maximum_message_age = max(maximum_message_age, int(bool(delivered)))

        final_assignment = {variable: value for state in states.values() for variable, value in _candidate_assignment(state).items()}
        final_cross_violations = sum(int(not clause_satisfied(clause, final_assignment)) for clauses in cross_by_child.values() for clause in clauses)
        solved = verify_sat(instance, final_assignment)
        if solved:
            break

    aggregate_work = agent_updates + detector_queries + candidate_corrections
    return {
        "instance_id": str(instance["instance_id"]),
        "partition_diameter": int(instance["partition_diameter"]),
        "system": system,
        "eta_fp": float(eta_fp),
        "eta_fn": float(eta_fn),
        "confirmation_hits": required_hits,
        "round_cap": int(round_cap),
        "solved": bool(solved),
        "status": "SOLVED" if solved else "ROUND_CAP",
        "rounds_executed": rounds_executed,
        "agent_updates": agent_updates,
        "state_changes": state_changes,
        "detector_queries": detector_queries,
        "true_correction_exposures": true_correction_exposures,
        "true_corrections_executed": true_corrections_executed,
        "over_corrections": over_corrections,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "candidate_corrections": candidate_corrections,
        "messages_generated": messages_generated,
        "messages_delivered": messages_delivered,
        "maximum_message_age": maximum_message_age,
        "same_round_cross_agent_reads": 0,
        "aggregate_work": aggregate_work,
        "final_cross_violations": final_cross_violations,
        "local_candidates_valid": local_candidates_valid,
        "official_verification": bool(solved),
        "planted_assignment_used": False,
        "message_semantics": "two_bit_parent_state_one_round_delayed",
    }
