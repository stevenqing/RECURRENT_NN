"""Rung-1 Phase 1 R2 symbolic efficiency and node-budget sweep."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any

from tqdm.auto import tqdm

from experiments.rung1_distributed_graph_coloring import (
    ARMS,
    REGISTER_CAPACITY,
    REPO_ROOT,
    SOURCE,
    _make_instance,
    _mcnemar_p,
    _rel,
    _sign_test_p_less,
    _solve,
)

RUN_ROOT = REPO_ROOT / "results/rung1_phase1_r2_budget_sweep"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_057_rung1_phase1_r2_budget_sweep.json"
R4_RESULTS_PATH = REPO_ROOT / "results/rung1_phase1_r4_natural_pool/results.json"

SCHEMA_VERSION = "rung1_phase1_r2_budget_sweep_v0"
ITEM_NUMBER = "057"
STATUS_PASS = "RUNG1_PHASE1_R2_SYMBOLIC_BUDGET_SWEEP_RECORDED"
NODE_CAPS = (60, 120, 240, 480, 960)
REFERENCE_NODE_CAP = 120
BUDGET_SOLVE_THRESHOLD = 0.95


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _instances(r4_results: dict[str, Any]) -> list[Any]:
    instances = []
    for row in tqdm(r4_results["instance_manifest"], desc="R2 reconstruct instances", unit="instance", dynamic_ncols=True):
        edges = tuple(tuple(edge) for edge in row["edges"])
        instance = _make_instance(int(row["seed"]), int(row["source_index"]), str(row["source_kind"]), int(row["n_vertices"]), int(row["k"]), edges)
        if instance is None:
            raise ValueError(f"could not reconstruct instance {row['instance_id']}")
        instance = instance.__class__(
            instance_id=row["instance_id"],
            seed=instance.seed,
            source_index=instance.source_index,
            source_kind=instance.source_kind,
            n=instance.n,
            k=instance.k,
            edges=instance.edges,
            partitions=instance.partitions,
            order=instance.order,
            color_orders=instance.color_orders,
            band=row["depth_bin"],
            chromatic_number=instance.chromatic_number,
            reference_depth=instance.reference_depth,
            boundary_conflict_exact=instance.boundary_conflict_exact,
        )
        instances.append(instance)
    return instances


def _metric_rows(instances: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total = len(instances) * len(NODE_CAPS) * len(ARMS)
    with tqdm(total=total, desc="R2 node-cap sweep", unit="solve", dynamic_ncols=True) as progress:
        for instance in instances:
            for node_cap in NODE_CAPS:
                for arm in ARMS:
                    result = _solve(instance, arm, node_cap=node_cap, register_capacity=REGISTER_CAPACITY)
                    progress.update(1)
                    rows.append({
                        "instance_id": instance.instance_id,
                        "seed": instance.seed,
                        "depth_bin": instance.band,
                        "arm": arm,
                        "node_cap": node_cap,
                        "register_capacity": REGISTER_CAPACITY,
                        "solved": result.solved,
                        "status": result.status,
                        "steps_to_solve_or_cap": result.steps,
                        "total_retractions": result.total_retractions,
                        "comm_tokens": result.comm_tokens,
                        "peak_register_entries": result.peak_register_entries,
                        "overflow_entries": result.overflow_entries,
                        "overflowed": result.overflow_entries > 0 or result.status == "REGISTER_CAPACITY_EXCEEDED",
                        "reference_cross_agent_conflict_depth": instance.reference_depth,
                        "boundary_conflict_exact": result.boundary_conflict_exact,
                        "source": SOURCE,
                        "provenance": "phase0_symbolic_loop_frozen_from_item051_r4_natural_pool_node_cap_sweep",
                    })
    return rows


def _solve_budget_rows(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    depth_bins = sorted({row["depth_bin"] for row in metric_rows}, key=lambda value: 10 if value == "9+" else int(value))
    for depth_bin in depth_bins:
        for arm in ARMS:
            budget_at_95: int | str = "not_reached"
            for node_cap in NODE_CAPS:
                subset = [row for row in metric_rows if row["depth_bin"] == depth_bin and row["arm"] == arm and row["node_cap"] == node_cap]
                solve_rate = mean(float(row["solved"]) for row in subset)
                rows.append({
                    "depth_bin": depth_bin,
                    "arm": arm,
                    "node_cap": node_cap,
                    "n": len(subset),
                    "solve_rate": solve_rate,
                    "node_cap_exhaustions": sum(row["status"] == "NODE_CAP_EXHAUSTED" for row in subset),
                    "mean_total_retractions": mean(float(row["total_retractions"]) for row in subset),
                    "mean_comm_tokens": mean(float(row["comm_tokens"]) for row in subset),
                    "source": SOURCE,
                    "provenance": "solve_rate_vs_node_cap_rg_native_natural_pool",
                })
                if budget_at_95 == "not_reached" and solve_rate >= BUDGET_SOLVE_THRESHOLD:
                    budget_at_95 = node_cap
            for row in rows:
                if row["depth_bin"] == depth_bin and row["arm"] == arm:
                    row["budget_at_95_solve"] = budget_at_95
    return rows


def _efficiency_rows(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reference_rows = [row for row in metric_rows if row["node_cap"] == REFERENCE_NODE_CAP]
    depth_bins = sorted({row["depth_bin"] for row in reference_rows}, key=lambda value: 10 if value == "9+" else int(value))
    for depth_bin in depth_bins:
        cbj = {row["instance_id"]: row for row in reference_rows if row["depth_bin"] == depth_bin and row["arm"] == "cbj_bounded"}
        chrono = {row["instance_id"]: row for row in reference_rows if row["depth_bin"] == depth_bin and row["arm"] == "chronological_rollback"}
        ids = sorted(set(cbj) & set(chrono))
        retraction_diffs = [float(cbj[item]["total_retractions"]) - float(chrono[item]["total_retractions"]) for item in ids]
        comm_diffs = [float(cbj[item]["comm_tokens"]) - float(chrono[item]["comm_tokens"]) for item in ids]
        rows.append({
            "depth_bin": depth_bin,
            "node_cap": REFERENCE_NODE_CAP,
            "n_pairs": len(ids),
            "cbj_solve_rate": mean(float(cbj[item]["solved"]) for item in ids),
            "chronological_solve_rate": mean(float(chrono[item]["solved"]) for item in ids),
            "solve_rate_delta_cbj_minus_chronological": mean(float(cbj[item]["solved"]) - float(chrono[item]["solved"]) for item in ids),
            "mcnemar_one_sided_p_cbj_gt_chronological": _mcnemar_p([bool(cbj[item]["solved"]) for item in ids], [bool(chrono[item]["solved"]) for item in ids]),
            "mean_retraction_delta_cbj_minus_chronological": mean(retraction_diffs),
            "retraction_sign_p_cbj_less": _sign_test_p_less(retraction_diffs),
            "retraction_advantage_chronological_minus_cbj": -mean(retraction_diffs),
            "mean_comm_token_delta_cbj_minus_chronological": mean(comm_diffs),
            "comm_sign_p_cbj_less": _sign_test_p_less(comm_diffs),
            "comm_token_advantage_chronological_minus_cbj": -mean(comm_diffs),
            "source": SOURCE,
            "provenance": "paired_efficiency_primary_reference_budget_rg_native_natural_pool",
        })
    return rows


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    acceptance = results["acceptance"]
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": ITEM_NUMBER,
        "name": "Rung-1 Phase 1 R2 symbolic node-cap budget sweep",
        "status": results["status"],
        "purpose": "Run the Phase 0 symbolic confirmation for the reordered Phase 1 claim: paired efficiency is primary and solve-rate is reported as a node-cap budget curve on the R4 RG-native natural pool.",
        "code_added_used": [{"path": "experiments/rung1_phase1_r2_budget_sweep.py", "change": "Consumes the R4 edge manifest, sweeps node_cap 60/120/240/480/960, and reports efficiency plus budget@95% solve metrics."}],
        "commands": [{"command": ".venv/bin/python -m experiments.rung1_phase1_r2_budget_sweep", "purpose": "Run symbolic node-cap budget sweep on the R4 pool."}],
        "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH)],
        "provenance": results["generation_config"],
        "result_tables": {
            "efficiency_gap_by_depth": {"rows": results["efficiency_gap_by_depth"]},
            "solve_rate_vs_node_cap": {"rows": results["solve_rate_vs_node_cap"]},
            "instance_arm_node_cap_metrics": {"rows": results["instance_arm_node_cap_metrics"]},
        },
        "honesty": {"does_not_establish": "This is the Phase 0 symbolic budget confirmation only. It does not run Qwen one-shot or fallible Phase 1 operators."},
        "decision": {
            "gate_outcomes": [
                {"gate": "node_cap_sweep_complete", "outcome": "PASS" if acceptance["node_cap_sweep_complete"] else "FAIL", "number": f"node_caps={list(NODE_CAPS)}"},
                {"gate": "efficiency_advantage_all_depths", "outcome": "PASS" if acceptance["efficiency_advantage_all_depths"] else "FAIL", "number": f"depths={acceptance['efficiency_depths_with_advantage']}"},
            ],
            "next_step_routing": "If R3 hardness gate passes, proceed to Phase 1 P1a/P1b/P1c with efficiency-gap survival as primary.",
            "outcome": results["status"],
        },
    }


def run(r4_results_path: Path) -> dict[str, Any]:
    r4 = _read_json(r4_results_path)
    instances = _instances(r4)
    metric_rows = _metric_rows(instances)
    budget_rows = _solve_budget_rows(metric_rows)
    efficiency_rows = _efficiency_rows(metric_rows)
    depth_bins = {row["depth_bin"] for row in efficiency_rows}
    advantage_depths = [row["depth_bin"] for row in efficiency_rows if row["retraction_advantage_chronological_minus_cbj"] > 0 and row["comm_token_advantage_chronological_minus_cbj"] > 0]
    acceptance = {
        "node_cap_sweep_complete": {row["node_cap"] for row in metric_rows} == set(NODE_CAPS),
        "efficiency_advantage_all_depths": set(advantage_depths) == depth_bins,
        "efficiency_depths_with_advantage": advantage_depths,
    }
    results = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": STATUS_PASS,
        "generation_config": {
            "r4_results_path": _rel(r4_results_path),
            "node_caps": list(NODE_CAPS),
            "reference_node_cap": REFERENCE_NODE_CAP,
            "budget_solve_threshold": BUDGET_SOLVE_THRESHOLD,
            "register_capacity": REGISTER_CAPACITY,
            "arms": list(ARMS),
            "source": SOURCE,
        },
        "acceptance": acceptance,
        "efficiency_gap_by_depth": efficiency_rows,
        "solve_rate_vs_node_cap": budget_rows,
        "instance_arm_node_cap_metrics": metric_rows,
    }
    _write_json(RESULTS_PATH, results)
    _write_json(ITEM_PATH, _build_item(results))
    return results


def main() -> None:
    global RUN_ROOT, RESULTS_PATH, ITEM_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--r4-results", default=str(R4_RESULTS_PATH))
    parser.add_argument("--output-dir", default=str(RUN_ROOT))
    parser.add_argument("--item-output", default=str(ITEM_PATH))
    args = parser.parse_args()
    RUN_ROOT = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    RESULTS_PATH = RUN_ROOT / "results.json"
    ITEM_PATH = Path(args.item_output) if Path(args.item_output).is_absolute() else REPO_ROOT / args.item_output
    r4_results = Path(args.r4_results) if Path(args.r4_results).is_absolute() else REPO_ROOT / args.r4_results
    run(r4_results)


if __name__ == "__main__":
    main()