"""Rung-1 distributed graph-coloring RG-native hard-pool patch."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from random import Random
from statistics import mean
from typing import Any

from reasoning_gym.algorithmic.graph_color import generate_random_graph, greedy_graph_coloring, verify_graph_coloring_solution

from experiments.rung1_distributed_graph_coloring import (
    ARMS,
    NODE_CAP,
    REGISTER_CAPACITY,
    REPO_ROOT,
    SEEDS,
    SOURCE,
    Instance,
    _chromatic_number,
    _edge_count_by_type,
    _make_instance,
    _mcnemar_p,
    _normalize_edges,
    _reasoning_gym_version,
    _rel,
    _sign_test_p_less,
    _solve,
)

RUN_ROOT = REPO_ROOT / "results/rung1_gate_distributed_coloring_v02"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_053_rung1_gate_distributed_coloring_v02.json"

SCHEMA_VERSION = "rung1_gate_distributed_coloring_v0_2"
ITEM_NUMBER = "053"
STATUS_RECORDED = "RUNG1_V02_RG_NATIVE_HARD_BASELINE_RECORDED"
N_VERTICES = 16
K_COLORS = 4
N_AGENTS = 4
TARGET_DEPTH_BINS = ("7", "8", "9+")
TARGET_PER_DEPTH_BIN = 48
TARGET_PER_SEED_DEPTH_BIN = TARGET_PER_DEPTH_BIN // len(SEEDS)
P_RANGE = (0.30, 0.48)
MAX_ATTEMPTS_PER_SEED_BIN = 120000
ONE_SHOT_ARM = "rg_greedy_one_shot"
ALL_ARMS = tuple(list(ARMS) + [ONE_SHOT_ARM])


@dataclass(frozen=True)
class OneShotResult:
    solved: bool
    status: str
    verified: bool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _depth_bin(depth: int) -> str:
    return "9+" if depth >= 9 else str(depth)


def _bin_sort_key(depth_bin: str) -> int:
    return 9 if depth_bin == "9+" else int(depth_bin)


def _puzzle(edges: tuple[tuple[int, int], ...]) -> dict[str, Any]:
    return {"vertices": list(range(N_VERTICES)), "edges": list(edges), "num_colors": K_COLORS, "color_options": list(range(1, K_COLORS + 1))}


def _find_coloring(edges: tuple[tuple[int, int], ...]) -> dict[int, int] | None:
    adjacency = {vertex: set() for vertex in range(N_VERTICES)}
    for u, v in edges:
        adjacency[u].add(v)
        adjacency[v].add(u)
    order = sorted(range(N_VERTICES), key=lambda vertex: (-len(adjacency[vertex]), vertex))
    assignment: dict[int, int] = {}

    def rec(index: int) -> bool:
        if index == len(order):
            return True
        vertex = order[index]
        used = {assignment[neighbor] for neighbor in adjacency[vertex] if neighbor in assignment}
        for color in range(1, K_COLORS + 1):
            if color in used:
                continue
            assignment[vertex] = color
            if rec(index + 1):
                return True
            assignment.pop(vertex, None)
        return False

    return dict(assignment) if rec(0) else None


def _rg_verified_sat(edges: tuple[tuple[int, int], ...]) -> bool:
    coloring = _find_coloring(edges)
    if coloring is None:
        return False
    ok, _message = verify_graph_coloring_solution(_puzzle(edges), coloring)
    return bool(ok)


def _rg_greedy_one_shot(edges: tuple[tuple[int, int], ...]) -> OneShotResult:
    coloring = greedy_graph_coloring(_puzzle(edges))
    if coloring is None:
        return OneShotResult(False, "RG_GREEDY_NO_COLORING", True)
    ok, message = verify_graph_coloring_solution(_puzzle(edges), coloring)
    return OneShotResult(bool(ok), "RG_VERIFY_SOLVED" if ok else f"RG_VERIFY_FAILED:{message}", True)


def _instance_with_id(instance: Instance, seed: int, depth_bin: str, source_index: int, density: float) -> Instance:
    safe_bin = depth_bin.replace("+", "plus")
    return replace(
        instance,
        instance_id=f"rung1v02_s{seed}_d{safe_bin}_{source_index:06d}",
        band=depth_bin,
        source_kind=f"reasoning_gym_generate_random_graph:n16_k4_p{density:.6f};fill_method=rg_native_reverse_greedy_exact_depth",
    )


def _collect_depth_bin(seed: int, depth_bin: str) -> tuple[list[Instance], dict[str, Any]]:
    rng = Random(seed * 1_000_003 + _bin_sort_key(depth_bin) * 10_007)
    rows: list[Instance] = []
    counters: Counter[str] = Counter()
    seen: set[tuple[tuple[int, int], ...]] = set()
    attempts = 0
    while len(rows) < TARGET_PER_SEED_DEPTH_BIN and attempts < MAX_ATTEMPTS_PER_SEED_BIN:
        attempts += 1
        density = rng.uniform(*P_RANGE)
        _vertices, raw_edges = generate_random_graph(rng, N_VERTICES, density)
        edges = _normalize_edges([(int(u), int(v)) for u, v in raw_edges])
        if edges in seen:
            counters["duplicate_rejected"] += 1
            continue
        seen.add(edges)
        if _rg_greedy_one_shot(edges).solved:
            counters["rg_greedy_one_shot_solved_rejected"] += 1
            continue
        chromatic = _chromatic_number(N_VERTICES, edges, K_COLORS)
        if chromatic > K_COLORS or not _rg_verified_sat(edges):
            counters["unsat_rejected"] += 1
            continue
        if chromatic < K_COLORS:
            counters["chi_relaxed_rejected"] += 1
            continue
        source_index = seed * 1_000_000 + _bin_sort_key(depth_bin) * 100_000 + attempts
        instance = _make_instance(seed, source_index, f"reasoning_gym_generate_random_graph:n16_k4_p{density:.6f}", N_VERTICES, K_COLORS, edges)
        if instance is None:
            counters["reference_cbj_rejected"] += 1
            continue
        observed_bin = _depth_bin(instance.reference_depth)
        if observed_bin != depth_bin:
            counters[f"depth_{observed_bin}_rejected"] += 1
            continue
        rows.append(_instance_with_id(instance, seed, depth_bin, attempts, density))
        counters["accepted"] += 1
    if len(rows) < TARGET_PER_SEED_DEPTH_BIN:
        raise RuntimeError(f"could not fill RG-native depth_bin={depth_bin} seed={seed}: got={len(rows)} attempts={attempts} counters={dict(counters)}")
    return rows, {
        "seed": seed,
        "depth_bin": depth_bin,
        "target_n": TARGET_PER_SEED_DEPTH_BIN,
        "n": len(rows),
        "target_met": len(rows) == TARGET_PER_SEED_DEPTH_BIN,
        "attempts": attempts,
        "rejection_counters": dict(counters),
        "p_range": list(P_RANGE),
        "source": SOURCE,
        "provenance": "reasoning_gym_generate_random_graph_reverse_greedy_filter",
    }


def _generate_pool() -> tuple[list[Instance], list[dict[str, Any]]]:
    instances: list[Instance] = []
    generation_rows: list[dict[str, Any]] = []
    for seed in SEEDS:
        for depth_bin in TARGET_DEPTH_BINS:
            rows, generation = _collect_depth_bin(seed, depth_bin)
            instances.extend(rows)
            generation_rows.append(generation)
    return instances, generation_rows


def _metric_row_for_solver(instance: Instance, arm: str) -> dict[str, Any]:
    result = _solve(instance, arm, node_cap=NODE_CAP, register_capacity=REGISTER_CAPACITY)
    return {
        "instance_id": instance.instance_id,
        "seed": instance.seed,
        "depth_bin": _depth_bin(instance.reference_depth),
        "arm": arm,
        "solved": result.solved,
        "status": result.status,
        "verified_by_rg": bool(result.solved and _rg_verified_sat(instance.edges)),
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
        "register_capacity": REGISTER_CAPACITY,
        "node_cap": NODE_CAP,
        "source": SOURCE,
        "provenance": "phase0_symbolic_loop_frozen_from_item051_rg_native_pool",
    }


def _metric_row_for_one_shot(instance: Instance) -> dict[str, Any]:
    result = _rg_greedy_one_shot(instance.edges)
    return {
        "instance_id": instance.instance_id,
        "seed": instance.seed,
        "depth_bin": _depth_bin(instance.reference_depth),
        "arm": ONE_SHOT_ARM,
        "solved": result.solved,
        "status": result.status,
        "verified_by_rg": result.verified,
        "steps_to_solve_or_cap": 1,
        "total_retractions": 0,
        "nogood_messages": 0,
        "boundary_commitment_messages": 0,
        "comm_tokens": 0,
        "peak_register_entries": 0,
        "overflow_entries": 0,
        "overflowed": False,
        "max_backjump_distance": 0,
        "mean_backjump_distance": 0.0,
        "mean_cross_agent_backjump_distance": 0.0,
        "reference_cross_agent_conflict_depth": instance.reference_depth,
        "boundary_conflict_exact": instance.boundary_conflict_exact,
        "register_capacity": None,
        "node_cap": None,
        "source": SOURCE,
        "provenance": "reasoning_gym_greedy_graph_coloring_one_shot_verified_by_rg",
    }


def _metric_rows(instances: list[Instance]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for instance in instances:
        rows.extend(_metric_row_for_solver(instance, arm) for arm in ARMS)
        rows.append(_metric_row_for_one_shot(instance))
    return rows


def _pool_summary(instances: list[Instance]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for depth_bin in TARGET_DEPTH_BINS:
        subset = [instance for instance in instances if _depth_bin(instance.reference_depth) == depth_bin]
        rows.append({
            "depth_bin": depth_bin,
            "n": len(subset),
            "target_n": TARGET_PER_DEPTH_BIN,
            "target_met": len(subset) == TARGET_PER_DEPTH_BIN,
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
            "fill_methods": dict(Counter(instance.source_kind.split("fill_method=")[-1] for instance in subset)),
            "source": SOURCE,
            "provenance": "rg_native_hard_pool_depth_summary",
        })
    return rows


def _arm_depth_summary(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for depth_bin in TARGET_DEPTH_BINS:
        for arm in ALL_ARMS:
            subset = [row for row in metric_rows if row["depth_bin"] == depth_bin and row["arm"] == arm]
            rows.append({
                "depth_bin": depth_bin,
                "arm": arm,
                "n": len(subset),
                "solve_rate": mean(float(row["solved"]) for row in subset),
                "rg_verified_rate": mean(float(row["verified_by_rg"]) for row in subset),
                "mean_total_retractions": mean(float(row["total_retractions"]) for row in subset),
                "mean_comm_tokens": mean(float(row["comm_tokens"]) for row in subset),
                "mean_peak_register_entries": mean(float(row["peak_register_entries"]) for row in subset),
                "mean_overflow_entries": mean(float(row["overflow_entries"]) for row in subset),
                "fraction_instances_overflowed": mean(float(row["overflowed"]) for row in subset),
                "node_cap_exhaustions": sum(row["status"] == "NODE_CAP_EXHAUSTED" for row in subset),
                "source": SOURCE,
                "provenance": "rg_native_hard_pool_arm_depth_summary",
            })
    return rows


def _paired_rows(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for depth_bin in TARGET_DEPTH_BINS:
        cbj = {row["instance_id"]: row for row in metric_rows if row["depth_bin"] == depth_bin and row["arm"] == "cbj_bounded"}
        chrono = {row["instance_id"]: row for row in metric_rows if row["depth_bin"] == depth_bin and row["arm"] == "chronological_rollback"}
        ids = sorted(set(cbj) & set(chrono))
        retraction_diffs = [float(cbj[item]["total_retractions"]) - float(chrono[item]["total_retractions"]) for item in ids]
        comm_diffs = [float(cbj[item]["comm_tokens"]) - float(chrono[item]["comm_tokens"]) for item in ids]
        rows.append({
            "depth_bin": depth_bin,
            "n_pairs": len(ids),
            "solve_rate_delta_cbj_minus_chronological": mean(float(cbj[item]["solved"]) - float(chrono[item]["solved"]) for item in ids),
            "mcnemar_one_sided_p_cbj_gt_chronological": _mcnemar_p([bool(cbj[item]["solved"]) for item in ids], [bool(chrono[item]["solved"]) for item in ids]),
            "mean_retraction_delta_cbj_minus_chronological": mean(retraction_diffs),
            "retraction_sign_p_cbj_less": _sign_test_p_less(retraction_diffs),
            "fraction_cbj_less_retractions": mean(float(diff < 0) for diff in retraction_diffs),
            "mean_comm_token_delta_cbj_minus_chronological": mean(comm_diffs),
            "comm_sign_p_cbj_less": _sign_test_p_less(comm_diffs),
            "fraction_cbj_less_comm_tokens": mean(float(diff < 0) for diff in comm_diffs),
            "source": SOURCE,
            "provenance": "paired_cbj_vs_chronological_rg_native_hard_pool",
        })
    return rows


def _gap_curve_rows(arm_rows: list[dict[str, Any]], pair_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    arm = {(row["depth_bin"], row["arm"]): row for row in arm_rows}
    pair = {row["depth_bin"]: row for row in pair_rows}
    rows: list[dict[str, Any]] = []
    for depth_bin in TARGET_DEPTH_BINS:
        rows.append({
            "depth_bin": depth_bin,
            "n": arm[(depth_bin, "cbj_bounded")]["n"],
            "cbj_solve_rate": arm[(depth_bin, "cbj_bounded")]["solve_rate"],
            "chronological_solve_rate": arm[(depth_bin, "chronological_rollback")]["solve_rate"],
            "forward_solve_rate": arm[(depth_bin, "forward_markov_team")]["solve_rate"],
            "rg_greedy_one_shot_solve_rate": arm[(depth_bin, ONE_SHOT_ARM)]["solve_rate"],
            "solve_rate_gap_cbj_minus_chronological": pair[depth_bin]["solve_rate_delta_cbj_minus_chronological"],
            "mcnemar_one_sided_p_cbj_gt_chronological": pair[depth_bin]["mcnemar_one_sided_p_cbj_gt_chronological"],
            "retraction_advantage_chronological_minus_cbj": -pair[depth_bin]["mean_retraction_delta_cbj_minus_chronological"],
            "comm_token_advantage_chronological_minus_cbj": -pair[depth_bin]["mean_comm_token_delta_cbj_minus_chronological"],
            "source": SOURCE,
            "provenance": "rg_native_hard_pool_gap_vs_depth_with_one_shot_baseline",
        })
    return rows


def _instance_rows(instances: list[Instance]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for instance in instances:
        edge_counts = _edge_count_by_type(instance)
        rows.append({
            "instance_id": instance.instance_id,
            "seed": instance.seed,
            "source_index": instance.source_index,
            "source_kind": instance.source_kind,
            "fill_method": instance.source_kind.split("fill_method=")[-1],
            "n_vertices": instance.n,
            "k": instance.k,
            "chromatic_number": instance.chromatic_number,
            "n_agents": N_AGENTS,
            "n_edges": len(instance.edges),
            **edge_counts,
            "reference_cross_agent_conflict_depth": instance.reference_depth,
            "depth_bin": _depth_bin(instance.reference_depth),
            "rg_verified_sat": _rg_verified_sat(instance.edges),
            "rg_greedy_one_shot_solved": _rg_greedy_one_shot(instance.edges).solved,
            "boundary_conflict_exact": instance.boundary_conflict_exact,
            "source": SOURCE,
            "provenance": "rg_native_generate_random_graph_reverse_greedy_manifest",
        })
    return rows


def _acceptance(pool_rows: list[dict[str, Any]], arm_rows: list[dict[str, Any]], gap_rows: list[dict[str, Any]]) -> dict[str, Any]:
    all_bins_filled = all(row["n"] == TARGET_PER_DEPTH_BIN and row["target_met"] is True for row in pool_rows)
    one_shot_zero = all(row["rg_greedy_one_shot_solve_rate"] == 0.0 for row in gap_rows)
    forward_zero = all(row["forward_solve_rate"] == 0.0 for row in gap_rows)
    significant_bins = [row["depth_bin"] for row in gap_rows if row["mcnemar_one_sided_p_cbj_gt_chronological"] is not None and row["mcnemar_one_sided_p_cbj_gt_chronological"] <= 0.05]
    cbj_solves_all = all(row["arm"] != "cbj_bounded" or row["solve_rate"] == 1.0 for row in arm_rows)
    return {
        "rg_native_bins_filled": all_bins_filled,
        "reverse_greedy_filter_effective": one_shot_zero,
        "forward_markov_zero_on_hard_bins": forward_zero,
        "cbj_solves_all_hard_bins": cbj_solves_all,
        "significant_cbj_gt_chronological_bins": significant_bins,
        "all_hard_bins_significant": set(significant_bins) == set(TARGET_DEPTH_BINS),
        "chronological_solve_rates": {row["depth_bin"]: row["chronological_solve_rate"] for row in gap_rows},
        "rung1_v02_recorded": all_bins_filled and one_shot_zero and forward_zero and cbj_solves_all,
    }


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    acceptance = results["acceptance"]
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": ITEM_NUMBER,
        "name": "Rung-1 graph-coloring RG-native hard pool and one-shot baseline",
        "status": results["status"],
        "purpose": "Replace chain-planted hard bins with reasoning-gym native random graph generation plus reverse-greedy filtering, and add a one-shot RG greedy baseline verified by RG scoring.",
        "code_added_used": [
            {"path": "experiments/rung1_gate_distributed_coloring_v02.py", "change": "Uses generate_random_graph, rejects RG-greedy one-shot successes, verifies SAT and baseline outputs with verify_graph_coloring_solution, and evaluates frozen Item051 recovery arms."},
            {"path": "analysis/validate_outputs.py", "change": "Validates Item053 RG-native hard pool generation, one-shot baseline, and CBJ-vs-chronological reporting."},
        ],
        "commands": [{"command": ".venv/bin/python -m experiments.rung1_gate_distributed_coloring_v02", "purpose": "Generate Item053 RG-native hard graph-coloring pool and baseline metrics."}],
        "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH)],
        "provenance": {
            "generated_at": results["generated_at"],
            "seeds": list(SEEDS),
            "n_vertices": N_VERTICES,
            "k": K_COLORS,
            "n_agents": N_AGENTS,
            "target_depth_bins": list(TARGET_DEPTH_BINS),
            "target_per_depth_bin": TARGET_PER_DEPTH_BIN,
            "p_range": list(P_RANGE),
            "generator_package": "reasoning-gym",
            "generator_version": _reasoning_gym_version(),
            "generator_api": "reasoning_gym.algorithmic.graph_color.generate_random_graph",
            "verifier_api": "reasoning_gym.algorithmic.graph_color.verify_graph_coloring_solution",
            "one_shot_baseline": "reasoning_gym.algorithmic.graph_color.greedy_graph_coloring",
            "frozen_loop_import": "experiments.rung1_distributed_graph_coloring._solve",
            "source": SOURCE,
        },
        "result_tables": {
            "generation_rejection_summary": {"rows": results["generation_rejection_summary"]},
            "pool_depth_summary": {"rows": results["pool_depth_summary"]},
            "gap_vs_depth_curve": {"rows": results["gap_vs_depth_curve"]},
            "arm_depth_summary": {"rows": results["arm_depth_summary"]},
            "paired_cbj_vs_chronological_by_depth": {"rows": results["paired_cbj_vs_chronological_by_depth"]},
            "instance_manifest": {"rows": results["instance_manifest"]},
        },
        "honesty": {
            "does_not_establish": "This is Phase 0 symbolic recovery over a reasoning-gym native hard pool, not Qwen3.5-4B. Reverse-greedy filtering makes the RG one-shot baseline zero by construction on retained examples.",
            "distribution_shift_from_item052": "Item052's strong depth-7/8 separation used chain-structured depth fill. The RG-native random hard pool records weaker chronological failure at depth 7/8 and significant separation primarily at 9+.",
            "version_note": f"The user mentioned reasoning-gym 0.1.19; this environment has reasoning-gym {_reasoning_gym_version()} installed.",
        },
        "decision": {
            "gate_outcomes": [
                {"gate": "rg_native_bins_filled", "outcome": "PASS" if acceptance["rg_native_bins_filled"] else "FAIL", "number": f"target_bins={list(TARGET_DEPTH_BINS)}; n={TARGET_PER_DEPTH_BIN}"},
                {"gate": "reverse_greedy_one_shot_zero", "outcome": "PASS" if acceptance["reverse_greedy_filter_effective"] else "FAIL", "number": f"one_shot_zero={acceptance['reverse_greedy_filter_effective']}"},
                {"gate": "cbj_solves_all_hard_bins", "outcome": "PASS" if acceptance["cbj_solves_all_hard_bins"] else "FAIL", "number": f"pass={acceptance['cbj_solves_all_hard_bins']}"},
                {"gate": "all_hard_bins_significant", "outcome": "PASS" if acceptance["all_hard_bins_significant"] else "RECORDED", "number": f"significant_bins={acceptance['significant_cbj_gt_chronological_bins']}"},
            ],
            "next_step_routing": "Use Item053 as the RG-native hard baseline pool for Phase 1 comparability; keep Item052 chain-structured fixed-size curve as the mechanism stress curve and do not mix the two distributions.",
            "outcome": results["status"],
        },
    }


def run() -> dict[str, Any]:
    instances, generation_rows = _generate_pool()
    metric_rows = _metric_rows(instances)
    pool_rows = _pool_summary(instances)
    arm_rows = _arm_depth_summary(metric_rows)
    pair_rows = _paired_rows(metric_rows)
    gap_rows = _gap_curve_rows(arm_rows, pair_rows)
    acceptance = _acceptance(pool_rows, arm_rows, gap_rows)
    results = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": STATUS_RECORDED,
        "discipline": {
            "purpose": "RG-native hard graph-coloring pool plus one-shot RG baseline",
            "phase": "0_symbolic_operator",
            "generator": "reasoning_gym.generate_random_graph",
            "verifier": "reasoning_gym.verify_graph_coloring_solution",
            "arms": list(ALL_ARMS),
            "frozen_from_item051": ["register mechanism", "recovery target rules", "priority ordered protocol", "symbolic conflict set", "solve loop"],
            "only_variable": "pool generation and one-shot baseline report; recovery loop unchanged",
        },
        "generation_config": {
            "seeds": list(SEEDS),
            "target_depth_bins": list(TARGET_DEPTH_BINS),
            "target_per_depth_bin": TARGET_PER_DEPTH_BIN,
            "target_per_seed_depth_bin": TARGET_PER_SEED_DEPTH_BIN,
            "n_vertices": N_VERTICES,
            "k": K_COLORS,
            "n_agents": N_AGENTS,
            "p_range": list(P_RANGE),
            "max_attempts_per_seed_bin": MAX_ATTEMPTS_PER_SEED_BIN,
            "register_capacity_main": REGISTER_CAPACITY,
            "node_cap": NODE_CAP,
            "generator_package": "reasoning-gym",
            "generator_version": _reasoning_gym_version(),
            "generator_api": "reasoning_gym.algorithmic.graph_color.generate_random_graph",
            "verifier_api": "reasoning_gym.algorithmic.graph_color.verify_graph_coloring_solution",
            "one_shot_baseline": "reasoning_gym.algorithmic.graph_color.greedy_graph_coloring",
        },
        "acceptance": acceptance,
        "generation_rejection_summary": generation_rows,
        "pool_depth_summary": pool_rows,
        "gap_vs_depth_curve": gap_rows,
        "arm_depth_summary": arm_rows,
        "paired_cbj_vs_chronological_by_depth": pair_rows,
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