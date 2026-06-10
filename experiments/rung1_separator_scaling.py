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
SCHEMA_VERSION = "rung1_separator_scaling_symbolic_v0_1"
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
    return {"corr_d_global_b": corr, "vif_d_global_b": vif, "min_unique_d_global_per_b": min_d, "min_unique_b_per_d_global": min_b, "unique_d_global_by_b": d_by_b, "unique_b_by_d_global": b_by_d, "axes_independent": abs(corr) < AXES_CORR_THRESHOLD and vif < 2.0 and min_d >= 3 and min_b >= 3, "source": SOURCE, "provenance": "separator_scaling_axes_independence_check_v0_1"}


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
            common = {"instance_id": instance.instance_id, "cell_id": item.get("cell_id"), "sweep": item.get("sweep"), "d_global_reference": d_global, "b": b, "d_boundary": int(item["d_boundary"]), "d_local": int(item["d_local"]), "m_blocks": int(item["m_blocks"]), "local_contribution": int(item["local_contribution"]), "register_capacity_D": register_capacity_d, "comm_budget_C": comm_budget_c, "node_cap": node_cap, "seed": instance.seed, "source": SOURCE}
            mono = _solve_monolith(instance, node_cap, register_capacity_d, keff_by_cell[(str(d_global), str(b))])
            rows.append({**common, "arm": "monolith_cbj", "solved": mono["solved"], "status": mono["status"], "peak_register_entries": mono["peak_register_entries"], "comm_tokens": mono["comm_tokens"], "total_retractions": mono["total_retractions"], "overflowed": mono["overflowed"], "steps_to_solve_or_cap": mono["steps"], "provenance": "monolith_global_cbj_effective_capacity_law_v0"})
            progress.update(1)
            for arm_label, frozen_arm in TEAM_ARM_MAP.items():
                result = _solve(instance, frozen_arm, node_cap=node_cap, register_capacity=comm_budget_c)
                status = _normalize_status(result.status)
                rows.append({**common, "arm": arm_label, "solved": result.solved, "status": status, "peak_register_entries": math.ceil(result.peak_register_entries / int(item["m_blocks"])), "comm_tokens": result.comm_tokens, "total_retractions": result.total_retractions, "overflowed": status == "OVERFLOW_FAIL", "steps_to_solve_or_cap": result.steps, "provenance": "phase0_symbolic_loop_frozen_from_item051_separator_scaling_v0"})
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
    return [{"term": names[i], "beta": beta[i], "ci": [beta[i] - 1.96 * se[i], beta[i] + 1.96 * se[i]], "r2": r2, "n": len(y), "source": SOURCE, "provenance": "separator_scaling_pooled_interaction_ols_v0_1"} for i in range(6)]


