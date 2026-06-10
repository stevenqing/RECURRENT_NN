"""Rung-1 separator-scaling symbolic experiment."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

from tqdm.auto import tqdm

from experiments.gen_separator_scaling import generate_separator_scaling_pool
from experiments.rung1_distributed_graph_coloring import (
    Instance,
    REPO_ROOT,
    SOURCE,
    _adjacency,
    _default_color_orders,
    _rel,
    _solve,
)

RUN_ROOT = REPO_ROOT / "results/rung1_separator_scaling"
RESULTS_PATH = RUN_ROOT / "results.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_058_rung1_separator_scaling.json"
SCHEMA_VERSION = "rung1_separator_scaling_symbolic_v0"
ITEM_NUMBER = "058"
STATUS_PASS = "RUNG1_SEPARATOR_SCALING_SYMBOLIC_PASS"
STATUS_KILL = "RUNG1_SEPARATOR_SCALING_SYMBOLIC_KILL_RECORDED"
STATUS_PARTIAL = "RUNG1_SEPARATOR_SCALING_SYMBOLIC_POOL_PARTIAL"
TEAM_ARM_MAP = {
    "forward_markov_team": "forward_markov_team",
    "chronological_rollback_team": "chronological_rollback",
    "cbj_bounded_team": "cbj_bounded",
}
ARMS = ("monolith_cbj", "forward_markov_team", "chronological_rollback_team", "cbj_bounded_team")
DEFAULT_D_GLOBAL_BINS = (4, 5, 6, 7)
DEFAULT_B_BINS = (3, 4)
DEFAULT_M_BLOCKS = 4
DEFAULT_N_PER_BLOCK = 4
DEFAULT_K = 4
DEFAULT_D_LOCAL = 2
DEFAULT_N_PER_CELL = 5
DEFAULT_REGISTER_CAPACITY_D = 6
DEFAULT_COMM_BUDGET_C = 16
DEFAULT_NODE_CAP = 240
COLLAPSE_TOLERANCE = 3.0
FLAT_SLOPE_ABS_THRESHOLD = 1.0
HIGH_SOLVE_THRESHOLD = 0.75
LOW_SOLVE_THRESHOLD = 0.50


@dataclass(frozen=True)
class MonoResult:
    solved: bool
    status: str
    steps: int
    total_retractions: int
    comm_tokens: int
    peak_register_entries: int
    overflowed: bool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _depth_key(value: str | int) -> int:
    return int(value)


def _instance_from_row(row: dict[str, Any]) -> Instance:
    return Instance(
        instance_id=str(row["instance_id"]),
        seed=int(row["seed"]),
        source_index=int(row["source_index"]),
        source_kind=str(row["source_kind"]),
        n=int(row["n_vertices"]),
        k=int(row["k"]),
        chromatic_number=int(row["k"]),
        edges=tuple(tuple(int(x) for x in edge) for edge in row["edges"]),
        partitions=tuple(int(x) for x in row["partitions"]),
        order=tuple(int(x) for x in row["order"]),
        color_orders=_default_color_orders(int(row["n_vertices"]), int(row["k"])),
        reference_depth=int(row["d_global_reference"]),
        band=str(row["d_global_reference"]),
        boundary_conflict_exact=bool(row.get("boundary_conflict_exact", True)),
    )


def _normalize_status(status: str) -> str:
    if status == "SOLVED":
        return "SOLVED"
    if status in {"REGISTER_CAPACITY_EXCEEDED", "OVERFLOW_FAIL"}:
        return "OVERFLOW_FAIL"
    if status in {"NODE_CAP_EXHAUSTED", "NODE_CAP"}:
        return "NODE_CAP"
    return "FORWARD_DEAD_END"


def _solve_monolith_global_cbj(instance: Instance, node_cap: int, register_capacity_d: int, keff_hat: float) -> MonoResult:
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
        if steps >= node_cap:
            return MonoResult(False, "NODE_CAP", steps, retractions, 0, math.ceil(max(first_conflict_depth, max_backjump_distance) * math.log(max(keff_hat, 1.0001))), False)
        if cursor >= len(order):
            effective_peak = math.ceil(max(first_conflict_depth, max_backjump_distance) * math.log(max(keff_hat, 1.0001)))
            if effective_peak > register_capacity_d:
                return MonoResult(False, "OVERFLOW_FAIL", steps, retractions, 0, effective_peak, True)
            return MonoResult(True, "SOLVED", steps, retractions, 0, effective_peak, False)
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
            return MonoResult(False, "OVERFLOW_FAIL", steps, retractions, 0, effective_peak, True)
        if not register:
            return MonoResult(False, "FORWARD_DEAD_END", steps, retractions, 0, effective_peak, False)
        target_vertex = max(nogood, key=lambda item: position[item]) if nogood else register[-1]["vertex"]
        target_index = max(index for index, entry in enumerate(register) if entry["vertex"] == target_vertex)
        popped = register[target_index:]
        distance = len(popped)
        max_backjump_distance = max(max_backjump_distance, distance)
        retractions += distance
        for entry in popped:
            assignment.pop(entry["vertex"], None)
        for entry in popped[1:]:
            next_choice_index[entry["vertex"]] = 0
        next_choice_index[vertex] = 0
        cursor = register[target_index]["order_index"]
        register = register[:target_index]


def _keff_rows(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    global_keff = mean(float(row["mean_live_domain_at_decision"]) for row in manifest) if manifest else 0.0
    rows = []
    keys = sorted({(row["d_global_reference"], row["b"]) for row in manifest}, key=lambda item: (item[0], item[1]))
    for d_global, b in keys:
        subset = [row for row in manifest if row["d_global_reference"] == d_global and row["b"] == b]
        cell_keff = mean(float(row["mean_live_domain_at_decision"]) for row in subset)
        rows.append({
            "d_global_bin": str(d_global),
            "b_bin": str(b),
            "mean_live_domain_at_decision": cell_keff,
            "density": mean(float(row["density"]) for row in subset),
            "n": len(subset),
            "keff_constant_flag": abs(cell_keff - global_keff) <= 0.10 * global_keff if global_keff else False,
            "source": SOURCE,
            "provenance": "separator_scaling_measured_keff_by_cell_v0",
        })
    return rows


def _metric_rows(manifest: list[dict[str, Any]], keff_rows: list[dict[str, Any]], register_capacity_d: int, comm_budget_c: int, node_cap: int) -> list[dict[str, Any]]:
    keff_by_cell = {(row["d_global_bin"], row["b_bin"]): float(row["mean_live_domain_at_decision"]) for row in keff_rows}
    rows: list[dict[str, Any]] = []
    total = len(manifest) * len(ARMS)
    with tqdm(total=total, desc="separator symbolic arms", unit="solve", dynamic_ncols=True) as progress:
        for item in manifest:
            instance = _instance_from_row(item)
            d_global = int(item["d_global_reference"])
            b = int(item["b"])
            keff_hat = keff_by_cell[(str(d_global), str(b))]
            mono = _solve_monolith_global_cbj(instance, node_cap, register_capacity_d, keff_hat)
            rows.append({
                "instance_id": instance.instance_id,
                "arm": "monolith_cbj",
                "d_global_reference": d_global,
                "b": b,
                "solved": mono.solved,
                "status": mono.status,
                "peak_register_entries": mono.peak_register_entries,
                "comm_tokens": mono.comm_tokens,
                "total_retractions": mono.total_retractions,
                "overflowed": mono.overflowed,
                "steps_to_solve_or_cap": mono.steps,
                "register_capacity_D": register_capacity_d,
                "comm_budget_C": comm_budget_c,
                "node_cap": node_cap,
                "seed": instance.seed,
                "source": SOURCE,
                "provenance": "monolith_global_cbj_effective_capacity_law_v0",
            })
            progress.update(1)
            for arm_label, frozen_arm in TEAM_ARM_MAP.items():
                result = _solve(instance, frozen_arm, node_cap=node_cap, register_capacity=comm_budget_c)
                status = _normalize_status(result.status)
                rows.append({
                    "instance_id": instance.instance_id,
                    "arm": arm_label,
                    "d_global_reference": d_global,
                    "b": b,
                    "solved": result.solved,
                    "status": status,
                    "peak_register_entries": math.ceil(result.peak_register_entries / int(item["m_blocks"])),
                    "comm_tokens": result.comm_tokens,
                    "total_retractions": result.total_retractions,
                    "overflowed": status == "OVERFLOW_FAIL",
                    "steps_to_solve_or_cap": result.steps,
                    "register_capacity_D": register_capacity_d,
                    "comm_budget_C": comm_budget_c,
                    "node_cap": node_cap,
                    "seed": instance.seed,
                    "source": SOURCE,
                    "provenance": "phase0_symbolic_loop_frozen_from_item051_separator_scaling_v0",
                })
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
    keys = sorted({(row["d_global_reference"], row["b"]) for row in metric_rows}, key=lambda item: (item[0], item[1]))
    for d_global, b in keys:
        for arm in ARMS:
            subset = _group(metric_rows, d_global, b, arm)
            keff = keff_by_cell[(str(d_global), str(b))]
            rows.append({
                "d_global_bin": str(d_global),
                "b_bin": str(b),
                "arm": arm,
                "n": len(subset),
                "solve_rate": mean(float(row["solved"]) for row in subset),
                "mean_peak_register_entries": mean(float(row["peak_register_entries"]) for row in subset),
                "overflow_rate": mean(float(row["overflowed"]) for row in subset),
                "predicted_collapse_d": register_capacity_d / math.log(max(keff, 1.0001)),
                "observed_solve_at_this_dglobal": mean(float(row["solved"]) for row in subset),
                "source": SOURCE,
                "provenance": "separator_scaling_capacity_leg_v0",
            })
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
            if row == col:
                continue
            factor = aug[row][col]
            aug[row] = [value - factor * base for value, base in zip(aug[row], aug[col])]
    return [row[n:] for row in aug]


def _ols(rows: list[dict[str, Any]], y_key: str) -> dict[str, Any]:
    if len(rows) < 3:
        return {"slope_d_global": 0.0, "ci_d_global": [0.0, 0.0], "slope_b": 0.0, "ci_b": [0.0, 0.0], "r2": 0.0}
    x = [[1.0, float(row["d_global_bin"]), float(row["b_bin"])] for row in rows]
    y = [float(row[y_key]) for row in rows]
    xtx = [[sum(xi[a] * xi[b] for xi in x) for b in range(3)] for a in range(3)]
    try:
        inv = _invert(xtx)
    except ValueError:
        xtx = [[value + (1e-6 if a == b else 0.0) for b, value in enumerate(row)] for a, row in enumerate(xtx)]
        inv = _invert(xtx)
    xty = [sum(xi[a] * yi for xi, yi in zip(x, y)) for a in range(3)]
    beta = [sum(inv[i][j] * xty[j] for j in range(3)) for i in range(3)]
    pred = [sum(beta[i] * xi[i] for i in range(3)) for xi in x]
    residuals = [yi - pi for yi, pi in zip(y, pred)]
    sse = sum(value * value for value in residuals)
    mean_y = mean(y) if y else 0.0
    sst = sum((yi - mean_y) ** 2 for yi in y)
    dof = max(len(y) - 3, 1)
    sigma2 = sse / dof
    se = [math.sqrt(max(sigma2 * inv[i][i], 0.0)) for i in range(3)]
    return {
        "slope_d_global": beta[1],
        "ci_d_global": [beta[1] - 1.96 * se[1], beta[1] + 1.96 * se[1]],
        "slope_b": beta[2],
        "ci_b": [beta[2] - 1.96 * se[2], beta[2] + 1.96 * se[2]],
        "r2": 1.0 - sse / sst if sst > 0 else 1.0,
    }


def _double_dissociation(metric_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    detail = []
    for arm in ("cbj_bounded_team", "chronological_rollback_team"):
        keys = sorted({(row["d_global_reference"], row["b"]) for row in metric_rows}, key=lambda item: (item[0], item[1]))
        for d_global, b in keys:
            subset = _group(metric_rows, d_global, b, arm)
            detail.append({
                "arm": arm,
                "d_global_bin": str(d_global),
                "b_bin": str(b),
                "mean_comm_tokens": mean(float(row["comm_tokens"]) for row in subset),
                "mean_total_retractions": mean(float(row["total_retractions"]) for row in subset),
                "n": len(subset),
                "source": SOURCE,
                "provenance": "separator_scaling_double_dissociation_cell_means_v0",
            })
    summary = []
    for arm in ("cbj_bounded_team", "chronological_rollback_team"):
        fit = _ols([row for row in detail if row["arm"] == arm], "mean_comm_tokens")
        summary.append({"arm": arm, **fit, "source": SOURCE, "provenance": "separator_scaling_comm_tokens_ols_v0"})
    return detail, summary


def _collapse_depth(capacity_rows: list[dict[str, Any]], arm: str) -> int | None:
    by_depth: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in capacity_rows:
        if row["arm"] == arm:
            by_depth[int(row["d_global_bin"])].append(row)
    for depth in sorted(by_depth):
        solve_rate = mean(float(row["solve_rate"]) for row in by_depth[depth])
        if solve_rate <= LOW_SOLVE_THRESHOLD:
            return depth
    return None


def _verdict(capacity_rows: list[dict[str, Any]], dd_summary: list[dict[str, Any]], keff_rows: list[dict[str, Any]], cell_rows: list[dict[str, Any]], register_capacity_d: int) -> list[dict[str, Any]]:
    verdict = []
    all_targets_met = all(row["target_met"] for row in cell_rows)
    keff_constant = all(row["keff_constant_flag"] for row in keff_rows)
    predicted = mean(float(row["predicted_collapse_d"]) for row in capacity_rows if row["arm"] == "monolith_cbj")
    observed = _collapse_depth(capacity_rows, "monolith_cbj")
    cbj_fit = next(row for row in dd_summary if row["arm"] == "cbj_bounded_team")
    chrono_fit = next(row for row in dd_summary if row["arm"] == "chronological_rollback_team")
    min_b = min(int(row["b_bin"]) for row in capacity_rows)
    max_d = max(int(row["d_global_bin"]) for row in capacity_rows)
    small_b_high_d_cbj = next(row for row in capacity_rows if row["arm"] == "cbj_bounded_team" and int(row["b_bin"]) == min_b and int(row["d_global_bin"]) == max_d)
    small_b_high_d_mono = next(row for row in capacity_rows if row["arm"] == "monolith_cbj" and int(row["b_bin"]) == min_b and int(row["d_global_bin"]) == max_d)
    checks = [
        ("pool_targets_met", "all cells target_met=True", str(all_targets_met), all_targets_met),
        ("keff_constant", "K_eff within +/-10% across cells", str(keff_constant), keff_constant),
        ("cap_monolith_collapse", "monolith solve drops at predicted capacity", f"observed={observed}; predicted={predicted:.3f}", observed is not None),
        ("cap_team_survives", "cbj_team high solve where small-b monolith collapses", f"cbj={small_b_high_d_cbj['solve_rate']:.3f}; mono={small_b_high_d_mono['solve_rate']:.3f}", small_b_high_d_cbj["solve_rate"] >= HIGH_SOLVE_THRESHOLD and small_b_high_d_mono["solve_rate"] <= LOW_SOLVE_THRESHOLD),
        ("dd_cbj_flat_in_dglobal", "slope_d_global(cbj) ~= 0", f"slope={cbj_fit['slope_d_global']:.4f}; ci={cbj_fit['ci_d_global']}", abs(cbj_fit["slope_d_global"]) <= FLAT_SLOPE_ABS_THRESHOLD and cbj_fit["ci_d_global"][0] <= 0),
        ("dd_cbj_rises_in_b", "slope_b(cbj) > 0", f"slope={cbj_fit['slope_b']:.4f}; ci={cbj_fit['ci_b']}", cbj_fit["slope_b"] > 0),
        ("dd_chrono_rises_in_dglobal", "slope_d_global(chrono) > 0", f"slope={chrono_fit['slope_d_global']:.4f}; ci={chrono_fit['ci_d_global']}", chrono_fit["slope_d_global"] > 0),
        ("dd_chrono_flat_in_b", "slope_b(chrono) ~= 0 or weaker than cbj", f"chrono={chrono_fit['slope_b']:.4f}; cbj={cbj_fit['slope_b']:.4f}", abs(chrono_fit["slope_b"]) <= abs(cbj_fit["slope_b"])),
        ("quant_collapse_matches_law", "observed collapse within D/ln K_eff +/- constant", f"observed={observed}; predicted={predicted:.3f}; tolerance={COLLAPSE_TOLERANCE}", observed is not None and abs(observed - predicted) <= COLLAPSE_TOLERANCE),
    ]
    kill_cbj_d = cbj_fit["ci_d_global"][0] > 0
    kill_capacity = observed is None or abs(observed - predicted) > COLLAPSE_TOLERANCE
    kill_forced_not_better = not (small_b_high_d_cbj["solve_rate"] > small_b_high_d_mono["solve_rate"])
    for check, predicted_text, observed_text, passed in checks:
        verdict.append({"check": check, "predicted": predicted_text, "observed": observed_text, "pass": bool(passed), "source": SOURCE, "provenance": "separator_scaling_preregistered_verdict_v0"})
    overall = all(row["pass"] for row in verdict) and not (kill_cbj_d or kill_capacity or kill_forced_not_better)
    verdict.extend([
        {"check": "kill_cbj_comm_rises_with_dglobal", "predicted": "must be false", "observed": f"ci_d_global={cbj_fit['ci_d_global']}", "pass": not kill_cbj_d, "source": SOURCE, "provenance": "separator_scaling_kill_check_v0"},
        {"check": "kill_capacity_law_mismatch", "predicted": "must be false", "observed": f"observed={observed}; predicted={predicted:.3f}", "pass": not kill_capacity, "source": SOURCE, "provenance": "separator_scaling_kill_check_v0"},
        {"check": "kill_forced_not_better", "predicted": "must be false", "observed": f"cbj={small_b_high_d_cbj['solve_rate']:.3f}; mono={small_b_high_d_mono['solve_rate']:.3f}", "pass": not kill_forced_not_better, "source": SOURCE, "provenance": "separator_scaling_kill_check_v0"},
        {"check": "overall_pass", "predicted": "all preregistered checks pass", "observed": f"overall_pass={overall}", "pass": overall, "source": SOURCE, "provenance": "separator_scaling_preregistered_verdict_v0"},
    ])
    return verdict


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    verdict_by_check = {row["check"]: row for row in results["verdict"]}
    overall = verdict_by_check["overall_pass"]["pass"]
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": ITEM_NUMBER,
        "name": "Rung-1 separator-scaling symbolic double-dissociation",
        "status": results["status"],
        "purpose": "Run the separator-scaling symbolic pilot over d_global x b with fixed per-component capacity, adding monolith_cbj, measured K_eff, capacity-law checks, and preregistered kill conditions before any LLM operator run.",
        "code_added_used": [
            {"path": "experiments/gen_separator_scaling.py", "change": "Generates block-structured separator-scaling graph-coloring cells with measured d_global and K_eff."},
            {"path": "experiments/rung1_separator_scaling.py", "change": "Runs monolith_cbj plus the frozen Item051 team arms, reports capacity/double-dissociation tables, and writes preregistered verdict rows."},
        ],
        "commands": [{"command": ".venv/bin/python -m experiments.rung1_separator_scaling", "purpose": "Run the symbolic separator-scaling pilot and Item058 contract."}],
        "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH)],
        "provenance": results["generation_config"],
        "result_tables": {
            "instance_manifest": {"rows": results["instance_manifest"]},
            "keff_by_cell": {"rows": results["keff_by_cell"]},
            "instance_arm_metrics": {"rows": results["instance_arm_metrics"]},
            "capacity_leg": {"rows": results["capacity_leg"]},
            "double_dissociation_detail": {"rows": results["double_dissociation_detail"]},
            "double_dissociation_regression": {"rows": results["double_dissociation_regression"]},
            "verdict": {"rows": results["verdict"]},
        },
        "honesty": {
            "does_not_establish": "This is a symbolic pilot only. It does not run Qwen agents or LLM fallibility/K_eff inflation.",
            "failure_disambiguation": "Per-arm rows separate SOLVED, OVERFLOW_FAIL, FORWARD_DEAD_END, and NODE_CAP; no failed mode is collapsed into solve=0.",
            "pool_scope": "Independent block-structured separator-scaling pool; it is not mixed with Item052 chain-planted or Item055 natural pools.",
        },
        "decision": {
            "gate_outcomes": [
                {"gate": row["check"], "outcome": "PASS" if row["pass"] else "FAIL", "number": row["observed"]} for row in results["verdict"]
            ],
            "next_step_routing": "Proceed to the LLM-operator separator-scaling version only if overall_pass=True; otherwise stop at the triggered symbolic kill/partial condition.",
            "outcome": results["status"],
            "overall_pass": overall,
        },
    }


def run(
    d_global_bins: tuple[int, ...],
    b_bins: tuple[int, ...],
    n_per_cell: int,
    seed: int,
    m_blocks: int,
    n_per_block: int,
    k: int,
    d_local: int,
    register_capacity_d: int,
    comm_budget_c: int,
    node_cap: int,
) -> dict[str, Any]:
    manifest: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    for d_global in tqdm(d_global_bins, desc="separator cells d_global", unit="d", dynamic_ncols=True):
        for b in tqdm(b_bins, desc=f"separator cells d={d_global}", unit="b", leave=False, dynamic_ncols=True):
            cell = generate_separator_scaling_pool(m_blocks, n_per_block, k, d_local, b, d_global, n_per_cell, seed + d_global * 101 + b * 17)
            manifest.extend(cell["instance_manifest"])
            cell_rows.append(cell["cell"])
    for row in manifest:
        row["register_capacity_D"] = register_capacity_d
        row["comm_budget_C"] = comm_budget_c
    keff = _keff_rows(manifest)
    metrics = _metric_rows(manifest, keff, register_capacity_d, comm_budget_c, node_cap)
    capacity = _capacity_leg(metrics, keff, register_capacity_d)
    dd_detail, dd_regression = _double_dissociation(metrics)
    verdict = _verdict(capacity, dd_regression, keff, cell_rows, register_capacity_d)
    overall = next(row for row in verdict if row["check"] == "overall_pass")["pass"]
    pool_complete = all(row["target_met"] for row in cell_rows)
    status = STATUS_PASS if overall else (STATUS_KILL if pool_complete else STATUS_PARTIAL)
    results = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": status,
        "generation_config": {
            "d_global_bins": list(d_global_bins),
            "b_bins": list(b_bins),
            "n_per_cell": n_per_cell,
            "seed": seed,
            "m_blocks": m_blocks,
            "n_per_block": n_per_block,
            "k": k,
            "d_local": d_local,
            "register_capacity_D": register_capacity_d,
            "comm_budget_C": comm_budget_c,
            "node_cap": node_cap,
            "arms": list(ARMS),
            "team_loop_provenance": "phase0_symbolic_loop_frozen_from_item051_separator_scaling_v0",
            "monolith_provenance": "global_cbj_effective_register_capacity_D_over_ln_keff_v0",
            "source": SOURCE,
        },
        "cell_generation": cell_rows,
        "acceptance": {
            "overall_pass": overall,
            "pool_complete": pool_complete,
            "llm_version_allowed": overall,
        },
        "instance_manifest": manifest,
        "keff_by_cell": keff,
        "instance_arm_metrics": metrics,
        "capacity_leg": capacity,
        "double_dissociation_detail": dd_detail,
        "double_dissociation_regression": dd_regression,
        "verdict": verdict,
    }
    _write_json(RESULTS_PATH, results)
    _write_json(ITEM_PATH, _build_item(results))
    return results


def main() -> None:
    global RUN_ROOT, RESULTS_PATH, ITEM_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(RUN_ROOT))
    parser.add_argument("--item-output", default=str(ITEM_PATH))
    parser.add_argument("--d-global-bins", nargs="+", type=int, default=list(DEFAULT_D_GLOBAL_BINS))
    parser.add_argument("--b-bins", nargs="+", type=int, default=list(DEFAULT_B_BINS))
    parser.add_argument("--n-per-cell", type=int, default=DEFAULT_N_PER_CELL)
    parser.add_argument("--seed", type=int, default=20260610)
    parser.add_argument("--m-blocks", type=int, default=DEFAULT_M_BLOCKS)
    parser.add_argument("--n-per-block", type=int, default=DEFAULT_N_PER_BLOCK)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--d-local", type=int, default=DEFAULT_D_LOCAL)
    parser.add_argument("--register-capacity-d", type=int, default=DEFAULT_REGISTER_CAPACITY_D)
    parser.add_argument("--comm-budget-c", type=int, default=DEFAULT_COMM_BUDGET_C)
    parser.add_argument("--node-cap", type=int, default=DEFAULT_NODE_CAP)
    args = parser.parse_args()
    RUN_ROOT = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO_ROOT / args.output_dir
    RESULTS_PATH = RUN_ROOT / "results.json"
    ITEM_PATH = Path(args.item_output) if Path(args.item_output).is_absolute() else REPO_ROOT / args.item_output
    run(
        tuple(args.d_global_bins),
        tuple(args.b_bins),
        args.n_per_cell,
        args.seed,
        args.m_blocks,
        args.n_per_block,
        args.k,
        args.d_local,
        args.register_capacity_d,
        args.comm_budget_c,
        args.node_cap,
    )


if __name__ == "__main__":
    main()
