"""Rollback-signal policies for the SPEC v7-RPD symbolic environment gate."""

from __future__ import annotations

from itertools import permutations
import hashlib
from typing import Any, Mapping

import torch

from experiments.signal.detector import DeterministicNoisyDetector
from experiments.signal.long_diameter_graph import (
    GraphCompletionOracle,
    _direct_color_valid,
    verify_coloring,
)
from register.structured import StructuredRegister


SYSTEMS = ("R_exact", "R_commit", "R_soft2")
_COLOR_PERMUTATIONS = list(permutations((1, 2, 3)))


def _stable_integer(*parts: object) -> int:
    payload = "::".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _branch_encoding(vertex: int, color: int, hidden_dim: int = 16) -> torch.Tensor:
    vector = torch.zeros(1, int(hidden_dim), dtype=torch.float32)
    vector[0, (int(vertex) * 5 + int(color) * 3) % int(hidden_dim)] = 1.0
    vector[0, (int(vertex) * 11 + int(color) * 7 + 1) % int(hidden_dim)] += 0.5
    return vector


def _restart_color_order(instance_id: str, vertex: int, restart: int) -> list[int]:
    index = _stable_integer("v7_restart", instance_id, int(vertex), int(restart)) % len(_COLOR_PERMUTATIONS)
    return list(_COLOR_PERMUTATIONS[index])


