"""Rung-1 distributed graph-coloring fixed-size depth-curve patch.

This Item052 runner keeps the Item051 symbolic register/recovery loop frozen and
changes only pool construction plus metrics reporting. The main pool is fixed at
n=16, k=4, m=4 and is binned by measured reference CBJ cross-agent conflict
 depth.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
from statistics import mean
from typing import Any

from reasoning_gym.algorithmic.graph_color import generate_graph_coloring_puzzle

from experiments.rung1_distributed_graph_coloring import (
    ARMS,
    NODE_CAP,
    REGISTER_CAPACITY,
    REPO_ROOT,
    SEEDS,
    SOURCE,
    Instance,
    _edge_count_by_type,
    _make_instance,
    _mcnemar_p,
    _normalize_edges,
    _reasoning_gym_version,
    _rel,
    _sign_test_p_less,
    _solve,
)

RUN_ROOT = REPO_ROOT / "results/rung1_gate_distributed_coloring_v01"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_052_rung1_gate_distributed_coloring_v01.json"

SCHEMA_VERSION = "rung1_gate_distributed_coloring_v0_1"
ITEM_NUMBER = "052"
STATUS_PASS = "RUNG1_V01_FIXED_SIZE_DEPTH_CURVE_PASSED"
STATUS_REVIEW = "RUNG1_V01_FIXED_SIZE_DEPTH_CURVE_REVIEW"
N_VERTICES = 16
K_COLORS = 4
N_AGENTS = 4
DEPTH_BINS = ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9+")
STRUCTURAL_HOLE_BINS = {"1", "2", "3"}
ATTAINABLE_DEPTH_BINS = tuple(bin_name for bin_name in DEPTH_BINS if bin_name not in STRUCTURAL_HOLE_BINS)
TARGET_PER_DEPTH_BIN = 48
TARGET_PER_SEED_DEPTH_BIN = TARGET_PER_DEPTH_BIN // len(SEEDS)
REFERENCE_NODE_CAP = 600
MAX_EXACT_ATTEMPTS = 50000
GYM_ZERO_CONFIGS = (0.20, 0.24, 0.28, 0.32, 0.36)
CBJ_SWEEP_CAPACITIES = (16, 32)
HIGH_DEPTH_SWEEP_BINS = ("9+",)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _depth_bin(depth: int) -> str:
    return "9+" if depth >= 9 else str(depth)


def _bin_sort_key(bin_name: str) -> int:
    return 9 if bin_name == "9+" else int(bin_name)


def _gym_edges(seed: int, source_index: int, edge_probability: float) -> tuple[tuple[int, int], ...]:
    generator_seed = seed * 1_000_003 + source_index * 97_003 + int(round(edge_probability * 10_000))
    puzzle = generate_graph_coloring_puzzle(
        rng=random.Random(generator_seed),
        num_vertices=N_VERTICES,
        edge_probability=edge_probability,
        num_colors=K_COLORS,
    )
    return _normalize_edges([(int(u), int(v)) for u, v in puzzle["edges"]])


def _instance_with_id(instance: Instance, seed: int, depth_bin: str, source_index: int, fill_method: str) -> Instance:
    safe_bin = depth_bin.replace("+", "plus")
    return replace(
        instance,
        instance_id=f"rung1v01_s{seed}_d{safe_bin}_{source_index:06d}",
        band=depth_bin,
        source_kind=f"{instance.source_kind};fill_method={fill_method}",
    )


def _make_fixed_instance(seed: int, source_index: int, source_kind: str, edges: tuple[tuple[int, int], ...], color_orders: dict[int, tuple[int, ...]] | None = None) -> Instance | None:
    return _make_instance(seed, source_index, source_kind, N_VERTICES, K_COLORS, edges, color_orders)


def _plant_depth_edges(seed: int, depth: int, attempt: int) -> tuple[tuple[tuple[int, int], ...], dict[int, tuple[int, ...]]]:
    rng = random.Random(seed * 1_000_003 + depth * 10_007 + attempt)
    target = depth
    edges: set[tuple[int, int]] = set()
    # A future K4 makes chi=4 without making the first target conflict unsatisfiable.
    for i in range(12, 16):
        for j in range(i + 1, 16):
            edges.add((i, j))
    # The target sees four initially distinct boundary blockers.
    for blocker in range(4):
        edges.add(tuple(sorted((target, blocker))))
    # Delay target within its agent block when needed, preserving agent-major order.
    agent_start = (target // 4) * 4
    for vertex in range(agent_start, target):
        for future in range(8, 12):
            if future != target:
                edges.add(tuple(sorted((vertex, future))))
    # The remaining edges come from the installed reasoning-gym graph generator; the
    # chain overlay controls depth while the gym sample supplies background texture.
    gym_background = generate_graph_coloring_puzzle(
        rng=rng,
        num_vertices=N_VERTICES,
        edge_probability=0.03,
        num_colors=K_COLORS,
    )["edges"]
    for u, v in gym_background:
        if u == target or v == target:
            continue
        edges.add(tuple(sorted((int(u), int(v)))))
    color_orders = {
        0: (1, 2, 3, 4),
        1: (2, 1, 3, 4),
        2: (3, 1, 2, 4),
        3: (4, 1, 2, 3),
    }
    return _normalize_edges(list(edges)), color_orders


def _collect_gym_bin(seed: int, depth_bin: str, target_n: int, configs: tuple[float, ...], source_offset: int) -> list[Instance]:
    chi4_rows: list[Instance] = []
    relaxed_rows: list[Instance] = []
    seen: set[tuple[tuple[int, int], ...]] = set()
    for attempt in range(MAX_EXACT_ATTEMPTS):
        edge_probability = configs[attempt % len(configs)]
        source_index = source_offset + attempt
        edges = _gym_edges(seed, source_index, edge_probability)
        if edges in seen:
            continue
        seen.add(edges)
        source_kind = f"reasoning_gym_graph_color_generator:n16_k4_p{edge_probability:.2f}"
        instance = _make_fixed_instance(seed, source_index, source_kind, edges)
        if instance is None or _depth_bin(instance.reference_depth) != depth_bin:
            continue
        filled = _instance_with_id(instance, seed, depth_bin, source_index, "reasoning_gym_exact_rejection")
        if filled.chromatic_number == K_COLORS:
            chi4_rows.append(filled)
        elif filled.chromatic_number == K_COLORS - 1:
            relaxed_rows.append(filled)
        if len(chi4_rows) >= target_n:
            return chi4_rows[:target_n]
    rows = chi4_rows + relaxed_rows
    if len(rows) < target_n:
        raise RuntimeError(f"could not fill depth_bin={depth_bin} from gym: seed={seed} got={len(rows)} target={target_n}")
    return rows[:target_n]


def _collect_planted_bin(seed: int, depth_bin: str, target_n: int, source_offset: int) -> list[Instance]:
    depth = 9 if depth_bin == "9+" else int(depth_bin)
    rows: list[Instance] = []
    seen: set[tuple[tuple[int, int], ...]] = set()
    for attempt in range(MAX_EXACT_ATTEMPTS):
        source_index = source_offset + attempt
        edges, color_orders = _plant_depth_edges(seed, depth, attempt)
        if edges in seen:
            continue
        seen.add(edges)
        source_kind = f"reasoning_gym_graph_color_generator_plus_chain_structured_depth_plant:n16_k4_target_d{depth}"
        instance = _make_fixed_instance(seed, source_index, source_kind, edges, color_orders)
        if instance is None or instance.chromatic_number != K_COLORS or _depth_bin(instance.reference_depth) != depth_bin:
            continue
        rows.append(_instance_with_id(instance, seed, depth_bin, source_index, "chain_structured_exact_depth_fill"))
        if len(rows) >= target_n:
            return rows
    raise RuntimeError(f"could not fill planted depth_bin={depth_bin}: seed={seed} got={len(rows)} target={target_n}")


def _generate_pool() -> tuple[list[Instance], list[dict[str, Any]]]:
    instances: list[Instance] = []
    availability_rows: list[dict[str, Any]] = []
    for seed in SEEDS:
        for depth_bin in DEPTH_BINS:
            if depth_bin in STRUCTURAL_HOLE_BINS:
                availability_rows.append({
                    "seed": seed,
                    "depth_bin": depth_bin,
                    "target_n": TARGET_PER_SEED_DEPTH_BIN,
                    "n": 0,
                    "target_met": False,
                    "structural_hole": True,
                    "reason": "With k=4 graph coloring, a dead-end needs four prior color blockers, so the first nonzero cross-agent conflict depth is at least 4.",
                    "source": SOURCE,
                    "provenance": "fixed_k4_structural_reachability_check",
                })
                continue
            offset = seed * 1_000_000 + _bin_sort_key(depth_bin) * 100_000
            if depth_bin == "0":
                rows = _collect_gym_bin(seed, depth_bin, TARGET_PER_SEED_DEPTH_BIN, GYM_ZERO_CONFIGS, offset)
            else:
                rows = _collect_planted_bin(seed, depth_bin, TARGET_PER_SEED_DEPTH_BIN, offset)
            instances.extend(rows)
            availability_rows.append({
                "seed": seed,
                "depth_bin": depth_bin,
                "target_n": TARGET_PER_SEED_DEPTH_BIN,
                "n": len(rows),
                "target_met": len(rows) == TARGET_PER_SEED_DEPTH_BIN,
                "structural_hole": False,
                "reason": "filled",
                "source": SOURCE,
                "provenance": "fixed_size_depth_bin_rejection_sampling",
            })
    return instances, availability_rows


def _row_for_instance(instance: Instance, arm: str, register_capacity: int, result: Any) -> dict[str, Any]:
    return {
        "instance_id": instance.instance_id,
        "seed": instance.seed,
        "depth_bin": _depth_bin(instance.reference_depth),
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
        "overflowed": result.overflow_entries > 0 or result.status == "REGISTER_CAPACITY_EXCEEDED",
        "max_backjump_distance": result.max_backjump_distance,
        "mean_backjump_distance": result.mean_backjump_distance,
        "mean_cross_agent_backjump_distance": result.mean_cross_agent_backjump_distance,
        "reference_cross_agent_conflict_depth": instance.reference_depth,
        "boundary_conflict_exact": result.boundary_conflict_exact,
        "register_capacity": register_capacity,
        "node_cap": NODE_CAP,
        "source": SOURCE,
        "provenance": "phase0_symbolic_priority_ordered_distributed_graph_coloring_loop_frozen_from_item051",
    }


def _metric_rows(instances: list[Instance]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for instance in instances:
        for arm in ARMS:
            rows.append(_row_for_instance(instance, arm, REGISTER_CAPACITY, _solve(instance, arm, node_cap=NODE_CAP, register_capacity=REGISTER_CAPACITY)))
    return rows


def _cap_sweep_rows(instances: list[Instance]) -> list[dict[str, Any]]:
    high_instances = [instance for instance in instances if _depth_bin(instance.reference_depth) in HIGH_DEPTH_SWEEP_BINS]
    rows: list[dict[str, Any]] = []
    for instance in high_instances:
        for capacity in CBJ_SWEEP_CAPACITIES:
            rows.append(_row_for_instance(instance, "cbj_bounded", capacity, _solve(instance, "cbj_bounded", node_cap=NODE_CAP, register_capacity=capacity)))
    return rows


def _mean_bool(rows: list[dict[str, Any]], key: str) -> float:
    return mean(float(row[key]) for row in rows) if rows else 0.0


def _arm_depth_summary(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for depth_bin in ATTAINABLE_DEPTH_BINS:
        for arm in ARMS:
            subset = [row for row in metric_rows if row["depth_bin"] == depth_bin and row["arm"] == arm and row["register_capacity"] == REGISTER_CAPACITY]
            rows.append({
                "depth_bin": depth_bin,
                "arm": arm,
                "n": len(subset),
                "solve_rate": _mean_bool(subset, "solved"),
                "mean_total_retractions": mean(float(row["total_retractions"]) for row in subset),
                "mean_comm_tokens": mean(float(row["comm_tokens"]) for row in subset),
                "mean_boundary_commitment_messages": mean(float(row["boundary_commitment_messages"]) for row in subset),
                "mean_nogood_messages": mean(float(row["nogood_messages"]) for row in subset),
                "mean_peak_register_entries": mean(float(row["peak_register_entries"]) for row in subset),
                "mean_overflow_entries": mean(float(row["overflow_entries"]) for row in subset),
                "fraction_instances_overflowed": _mean_bool(subset, "overflowed"),
                "mean_backjump_distance": mean(float(row["mean_backjump_distance"]) for row in subset),
                "mean_cross_agent_backjump_distance": mean(float(row["mean_cross_agent_backjump_distance"]) for row in subset),
                "node_cap_exhaustions": sum(row["status"] == "NODE_CAP_EXHAUSTED" for row in subset),
                "register_capacity": REGISTER_CAPACITY,
                "source": SOURCE,
                "provenance": "same_bounded_register_only_recovery_target_differs_fixed_size_depth_bin",
            })
    return rows


def _paired_rows(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for depth_bin in ATTAINABLE_DEPTH_BINS:
        cbj = {row["instance_id"]: row for row in metric_rows if row["depth_bin"] == depth_bin and row["arm"] == "cbj_bounded" and row["register_capacity"] == REGISTER_CAPACITY}
        chrono = {row["instance_id"]: row for row in metric_rows if row["depth_bin"] == depth_bin and row["arm"] == "chronological_rollback" and row["register_capacity"] == REGISTER_CAPACITY}
        ids = sorted(set(cbj) & set(chrono))
        solve_delta = mean(float(cbj[item]["solved"]) - float(chrono[item]["solved"]) for item in ids)
        retraction_diffs = [float(cbj[item]["total_retractions"]) - float(chrono[item]["total_retractions"]) for item in ids]
        comm_diffs = [float(cbj[item]["comm_tokens"]) - float(chrono[item]["comm_tokens"]) for item in ids]
        rows.append({
            "depth_bin": depth_bin,
            "n_pairs": len(ids),
            "solve_rate_delta_cbj_minus_chronological": solve_delta,
            "mcnemar_one_sided_p_cbj_gt_chronological": _mcnemar_p([bool(cbj[item]["solved"]) for item in ids], [bool(chrono[item]["solved"]) for item in ids]),
            "mean_retraction_delta_cbj_minus_chronological": mean(retraction_diffs),
            "retraction_sign_p_cbj_less": _sign_test_p_less(retraction_diffs),
            "fraction_cbj_less_retractions": mean(float(diff < 0) for diff in retraction_diffs),
            "mean_comm_token_delta_cbj_minus_chronological": mean(comm_diffs),
            "comm_sign_p_cbj_less": _sign_test_p_less(comm_diffs),
            "fraction_cbj_less_comm_tokens": mean(float(diff < 0) for diff in comm_diffs),
            "register_capacity": REGISTER_CAPACITY,
            "source": SOURCE,
            "provenance": "paired_instance_effects_cbj_vs_chronological_fixed_size_depth_bin",
        })
    return rows


def _pool_summary(instances: list[Instance], availability_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    availability_by_bin = {row["depth_bin"]: row for row in availability_rows if row["seed"] == SEEDS[0]}
    for depth_bin in DEPTH_BINS:
        subset = [instance for instance in instances if _depth_bin(instance.reference_depth) == depth_bin]
        if not subset:
            rows.append({
                "depth_bin": depth_bin,
                "n": 0,
                "target_n": TARGET_PER_DEPTH_BIN,
                "target_met": False,
                "structural_hole": depth_bin in STRUCTURAL_HOLE_BINS,
                "n_vertices": N_VERTICES,
                "k": K_COLORS,
                "n_agents": N_AGENTS,
                "seeds": list(SEEDS),
                "actual_depth_min": None,
                "actual_depth_max": None,
                "mean_actual_depth": None,
                "mean_n_edges": None,
                "mean_boundary_edges": None,
                "chromatic_number_distribution": {},
                "fill_methods": {},
                "source": SOURCE,
                "provenance": availability_by_bin.get(depth_bin, {}).get("provenance", "fixed_size_depth_bin_pool_summary"),
            })
            continue
        fill_methods = Counter(instance.source_kind.split("fill_method=")[-1] for instance in subset)
        rows.append({
            "depth_bin": depth_bin,
            "n": len(subset),
            "target_n": TARGET_PER_DEPTH_BIN,
            "target_met": len(subset) == TARGET_PER_DEPTH_BIN,
            "structural_hole": False,
            "n_vertices": N_VERTICES,
            "k": K_COLORS,
            "n_agents": N_AGENTS,
            "seeds": sorted({instance.seed for instance in subset}),
            "actual_depth_min": min(instance.reference_depth for instance in subset),
            "actual_depth_max": max(instance.reference_depth for instance in subset),
            "mean_actual_depth": mean(float(instance.reference_depth) for instance in subset),
            "mean_n_edges": mean(float(len(instance.edges)) for instance in subset),
            "mean_boundary_edges": mean(float(_edge_count_by_type(instance)["boundary_edges"]) for instance in subset),
            "chromatic_number_distribution": dict(Counter(str(instance.chromatic_number) for instance in subset)),
            "fill_methods": dict(fill_methods),
            "source": SOURCE,
            "provenance": "fixed_size_depth_bin_pool_summary",
        })
    return rows


def _instance_rows(instances: list[Instance]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for instance in instances:
        edge_counts = _edge_count_by_type(instance)
        fill_method = instance.source_kind.split("fill_method=")[-1]
        rows.append({
            "instance_id": instance.instance_id,
            "seed": instance.seed,
            "source_index": instance.source_index,
            "source_kind": instance.source_kind,
            "fill_method": fill_method,
            "n_vertices": instance.n,
            "k": instance.k,
            "chromatic_number": instance.chromatic_number,
            "k_policy": "prefer_chi_equals_4_relax_to_chi_3_only_if_needed",
            "n_agents": N_AGENTS,
            "n_edges": len(instance.edges),
            **edge_counts,
            "reference_cross_agent_conflict_depth": instance.reference_depth,
            "depth_bin": _depth_bin(instance.reference_depth),
            "depth_tolerance_used": False,
            "boundary_conflict_exact": instance.boundary_conflict_exact,
            "source": SOURCE,
            "provenance": "fixed_n16_k4_depth_bin_manifest",
        })
    return rows


def _gap_curve_rows(arm_rows: list[dict[str, Any]], pair_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_arm = {(row["depth_bin"], row["arm"]): row for row in arm_rows}
    pair_by_bin = {row["depth_bin"]: row for row in pair_rows}
    rows: list[dict[str, Any]] = []
    for depth_bin in ATTAINABLE_DEPTH_BINS:
        cbj = by_arm[(depth_bin, "cbj_bounded")]
        chrono = by_arm[(depth_bin, "chronological_rollback")]
        forward = by_arm[(depth_bin, "forward_markov_team")]
        pair = pair_by_bin[depth_bin]
        rows.append({
            "depth_bin": depth_bin,
            "n": cbj["n"],
            "cbj_solve_rate": cbj["solve_rate"],
            "chronological_solve_rate": chrono["solve_rate"],
            "forward_solve_rate": forward["solve_rate"],
            "solve_rate_gap_cbj_minus_chronological": pair["solve_rate_delta_cbj_minus_chronological"],
            "mcnemar_one_sided_p_cbj_gt_chronological": pair["mcnemar_one_sided_p_cbj_gt_chronological"],
            "retraction_advantage_chronological_minus_cbj": -pair["mean_retraction_delta_cbj_minus_chronological"],
            "retraction_sign_p_cbj_less": pair["retraction_sign_p_cbj_less"],
            "comm_token_advantage_chronological_minus_cbj": -pair["mean_comm_token_delta_cbj_minus_chronological"],
            "comm_sign_p_cbj_less": pair["comm_sign_p_cbj_less"],
            "mean_cbj_peak_register_entries": cbj["mean_peak_register_entries"],
            "mean_cbj_overflow_entries": cbj["mean_overflow_entries"],
            "fraction_cbj_instances_overflowed": cbj["fraction_instances_overflowed"],
            "source": SOURCE,
            "provenance": "size_matched_gap_vs_depth_curve_fixed_n16_k4_m4",
        })
    return rows


def _cap_sweep_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for depth_bin in HIGH_DEPTH_SWEEP_BINS:
        for capacity in CBJ_SWEEP_CAPACITIES:
            subset = [row for row in rows if row["depth_bin"] == depth_bin and row["register_capacity"] == capacity]
            summary.append({
                "depth_bin": depth_bin,
                "arm": "cbj_bounded",
                "register_capacity": capacity,
                "n": len(subset),
                "solve_rate": _mean_bool(subset, "solved"),
                "mean_total_retractions": mean(float(row["total_retractions"]) for row in subset),
                "mean_comm_tokens": mean(float(row["comm_tokens"]) for row in subset),
                "mean_peak_register_entries": mean(float(row["peak_register_entries"]) for row in subset),
                "mean_overflow_entries": mean(float(row["overflow_entries"]) for row in subset),
                "fraction_instances_overflowed": _mean_bool(subset, "overflowed"),
                "source": SOURCE,
                "provenance": "cbj_register_capacity_sweep_high_depth_fixed_pool_loop_frozen",
            })
    return summary


def _acceptance(pool_rows: list[dict[str, Any]], gap_rows: list[dict[str, Any]], cap_summary: list[dict[str, Any]]) -> dict[str, Any]:
    attainable_pool = [row for row in pool_rows if row["depth_bin"] in ATTAINABLE_DEPTH_BINS]
    gaps = [float(row["solve_rate_gap_cbj_minus_chronological"]) for row in gap_rows]
    significant_bins = [row["depth_bin"] for row in gap_rows if row["mcnemar_one_sided_p_cbj_gt_chronological"] is not None and row["mcnemar_one_sided_p_cbj_gt_chronological"] <= 0.05 and row["solve_rate_gap_cbj_minus_chronological"] > 0]
    crossover = significant_bins[0] if significant_bins else None
    crossover_index = next((index for index, row in enumerate(gap_rows) if row["depth_bin"] == crossover), None)
    post_crossover = gap_rows[crossover_index:] if crossover_index is not None else []
    monotonic_gap = all(gaps[index] <= gaps[index + 1] + 1e-12 for index in range(len(gaps) - 1))
    forward_ge1_near_zero = all(row["forward_solve_rate"] <= 0.05 for row in gap_rows if row["depth_bin"] != "0")
    post_crossover_significant = bool(post_crossover) and all(row["mcnemar_one_sided_p_cbj_gt_chronological"] is not None and row["mcnemar_one_sided_p_cbj_gt_chronological"] <= 0.05 for row in post_crossover)
    cap_rows_ok = {row["register_capacity"] for row in cap_summary if row["depth_bin"] == "9+"} == set(CBJ_SWEEP_CAPACITIES)
    cap16 = next((row for row in cap_summary if row["depth_bin"] == "9+" and row["register_capacity"] == 16), {})
    cap32 = next((row for row in cap_summary if row["depth_bin"] == "9+" and row["register_capacity"] == 32), {})
    if cap16.get("fraction_instances_overflowed", 1.0) > 0.0:
        cap_interpretation = "cap16_spill_observed"
    elif cap16.get("mean_peak_register_entries") == REGISTER_CAPACITY and cap32.get("mean_peak_register_entries") == REGISTER_CAPACITY:
        cap_interpretation = "no_spill_fixed_n16_task_peak_saturates_at_16_cap32_no_trajectory_change"
    else:
        cap_interpretation = "no_spill_cap32_headroom_visible"
    return {
        "fixed_size_invariant_pass": all(row["n_vertices"] == N_VERTICES and row["k"] == K_COLORS and row["n_agents"] == N_AGENTS for row in attainable_pool),
        "attainable_bins_filled": all(row["n"] == TARGET_PER_DEPTH_BIN and row["target_met"] is True for row in attainable_pool),
        "structural_hole_bins": sorted(STRUCTURAL_HOLE_BINS, key=int),
        "structural_holes_recorded": all(row["structural_hole"] is True and row["n"] == 0 for row in pool_rows if row["depth_bin"] in STRUCTURAL_HOLE_BINS),
        "solve_gap_monotonic_non_decreasing": monotonic_gap,
        "crossover_depth_bin": crossover,
        "post_crossover_significant": post_crossover_significant,
        "forward_ge1_near_zero": forward_ge1_near_zero,
        "cap_sweep_complete": cap_rows_ok,
        "cap_sweep_interpretation": cap_interpretation,
        "rung1_v01_gate_pass": all([
            all(row["n"] == TARGET_PER_DEPTH_BIN and row["target_met"] is True for row in attainable_pool),
            monotonic_gap,
            crossover is not None,
            post_crossover_significant,
            forward_ge1_near_zero,
            cap_rows_ok,
        ]),
    }


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    acceptance = results["acceptance"]
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": ITEM_NUMBER,
        "name": "Rung-1 gate distributed coloring v0.1 fixed-size depth curve",
        "status": results["status"],
        "purpose": "Patch the Rung-1 distributed graph-coloring gate from coarse deep-band separation to a fixed-size per-depth Phase 0 curve while keeping register, recovery, conflict-set, and loop code frozen.",
        "code_added_used": [
            {"path": "experiments/rung1_gate_distributed_coloring_v01.py", "change": "Builds fixed n=16,k=4,m=4 depth-bin pools, reports gap-vs-depth metrics, and runs a CBJ cap 16/32 high-depth sweep while importing the frozen Item051 solve loop."},
            {"path": "analysis/validate_outputs.py", "change": "Validates Item052 fixed-size bins, structural shallow-depth holes, gap curve, overflow summary, and CBJ cap sweep."},
        ],
        "commands": [{"command": ".venv/bin/python -m experiments.rung1_gate_distributed_coloring_v01", "purpose": "Generate Item052 fixed-size depth-bin pool and metrics."}],
        "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH)],
        "provenance": {
            "repo": str(REPO_ROOT),
            "generated_at": results["generated_at"],
            "phase": "0_symbolic_operator",
            "seeds": list(SEEDS),
            "n_vertices": N_VERTICES,
            "k": K_COLORS,
            "n_agents": N_AGENTS,
            "register_capacity_main": REGISTER_CAPACITY,
            "cbj_sweep_capacities": list(CBJ_SWEEP_CAPACITIES),
            "node_cap": NODE_CAP,
            "binning_key": "reference_cross_agent_conflict_depth",
            "generator_package": "reasoning-gym",
            "generator_version": _reasoning_gym_version(),
            "generator_api": "reasoning_gym.algorithmic.graph_color.generate_graph_coloring_puzzle",
            "frozen_loop_import": "experiments.rung1_distributed_graph_coloring._solve",
            "source": SOURCE,
        },
        "result_tables": {
            "pool_depth_summary": {"columns": ["depth_bin", "n", "target_n", "target_met", "structural_hole", "n_vertices", "k", "n_agents", "seeds", "actual_depth_min", "actual_depth_max", "mean_actual_depth", "mean_n_edges", "mean_boundary_edges", "chromatic_number_distribution", "fill_methods", "source", "provenance"], "rows": results["pool_depth_summary"]},
            "gap_vs_depth_curve": {"columns": ["depth_bin", "n", "cbj_solve_rate", "chronological_solve_rate", "forward_solve_rate", "solve_rate_gap_cbj_minus_chronological", "mcnemar_one_sided_p_cbj_gt_chronological", "retraction_advantage_chronological_minus_cbj", "retraction_sign_p_cbj_less", "comm_token_advantage_chronological_minus_cbj", "comm_sign_p_cbj_less", "mean_cbj_peak_register_entries", "mean_cbj_overflow_entries", "fraction_cbj_instances_overflowed", "source", "provenance"], "rows": results["gap_vs_depth_curve"]},
            "arm_depth_summary": {"columns": ["depth_bin", "arm", "n", "solve_rate", "mean_total_retractions", "mean_comm_tokens", "mean_boundary_commitment_messages", "mean_nogood_messages", "mean_peak_register_entries", "mean_overflow_entries", "fraction_instances_overflowed", "mean_backjump_distance", "mean_cross_agent_backjump_distance", "node_cap_exhaustions", "register_capacity", "source", "provenance"], "rows": results["arm_depth_summary"]},
            "paired_cbj_vs_chronological_by_depth": {"columns": ["depth_bin", "n_pairs", "solve_rate_delta_cbj_minus_chronological", "mcnemar_one_sided_p_cbj_gt_chronological", "mean_retraction_delta_cbj_minus_chronological", "retraction_sign_p_cbj_less", "fraction_cbj_less_retractions", "mean_comm_token_delta_cbj_minus_chronological", "comm_sign_p_cbj_less", "fraction_cbj_less_comm_tokens", "register_capacity", "source", "provenance"], "rows": results["paired_cbj_vs_chronological_by_depth"]},
            "cbj_register_capacity_sweep": {"columns": ["depth_bin", "arm", "register_capacity", "n", "solve_rate", "mean_total_retractions", "mean_comm_tokens", "mean_peak_register_entries", "mean_overflow_entries", "fraction_instances_overflowed", "source", "provenance"], "rows": results["cbj_register_capacity_sweep"]},
            "instance_manifest": {"columns": ["instance_id", "seed", "source_index", "source_kind", "fill_method", "n_vertices", "k", "chromatic_number", "k_policy", "n_agents", "n_edges", "boundary_edges", "intra_block_edges", "reference_cross_agent_conflict_depth", "depth_bin", "depth_tolerance_used", "boundary_conflict_exact", "source", "provenance"], "rows": results["instance_manifest"]},
        },
        "honesty": {
            "does_not_establish": "This is still Phase 0 symbolic recovery over a fixed-size graph-coloring pool, not Qwen3.5-4B. With k=4, exact depth bins 1-3 are structurally unreachable for first dead-ends because four color blockers are needed; they are reported as holes rather than filled by incompatible k values.",
            "density_confound": "Even with fixed n/k/m, edge density and boundary-edge count vary by depth; pool_depth_summary reports mean_n_edges, mean_boundary_edges, and chi distribution per bin.",
            "cap_sweep_interpretation": results["acceptance"].get("cap_sweep_interpretation"),
        },
        "decision": {
            "gate_outcomes": [
                {"gate": "fixed_size_attainable_bins_filled", "outcome": "PASS" if acceptance["attainable_bins_filled"] else "FAIL", "number": f"target_per_attainable_bin={TARGET_PER_DEPTH_BIN}"},
                {"gate": "structural_shallow_holes_recorded", "outcome": "PASS" if acceptance["structural_holes_recorded"] else "FAIL", "number": f"holes={acceptance['structural_hole_bins']}"},
                {"gate": "solve_gap_monotonic_and_crossover", "outcome": "PASS" if acceptance["solve_gap_monotonic_non_decreasing"] and acceptance["crossover_depth_bin"] else "FAIL", "number": f"crossover={acceptance['crossover_depth_bin']}"},
                {"gate": "forward_ge1_near_zero", "outcome": "PASS" if acceptance["forward_ge1_near_zero"] else "FAIL", "number": f"pass={acceptance['forward_ge1_near_zero']}"},
                {"gate": "cbj_cap_sweep_complete", "outcome": "PASS" if acceptance["cap_sweep_complete"] else "FAIL", "number": f"capacities={list(CBJ_SWEEP_CAPACITIES)}"},
            ],
            "next_step_routing": "Use the fixed-size attainable-bin pool for Phase 1 gap-vs-depth reproduction; keep Item051 deep-stress pool separate and labeled as secondary stress evidence.",
            "outcome": results["status"],
        },
    }


def run() -> dict[str, Any]:
    instances, availability_rows = _generate_pool()
    metric_rows = _metric_rows(instances)
    cap_rows = _cap_sweep_rows(instances)
    arm_rows = _arm_depth_summary(metric_rows)
    pair_rows = _paired_rows(metric_rows)
    gap_rows = _gap_curve_rows(arm_rows, pair_rows)
    cap_summary = _cap_sweep_summary(cap_rows)
    pool_rows = _pool_summary(instances, availability_rows)
    acceptance = _acceptance(pool_rows, gap_rows, cap_summary)
    status = STATUS_PASS if acceptance["rung1_v01_gate_pass"] else STATUS_REVIEW
    results = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": status,
        "discipline": {
            "purpose": "fixed-size size-matched gap-vs-depth curve for distributed graph coloring",
            "phase": "0_symbolic_operator",
            "operator": "symbolic_priority_ordered_MCV_LCV_with_seeded_ties",
            "arms": list(ARMS),
            "only_variable": "RECOVERY backjump target rule for main arms; CBJ register_capacity for high-depth sweep only",
            "frozen_from_item051": ["register mechanism", "recovery target rules", "priority ordered protocol", "symbolic conflict set", "solve loop"],
            "n_vertices": N_VERTICES,
            "k": K_COLORS,
            "n_agents": N_AGENTS,
            "depth_bins": list(DEPTH_BINS),
            "structural_hole_bins": sorted(STRUCTURAL_HOLE_BINS, key=int),
        },
        "generation_config": {
            "seeds": list(SEEDS),
            "target_per_depth_bin": TARGET_PER_DEPTH_BIN,
            "target_per_seed_depth_bin": TARGET_PER_SEED_DEPTH_BIN,
            "n_vertices": N_VERTICES,
            "k": K_COLORS,
            "n_agents": N_AGENTS,
            "node_cap": NODE_CAP,
            "reference_node_cap": REFERENCE_NODE_CAP,
            "register_capacity_main": REGISTER_CAPACITY,
            "cbj_sweep_capacities": list(CBJ_SWEEP_CAPACITIES),
            "generator_package": "reasoning-gym",
            "generator_version": _reasoning_gym_version(),
            "generator_api": "reasoning_gym.algorithmic.graph_color.generate_graph_coloring_puzzle",
            "zero_depth_density_scan": GYM_ZERO_CONFIGS,
            "chain_structured_fill_bins": ["4", "5", "6", "7", "8", "9+"],
            "max_exact_attempts": MAX_EXACT_ATTEMPTS,
        },
        "availability_by_seed_bin": availability_rows,
        "acceptance": acceptance,
        "pool_depth_summary": pool_rows,
        "gap_vs_depth_curve": gap_rows,
        "arm_depth_summary": arm_rows,
        "paired_cbj_vs_chronological_by_depth": pair_rows,
        "cbj_register_capacity_sweep": cap_summary,
        "cbj_register_capacity_sweep_instance_metrics": cap_rows,
        "instance_manifest": _instance_rows(instances),
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
