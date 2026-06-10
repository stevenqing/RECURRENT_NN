"""Rung-1 Phase 1 R4 RG-native natural pool lead-in generation."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from random import Random
from statistics import mean
from typing import Any

from reasoning_gym.algorithmic.graph_color import generate_random_graph, greedy_graph_coloring, verify_graph_coloring_solution

from experiments.rung1_distributed_graph_coloring import (
    REPO_ROOT,
    SEEDS,
    SOURCE,
    Instance,
    _chromatic_number,
    _edge_count_by_type,
    _make_instance,
    _normalize_edges,
    _reasoning_gym_version,
    _rel,
)

RUN_ROOT = REPO_ROOT / "results/rung1_phase1_r4_natural_pool"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_055_rung1_phase1_r4_natural_pool.json"

SCHEMA_VERSION = "rung1_phase1_r4_natural_pool_v0"
ITEM_NUMBER = "055"
STATUS_PASS = "RUNG1_PHASE1_R4_NATURAL_POOL_READY"
STATUS_PARTIAL = "RUNG1_PHASE1_R4_NATURAL_POOL_PARTIAL"
N_VERTICES = 16
K_COLORS = 4
N_AGENTS = 4
TARGET_DEPTH_BINS = ("4", "5", "6", "7", "8", "9", "9+")
TARGET_PER_DEPTH_BIN = 48
TARGET_PER_SEED_DEPTH_BIN = TARGET_PER_DEPTH_BIN // len(SEEDS)
P_RANGE = (0.30, 0.48)
MAX_ATTEMPTS_PER_SEED_BIN = 900000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _depth_bin(depth: int) -> str:
    if depth == 9:
        return "9"
    return "9+" if depth >= 10 else str(depth)


def _bin_sort_key(depth_bin: str) -> int:
    return 10 if depth_bin == "9+" else int(depth_bin)


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
    solved, _message = verify_graph_coloring_solution(_puzzle(edges), coloring)
    return bool(solved)


def _rg_greedy_solved(edges: tuple[tuple[int, int], ...]) -> bool:
    coloring = greedy_graph_coloring(_puzzle(edges))
    if coloring is None:
        return False
    solved, _message = verify_graph_coloring_solution(_puzzle(edges), coloring)
    return bool(solved)


def _instance_with_id(instance: Instance, seed: int, depth_bin: str, source_index: int, density: float) -> Instance:
    safe_bin = depth_bin.replace("+", "plus")
    return replace(
        instance,
        instance_id=f"rung1p1r4_s{seed}_d{safe_bin}_{source_index:06d}",
        band=depth_bin,
        source_kind=f"reasoning_gym_generate_random_graph:n16_k4_p{density:.6f};fill_method=rg_native_reverse_greedy_exact_depth_r4",
    )


def _collect_depth_bin(seed: int, depth_bin: str, target_n: int) -> tuple[list[Instance], dict[str, Any]]:
    rng = Random(seed * 1_000_003 + _bin_sort_key(depth_bin) * 10_007 + 55)
    rows: list[Instance] = []
    counters: Counter[str] = Counter()
    seen: set[tuple[tuple[int, int], ...]] = set()
    attempts = 0
    while len(rows) < target_n and attempts < MAX_ATTEMPTS_PER_SEED_BIN:
        attempts += 1
        density = rng.uniform(*P_RANGE)
        _vertices, raw_edges = generate_random_graph(rng, N_VERTICES, density)
        edges = _normalize_edges([(int(u), int(v)) for u, v in raw_edges])
        if edges in seen:
            counters["duplicate_rejected"] += 1
            continue
        seen.add(edges)
        if _rg_greedy_solved(edges):
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
    return rows, {
        "seed": seed,
        "depth_bin": depth_bin,
        "target_n": target_n,
        "n": len(rows),
        "target_met": len(rows) == target_n,
        "attempts": attempts,
        "rejection_counters": dict(counters),
        "p_range": list(P_RANGE),
        "source": SOURCE,
        "provenance": "reasoning_gym_generate_random_graph_reverse_greedy_filter_r4",
    }


def _collect_task(task: tuple[int, str, int]) -> tuple[list[Instance], dict[str, Any]]:
    seed, depth_bin, target_per_seed = task
    return _collect_depth_bin(seed, depth_bin, target_per_seed)


def _generate_pool(target_per_depth_bin: int = TARGET_PER_DEPTH_BIN, workers: int = 1) -> tuple[list[Instance], list[dict[str, Any]]]:
    instances: list[Instance] = []
    generation_rows: list[dict[str, Any]] = []
    target_per_seed = target_per_depth_bin // len(SEEDS)
    tasks = [(seed, depth_bin, target_per_seed) for seed in SEEDS for depth_bin in TARGET_DEPTH_BINS]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for rows, generation in executor.map(_collect_task, tasks):
                instances.extend(rows)
                generation_rows.append(generation)
        return instances, generation_rows
    for task in tasks:
        rows, generation = _collect_task(task)
        instances.extend(rows)
        generation_rows.append(generation)
    return instances, generation_rows


def _pool_rows(instances: list[Instance], target_per_depth_bin: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for depth_bin in TARGET_DEPTH_BINS:
        subset = [instance for instance in instances if _depth_bin(instance.reference_depth) == depth_bin]
        edge_counts = [_edge_count_by_type(instance) for instance in subset]
        rows.append({
            "depth_bin": depth_bin,
            "n": len(subset),
            "target_n": target_per_depth_bin,
            "target_met": len(subset) == target_per_depth_bin,
            "n_vertices": N_VERTICES,
            "k": K_COLORS,
            "n_agents": N_AGENTS,
            "actual_depth_min": min([instance.reference_depth for instance in subset], default=None),
            "actual_depth_max": max([instance.reference_depth for instance in subset], default=None),
            "mean_actual_depth": mean(float(instance.reference_depth) for instance in subset) if subset else None,
            "mean_n_edges": mean(float(len(instance.edges)) for instance in subset) if subset else None,
            "mean_boundary_edges": mean(float(row["boundary_edges"]) for row in edge_counts) if edge_counts else None,
            "chromatic_number_distribution": dict(Counter(str(instance.chromatic_number) for instance in subset)),
            "source": SOURCE,
            "provenance": "rg_native_natural_pool_r4_depth_summary",
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
            "edges": [list(edge) for edge in instance.edges],
            **edge_counts,
            "reference_cross_agent_conflict_depth": instance.reference_depth,
            "depth_bin": _depth_bin(instance.reference_depth),
            "rg_verified_sat": _rg_verified_sat(instance.edges),
            "rg_greedy_one_shot_solved": _rg_greedy_solved(instance.edges),
            "boundary_conflict_exact": instance.boundary_conflict_exact,
            "source": SOURCE,
            "provenance": "rg_native_generate_random_graph_reverse_greedy_r4_manifest_with_edges",
        })
    return rows


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    acceptance = results["acceptance"]
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": ITEM_NUMBER,
        "name": "Rung-1 Phase 1 R4 RG-native natural pool lead-in",
        "status": results["status"],
        "purpose": "Generate the RG-native reverse-greedy natural pool lead-in for Phase 1, adding exact depth bins 4, 5, 6, and 9 while preserving natural distribution boundaries and saving edge lists for Qwen one-shot scoring.",
        "code_added_used": [
            {"path": "experiments/rung1_phase1_r4_natural_pool.py", "change": "Generates RG-native reverse-greedy exact-depth bins 4,5,6,7,8,9,9+ and saves edge manifests for downstream Qwen one-shot and budget sweeps."}
        ],
        "commands": [{"command": ".venv/bin/python -m experiments.rung1_phase1_r4_natural_pool", "purpose": "Generate the Phase 1 RG-native natural pool lead-in."}],
        "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH)],
        "provenance": results["generation_config"],
        "result_tables": {
            "pool_depth_summary": {"rows": results["pool_depth_summary"]},
            "generation_rejection_summary": {"rows": results["generation_rejection_summary"]},
            "instance_manifest": {"rows": results["instance_manifest"]},
        },
        "honesty": {
            "does_not_establish": "This artifact only generates the natural RG-native pool. It does not run Qwen one-shot, node-cap budget sweeps, or Phase 1 fallible-operator recovery.",
            "distribution_boundary": "Rows are all generated with reasoning_gym.generate_random_graph and reverse-greedy filtering; no Item052 chain-planted rows are mixed in.",
        },
        "decision": {
            "gate_outcomes": [
                {"gate": "rg_native_depth_bins_filled", "outcome": "PASS" if acceptance["all_bins_filled"] else "PARTIAL", "number": f"bins={list(TARGET_DEPTH_BINS)}; target_per_bin={results['generation_config']['target_per_depth_bin']}"},
                {"gate": "edge_manifest_saved", "outcome": "PASS" if acceptance["edge_manifest_saved"] else "FAIL", "number": f"instances={len(results['instance_manifest'])}"},
                {"gate": "reverse_greedy_filter_effective", "outcome": "PASS" if acceptance["reverse_greedy_filter_effective"] else "FAIL", "number": "rg_greedy_one_shot_solved=false for manifest rows"},
            ],
            "next_step_routing": "Run R3 qwen_one_shot direct-answer and with-CoT on this exact edge manifest before node-cap symbolic sweeps.",
            "outcome": results["status"],
        },
    }


def run(target_per_depth_bin: int = TARGET_PER_DEPTH_BIN, workers: int = 1) -> dict[str, Any]:
    instances, generation_rows = _generate_pool(target_per_depth_bin=target_per_depth_bin, workers=workers)
    pool_rows = _pool_rows(instances, target_per_depth_bin)
    manifest_rows = _instance_rows(instances)
    acceptance = {
        "all_bins_filled": all(row["n"] == row["target_n"] and row["target_met"] is True for row in pool_rows),
        "edge_manifest_saved": bool(manifest_rows) and all(row.get("edges") for row in manifest_rows),
        "reverse_greedy_filter_effective": bool(manifest_rows) and all(row.get("rg_greedy_one_shot_solved") is False for row in manifest_rows),
    }
    status = STATUS_PASS if acceptance["all_bins_filled"] else STATUS_PARTIAL
    results = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": status,
        "generation_config": {
            "seeds": list(SEEDS),
            "target_depth_bins": list(TARGET_DEPTH_BINS),
            "target_per_depth_bin": target_per_depth_bin,
            "target_per_seed_depth_bin": target_per_depth_bin // len(SEEDS),
            "workers": workers,
            "n_vertices": N_VERTICES,
            "k": K_COLORS,
            "n_agents": N_AGENTS,
            "p_range": list(P_RANGE),
            "max_attempts_per_seed_bin": MAX_ATTEMPTS_PER_SEED_BIN,
            "generator_package": "reasoning-gym",
            "generator_version": _reasoning_gym_version(),
            "generator_api": "reasoning_gym.algorithmic.graph_color.generate_random_graph",
            "verifier_api": "reasoning_gym.algorithmic.graph_color.verify_graph_coloring_solution",
            "source": SOURCE,
        },
        "acceptance": acceptance,
        "pool_depth_summary": pool_rows,
        "generation_rejection_summary": generation_rows,
        "instance_manifest": manifest_rows,
    }
    _write_json(RESULTS_PATH, results)
    _write_json(ITEM_PATH, _build_item(results))
    return results


def main() -> None:
    global RUN_ROOT, RESULTS_PATH, ITEM_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(RUN_ROOT))
    parser.add_argument("--target-per-depth-bin", type=int, default=TARGET_PER_DEPTH_BIN)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--item-output", default=str(ITEM_PATH))
    args = parser.parse_args()
    RUN_ROOT = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    RESULTS_PATH = RUN_ROOT / "results.json"
    ITEM_PATH = Path(args.item_output) if Path(args.item_output).is_absolute() else REPO_ROOT / args.item_output
    run(target_per_depth_bin=args.target_per_depth_bin, workers=args.workers)


if __name__ == "__main__":
    main()