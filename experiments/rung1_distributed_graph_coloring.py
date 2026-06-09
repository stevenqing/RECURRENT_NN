"""Rung-1 distributed graph-coloring gate.

Phase 0 uses a symbolic graph-coloring operator so the only experimental
variable is recovery target selection: forward-only, chronological rollback, or
conflict-directed backjumping over the same bounded boundary register.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.metadata as importlib_metadata
import json
import math
from pathlib import Path
import random
from statistics import mean
from typing import Any, Literal

from reasoning_gym.algorithmic.graph_color import generate_graph_coloring_puzzle


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = REPO_ROOT / "results/rung1_distributed_graph_coloring"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_051_rung1_distributed_graph_coloring.json"

SOURCE = "autonomous_stage_a_run"
SEEDS = (42, 137)
BANDS = ("R0", "R1-2", "R3+")
ARMS = ("forward_markov_team", "chronological_rollback", "cbj_bounded")
N_AGENTS = 4
TARGET_PER_BAND = 64
TARGET_PER_SEED_BAND = TARGET_PER_BAND // len(SEEDS)
REGISTER_CAPACITY = 16
NODE_CAP = 120
REFERENCE_NODE_CAP = 600
R0_GYM_CONFIGS = ((10, 2, 0.08), (10, 2, 0.10), (12, 2, 0.10), (16, 4, 0.24))
SHALLOW_GYM_CONFIGS = ((8, 2, 0.20), (10, 2, 0.26), (10, 2, 0.34), (10, 2, 0.45), (12, 2, 0.14), (12, 2, 0.38))
DEEP_GYM_CONFIGS = ((16, 4, 0.38),)
MAX_GYM_ATTEMPTS_PER_SEED_BAND = 50000


@dataclass(frozen=True)
class Instance:
    instance_id: str
    seed: int
    source_index: int
    source_kind: str
    n: int
    k: int
    chromatic_number: int
    edges: tuple[tuple[int, int], ...]
    partitions: tuple[int, ...]
    order: tuple[int, ...]
    color_orders: dict[int, tuple[int, ...]]
    reference_depth: int
    band: str
    boundary_conflict_exact: bool


@dataclass(frozen=True)
class SolveResult:
    solved: bool
    status: str
    steps: int
    total_retractions: int
    nogood_messages: int
    boundary_commit_messages: int
    comm_tokens: int
    peak_register_entries: int
    overflow_entries: int
    max_backjump_distance: int
    mean_backjump_distance: float
    mean_cross_agent_backjump_distance: float
    first_conflict_depth: int | None
    boundary_conflict_exact: bool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _reasoning_gym_version() -> str:
    return importlib_metadata.version("reasoning-gym")


def _band(depth: int) -> str:
    if depth == 0:
        return "R0"
    if depth <= 2:
        return "R1-2"
    return "R3+"


def _partitions(n: int, m: int = N_AGENTS) -> tuple[int, ...]:
    return tuple(min(vertex * m // n, m - 1) for vertex in range(n))


def _adjacency(n: int, edges: tuple[tuple[int, int], ...]) -> dict[int, set[int]]:
    adj = {vertex: set() for vertex in range(n)}
    for u, v in edges:
        adj[u].add(v)
        adj[v].add(u)
    return adj


def _priority_mcv_order(n: int, edges: tuple[tuple[int, int], ...], partitions: tuple[int, ...]) -> tuple[int, ...]:
    degree = {vertex: 0 for vertex in range(n)}
    for u, v in edges:
        degree[u] += 1
        degree[v] += 1
    order: list[int] = []
    for agent in range(max(partitions) + 1):
        vertices = [vertex for vertex in range(n) if partitions[vertex] == agent]
        order.extend(sorted(vertices, key=lambda vertex: (-degree[vertex], vertex)))
    return tuple(order)


def _normalize_edges(edges: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted({tuple(sorted(edge)) for edge in edges if edge[0] != edge[1]}))


def _default_color_orders(n: int, k: int) -> dict[int, tuple[int, ...]]:
    return {vertex: tuple(range(1, k + 1)) for vertex in range(n)}


def _can_color_with_k(n: int, edges: tuple[tuple[int, int], ...], k: int) -> bool:
    adj = _adjacency(n, edges)
    order = sorted(range(n), key=lambda vertex: (-len(adj[vertex]), vertex))
    assignment: dict[int, int] = {}

    def rec(index: int) -> bool:
        if index == len(order):
            return True
        vertex = order[index]
        forbidden = {assignment[neighbor] for neighbor in adj[vertex] if neighbor in assignment}
        for color in range(1, k + 1):
            if color in forbidden:
                continue
            assignment[vertex] = color
            if rec(index + 1):
                return True
            assignment.pop(vertex, None)
        return False

    return rec(0)


def _chromatic_number(n: int, edges: tuple[tuple[int, int], ...], max_k: int) -> int:
    for k in range(1, max_k + 1):
        if _can_color_with_k(n, edges, k):
            return k
    return max_k + 1


def _solve(instance: Instance, arm: Literal["forward_markov_team", "chronological_rollback", "cbj_bounded"], node_cap: int = NODE_CAP, register_capacity: int = REGISTER_CAPACITY) -> SolveResult:
    adj = _adjacency(instance.n, instance.edges)
    order = list(instance.order)
    position = {vertex: index for index, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    register: list[dict[str, int]] = []
    next_choice_index = {vertex: 0 for vertex in order}
    steps = 0
    retractions = 0
    nogood_messages = 0
    commit_messages = 0
    comm_tokens = 0
    peak_register = 0
    overflow_entries = 0
    first_conflict_depth: int | None = None
    boundary_conflict_exact = True
    backjump_distances: list[int] = []
    cross_agent_distances: list[int] = []
    cursor = 0
    while True:
        if steps >= node_cap:
            return SolveResult(False, "NODE_CAP_EXHAUSTED", steps, retractions, nogood_messages, commit_messages, comm_tokens, peak_register, overflow_entries, max(backjump_distances, default=0), mean(backjump_distances) if backjump_distances else 0.0, mean(cross_agent_distances) if cross_agent_distances else 0.0, first_conflict_depth, boundary_conflict_exact)
        if cursor >= len(order):
            return SolveResult(True, "SOLVED", steps, retractions, nogood_messages, commit_messages, comm_tokens, peak_register, overflow_entries, max(backjump_distances, default=0), mean(backjump_distances) if backjump_distances else 0.0, mean(cross_agent_distances) if cross_agent_distances else 0.0, first_conflict_depth or 0, boundary_conflict_exact)
        vertex = order[cursor]
        steps += 1
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
            if len(register) >= register_capacity:
                overflow_entries += 1
                return SolveResult(False, "REGISTER_CAPACITY_EXCEEDED", steps, retractions, nogood_messages, commit_messages, comm_tokens, peak_register, overflow_entries, max(backjump_distances, default=0), mean(backjump_distances) if backjump_distances else 0.0, mean(cross_agent_distances) if cross_agent_distances else 0.0, first_conflict_depth, boundary_conflict_exact)
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor, "agent": instance.partitions[vertex]})
            commit_messages += 1
            comm_tokens += 4
            peak_register = max(peak_register, len(register))
            cursor += 1
            continue

        nogood = set(boundary_blocker_by_color.values())
        if set(blockers_by_color) != set(boundary_blocker_by_color):
            boundary_conflict_exact = False
        if first_conflict_depth is None:
            earliest = min((position[item] for item in nogood), default=cursor)
            first_conflict_depth = cursor - earliest
        nogood_messages += 1
        comm_tokens += 2 + 2 * len(nogood)
        if arm == "forward_markov_team":
            return SolveResult(False, "FORWARD_DEAD_END", steps, retractions, nogood_messages, commit_messages, comm_tokens, peak_register, overflow_entries, max(backjump_distances, default=0), mean(backjump_distances) if backjump_distances else 0.0, mean(cross_agent_distances) if cross_agent_distances else 0.0, first_conflict_depth, boundary_conflict_exact)
        if not register:
            return SolveResult(False, "NO_RECOVERY_TARGET", steps, retractions, nogood_messages, commit_messages, comm_tokens, peak_register, overflow_entries, max(backjump_distances, default=0), mean(backjump_distances) if backjump_distances else 0.0, mean(cross_agent_distances) if cross_agent_distances else 0.0, first_conflict_depth, boundary_conflict_exact)
        if arm == "chronological_rollback" or not nogood:
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
        for entry in popped[1:]:
            next_choice_index[entry["vertex"]] = 0
        next_choice_index[vertex] = 0
        cursor = register[target_index]["order_index"]
        register = register[:target_index]


def _reasoning_gym_edges(seed: int, source_index: int, n: int, k: int, edge_probability: float) -> tuple[tuple[int, int], ...]:
    generator_seed = seed * 1_000_003 + source_index * 97_003 + n * 10_007 + k * 1_009 + int(round(edge_probability * 10_000))
    puzzle = generate_graph_coloring_puzzle(
        rng=random.Random(generator_seed),
        num_vertices=n,
        edge_probability=edge_probability,
        num_colors=k,
    )
    vertices = puzzle["vertices"]
    if vertices != list(range(n)):
        raise ValueError(f"unexpected reasoning_gym graph_color vertices: {vertices!r}")
    return _normalize_edges([(int(u), int(v)) for u, v in puzzle["edges"]])


def _make_reasoning_gym_instance(seed: int, source_index: int, n: int, k: int, edge_probability: float) -> Instance | None:
    edges = _reasoning_gym_edges(seed, source_index, n, k, edge_probability)
    source_kind = f"reasoning_gym_graph_color_generator:n{n}_k{k}_p{edge_probability:.2f}"
    return _make_instance(seed, source_index, source_kind, n, k, edges)


def _make_instance(seed: int, source_index: int, source_kind: str, n: int, k: int, edges: tuple[tuple[int, int], ...], color_orders: dict[int, tuple[int, ...]] | None = None) -> Instance | None:
    partitions = _partitions(n)
    order = _priority_mcv_order(n, edges, partitions)
    orders = _default_color_orders(n, k)
    if color_orders:
        orders.update(color_orders)
    chromatic = _chromatic_number(n, edges, k)
    if chromatic not in {k, k - 1}:
        return None
    provisional = Instance(f"pending_{seed}_{source_index}", seed, source_index, source_kind, n, k, chromatic, edges, partitions, order, orders, 0, "R0", True)
    reference = _solve(provisional, "cbj_bounded", REFERENCE_NODE_CAP)
    if not reference.solved or not reference.boundary_conflict_exact:
        return None
    depth = int(reference.first_conflict_depth or 0)
    band = _band(depth)
    instance_id = f"rung1_s{seed}_{band}_{source_index:05d}"
    return Instance(instance_id, seed, source_index, source_kind, n, k, chromatic, edges, partitions, order, orders, depth, band, reference.boundary_conflict_exact)


def _fill_band_from_reasoning_gym(seed: int, band: str, configs: tuple[tuple[int, int, float], ...]) -> list[Instance]:
    rows: list[Instance] = []
    band_offset = {"R0": 0, "R1-2": 100000, "R3+": 200000}[band]
    attempt = 0
    while len(rows) < TARGET_PER_SEED_BAND and attempt < MAX_GYM_ATTEMPTS_PER_SEED_BAND:
        n, k, edge_probability = configs[attempt % len(configs)]
        source_index = band_offset + attempt
        instance = _make_reasoning_gym_instance(seed, source_index, n, k, edge_probability)
        if instance is not None and instance.band == band:
            rows.append(instance)
        attempt += 1
    if len(rows) < TARGET_PER_SEED_BAND:
        raise RuntimeError(f"could not fill {band} from reasoning_gym for seed={seed}: got={len(rows)} attempts={attempt}")
    return rows


def _generate_pool() -> list[Instance]:
    instances: list[Instance] = []
    for seed in SEEDS:
        by_band = {
            "R0": _fill_band_from_reasoning_gym(seed, "R0", R0_GYM_CONFIGS),
            "R1-2": _fill_band_from_reasoning_gym(seed, "R1-2", SHALLOW_GYM_CONFIGS),
            "R3+": _fill_band_from_reasoning_gym(seed, "R3+", DEEP_GYM_CONFIGS),
        }
        for band in BANDS:
            instances.extend(by_band[band])
    return instances


def _sign_test_p_less(diffs: list[float]) -> float | None:
    nonzero = [diff for diff in diffs if diff != 0]
    n = len(nonzero)
    if n == 0:
        return None
    successes = sum(diff < 0 for diff in nonzero)
    return sum(math.comb(n, i) for i in range(successes, n + 1)) / (2 ** n)


def _mcnemar_p(cbj: list[bool], chrono: list[bool]) -> float | None:
    cbj_only = sum(c and not h for c, h in zip(cbj, chrono))
    chrono_only = sum(h and not c for c, h in zip(cbj, chrono))
    n = cbj_only + chrono_only
    if n == 0:
        return None
    return sum(math.comb(n, i) for i in range(cbj_only, n + 1)) / (2 ** n)


def _row_for_instance(instance: Instance, arm: str, result: SolveResult) -> dict[str, Any]:
    return {
        "instance_id": instance.instance_id,
        "seed": instance.seed,
        "band": instance.band,
        "arm": arm,
        "solved": result.solved,
        "status": result.status,
        "steps_to_solve_or_cap": result.steps,
        "total_retractions": result.total_retractions,
        "nogood_messages": result.nogood_messages,
        "boundary_commitment_messages": result.boundary_commit_messages,
        "comm_tokens": result.comm_tokens,
        "peak_register_entries": result.peak_register_entries,
        "overflow_entries": result.overflow_entries,
        "max_backjump_distance": result.max_backjump_distance,
        "mean_backjump_distance": result.mean_backjump_distance,
        "mean_cross_agent_backjump_distance": result.mean_cross_agent_backjump_distance,
        "reference_cross_agent_conflict_depth": instance.reference_depth,
        "boundary_conflict_exact": result.boundary_conflict_exact,
        "register_capacity": REGISTER_CAPACITY,
        "node_cap": NODE_CAP,
        "source": SOURCE,
        "provenance": "phase0_symbolic_priority_ordered_distributed_graph_coloring",
    }


def _summaries(instances: list[Instance], metric_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    pool_rows = []
    for band in BANDS:
        subset = [instance for instance in instances if instance.band == band]
        pool_rows.append({
            "band": band,
            "n": len(subset),
            "target_n": TARGET_PER_BAND,
            "target_met": len(subset) == TARGET_PER_BAND,
            "seeds": sorted({instance.seed for instance in subset}),
            "min_cross_agent_conflict_depth": min(instance.reference_depth for instance in subset),
            "max_cross_agent_conflict_depth": max(instance.reference_depth for instance in subset),
            "mean_boundary_edges": mean(_edge_count_by_type(instance)["boundary_edges"] for instance in subset),
            "source": SOURCE,
            "provenance": "reference_cbj_solver_rejection_sampling_by_cross_agent_conflict_depth",
        })
    arm_rows = []
    for band in BANDS:
        for arm in ARMS:
            subset = [row for row in metric_rows if row["band"] == band and row["arm"] == arm]
            arm_rows.append({
                "band": band,
                "arm": arm,
                "n": len(subset),
                "solve_rate": mean(float(row["solved"]) for row in subset),
                "mean_total_retractions": mean(float(row["total_retractions"]) for row in subset),
                "mean_comm_tokens": mean(float(row["comm_tokens"]) for row in subset),
                "mean_boundary_commitment_messages": mean(float(row["boundary_commitment_messages"]) for row in subset),
                "mean_nogood_messages": mean(float(row["nogood_messages"]) for row in subset),
                "mean_peak_register_entries": mean(float(row["peak_register_entries"]) for row in subset),
                "mean_backjump_distance": mean(float(row["mean_backjump_distance"]) for row in subset),
                "mean_cross_agent_backjump_distance": mean(float(row["mean_cross_agent_backjump_distance"]) for row in subset),
                "node_cap_exhaustions": sum(row["status"] == "NODE_CAP_EXHAUSTED" for row in subset),
                "source": SOURCE,
                "provenance": "same_bounded_register_only_recovery_target_differs",
            })
    pair_rows = []
    for band in BANDS:
        cbj = {row["instance_id"]: row for row in metric_rows if row["band"] == band and row["arm"] == "cbj_bounded"}
        chrono = {row["instance_id"]: row for row in metric_rows if row["band"] == band and row["arm"] == "chronological_rollback"}
        ids = sorted(set(cbj) & set(chrono))
        solve_delta = mean(float(cbj[item]["solved"]) - float(chrono[item]["solved"]) for item in ids)
        retraction_diffs = [float(cbj[item]["total_retractions"]) - float(chrono[item]["total_retractions"]) for item in ids]
        comm_diffs = [float(cbj[item]["comm_tokens"]) - float(chrono[item]["comm_tokens"]) for item in ids]
        pair_rows.append({
            "band": band,
            "n_pairs": len(ids),
            "solve_rate_delta_cbj_minus_chronological": solve_delta,
            "mcnemar_one_sided_p_cbj_gt_chronological": _mcnemar_p([bool(cbj[item]["solved"]) for item in ids], [bool(chrono[item]["solved"]) for item in ids]),
            "mean_retraction_delta_cbj_minus_chronological": mean(retraction_diffs),
            "retraction_sign_p_cbj_less": _sign_test_p_less(retraction_diffs),
            "fraction_cbj_less_retractions": mean(float(diff < 0) for diff in retraction_diffs),
            "mean_comm_token_delta_cbj_minus_chronological": mean(comm_diffs),
            "comm_sign_p_cbj_less": _sign_test_p_less(comm_diffs),
            "fraction_cbj_less_comm_tokens": mean(float(diff < 0) for diff in comm_diffs),
            "source": SOURCE,
            "provenance": "paired_instance_effects_cbj_vs_chronological",
        })
    deep_arm = {row["arm"]: row for row in arm_rows if row["band"] == "R3+"}
    deep_pair = next(row for row in pair_rows if row["band"] == "R3+")
    solve_gate = deep_pair["solve_rate_delta_cbj_minus_chronological"] >= 0.20 and (deep_pair["mcnemar_one_sided_p_cbj_gt_chronological"] is not None and deep_pair["mcnemar_one_sided_p_cbj_gt_chronological"] <= 0.05)
    retract_gate = deep_pair["mean_retraction_delta_cbj_minus_chronological"] < 0 and (deep_pair["retraction_sign_p_cbj_less"] is not None and deep_pair["retraction_sign_p_cbj_less"] <= 0.05)
    comm_gate = deep_pair["mean_comm_token_delta_cbj_minus_chronological"] < 0 and (deep_pair["comm_sign_p_cbj_less"] is not None and deep_pair["comm_sign_p_cbj_less"] <= 0.05)
    forward_gate = deep_arm["forward_markov_team"]["solve_rate"] <= 0.05
    acceptance = {
        "deep_band": "R3+",
        "cbj_solve_rate_deep": deep_arm["cbj_bounded"]["solve_rate"],
        "chronological_solve_rate_deep": deep_arm["chronological_rollback"]["solve_rate"],
        "forward_solve_rate_deep": deep_arm["forward_markov_team"]["solve_rate"],
        "solve_rate_delta_cbj_minus_chronological": deep_pair["solve_rate_delta_cbj_minus_chronological"],
        "solve_gate_pass": solve_gate,
        "retraction_gate_pass": retract_gate,
        "comm_gate_pass": comm_gate,
        "forward_gate_pass": forward_gate,
        "rung1_gate_pass": solve_gate and retract_gate and comm_gate and forward_gate,
    }
    return pool_rows, arm_rows, pair_rows, acceptance


def _edge_count_by_type(instance: Instance) -> dict[str, int]:
    boundary = sum(instance.partitions[u] != instance.partitions[v] for u, v in instance.edges)
    return {"boundary_edges": boundary, "intra_block_edges": len(instance.edges) - boundary}


def _instance_rows(instances: list[Instance]) -> list[dict[str, Any]]:
    rows = []
    for instance in instances:
        edge_counts = _edge_count_by_type(instance)
        rows.append({
            "instance_id": instance.instance_id,
            "seed": instance.seed,
            "source_index": instance.source_index,
            "source_kind": instance.source_kind,
            "n_vertices": instance.n,
            "k": instance.k,
            "chromatic_number": instance.chromatic_number,
            "k_policy": "chi_or_chi_plus_1",
            "n_agents": N_AGENTS,
            "n_edges": len(instance.edges),
            **edge_counts,
            "reference_cross_agent_conflict_depth": instance.reference_depth,
            "band": instance.band,
            "boundary_conflict_exact": instance.boundary_conflict_exact,
            "source": SOURCE,
            "provenance": "reasoning_gym_graph_color_generator_rejection_sample",
        })
    return rows


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    acceptance = results["acceptance"]
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": "051",
        "name": "Rung-1 distributed graph-coloring CBJ gate",
        "status": results["status"],
        "purpose": "Run the Phase 0 symbolic Rung-1 gate on distributed graph coloring to isolate whether conflict-directed backjump targets beat chronological rollback when cross-agent root causes are deep.",
        "code_added_used": [
            {"path": "experiments/rung1_distributed_graph_coloring.py", "change": "Uses installed reasoning-gym graph_color puzzle generation, balanced 4-agent partitioning, symbolic conflict sets, and three-arm shared-register recovery evaluation."},
            {"path": "analysis/validate_outputs.py", "change": "Validates the Rung-1 item, pool, shared-register discipline, and deep-band gate metrics."},
        ],
        "commands": [{"command": ".venv/bin/python -m experiments.rung1_distributed_graph_coloring", "purpose": "Generate the Phase 0 symbolic distributed graph-coloring pool, run all three arms, and write Item051."}],
        "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH)],
        "provenance": {
            "repo": str(REPO_ROOT),
            "generated_at": results["generated_at"],
            "phase": "0_symbolic_operator",
            "seeds": list(SEEDS),
            "n_agents": N_AGENTS,
            "register_capacity": REGISTER_CAPACITY,
            "node_cap": NODE_CAP,
            "binning_key": "reference_cross_agent_conflict_depth",
            "generator_package": "reasoning-gym",
            "generator_version": _reasoning_gym_version(),
            "generator_api": "reasoning_gym.algorithmic.graph_color.generate_graph_coloring_puzzle",
            "source": SOURCE,
        },
        "result_tables": {
            "pool_summary": {"columns": ["band", "n", "target_n", "target_met", "seeds", "min_cross_agent_conflict_depth", "max_cross_agent_conflict_depth", "mean_boundary_edges", "source", "provenance"], "rows": results["pool_summary"]},
            "instance_manifest": {"columns": ["instance_id", "seed", "source_kind", "n_vertices", "k", "chromatic_number", "k_policy", "n_agents", "n_edges", "boundary_edges", "intra_block_edges", "reference_cross_agent_conflict_depth", "band", "boundary_conflict_exact", "source", "provenance"], "rows": results["instance_manifest"]},
            "arm_band_summary": {"columns": ["band", "arm", "n", "solve_rate", "mean_total_retractions", "mean_comm_tokens", "mean_boundary_commitment_messages", "mean_nogood_messages", "mean_peak_register_entries", "mean_backjump_distance", "mean_cross_agent_backjump_distance", "node_cap_exhaustions", "source", "provenance"], "rows": results["arm_band_summary"]},
            "paired_cbj_vs_chronological": {"columns": ["band", "n_pairs", "solve_rate_delta_cbj_minus_chronological", "mcnemar_one_sided_p_cbj_gt_chronological", "mean_retraction_delta_cbj_minus_chronological", "retraction_sign_p_cbj_less", "fraction_cbj_less_retractions", "mean_comm_token_delta_cbj_minus_chronological", "comm_sign_p_cbj_less", "fraction_cbj_less_comm_tokens", "source", "provenance"], "rows": results["paired_cbj_vs_chronological"]},
            "instance_arm_metrics": {"columns": ["instance_id", "seed", "band", "arm", "solved", "status", "steps_to_solve_or_cap", "total_retractions", "nogood_messages", "boundary_commitment_messages", "comm_tokens", "peak_register_entries", "overflow_entries", "max_backjump_distance", "mean_backjump_distance", "mean_cross_agent_backjump_distance", "reference_cross_agent_conflict_depth", "boundary_conflict_exact", "register_capacity", "node_cap", "source", "provenance"], "rows": results["instance_arm_metrics"]},
        },
        "honesty": {"does_not_establish": "This is Phase 0 with a symbolic MCV/LCV operator over instances generated by the installed reasoning-gym graph_color puzzle generator, not the Qwen3.5 multi-agent operator. It tests the recovery-target mechanism under shared bounded-register accounting; Phase 1 must swap in the LLM operator without changing pool, register, or recovery code."},
        "decision": {
            "gate_outcomes": [
                {"gate": "deep_cbj_solve_rate_gt_chronological", "outcome": "PASS" if acceptance["solve_gate_pass"] else "FAIL", "number": f"delta={acceptance['solve_rate_delta_cbj_minus_chronological']:.4f}; cbj={acceptance['cbj_solve_rate_deep']:.4f}; chronological={acceptance['chronological_solve_rate_deep']:.4f}"},
                {"gate": "deep_cbj_total_retractions_less", "outcome": "PASS" if acceptance["retraction_gate_pass"] else "FAIL", "number": f"pass={acceptance['retraction_gate_pass']}"},
                {"gate": "deep_cbj_comm_tokens_less", "outcome": "PASS" if acceptance["comm_gate_pass"] else "FAIL", "number": f"pass={acceptance['comm_gate_pass']}"},
                {"gate": "deep_forward_markov_near_zero", "outcome": "PASS" if acceptance["forward_gate_pass"] else "FAIL", "number": f"forward_solve_rate={acceptance['forward_solve_rate_deep']:.4f}"},
            ],
            "next_step_routing": "Proceed to Phase 1 Qwen3.5-4B on the frozen pool if rung1_gate_pass is true; otherwise increase cut/tighten k or plant deeper chain-structured blocks and rerun Phase 0.",
            "outcome": results["status"],
        },
    }


def run() -> dict[str, Any]:
    instances = _generate_pool()
    metric_rows: list[dict[str, Any]] = []
    for instance in instances:
        for arm in ARMS:
            metric_rows.append(_row_for_instance(instance, arm, _solve(instance, arm)))
    pool_rows, arm_rows, pair_rows, acceptance = _summaries(instances, metric_rows)
    status = "RUNG1_PHASE0_SYMBOLIC_GATE_PASSED" if acceptance["rung1_gate_pass"] else "RUNG1_PHASE0_SYMBOLIC_DEEPEN_AND_RERUN"
    results = {
        "schema_version": "rung1_distributed_graph_coloring_v0",
        "generated_at": _now(),
        "status": status,
        "discipline": {
            "purpose": "isolate backjump-target rule on distributed graph coloring deep cross-agent conflicts",
            "phase": "0_symbolic_operator",
            "operator": "symbolic_priority_ordered_MCV_LCV_with_seeded_ties",
            "arms": list(ARMS),
            "only_variable": "RECOVERY backjump target rule",
            "shared_register": "bounded reversible boundary commitment register",
            "register_capacity": REGISTER_CAPACITY,
            "forward_markov_team": "no retraction; fail on first dead-end",
            "chronological_rollback": "pop exactly the shared register stack top",
            "cbj_bounded": "pop until the deepest commitment in the symbolic boundary nogood is removed",
            "binning_key": "reference_cross_agent_conflict_depth",
            "deep_band": "R3+ means cross-agent conflict depth >= 3",
        },
        "generation_config": {"seeds": list(SEEDS), "target_per_band": TARGET_PER_BAND, "target_per_seed_band": TARGET_PER_SEED_BAND, "n_agents": N_AGENTS, "node_cap": NODE_CAP, "reference_node_cap": REFERENCE_NODE_CAP, "register_capacity": REGISTER_CAPACITY, "generator_package": "reasoning-gym", "generator_version": _reasoning_gym_version(), "generator_api": "reasoning_gym.algorithmic.graph_color.generate_graph_coloring_puzzle", "r0_configs": R0_GYM_CONFIGS, "shallow_configs": SHALLOW_GYM_CONFIGS, "deep_configs": DEEP_GYM_CONFIGS, "max_gym_attempts_per_seed_band": MAX_GYM_ATTEMPTS_PER_SEED_BAND},
        "acceptance": acceptance,
        "pool_summary": pool_rows,
        "instance_manifest": _instance_rows(instances),
        "arm_band_summary": arm_rows,
        "paired_cbj_vs_chronological": pair_rows,
        "instance_arm_metrics": metric_rows,
    }
    _write_json(RESULTS_PATH, results)
    _write_json(ITEM_PATH, _build_item(results))
    return results


def main() -> None:
    global RUN_ROOT, RESULTS_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(RUN_ROOT))
    args = parser.parse_args()
    RUN_ROOT = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    RESULTS_PATH = RUN_ROOT / "results.json"
    run()


if __name__ == "__main__":
    main()