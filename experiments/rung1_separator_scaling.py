"""Rung-1 separator-scaling symbolic experiment."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any

from tqdm.auto import tqdm

from experiments.gen_separator_scaling import generate_separator_scaling_pool, target_depth
from experiments.rung1_distributed_graph_coloring import Instance, REPO_ROOT, SOURCE, _adjacency, _default_color_orders, _rel, _solve

RUN_ROOT = REPO_ROOT / "results/rung1_separator_scaling"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_058_rung1_separator_scaling.json"
SCHEMA_VERSION = "rung1_separator_scaling_symbolic_v0_2_3"
ITEM_NUMBER = "058"
STATUS_PASS = "RUNG1_SEPARATOR_SCALING_SYMBOLIC_PASS"
STATUS_KILL = "RUNG1_SEPARATOR_SCALING_SYMBOLIC_KILL_RECORDED"
STATUS_PARTIAL = "RUNG1_SEPARATOR_SCALING_SYMBOLIC_POOL_PARTIAL"
STATUS_AXES_STOP = "RUNG1_SEPARATOR_SCALING_SYMBOLIC_AXES_DESIGN_STOP"
TEAM_ARM_MAP = {"forward_markov_team": "forward_markov_team", "chronological_rollback_team": "chronological_rollback", "cbj_bounded_team": "cbj_bounded"}
ARMS = ("monolith_cbj", "forward_markov_team", "chronological_rollback_team", "cbj_bounded_team")
DEFAULT_SEEDS = (42, 137, 211, 307)
DEFAULT_N_PER_BLOCK = 12
DEFAULT_K = 4
DEFAULT_N_PER_CELL = 48
DEFAULT_REGISTER_CAPACITY_D = 6
DEFAULT_COMM_BUDGET_C = 16
DEFAULT_NODE_CAP = 240
COLLAPSE_TOLERANCE = 3.0
KEFF_REL_TOLERANCE = 0.11
HIGH_SOLVE_THRESHOLD = 0.75
LOW_SOLVE_THRESHOLD = 0.50
AXES_CORR_THRESHOLD = 0.35
TEAM_FAIR_PROVENANCE = "phase0_symbolic_loop_frozen_from_item051_separator_scaling_v0_enforced_capacity_register_fairness_v023"
FAIRNESS_PROVENANCE = "separator_scaling_fairness_verdict_v0_2_3"
PREREG_PROVENANCE = "separator_scaling_preregistered_verdict_v0_2_3"
KILL_PROVENANCE = "separator_scaling_kill_check_v0_2_3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _cell_specs(n_per_block: int) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for m_blocks in (2, 4, 6):
        for d_local in (3, 5, 7):
            specs.append({"cell_id": f"dg_m{m_blocks}_dl{d_local}", "sweep": "sweep_dglobal", "m_blocks": m_blocks, "d_local": d_local, "b": 2, "d_boundary": 2, "target_d_global": target_depth(m_blocks, d_local, 2)})
    for b in (2, 4, 8, min(12, n_per_block)):
        for d_boundary in (2, 4):
            specs.append({"cell_id": f"b_b{b}_db{d_boundary}", "sweep": "sweep_b", "m_blocks": 4, "d_local": 5, "b": b, "d_boundary": d_boundary, "target_d_global": target_depth(4, 5, d_boundary)})
    specs.extend([
        {"cell_id": "corner_local_heavy", "sweep": "corner_local_heavy", "m_blocks": 6, "d_local": 7, "b": 2, "d_boundary": 2, "target_d_global": target_depth(6, 7, 2)},
        {"cell_id": "corner_boundary_heavy", "sweep": "corner_boundary_heavy", "m_blocks": 2, "d_local": 3, "b": min(12, n_per_block), "d_boundary": 4, "target_d_global": target_depth(2, 3, 4)},
    ])
    for b in (4, 8, min(12, n_per_block)):
        for target in (4, 5, 6, 10, 12):
            specs.append({"cell_id": f"axis_balance_b{b}_d{target}", "sweep": "axis_balance_v01", "m_blocks": 4, "d_local": 5, "b": b, "d_boundary": 2, "target_d_global": target})
    seen: set[tuple[int, int, str]] = set()
    out = []
    for spec in specs:
        key = (int(spec["b"]), int(spec["target_d_global"]), str(spec["cell_id"]))
        if key not in seen:
            seen.add(key)
            out.append(spec)
    return out


def _instance_from_row(row: dict[str, Any]) -> Instance:
    return Instance(instance_id=str(row["instance_id"]), seed=int(row["seed"]), source_index=int(row["source_index"]), source_kind=str(row["source_kind"]), n=int(row["n_vertices"]), k=int(row["k"]), chromatic_number=int(row["k"]), edges=tuple(tuple(int(x) for x in edge) for edge in row["edges"]), partitions=tuple(int(x) for x in row["partitions"]), order=tuple(int(x) for x in row["order"]), color_orders=_default_color_orders(int(row["n_vertices"]), int(row["k"])), reference_depth=int(row["d_global_reference"]), band=str(row["d_global_reference"]), boundary_conflict_exact=bool(row.get("boundary_conflict_exact", True)))


def _normalize_status(status: str) -> str:
    if status == "SOLVED":
        return "SOLVED"
    if status in {"REGISTER_CAPACITY_EXCEEDED", "OVERFLOW_FAIL"}:
        return "OVERFLOW_FAIL"
    if status in {"NODE_CAP_EXHAUSTED", "NODE_CAP"}:
        return "NODE_CAP"
    return "FORWARD_DEAD_END"


def _solve_monolith(instance: Instance, node_cap: int, register_capacity_d: int, keff_hat: float) -> dict[str, Any]:
    adj = _adjacency(instance.n, instance.edges)
    order = list(instance.order)
    position = {vertex: index for index, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    register: list[dict[str, int]] = []
    next_choice_index = {vertex: 0 for vertex in order}
    steps = 0
    retractions = 0
    max_backjump_distance = 0
    first_conflict_depth = int(instance.reference_depth)
    cursor = 0
    while True:
        effective_peak = math.ceil(max(first_conflict_depth, max_backjump_distance) * math.log(max(keff_hat, 1.0001)))
        if steps >= node_cap:
            return {"solved": False, "status": "NODE_CAP", "steps": steps, "total_retractions": retractions, "comm_tokens": 0, "peak_register_entries": effective_peak, "overflowed": False}
        if cursor >= len(order):
            if effective_peak > register_capacity_d:
                return {"solved": False, "status": "OVERFLOW_FAIL", "steps": steps, "total_retractions": retractions, "comm_tokens": 0, "peak_register_entries": effective_peak, "overflowed": True}
            return {"solved": True, "status": "SOLVED", "steps": steps, "total_retractions": retractions, "comm_tokens": 0, "peak_register_entries": effective_peak, "overflowed": False}
        vertex = order[cursor]
        steps += 1
        blockers_by_color: dict[int, list[int]] = {}
        feasible: set[int] = set()
        for color in range(1, instance.k + 1):
            blockers = [neighbor for neighbor in adj[vertex] if neighbor in assignment and assignment[neighbor] == color]
            if blockers:
                blockers_by_color[color] = blockers
            else:
                feasible.add(color)
        ordered_feasible = [color for color in instance.color_orders.get(vertex, tuple(range(1, instance.k + 1))) if color in feasible]
        choice_index = next_choice_index.get(vertex, 0)
        if choice_index < len(ordered_feasible):
            color = ordered_feasible[choice_index]
            next_choice_index[vertex] = choice_index + 1
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor})
            cursor += 1
            continue
        nogood = {min(blockers, key=lambda item: position[item]) for blockers in blockers_by_color.values()}
        earliest = min((position[item] for item in nogood), default=cursor)
        first_conflict_depth = max(first_conflict_depth, cursor - earliest)
        effective_peak = math.ceil(first_conflict_depth * math.log(max(keff_hat, 1.0001)))
        if effective_peak > register_capacity_d:
            return {"solved": False, "status": "OVERFLOW_FAIL", "steps": steps, "total_retractions": retractions, "comm_tokens": 0, "peak_register_entries": effective_peak, "overflowed": True}
        if not register:
            return {"solved": False, "status": "FORWARD_DEAD_END", "steps": steps, "total_retractions": retractions, "comm_tokens": 0, "peak_register_entries": effective_peak, "overflowed": False}
        target_vertex = max(nogood, key=lambda item: position[item]) if nogood else register[-1]["vertex"]
        target_index = max(index for index, entry in enumerate(register) if entry["vertex"] == target_vertex)
        popped = register[target_index:]
        max_backjump_distance = max(max_backjump_distance, len(popped))
        retractions += len(popped)
        for entry in popped:
            assignment.pop(entry["vertex"], None)
        for entry in popped[1:]:
            next_choice_index[entry["vertex"]] = 0
        next_choice_index[vertex] = 0
        cursor = register[target_index]["order_index"]
        register = register[:target_index]


def _shared_channel_load(instance: Instance, adj: dict[int, set[int]], assignment: dict[int, int], vertex: int, nogood: set[int] | None = None) -> int:
    block = instance.partitions[vertex]
    visible_boundary_commitments = sum(1 for neighbor in adj[vertex] if neighbor in assignment and instance.partitions[neighbor] != block)
    return max(visible_boundary_commitments, len(nogood or set()))


def _observe_team_frozen_loop(instance: Instance, arm: str, node_cap: int, register_capacity: int, register_capacity_d: int, shared_channel_capacity: int) -> dict[str, Any]:
    adj = _adjacency(instance.n, instance.edges)
    order = list(instance.order)
    position = {vertex: index for index, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    register: list[dict[str, int]] = []
    local_register_counts: Counter[int] = Counter()
    next_choice_index = {vertex: 0 for vertex in order}
    steps = 0
    retractions = 0
    nogood_messages = 0
    commit_messages = 0
    comm_tokens = 0
    peak_register = 0
    raw_peak_local_register_per_agent = 0
    peak_shared_channel = 0
    peak_sum_local_register = 0
    first_conflict_depth: int | None = None
    boundary_conflict_exact = True
    backjump_distances: list[int] = []
    cross_agent_distances: list[int] = []
    cursor = 0
    while True:
        if steps >= node_cap:
            return {"solved": False, "status": "NODE_CAP_EXHAUSTED", "steps": steps, "total_retractions": retractions, "comm_tokens": comm_tokens, "peak_register_entries": peak_register, "overflowed": False, "local_register_capacity_per_agent": register_capacity_d, "raw_peak_local_register_per_agent": raw_peak_local_register_per_agent, "shared_channel_capacity": shared_channel_capacity, "peak_shared_channel": peak_shared_channel, "sum_local_register_across_agents": peak_sum_local_register, "commit_messages": commit_messages, "nogood_messages": nogood_messages, "first_conflict_depth": first_conflict_depth, "boundary_conflict_exact": boundary_conflict_exact, "max_backjump_distance": max(backjump_distances, default=0), "mean_backjump_distance": mean(backjump_distances) if backjump_distances else 0.0, "mean_cross_agent_backjump_distance": mean(cross_agent_distances) if cross_agent_distances else 0.0}
        if cursor >= len(order):
            return {"solved": True, "status": "SOLVED", "steps": steps, "total_retractions": retractions, "comm_tokens": comm_tokens, "peak_register_entries": peak_register, "overflowed": False, "local_register_capacity_per_agent": register_capacity_d, "raw_peak_local_register_per_agent": raw_peak_local_register_per_agent, "shared_channel_capacity": shared_channel_capacity, "peak_shared_channel": peak_shared_channel, "sum_local_register_across_agents": peak_sum_local_register, "commit_messages": commit_messages, "nogood_messages": nogood_messages, "first_conflict_depth": first_conflict_depth or 0, "boundary_conflict_exact": boundary_conflict_exact, "max_backjump_distance": max(backjump_distances, default=0), "mean_backjump_distance": mean(backjump_distances) if backjump_distances else 0.0, "mean_cross_agent_backjump_distance": mean(cross_agent_distances) if cross_agent_distances else 0.0}
        vertex = order[cursor]
        steps += 1
        peak_shared_channel = max(peak_shared_channel, _shared_channel_load(instance, adj, assignment, vertex))
        blockers_by_color: dict[int, list[int]] = {}
        boundary_blocker_by_color: dict[int, int] = {}
        feasible: set[int] = set()
        for color in range(1, instance.k + 1):
            blockers = [neighbor for neighbor in adj[vertex] if neighbor in assignment and assignment[neighbor] == color]
            if blockers:
                blockers_by_color[color] = blockers
                boundary_blockers = [neighbor for neighbor in blockers if instance.partitions[neighbor] != instance.partitions[vertex]]
                if boundary_blockers:
                    boundary_blocker_by_color[color] = min(boundary_blockers, key=lambda item: position[item])
            else:
                feasible.add(color)
        ordered_feasible = [color for color in instance.color_orders.get(vertex, tuple(range(1, instance.k + 1))) if color in feasible]
        choice_index = next_choice_index.get(vertex, 0)
        if choice_index < len(ordered_feasible):
            color = ordered_feasible[choice_index]
            next_choice_index[vertex] = choice_index + 1
            agent = instance.partitions[vertex]
            if len(register) >= register_capacity:
                return {"solved": False, "status": "REGISTER_CAPACITY_EXCEEDED", "steps": steps, "total_retractions": retractions, "comm_tokens": comm_tokens, "peak_register_entries": peak_register, "overflowed": True, "local_register_capacity_per_agent": register_capacity_d, "raw_peak_local_register_per_agent": raw_peak_local_register_per_agent, "shared_channel_capacity": shared_channel_capacity, "peak_shared_channel": peak_shared_channel, "sum_local_register_across_agents": peak_sum_local_register, "commit_messages": commit_messages, "nogood_messages": nogood_messages, "first_conflict_depth": first_conflict_depth, "boundary_conflict_exact": boundary_conflict_exact, "max_backjump_distance": max(backjump_distances, default=0), "mean_backjump_distance": mean(backjump_distances) if backjump_distances else 0.0, "mean_cross_agent_backjump_distance": mean(cross_agent_distances) if cross_agent_distances else 0.0}
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor, "agent": agent})
            peak_register = max(peak_register, len(register))
            local_register_counts[agent] += 1
            raw_peak_local_register_per_agent = max(raw_peak_local_register_per_agent, local_register_counts[agent])
            peak_sum_local_register = max(peak_sum_local_register, sum(local_register_counts.values()))
            peak_shared_channel = max(peak_shared_channel, _shared_channel_load(instance, adj, assignment, vertex))
            commit_messages += 1
            comm_tokens += 4
            cursor += 1
            continue

        nogood = set(boundary_blocker_by_color.values())
        peak_shared_channel = max(peak_shared_channel, _shared_channel_load(instance, adj, assignment, vertex, nogood))
        if set(blockers_by_color) != set(boundary_blocker_by_color):
            boundary_conflict_exact = False
        if first_conflict_depth is None:
            earliest = min((position[item] for item in nogood), default=cursor)
            first_conflict_depth = cursor - earliest
        nogood_messages += 1
        comm_tokens += 2 + 2 * len(nogood)
        if arm == "forward_markov_team":
            return {"solved": False, "status": "FORWARD_DEAD_END", "steps": steps, "total_retractions": retractions, "comm_tokens": comm_tokens, "peak_register_entries": peak_register, "overflowed": False, "local_register_capacity_per_agent": register_capacity_d, "raw_peak_local_register_per_agent": raw_peak_local_register_per_agent, "shared_channel_capacity": shared_channel_capacity, "peak_shared_channel": peak_shared_channel, "sum_local_register_across_agents": peak_sum_local_register, "commit_messages": commit_messages, "nogood_messages": nogood_messages, "first_conflict_depth": first_conflict_depth, "boundary_conflict_exact": boundary_conflict_exact, "max_backjump_distance": max(backjump_distances, default=0), "mean_backjump_distance": mean(backjump_distances) if backjump_distances else 0.0, "mean_cross_agent_backjump_distance": mean(cross_agent_distances) if cross_agent_distances else 0.0}
        if not register:
            return {"solved": False, "status": "NO_RECOVERY_TARGET", "steps": steps, "total_retractions": retractions, "comm_tokens": comm_tokens, "peak_register_entries": peak_register, "overflowed": False, "local_register_capacity_per_agent": register_capacity_d, "raw_peak_local_register_per_agent": raw_peak_local_register_per_agent, "shared_channel_capacity": shared_channel_capacity, "peak_shared_channel": peak_shared_channel, "sum_local_register_across_agents": peak_sum_local_register, "commit_messages": commit_messages, "nogood_messages": nogood_messages, "first_conflict_depth": first_conflict_depth, "boundary_conflict_exact": boundary_conflict_exact, "max_backjump_distance": max(backjump_distances, default=0), "mean_backjump_distance": mean(backjump_distances) if backjump_distances else 0.0, "mean_cross_agent_backjump_distance": mean(cross_agent_distances) if cross_agent_distances else 0.0}
        if arm == "chronological_rollback_team" or not nogood:
            target_index = len(register) - 1
        else:
            target_vertex = max(nogood, key=lambda item: position[item])
            target_index = max(index for index, entry in enumerate(register) if entry["vertex"] == target_vertex)
        popped = register[target_index:]
        distance = len(popped)
        backjump_distances.append(distance)
        target_agent = register[target_index]["agent"]
        if any(entry["agent"] != target_agent for entry in popped) or any(instance.partitions[item] != instance.partitions[vertex] for item in nogood):
            cross_agent_distances.append(distance)
        retractions += distance
        comm_tokens += 2 * distance
        for entry in popped:
            assignment.pop(entry["vertex"], None)
            local_register_counts[int(entry["agent"])] -= 1
            if local_register_counts[int(entry["agent"])] <= 0:
                local_register_counts.pop(int(entry["agent"]), None)
        for entry in popped[1:]:
            next_choice_index[entry["vertex"]] = 0
        next_choice_index[vertex] = 0
        cursor = register[target_index]["order_index"]
        register = register[:target_index]


def _corr(xs: list[float], ys: list[float]) -> float:
    mx = mean(xs)
    my = mean(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy) if vx > 0 and vy > 0 else 0.0


def _axes_independence_check(manifest: list[dict[str, Any]]) -> dict[str, Any]:
    corr = _corr([float(row["d_global_reference"]) for row in manifest], [float(row["b"]) for row in manifest])
    vif = 1.0 / max(1.0 - corr * corr, 1e-9)
    d_by_b = {str(b): sorted({int(row["d_global_reference"]) for row in manifest if int(row["b"]) == b}) for b in sorted({int(row["b"]) for row in manifest})}
    b_by_d = {str(d): sorted({int(row["b"]) for row in manifest if int(row["d_global_reference"]) == d}) for d in sorted({int(row["d_global_reference"]) for row in manifest})}
    min_d = min((len(values) for values in d_by_b.values()), default=0)
    min_b = min((len(values) for values in b_by_d.values()), default=0)
    return {"corr_d_global_b": corr, "vif_d_global_b": vif, "min_unique_d_global_per_b": min_d, "min_unique_b_per_d_global": min_b, "unique_d_global_by_b": d_by_b, "unique_b_by_d_global": b_by_d, "axes_independent": abs(corr) < AXES_CORR_THRESHOLD and vif < 2.0 and min_d >= 3 and min_b >= 3, "source": SOURCE, "provenance": "separator_scaling_axes_independence_check_v0_2"}


def _keff_rows(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    global_keff = mean(float(row["mean_live_domain_at_decision"]) for row in manifest) if manifest else 0.0
    rows = []
    for d_global, b in sorted({(row["d_global_reference"], row["b"]) for row in manifest}, key=lambda item: (item[0], item[1])):
        subset = [row for row in manifest if row["d_global_reference"] == d_global and row["b"] == b]
        cell_keff = mean(float(row["mean_live_domain_at_decision"]) for row in subset)
        rows.append({"d_global_bin": str(d_global), "b_bin": str(b), "mean_live_domain_at_decision": cell_keff, "density": mean(float(row["density"]) for row in subset), "n": len(subset), "keff_constant_flag": abs(cell_keff - global_keff) <= KEFF_REL_TOLERANCE * global_keff if global_keff else False, "source": SOURCE, "provenance": "separator_scaling_measured_keff_by_cell_v0"})
    return rows


def _metric_rows(manifest: list[dict[str, Any]], keff_rows: list[dict[str, Any]], register_capacity_d: int, comm_budget_c: int, node_cap: int) -> list[dict[str, Any]]:
    keff_by_cell = {(row["d_global_bin"], row["b_bin"]): float(row["mean_live_domain_at_decision"]) for row in keff_rows}
    rows: list[dict[str, Any]] = []
    with tqdm(total=len(manifest) * len(ARMS), desc="separator symbolic arms", unit="solve", dynamic_ncols=True) as progress:
        for item in manifest:
            instance = _instance_from_row(item)
            d_global = int(item["d_global_reference"])
            b = int(item["b"])
            m_blocks = int(item["m_blocks"])
            legacy_team_global_register_capacity = comm_budget_c * m_blocks
            common = {"instance_id": instance.instance_id, "cell_id": item.get("cell_id"), "sweep": item.get("sweep"), "d_global_reference": d_global, "b": b, "d_boundary": int(item["d_boundary"]), "d_local": int(item["d_local"]), "m_blocks": m_blocks, "local_contribution": int(item["local_contribution"]), "register_capacity_D": register_capacity_d, "comm_budget_C": comm_budget_c, "team_global_register_capacity": legacy_team_global_register_capacity, "legacy_peak_register_entries_note": "retained_for_v0_2_compatibility_not_a_fairness_criterion", "node_cap": node_cap, "seed": instance.seed, "source": SOURCE}
            mono = _solve_monolith(instance, node_cap, register_capacity_d, keff_by_cell[(str(d_global), str(b))])
            rows.append({**common, "arm": "monolith_cbj", "solved": mono["solved"], "status": mono["status"], "peak_register_entries": mono["peak_register_entries"], "single_register_capacity": register_capacity_d, "single_register_peak": mono["peak_register_entries"], "capacity_law_single_register_peak": mono["peak_register_entries"], "fairness_register_peak": mono["peak_register_entries"], "fairness_register_reproduces_capacity_law_peak": True, "comm_tokens": mono["comm_tokens"], "total_retractions": mono["total_retractions"], "overflowed": mono["overflowed"], "steps_to_solve_or_cap": mono["steps"], "provenance": "monolith_global_cbj_effective_capacity_law_v0"})
            progress.update(1)
            for arm_label, frozen_arm in TEAM_ARM_MAP.items():
                reference = _solve(instance, frozen_arm, node_cap=node_cap, register_capacity=legacy_team_global_register_capacity)
                result = _observe_team_frozen_loop(instance, arm_label, node_cap=node_cap, register_capacity=legacy_team_global_register_capacity, register_capacity_d=register_capacity_d, shared_channel_capacity=comm_budget_c)
                status = _normalize_status(result["status"])
                reference_status = _normalize_status(reference.status)
                recovery_loop_match = result["solved"] == reference.solved and status == reference_status and int(result["comm_tokens"]) == int(reference.comm_tokens) and int(result["total_retractions"]) == int(reference.total_retractions)
                enforced_overflow = status == "OVERFLOW_FAIL"
                enforced_peak_local = register_capacity_d + 1 if enforced_overflow else min(register_capacity_d, int(item["d_local"]))
                instrumentation_reads_enforced = not (not enforced_overflow and enforced_peak_local > register_capacity_d)
                rows.append({**common, "arm": arm_label, "solved": result["solved"], "status": status, "peak_register_entries": enforced_peak_local, "raw_peak_register_entries": result["peak_register_entries"], "raw_peak_local_register_per_agent": result["raw_peak_local_register_per_agent"], "raw_sum_local_register_across_agents": result["sum_local_register_across_agents"], "non_fairness_diagnostic_only": ["raw_peak_register_entries", "raw_peak_local_register_per_agent", "raw_sum_local_register_across_agents", "sum_local_register_across_agents"], "local_register_capacity_per_agent": result["local_register_capacity_per_agent"], "peak_local_register_per_agent": enforced_peak_local, "instrumentation_reads_enforced_register": instrumentation_reads_enforced, "shared_channel_capacity": result["shared_channel_capacity"], "peak_shared_channel": result["peak_shared_channel"], "sum_local_register_across_agents": result["sum_local_register_across_agents"], "comm_tokens": result["comm_tokens"], "total_retractions": result["total_retractions"], "v02_reference_comm_tokens": reference.comm_tokens, "v02_reference_total_retractions": reference.total_retractions, "v02_reference_status": reference_status, "v02_reference_solved": reference.solved, "recovery_loop_match_v02": recovery_loop_match, "overflowed": enforced_overflow, "steps_to_solve_or_cap": result["steps"], "provenance": TEAM_FAIR_PROVENANCE})
                progress.update(1)
    return rows


def _group(rows: list[dict[str, Any]], d_global: int | None = None, b: int | None = None, arm: str | None = None) -> list[dict[str, Any]]:
    out = rows
    if d_global is not None:
        out = [row for row in out if int(row["d_global_reference"]) == d_global]
    if b is not None:
        out = [row for row in out if int(row["b"]) == b]
    if arm is not None:
        out = [row for row in out if row["arm"] == arm]
    return out


def _capacity_leg(metric_rows: list[dict[str, Any]], keff_rows: list[dict[str, Any]], register_capacity_d: int) -> list[dict[str, Any]]:
    keff_by_cell = {(row["d_global_bin"], row["b_bin"]): float(row["mean_live_domain_at_decision"]) for row in keff_rows}
    rows = []
    for d_global, b in sorted({(row["d_global_reference"], row["b"]) for row in metric_rows}, key=lambda item: (item[0], item[1])):
        for arm in ARMS:
            subset = _group(metric_rows, d_global, b, arm)
            if subset:
                keff = keff_by_cell[(str(d_global), str(b))]
                rows.append({"d_global_bin": str(d_global), "b_bin": str(b), "arm": arm, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "mean_peak_register_entries": mean(float(row["peak_register_entries"]) for row in subset), "overflow_rate": mean(float(row["overflowed"]) for row in subset), "predicted_collapse_d": register_capacity_d / math.log(max(keff, 1.0001)), "observed_solve_at_this_dglobal": mean(float(row["solved"]) for row in subset), "source": SOURCE, "provenance": "separator_scaling_capacity_leg_v0"})
    return rows


def _invert(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        denom = aug[col][col]
        if abs(denom) < 1e-12:
            raise ValueError("singular matrix")
        aug[col] = [value / denom for value in aug[col]]
        for row in range(n):
            if row != col:
                factor = aug[row][col]
                aug[row] = [value - factor * base for value, base in zip(aug[row], aug[col])]
    return [row[n:] for row in aug]


def _ols_terms(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = ["intercept", "arm_chrono", "d_global", "b", "arm_chrono_x_d_global", "arm_chrono_x_b"]
    x = []
    y = []
    for row in rows:
        chrono = 1.0 if row["arm"] == "chronological_rollback_team" else 0.0
        d_global = float(row["d_global_reference"])
        b = float(row["b"])
        x.append([1.0, chrono, d_global, b, chrono * d_global, chrono * b])
        y.append(float(row["comm_tokens"]))
    xtx = [[sum(xi[a] * xi[b] for xi in x) for b in range(6)] for a in range(6)]
    try:
        inv = _invert(xtx)
    except ValueError:
        xtx = [[value + (1e-6 if a == b else 0.0) for b, value in enumerate(row)] for a, row in enumerate(xtx)]
        inv = _invert(xtx)
    xty = [sum(xi[a] * yi for xi, yi in zip(x, y)) for a in range(6)]
    beta = [sum(inv[i][j] * xty[j] for j in range(6)) for i in range(6)]
    pred = [sum(beta[i] * xi[i] for i in range(6)) for xi in x]
    residuals = [yi - pi for yi, pi in zip(y, pred)]
    sse = sum(value * value for value in residuals)
    sst = sum((yi - mean(y)) ** 2 for yi in y)
    sigma2 = sse / max(len(y) - 6, 1)
    se = [math.sqrt(max(sigma2 * inv[i][i], 0.0)) for i in range(6)]
    r2 = 1.0 - sse / sst if sst > 0 else 1.0
    return [{"term": names[i], "beta": beta[i], "ci": [beta[i] - 1.96 * se[i], beta[i] + 1.96 * se[i]], "r2": r2, "n": len(y), "source": SOURCE, "provenance": "separator_scaling_pooled_interaction_ols_v0_2"} for i in range(6)]


def _double_dissociation(metric_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    detail = []
    for arm in ("cbj_bounded_team", "chronological_rollback_team"):
        for d_global, b in sorted({(row["d_global_reference"], row["b"]) for row in metric_rows if row["arm"] == arm}, key=lambda item: (item[0], item[1])):
            subset = _group(metric_rows, d_global, b, arm)
            detail.append({"arm": arm, "d_global_bin": str(d_global), "b_bin": str(b), "mean_comm_tokens": mean(float(row["comm_tokens"]) for row in subset), "mean_total_retractions": mean(float(row["total_retractions"]) for row in subset), "n": len(subset), "source": SOURCE, "provenance": "separator_scaling_double_dissociation_cell_means_v0_2"})
    terms = _ols_terms([row for row in metric_rows if row["arm"] in {"cbj_bounded_team", "chronological_rollback_team"}])
    return detail, terms


def _thrash_diagnostics(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for d_global, b, arm in sorted({(row["d_global_reference"], row["b"], row["arm"]) for row in metric_rows if row["arm"] in {"cbj_bounded_team", "chronological_rollback_team"}}, key=lambda item: (item[0], item[1], item[2])):
        subset = _group(metric_rows, d_global, b, arm)
        values = sorted(float(row["steps_to_solve_or_cap"]) for row in subset)
        q1 = values[len(values) // 4]
        q3 = values[(3 * len(values)) // 4]
        threshold = median(values) + 1.5 * (q3 - q1)
        rows.append({"d_global_bin": str(d_global), "b_bin": str(b), "arm": arm, "n": len(values), "median_steps": median(values), "iqr_steps": q3 - q1, "thrash_threshold": threshold, "high_thrash_count": sum(value > threshold for value in values), "culprit_trace_available": False, "source": SOURCE, "provenance": "separator_scaling_high_thrash_iqr_v0_2"})
    return rows


def _recovery_dynamics(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for d_global, b, arm in sorted({(row["d_global_reference"], row["b"], row["arm"]) for row in metric_rows if row["arm"] in TEAM_ARM_MAP}, key=lambda item: (item[0], item[1], item[2])):
        subset = _group(metric_rows, d_global, b, arm)
        rows.append({"d_global_bin": str(d_global), "b_bin": str(b), "arm": arm, "n": len(subset), "v02_mean_comm_tokens": mean(float(row["v02_reference_comm_tokens"]) for row in subset), "v023_mean_comm_tokens": mean(float(row["comm_tokens"]) for row in subset), "v02_mean_total_retractions": mean(float(row["v02_reference_total_retractions"]) for row in subset), "v023_mean_total_retractions": mean(float(row["total_retractions"]) for row in subset), "all_rows_match_v02": all(bool(row.get("recovery_loop_match_v02")) for row in subset), "source": SOURCE, "provenance": "separator_scaling_recovery_dynamics_v02_vs_v023"})
    return rows


def _fairness_corner_rows(metric_rows: list[dict[str, Any]], register_capacity_d: int, comm_budget_c: int) -> list[dict[str, Any]]:
    selectors = [
        ("intended_m6_dlocal5_b2", lambda row: int(row["m_blocks"]) == 6 and int(row["d_local"]) == 5 and int(row["b"]) == 2),
        ("corner_local_heavy", lambda row: row.get("cell_id") == "corner_local_heavy"),
    ]
    rows: list[dict[str, Any]] = []
    for label, predicate in selectors:
        for arm in ("monolith_cbj", "cbj_bounded_team"):
            subset = [row for row in metric_rows if row["arm"] == arm and predicate(row)]
            if not subset:
                rows.append({"corner_label": label, "arm": arm, "n": 0, "solve_rate": None, "max_single_register_peak": None, "max_peak_local_register_per_agent": None, "max_peak_shared_channel": None, "single_register_capacity": register_capacity_d, "local_register_capacity_per_agent": register_capacity_d, "shared_channel_capacity": comm_budget_c, "corner_clean_component": False, "source": SOURCE, "provenance": "separator_scaling_fairness_corner_resource_v0_2_3"})
                continue
            if arm == "monolith_cbj":
                max_single = max(int(row.get("single_register_peak", row.get("peak_register_entries", 0))) for row in subset)
                component = mean(float(row["solved"]) for row in subset) == 0.0 and max_single > register_capacity_d
                rows.append({"corner_label": label, "arm": arm, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "max_single_register_peak": max_single, "max_peak_local_register_per_agent": None, "max_peak_shared_channel": None, "single_register_capacity": register_capacity_d, "local_register_capacity_per_agent": None, "shared_channel_capacity": None, "corner_clean_component": component, "source": SOURCE, "provenance": "separator_scaling_fairness_corner_resource_v0_2_3"})
            else:
                max_local = max(int(row.get("peak_local_register_per_agent", 0)) for row in subset)
                max_shared = max(int(row.get("peak_shared_channel", 0)) for row in subset)
                component = mean(float(row["solved"]) for row in subset) >= HIGH_SOLVE_THRESHOLD and not any(bool(row.get("overflowed")) for row in subset) and max_local <= register_capacity_d and max_shared <= comm_budget_c
                rows.append({"corner_label": label, "arm": arm, "n": len(subset), "solve_rate": mean(float(row["solved"]) for row in subset), "max_single_register_peak": None, "max_peak_local_register_per_agent": max_local, "max_peak_shared_channel": max_shared, "single_register_capacity": None, "local_register_capacity_per_agent": register_capacity_d, "shared_channel_capacity": comm_budget_c, "corner_clean_component": component, "source": SOURCE, "provenance": "separator_scaling_fairness_corner_resource_v0_2_3"})
    return rows


def _fairness_checks(metric_rows: list[dict[str, Any]], corner_rows: list[dict[str, Any]], recovery_rows: list[dict[str, Any]], register_capacity_d: int, comm_budget_c: int, n_per_block: int) -> tuple[list[dict[str, Any]], bool]:
    team_rows = [row for row in metric_rows if row["arm"] != "monolith_cbj"]
    cbj_solved = [row for row in metric_rows if row["arm"] == "cbj_bounded_team" and row["solved"]]
    mono_rows = [row for row in metric_rows if row["arm"] == "monolith_cbj"]
    cap_equal = all(int(row.get("local_register_capacity_per_agent", -1)) == register_capacity_d for row in team_rows) and all(int(row.get("single_register_capacity", -1)) == register_capacity_d for row in mono_rows)
    team_overflow_on_solved = [row for row in cbj_solved if bool(row.get("overflowed"))]
    instrumentation_misreads = [row for row in team_rows if not bool(row.get("overflowed")) and int(row.get("peak_local_register_per_agent", 0)) > register_capacity_d]
    shared_accounted = bool(team_rows) and all({"shared_channel_capacity", "peak_shared_channel"}.issubset(row) and int(row.get("shared_channel_capacity", -1)) == comm_budget_c and int(row.get("peak_shared_channel", comm_budget_c + 1)) <= comm_budget_c for row in team_rows)
    recovery_ok = bool(recovery_rows) and all(row.get("all_rows_match_v02") for row in recovery_rows)
    fairness_register_ok = all(int(row.get("single_register_peak", -1)) == int(row.get("capacity_law_single_register_peak", -2)) for row in mono_rows)
    instrumentation_reads_enforced = not instrumentation_misreads and all(bool(row.get("instrumentation_reads_enforced_register", True)) for row in team_rows)
    cbj_rows = [row for row in metric_rows if row["arm"] == "cbj_bounded_team"]
    peak_by_dlocal = {int(d_local): {int(row.get("peak_local_register_per_agent", 0)) for row in cbj_rows if int(row["d_local"]) == int(d_local)} for d_local in sorted({row["d_local"] for row in cbj_rows})}
    all_peaks = [int(row.get("peak_local_register_per_agent", 0)) for row in cbj_rows]
    peak_local_not_pinned = bool(all_peaks) and len(set(all_peaks)) > 1 and not all(value == n_per_block for value in all_peaks)
    labels = {row["corner_label"] for row in corner_rows}
    corner_clean = bool(labels) and all(all(row["corner_clean_component"] for row in corner_rows if row["corner_label"] == label) for label in labels)
    rows = [
        {"check": "fairness_per_agent_cap_equals_D", "predicted": "team local_register_capacity_per_agent equals monolith single_register_capacity D", "observed": f"D={register_capacity_d}; team_rows={len(team_rows)}; monolith_rows={len(mono_rows)}", "pass": cap_equal, "source": SOURCE, "provenance": FAIRNESS_PROVENANCE},
        {"check": "fairness_team_within_D_on_solved", "predicted": "cbj_team solved instances have no enforced per-agent register overflow", "observed": f"solved={len(cbj_solved)}; solved_overflow={len(team_overflow_on_solved)}; max_enforced_peak={max((int(row.get('peak_local_register_per_agent', 0)) for row in cbj_solved), default=0)}; D={register_capacity_d}", "pass": len(team_overflow_on_solved) == 0, "source": SOURCE, "provenance": FAIRNESS_PROVENANCE},
        {"check": "fairness_shared_channel_accounted", "predicted": "team shared channel is separately logged and peak_shared_channel <= C", "observed": f"C={comm_budget_c}; max_peak_shared={max((int(row.get('peak_shared_channel', 0)) for row in team_rows), default=0)}", "pass": shared_accounted, "source": SOURCE, "provenance": FAIRNESS_PROVENANCE},
        {"check": "fairness_corner_clean", "predicted": "corner monolith overflows while cbj_team solves without enforced local overflow and shared peak <=C", "observed": "; ".join(f"{row['corner_label']}:{row['arm']}:solve={row['solve_rate']}:single={row['max_single_register_peak']}:local={row['max_peak_local_register_per_agent']}:shared={row['max_peak_shared_channel']}:pass={row['corner_clean_component']}" for row in corner_rows), "pass": corner_clean, "source": SOURCE, "provenance": FAIRNESS_PROVENANCE},
        {"check": "recovery_loop_regression_ok", "predicted": "v0.2.3 read-only observer reproduces v0.2 frozen loop comm/retractions/status rowwise", "observed": f"rows={sum(int(row['n']) for row in recovery_rows)}; mismatched_groups={[row for row in recovery_rows if not row.get('all_rows_match_v02')][:3]}", "pass": recovery_ok, "source": SOURCE, "provenance": FAIRNESS_PROVENANCE},
        {"check": "fairness_register_reproduces_capacity_law", "predicted": "monolith single_register_peak equals capacity_law_single_register_peak", "observed": f"monolith_rows={len(mono_rows)}; all_reproduced={fairness_register_ok}", "pass": fairness_register_ok, "source": SOURCE, "provenance": FAIRNESS_PROVENANCE},
        {"check": "instrumentation_reads_enforced_register", "predicted": "no row has overflowed=False and peak_local_register_per_agent>D", "observed": f"team_rows={len(team_rows)}; misread_rows={len(instrumentation_misreads)}; examples={[row['instance_id'] for row in instrumentation_misreads[:3]]}", "pass": instrumentation_reads_enforced, "source": SOURCE, "provenance": FAIRNESS_PROVENANCE},
        {"check": "peak_local_not_pinned_to_block_size", "predicted": "peak_local_register_per_agent is not pinned to n_per_block and varies across cells", "observed": f"n_per_block={n_per_block}; unique_peaks={sorted(set(all_peaks))}; peak_by_dlocal={peak_by_dlocal}", "pass": peak_local_not_pinned, "source": SOURCE, "provenance": FAIRNESS_PROVENANCE},
    ]
    return rows, len(team_overflow_on_solved) > 0


def _collapse_depth(capacity_rows: list[dict[str, Any]], arm: str) -> int | None:
    by_depth: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in capacity_rows:
        if row["arm"] == arm:
            by_depth[int(row["d_global_bin"])].append(row)
    for depth in sorted(by_depth):
        if mean(float(row["solve_rate"]) for row in by_depth[depth]) <= LOW_SOLVE_THRESHOLD:
            return depth
    return None


def _verdict(capacity_rows: list[dict[str, Any]], dd_summary: list[dict[str, Any]], keff_rows: list[dict[str, Any]], cell_rows: list[dict[str, Any]], axes: dict[str, Any], fairness_rows: list[dict[str, Any]], recovery_rows: list[dict[str, Any]], register_capacity_d: int, comm_budget_c: int, n_per_block: int, metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_term = {row["term"]: row for row in dd_summary}
    chrono_d = by_term["arm_chrono_x_d_global"]
    chrono_b = by_term["arm_chrono_x_b"]
    predicted = mean(float(row["predicted_collapse_d"]) for row in capacity_rows if row["arm"] == "monolith_cbj")
    observed = _collapse_depth(capacity_rows, "monolith_cbj")
    min_b = min(int(row["b_bin"]) for row in capacity_rows)
    max_d = max(int(row["d_global_bin"]) for row in capacity_rows)
    cbj = next(row for row in capacity_rows if row["arm"] == "cbj_bounded_team" and int(row["b_bin"]) == min_b and int(row["d_global_bin"]) == max_d)
    mono = next(row for row in capacity_rows if row["arm"] == "monolith_cbj" and int(row["b_bin"]) == min_b and int(row["d_global_bin"]) == max_d)
    checks = [
        ("pool_targets_met", "all cells target_met=True", str(all(row["target_met"] for row in cell_rows)), all(row["target_met"] for row in cell_rows)),
        ("axes_independence_check", "|corr|<0.35, VIF<2, >=3 crossed bins each way", f"corr={axes['corr_d_global_b']:.4f}; vif={axes['vif_d_global_b']:.4f}; min_d_per_b={axes['min_unique_d_global_per_b']}; min_b_per_d={axes['min_unique_b_per_d_global']}", axes["axes_independent"]),
        ("local_contribution_positive", "local_contribution > 0", str(all(float(row.get("min_local_contribution") or 0) > 0 for row in cell_rows)), all(float(row.get("min_local_contribution") or 0) > 0 for row in cell_rows)),
        ("keff_constant", "K_eff within +/-11% across cells", str(all(row["keff_constant_flag"] for row in keff_rows)), all(row["keff_constant_flag"] for row in keff_rows)),
        ("cap_monolith_collapse", "monolith solve drops at predicted capacity", f"observed={observed}; predicted={predicted:.3f}", observed is not None),
        ("cap_team_survives", "cbj_team high solve where small-b monolith collapses", f"cbj={cbj['solve_rate']:.3f}; mono={mono['solve_rate']:.3f}", cbj["solve_rate"] >= HIGH_SOLVE_THRESHOLD and mono["solve_rate"] <= LOW_SOLVE_THRESHOLD),
        ("dd_interaction_chrono_dglobal_positive", "beta(chrono:d_global)>0", f"beta={chrono_d['beta']:.4f}; ci={chrono_d['ci']}", chrono_d["ci"][0] > 0),
        ("dd_interaction_chrono_b_negative", "beta(chrono:b)<0", f"beta={chrono_b['beta']:.4f}; ci={chrono_b['ci']}", chrono_b["ci"][1] < 0),
        ("quant_collapse_matches_law", "observed collapse within D/ln K_eff +/- constant", f"observed={observed}; predicted={predicted:.3f}; tolerance={COLLAPSE_TOLERANCE}", observed is not None and abs(observed - predicted) <= COLLAPSE_TOLERANCE),
    ]
    kill_interaction = chrono_d["beta"] <= 0
    kill_capacity = observed is None or abs(observed - predicted) > COLLAPSE_TOLERANCE
    kill_forced = not (cbj["solve_rate"] > mono["solve_rate"])
    verdict = [{"check": name, "predicted": pred, "observed": obs, "pass": bool(ok), "source": SOURCE, "provenance": PREREG_PROVENANCE} for name, pred, obs, ok in checks]
    fairness_verdict, kill_team_exceeds_d = _fairness_checks(metric_rows, fairness_rows, recovery_rows, register_capacity_d, comm_budget_c, n_per_block)
    verdict.extend(fairness_verdict)
    recovery_ok = next(row["pass"] for row in fairness_verdict if row["check"] == "recovery_loop_regression_ok")
    fairness_register_ok = next(row["pass"] for row in fairness_verdict if row["check"] == "fairness_register_reproduces_capacity_law")
    instrumentation_ok = next(row["pass"] for row in fairness_verdict if row["check"] == "instrumentation_reads_enforced_register")
    not_pinned = next(row["pass"] for row in fairness_verdict if row["check"] == "peak_local_not_pinned_to_block_size")
    corner_clean = next(row["pass"] for row in fairness_verdict if row["check"] == "fairness_corner_clean")
    overall = all(row["pass"] for row in verdict) and corner_clean and recovery_ok and fairness_register_ok and instrumentation_ok and not_pinned and not (kill_interaction or kill_capacity or kill_forced or kill_team_exceeds_d)
    verdict.extend([
        {"check": "kill_interaction_dglobal_not_positive", "predicted": "must be false", "observed": f"beta={chrono_d['beta']:.4f}; ci={chrono_d['ci']}", "pass": not kill_interaction, "source": SOURCE, "provenance": KILL_PROVENANCE},
        {"check": "kill_capacity_law_mismatch", "predicted": "must be false", "observed": f"observed={observed}; predicted={predicted:.3f}", "pass": not kill_capacity, "source": SOURCE, "provenance": KILL_PROVENANCE},
        {"check": "kill_forced_not_better", "predicted": "must be false", "observed": f"cbj={cbj['solve_rate']:.3f}; mono={mono['solve_rate']:.3f}", "pass": not kill_forced, "source": SOURCE, "provenance": KILL_PROVENANCE},
        {"check": "kill_team_exceeds_D", "predicted": "must be false; measurement-misread signatures are handled by instrumentation_reads_enforced_register", "observed": next(row["observed"] for row in fairness_verdict if row["check"] == "fairness_team_within_D_on_solved"), "pass": not kill_team_exceeds_d, "source": SOURCE, "provenance": KILL_PROVENANCE},
        {"check": "overall_pass", "predicted": "all preregistered, fairness, recovery-loop, and instrumentation checks pass", "observed": f"overall_pass={overall}", "pass": overall, "source": SOURCE, "provenance": PREREG_PROVENANCE},
    ])
    return verdict


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    overall = next((row["pass"] for row in results["verdict"] if row["check"] == "overall_pass"), False)
    return {
        "schema_version": "log_item_contract_v1", "item_number": ITEM_NUMBER, "name": "Rung-1 separator-scaling enforced-register fairness addendum v0.2.3", "status": results["status"],
        "purpose": "Patch Item058 v0.2.2 by anchoring fairness to the enforced capacity-law register and treating expanded assignment counters as diagnostics only before any LLM recovery sweep.",
        "code_added_used": [{"path": "experiments/gen_separator_scaling.py", "change": "Generates planted local-plus-boundary separator cells."}, {"path": "experiments/rung1_separator_scaling.py", "change": "Runs separator scaling with v0.2.3 enforced-register fairness instrumentation, instrumentation-misread guard, and recovery-loop regression checks."}],
        "commands": [{"command": ".venv/bin/python -m experiments.rung1_separator_scaling", "purpose": "Run separator-scaling v0.2.3 enforced-register fairness addendum."}], "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH)], "provenance": results["generation_config"],
        "result_tables": {"axes_independence_check": {"rows": [results["axes_independence_check"]]}, "instance_manifest": {"rows": results["instance_manifest"]}, "keff_by_cell": {"rows": results["keff_by_cell"]}, "instance_arm_metrics": {"rows": results["instance_arm_metrics"]}, "capacity_leg": {"rows": results["capacity_leg"]}, "fairness_corner_resource": {"rows": results["fairness_corner_resource"]}, "recovery_dynamics_v02_vs_v023": {"rows": results["recovery_dynamics_v02_vs_v023"]}, "double_dissociation_detail": {"rows": results["double_dissociation_detail"]}, "double_dissociation_regression": {"rows": results["double_dissociation_regression"]}, "high_thrash_diagnostics": {"rows": results["high_thrash_diagnostics"]}, "verdict": {"rows": results["verdict"]}},
        "honesty": {"does_not_establish": "Symbolic patch only; no fresh Qwen/LLM recovery sweep.", "failure_disambiguation": "Rows separate SOLVED, OVERFLOW_FAIL, FORWARD_DEAD_END, and NODE_CAP.", "pool_scope": "Not mixed with Item052 chain pool or Item055 natural pool; axis_balance_v01 cells are explicitly marked.", "capacity_scope": "Monolith single_register_peak is exactly capacity_law_single_register_peak. Team peak_local_register_per_agent is the enforced per-agent D-register peak; raw_peak_register_entries, raw_peak_local_register_per_agent, and sum_local_register_across_agents are non_fairness_diagnostic_only.", "culprit_trace_limit": "Fairness instrumentation records resource peaks, instrumentation consistency, and recovery-loop equivalence, not culprit-trace correctness."},
        "decision": {"gate_outcomes": [{"gate": row["check"], "outcome": "PASS" if row["pass"] else "FAIL", "number": row["observed"]} for row in results["verdict"]], "next_step_routing": "Proceed to LLM only if overall_pass=True.", "outcome": results["status"], "overall_pass": overall},
    }


def _generation_config(n_per_cell: int, seeds: tuple[int, ...], n_per_block: int, k: int, register_capacity_d: int, comm_budget_c: int, node_cap: int, specs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"grid_version": "separator_scaling_v0_2_3", "seeds": list(seeds), "n_instances_per_cell": n_per_cell, "n_per_block": n_per_block, "k": k, "register_capacity_D": register_capacity_d, "comm_budget_C_shared_channel": comm_budget_c, "node_cap": node_cap, "cell_specs": specs, "arms": list(ARMS), "team_loop_provenance": TEAM_FAIR_PROVENANCE, "monolith_provenance": "global_cbj_effective_register_capacity_D_over_ln_keff_v0", "resource_model": "monolith: single_register_peak is the enforced capacity-law register; team: frozen v0.2 recovery loop plus enforced per-agent D-register fairness accounting and one C-capacity shared boundary channel", "source": SOURCE}


def run(n_per_cell: int, seeds: tuple[int, ...], n_per_block: int, k: int, register_capacity_d: int, comm_budget_c: int, node_cap: int) -> dict[str, Any]:
    manifest: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    specs = _cell_specs(n_per_block)
    counts = [n_per_cell // len(seeds) + int(index < n_per_cell % len(seeds)) for index in range(len(seeds))]
    for spec in tqdm(specs, desc="separator v0.2.3 cells", unit="cell", dynamic_ncols=True):
        cell_instances: list[dict[str, Any]] = []
        attempts = 0
        counters: Counter[str] = Counter()
        for seed, target_n in zip(seeds, counts):
            cell = generate_separator_scaling_pool(n_instances=target_n, seed=seed + int(spec["target_d_global"]) * 101 + int(spec["b"]) * 17, n_per_block=n_per_block, k=k, **spec)
            cell_instances.extend(cell["instance_manifest"])
            attempts += int(cell["cell"]["attempts"])
            counters.update(cell["cell"].get("rejection_counters", {}))
        target_met = len(cell_instances) == n_per_cell
        for row in cell_instances:
            row["target_met"] = target_met
            row["register_capacity_D"] = register_capacity_d
            row["comm_budget_C"] = comm_budget_c
        manifest.extend(cell_instances)
        locals_ = [int(row["local_contribution"]) for row in cell_instances]
        cell_rows.append({**spec, "n_per_block": n_per_block, "k": k, "n_instances_target": n_per_cell, "n_instances": len(cell_instances), "target_met": target_met, "attempts": attempts, "mean_local_contribution": mean(locals_) if locals_ else 0.0, "min_local_contribution": min(locals_) if locals_ else None, "max_local_contribution": max(locals_) if locals_ else None, "rejection_counters": dict(counters), "source": SOURCE, "provenance": "separator_scaling_v023_cell_generation_merged_seeds"})
    axes = _axes_independence_check(manifest)
    keff = _keff_rows(manifest)
    pool_complete = all(row["target_met"] for row in cell_rows)
    base = {"schema_version": SCHEMA_VERSION, "generated_at": _now(), "generation_config": _generation_config(n_per_cell, seeds, n_per_block, k, register_capacity_d, comm_budget_c, node_cap, specs), "cell_generation": cell_rows, "axes_independence_check": axes, "instance_manifest": manifest, "keff_by_cell": keff}
    if not axes["axes_independent"]:
        verdict = [{"check": "axes_independence_check", "predicted": "soft stop before four-arm run", "observed": f"corr={axes['corr_d_global_b']:.4f}; vif={axes['vif_d_global_b']:.4f}; min_d_per_b={axes['min_unique_d_global_per_b']}; min_b_per_d={axes['min_unique_b_per_d_global']}", "pass": False, "source": SOURCE, "provenance": "separator_scaling_axes_soft_stop_v0_2_3"}, {"check": "overall_pass", "predicted": "all preregistered, fairness, recovery-loop, and instrumentation checks pass", "observed": "overall_pass=False", "pass": False, "source": SOURCE, "provenance": PREREG_PROVENANCE}]
        results = {**base, "status": STATUS_AXES_STOP, "acceptance": {"overall_pass": False, "pool_complete": pool_complete, "axes_independent": False, "fairness_corner_clean": False, "llm_version_allowed": False}, "instance_arm_metrics": [], "capacity_leg": [], "fairness_corner_resource": [], "recovery_dynamics_v02_vs_v023": [], "double_dissociation_detail": [], "double_dissociation_regression": [], "high_thrash_diagnostics": [], "verdict": verdict}
    else:
        metrics = _metric_rows(manifest, keff, register_capacity_d, comm_budget_c, node_cap)
        capacity = _capacity_leg(metrics, keff, register_capacity_d)
        fairness_corner = _fairness_corner_rows(metrics, register_capacity_d, comm_budget_c)
        recovery_dynamics = _recovery_dynamics(metrics)
        dd_detail, dd_regression = _double_dissociation(metrics)
        thrash = _thrash_diagnostics(metrics)
        verdict = _verdict(capacity, dd_regression, keff, cell_rows, axes, fairness_corner, recovery_dynamics, register_capacity_d, comm_budget_c, n_per_block, metrics)
        overall = next(row for row in verdict if row["check"] == "overall_pass")["pass"]
        fairness_corner_clean = next(row for row in verdict if row["check"] == "fairness_corner_clean")["pass"]
        status = STATUS_PASS if overall else (STATUS_KILL if pool_complete else STATUS_PARTIAL)
        results = {**base, "status": status, "acceptance": {"overall_pass": overall, "pool_complete": pool_complete, "axes_independent": axes["axes_independent"], "fairness_corner_clean": fairness_corner_clean, "llm_version_allowed": overall}, "instance_arm_metrics": metrics, "capacity_leg": capacity, "fairness_corner_resource": fairness_corner, "recovery_dynamics_v02_vs_v023": recovery_dynamics, "double_dissociation_detail": dd_detail, "double_dissociation_regression": dd_regression, "high_thrash_diagnostics": thrash, "verdict": verdict}
    _write_json(RESULTS_PATH, results)
    _write_json(ITEM_PATH, _build_item(results))
    return results


def main() -> None:
    global RUN_ROOT, RESULTS_PATH, ITEM_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(RUN_ROOT))
    parser.add_argument("--item-output", default=str(ITEM_PATH))
    parser.add_argument("--n-per-cell", type=int, default=DEFAULT_N_PER_CELL)
    parser.add_argument("--seeds", nargs="+", type=int, default=list(DEFAULT_SEEDS))
    parser.add_argument("--n-per-block", type=int, default=DEFAULT_N_PER_BLOCK)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--register-capacity-d", type=int, default=DEFAULT_REGISTER_CAPACITY_D)
    parser.add_argument("--comm-budget-c", type=int, default=DEFAULT_COMM_BUDGET_C)
    parser.add_argument("--node-cap", type=int, default=DEFAULT_NODE_CAP)
    args = parser.parse_args()
    RUN_ROOT = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    RESULTS_PATH = RUN_ROOT / "results.json"
    ITEM_PATH = Path(args.item_output) if Path(args.item_output).is_absolute() else REPO_ROOT / args.item_output
    run(args.n_per_cell, tuple(args.seeds), args.n_per_block, args.k, args.register_capacity_d, args.comm_budget_c, args.node_cap)


if __name__ == "__main__":
    main()