def run_system(
    instance: Mapping[str, Any],
    *,
    system: str,
    eta_fp: float,
    eta_fn: float = 0.0,
    noise_seed: int = 20260712,
    max_activations: int = 5000,
    max_restarts: int = 12,
    register_dim: int = 64,
    register_hidden_dim: int = 16,
    completion_oracle: GraphCompletionOracle | None = None,
) -> dict[str, Any]:
    if system not in SYSTEMS:
        raise ValueError(f"unknown signal system: {system}")
    instance_id = str(instance["instance_id"])
    order = [int(value) for value in instance["order"]]
    detector = DeterministicNoisyDetector(float(eta_fp), float(eta_fn), int(noise_seed))
    oracle = completion_oracle if completion_oracle is not None else GraphCompletionOracle(instance)
    oracle_before = oracle.cache_info()

    def oracle_delta() -> dict[str, int]:
        current = oracle.cache_info()
        return {
            "hits": int(current["hits"] - oracle_before["hits"]),
            "misses": int(current["misses"] - oracle_before["misses"]),
            "size_total": int(current["size"]),
            "nodes_expanded": int(current["nodes_expanded"] - oracle_before["nodes_expanded"]),
        }

    register_seed = _stable_integer("v7_register", instance_id) % (2**31)
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(register_seed)
        register = StructuredRegister(
            dim=int(register_dim),
            hidden_dim=int(register_hidden_dim),
            max_keys=max(128, len(order) + 1),
        )
    register_state = register.init_state(1, torch.device("cpu"))

    assignment: dict[int, int] = {}
    trail: list[dict[str, Any]] = []
    next_choice = {vertex: 0 for vertex in order}
    cursor = 0
    restart = 0
    activations = 0
    recurrent_rounds = 0
    branch_attempts = 0
    detector_queries = 0
    exact_pops = 0
    hard_rollbacks = 0
    true_signal_rollbacks = 0
    over_rollbacks = 0
    false_positives = 0
    false_negatives = 0
    correct_work_destroyed = 0
    restart_work_destroyed = 0
    max_trail = 0
    register_residual_max = 0.0
    failure_reason = ""

    def color_order(vertex: int) -> list[int]:
        if system == "R_commit":
            return _restart_color_order(instance_id, vertex, restart)
        return [int(value) for value in instance["color_orders"][str(vertex)]]

    def pop_top(reason: str) -> bool:
        nonlocal cursor, exact_pops, hard_rollbacks, register_residual_max, register_state
        if not trail:
            return False
        item = trail.pop()
        variable = int(item["vertex"])
        assignment.pop(variable, None)
        register_state = register.pop(register_state, item["encoding"], int(item["depth"]))
        residual = float(torch.max(torch.abs(register_state - item["register_before"])).item())
        register_residual_max = max(register_residual_max, residual)
        cursor = int(item["cursor"])
        exact_pops += 1
        hard_rollbacks += int(reason == "hard_exhaustion")
        return True

    while activations < int(max_activations):
        if cursor >= len(order):
            solved = verify_coloring(instance, assignment)
            return {
                "instance_id": instance_id,
                "partition_diameter": int(instance["partition_diameter"]),
                "system": system,
                "eta_fp": float(eta_fp),
                "eta_fn": float(eta_fn),
                "solved": bool(solved),
                "status": "SOLVED" if solved else "OFFICIAL_SCORE_FAIL",
                "failure_reason": "" if solved else "full_assignment_invalid",
                "activations": activations,
                "recurrent_rounds": recurrent_rounds,
                "branch_attempts": branch_attempts,
                "detector_queries": detector_queries,
                "exact_pops": exact_pops,
                "hard_rollbacks": hard_rollbacks,
                "true_signal_rollbacks": true_signal_rollbacks,
                "over_rollbacks": over_rollbacks,
                "false_positives": false_positives,
                "false_negatives": false_negatives,
                "correct_work_destroyed": correct_work_destroyed,
                "restarts": restart,
                "restart_work_destroyed": restart_work_destroyed,
                "max_trail": max_trail,
                "register_residual_max": register_residual_max,
                "oracle_cache": oracle_delta(),
                "aggregate_work": branch_attempts + exact_pops + detector_queries + restart_work_destroyed,
                "official_verification": bool(solved),
                "planted_assignment_used": False,
            }

        activations += 1
        recurrent_rounds += 1
        vertex = order[cursor]
        colors = color_order(vertex)
        committed = False
        while next_choice[vertex] < len(colors):
            color = int(colors[next_choice[vertex]])
            next_choice[vertex] += 1
            branch_attempts += 1
            if not _direct_color_valid(instance, assignment, vertex, color):
                continue
            register_before = register_state.clone()
            encoding = _branch_encoding(vertex, color, int(register_hidden_dim))
            depth = len(trail)
            register_state = register.push(register_state, encoding, depth)
            assignment[vertex] = color
            trail.append({
                "vertex": vertex,
                "color": color,
                "cursor": cursor,
                "depth": depth,
                "encoding": encoding,
                "register_before": register_before,
            })
            max_trail = max(max_trail, len(trail))
            true_dead = not oracle.is_completable(assignment)
            first = detector.observe(
                instance_id=instance_id,
                assignment=assignment,
                true_dead=true_dead,
                query_index=0,
            )
            detector_queries += 1
            false_positives += int(first.false_positive)
            false_negatives += int(first.false_negative)
            trigger = bool(first.observed_dead)
            if system == "R_soft2" and trigger:
                second = detector.observe(
                    instance_id=instance_id,
                    assignment=assignment,
                    true_dead=true_dead,
                    query_index=1,
                )
                detector_queries += 1
                recurrent_rounds += 1
                false_positives += int(second.false_positive)
                false_negatives += int(second.false_negative)
                trigger = bool(second.observed_dead)
            if system == "R_commit":
                trigger = False
            if trigger:
                true_signal_rollbacks += int(true_dead)
                over_rollbacks += int(not true_dead)
                correct_work_destroyed += int(not true_dead)
                pop_top("signal")
                committed = True
                break
            cursor += 1
            committed = True
            break

        if committed:
            continue

        next_choice[vertex] = 0
        if system == "R_commit":
            if restart >= int(max_restarts):
                failure_reason = "restart_cap_reached"
                break
            restart_work_destroyed += len(trail)
            restart += 1
            assignment.clear()
            trail.clear()
            next_choice = {item: 0 for item in order}
            cursor = 0
            register_state = register.init_state(1, torch.device("cpu"))
            continue

        if not pop_top("hard_exhaustion"):
            failure_reason = "search_exhausted"
            break

    status = "ACTIVATION_CAP" if activations >= int(max_activations) else "EXHAUSTED"
    return {
        "instance_id": instance_id,
        "partition_diameter": int(instance["partition_diameter"]),
        "system": system,
        "eta_fp": float(eta_fp),
        "eta_fn": float(eta_fn),
        "solved": False,
        "status": status,
        "failure_reason": failure_reason or "activation_cap_reached",
        "activations": activations,
        "recurrent_rounds": recurrent_rounds,
        "branch_attempts": branch_attempts,
        "detector_queries": detector_queries,
        "exact_pops": exact_pops,
        "hard_rollbacks": hard_rollbacks,
        "true_signal_rollbacks": true_signal_rollbacks,
        "over_rollbacks": over_rollbacks,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "correct_work_destroyed": correct_work_destroyed,
        "restarts": restart,
        "restart_work_destroyed": restart_work_destroyed,
        "max_trail": max_trail,
        "register_residual_max": register_residual_max,
        "oracle_cache": oracle_delta(),
        "aggregate_work": branch_attempts + exact_pops + detector_queries + restart_work_destroyed,
        "official_verification": False,
        "planted_assignment_used": False,
    }