def _double_dissociation(metric_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    detail = []
    for arm in ("cbj_bounded_team", "chronological_rollback_team"):
        for d_global, b in sorted({(row["d_global_reference"], row["b"]) for row in metric_rows if row["arm"] == arm}, key=lambda item: (item[0], item[1])):
            subset = _group(metric_rows, d_global, b, arm)
            detail.append({"arm": arm, "d_global_bin": str(d_global), "b_bin": str(b), "mean_comm_tokens": mean(float(row["comm_tokens"]) for row in subset), "mean_total_retractions": mean(float(row["total_retractions"]) for row in subset), "n": len(subset), "source": SOURCE, "provenance": "separator_scaling_double_dissociation_cell_means_v0_1"})
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
        rows.append({"d_global_bin": str(d_global), "b_bin": str(b), "arm": arm, "n": len(values), "median_steps": median(values), "iqr_steps": q3 - q1, "thrash_threshold": threshold, "high_thrash_count": sum(value > threshold for value in values), "culprit_trace_available": False, "source": SOURCE, "provenance": "separator_scaling_high_thrash_iqr_v0_1"})
    return rows


def _collapse_depth(capacity_rows: list[dict[str, Any]], arm: str) -> int | None:
    by_depth: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in capacity_rows:
        if row["arm"] == arm:
            by_depth[int(row["d_global_bin"])].append(row)
    for depth in sorted(by_depth):
        if mean(float(row["solve_rate"]) for row in by_depth[depth]) <= LOW_SOLVE_THRESHOLD:
            return depth
    return None


def _verdict(capacity_rows: list[dict[str, Any]], dd_summary: list[dict[str, Any]], keff_rows: list[dict[str, Any]], cell_rows: list[dict[str, Any]], axes: dict[str, Any]) -> list[dict[str, Any]]:
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
    verdict = [{"check": name, "predicted": pred, "observed": obs, "pass": bool(ok), "source": SOURCE, "provenance": "separator_scaling_preregistered_verdict_v0_1"} for name, pred, obs, ok in checks]
    overall = all(row["pass"] for row in verdict) and not (kill_interaction or kill_capacity or kill_forced)
    verdict.extend([
        {"check": "kill_interaction_dglobal_not_positive", "predicted": "must be false", "observed": f"beta={chrono_d['beta']:.4f}; ci={chrono_d['ci']}", "pass": not kill_interaction, "source": SOURCE, "provenance": "separator_scaling_kill_check_v0_1"},
        {"check": "kill_capacity_law_mismatch", "predicted": "must be false", "observed": f"observed={observed}; predicted={predicted:.3f}", "pass": not kill_capacity, "source": SOURCE, "provenance": "separator_scaling_kill_check_v0_1"},
        {"check": "kill_forced_not_better", "predicted": "must be false", "observed": f"cbj={cbj['solve_rate']:.3f}; mono={mono['solve_rate']:.3f}", "pass": not kill_forced, "source": SOURCE, "provenance": "separator_scaling_kill_check_v0_1"},
        {"check": "overall_pass", "predicted": "all preregistered checks pass", "observed": f"overall_pass={overall}", "pass": overall, "source": SOURCE, "provenance": "separator_scaling_preregistered_verdict_v0_1"},
    ])
    return verdict


def _build_item(results: dict[str, Any]) -> dict[str, Any]:
    overall = next((row["pass"] for row in results["verdict"] if row["check"] == "overall_pass"), False)
    return {
        "schema_version": "log_item_contract_v1", "item_number": ITEM_NUMBER, "name": "Rung-1 separator-scaling symbolic double-dissociation patch v0.1", "status": results["status"],
        "purpose": "Patch Item058 with larger local blocks, independent d_global and b axes, local_contribution, axes precheck, pooled interaction verdict, and high-thrash diagnostics before any LLM operator run.",
        "code_added_used": [{"path": "experiments/gen_separator_scaling.py", "change": "Generates planted local-plus-boundary separator cells."}, {"path": "experiments/rung1_separator_scaling.py", "change": "Runs frozen Item051 team arms with axes/interactions/thrash diagnostics."}],
        "commands": [{"command": ".venv/bin/python -m experiments.rung1_separator_scaling", "purpose": "Run separator-scaling v0.1 symbolic patch."}], "artifacts": [_rel(RESULTS_PATH), _rel(ITEM_PATH)], "provenance": results["generation_config"],
        "result_tables": {"axes_independence_check": {"rows": [results["axes_independence_check"]]}, "instance_manifest": {"rows": results["instance_manifest"]}, "keff_by_cell": {"rows": results["keff_by_cell"]}, "instance_arm_metrics": {"rows": results["instance_arm_metrics"]}, "capacity_leg": {"rows": results["capacity_leg"]}, "double_dissociation_detail": {"rows": results["double_dissociation_detail"]}, "double_dissociation_regression": {"rows": results["double_dissociation_regression"]}, "high_thrash_diagnostics": {"rows": results["high_thrash_diagnostics"]}, "verdict": {"rows": results["verdict"]}},
        "honesty": {"does_not_establish": "Symbolic patch only; no Qwen/LLM operator run.", "failure_disambiguation": "Rows separate SOLVED, OVERFLOW_FAIL, FORWARD_DEAD_END, and NODE_CAP.", "pool_scope": "Not mixed with Item052 chain pool or Item055 natural pool; axis_balance_v01 cells are explicitly marked.", "culprit_trace_limit": "Frozen _solve lacks culprit trace; high-thrash counted without fabricating culprit correctness."},
        "decision": {"gate_outcomes": [{"gate": row["check"], "outcome": "PASS" if row["pass"] else "FAIL", "number": row["observed"]} for row in results["verdict"]], "next_step_routing": "Proceed to LLM only if overall_pass=True.", "outcome": results["status"], "overall_pass": overall},
    }


def _generation_config(n_per_cell: int, seeds: tuple[int, ...], n_per_block: int, k: int, register_capacity_d: int, comm_budget_c: int, node_cap: int, specs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"grid_version": "separator_scaling_v0_1", "seeds": list(seeds), "n_instances_per_cell": n_per_cell, "n_per_block": n_per_block, "k": k, "register_capacity_D": register_capacity_d, "comm_budget_C": comm_budget_c, "node_cap": node_cap, "cell_specs": specs, "arms": list(ARMS), "team_loop_provenance": "phase0_symbolic_loop_frozen_from_item051_separator_scaling_v0", "monolith_provenance": "global_cbj_effective_register_capacity_D_over_ln_keff_v0", "source": SOURCE}


def run(n_per_cell: int, seeds: tuple[int, ...], n_per_block: int, k: int, register_capacity_d: int, comm_budget_c: int, node_cap: int) -> dict[str, Any]:
    manifest: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    specs = _cell_specs(n_per_block)
    counts = [n_per_cell // len(seeds) + int(index < n_per_cell % len(seeds)) for index in range(len(seeds))]
    for spec in tqdm(specs, desc="separator v0.1 cells", unit="cell", dynamic_ncols=True):
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
        cell_rows.append({**spec, "n_per_block": n_per_block, "k": k, "n_instances_target": n_per_cell, "n_instances": len(cell_instances), "target_met": target_met, "attempts": attempts, "mean_local_contribution": mean(locals_) if locals_ else 0.0, "min_local_contribution": min(locals_) if locals_ else None, "max_local_contribution": max(locals_) if locals_ else None, "rejection_counters": dict(counters), "source": SOURCE, "provenance": "separator_scaling_v01_cell_generation_merged_seeds"})
    axes = _axes_independence_check(manifest)
    keff = _keff_rows(manifest)
    pool_complete = all(row["target_met"] for row in cell_rows)
    base = {"schema_version": SCHEMA_VERSION, "generated_at": _now(), "generation_config": _generation_config(n_per_cell, seeds, n_per_block, k, register_capacity_d, comm_budget_c, node_cap, specs), "cell_generation": cell_rows, "axes_independence_check": axes, "instance_manifest": manifest, "keff_by_cell": keff}
    if not axes["axes_independent"]:
        verdict = [{"check": "axes_independence_check", "predicted": "soft stop before four-arm run", "observed": f"corr={axes['corr_d_global_b']:.4f}; vif={axes['vif_d_global_b']:.4f}; min_d_per_b={axes['min_unique_d_global_per_b']}; min_b_per_d={axes['min_unique_b_per_d_global']}", "pass": False, "source": SOURCE, "provenance": "separator_scaling_axes_soft_stop_v0_1"}, {"check": "overall_pass", "predicted": "all preregistered checks pass", "observed": "overall_pass=False", "pass": False, "source": SOURCE, "provenance": "separator_scaling_preregistered_verdict_v0_1"}]
        results = {**base, "status": STATUS_AXES_STOP, "acceptance": {"overall_pass": False, "pool_complete": pool_complete, "axes_independent": False, "llm_version_allowed": False}, "instance_arm_metrics": [], "capacity_leg": [], "double_dissociation_detail": [], "double_dissociation_regression": [], "high_thrash_diagnostics": [], "verdict": verdict}
    else:
        metrics = _metric_rows(manifest, keff, register_capacity_d, comm_budget_c, node_cap)
        capacity = _capacity_leg(metrics, keff, register_capacity_d)
        dd_detail, dd_regression = _double_dissociation(metrics)
        thrash = _thrash_diagnostics(metrics)
        verdict = _verdict(capacity, dd_regression, keff, cell_rows, axes)
        overall = next(row for row in verdict if row["check"] == "overall_pass")["pass"]
        status = STATUS_PASS if overall else (STATUS_KILL if pool_complete else STATUS_PARTIAL)
        results = {**base, "status": status, "acceptance": {"overall_pass": overall, "pool_complete": pool_complete, "axes_independent": axes["axes_independent"], "llm_version_allowed": overall}, "instance_arm_metrics": metrics, "capacity_leg": capacity, "double_dissociation_detail": dd_detail, "double_dissociation_regression": dd_regression, "high_thrash_diagnostics": thrash, "verdict": verdict}
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
