"""Controlled multi-agent wrong-culprit erosion sweep for Rung-1."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _adjacency, _rel
from experiments.rung1_fallible_1d_rerun import _read_json, _write_json
from experiments.rung1_separator_p1b_full_table import GRADED_PATH, _operator_by_b
from experiments.rung1_separator_scaling import DEFAULT_NODE_CAP, _instance_from_row
from experiments.rung1_separator_llm_inloop import _load_separator_manifest


RESULTS_DIR = REPO_ROOT / "results/rung1_culprit_erosion_sweep"
RESULTS_PATH = RESULTS_DIR / "results.json"
PAIRED_PATH = REPO_ROOT / "results/rung1_paired_register_requirement/results.json"
SCHEMA_VERSION = "rung1_culprit_erosion_sweep_v0"
RHO_CULPRIT_VALUES = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
RHO_COMMIT_VALUES = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
B_VALUES = (2, 4)
DEPTHS = (4, 5, 6, 7, 9, 10, 12)
REGISTER_CAPACITY_D = 16
COMM_BUDGET_C = 16


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unit(*parts: Any) -> float:
    text = "::".join(str(part) for part in parts)
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(2**64)


def _quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p10": None, "p25": None, "median": None, "p75": None, "p90": None, "max": None, "mean": None}
    xs = sorted(values)
    def q(frac: float) -> float:
        index = frac * (len(xs) - 1)
        lo = math.floor(index)
        hi = math.ceil(index)
        if lo == hi:
            return xs[lo]
        return xs[lo] * (hi - index) + xs[hi] * (index - lo)
    return {"min": xs[0], "p10": q(0.1), "p25": q(0.25), "median": median(xs), "p75": q(0.75), "p90": q(0.9), "max": xs[-1], "mean": mean(xs)}


def _ols_slope_ci(points: list[tuple[float, float]]) -> dict[str, Any]:
    if len(points) < 3:
        return {"slope": None, "intercept": None, "n": len(points), "ci95": [None, None], "se": None}
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    xbar = mean(xs)
    ybar = mean(ys)
    sxx = sum((x - xbar) ** 2 for x in xs)
    if sxx == 0:
        return {"slope": None, "intercept": None, "n": len(points), "ci95": [None, None], "se": None}
    slope = sum((x - xbar) * (y - ybar) for x, y in points) / sxx
    intercept = ybar - slope * xbar
    residuals = [y - (intercept + slope * x) for x, y in points]
    if len(points) > 2:
        sigma2 = sum(r * r for r in residuals) / (len(points) - 2)
        se = math.sqrt(sigma2 / sxx)
        ci = [slope - 1.96 * se, slope + 1.96 * se]
    else:
        se = None
        ci = [None, None]
    return {"slope": slope, "intercept": intercept, "n": len(points), "ci95": ci, "se": se}


def _select_manifest(n_per_cell: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in _load_separator_manifest():
        b = int(row.get("b", -1))
        depth = int(row.get("d_global_reference", -1))
        if b in B_VALUES and depth in DEPTHS:
            grouped[(b, depth)].append(row)
    selected: list[dict[str, Any]] = []
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda row: (int(row["seed"]), int(row["source_index"]), str(row["instance_id"])))
        selected.extend(rows[:n_per_cell])
    return selected


def _shared_channel_load(instance: Any, adj: dict[int, set[int]], assignment: dict[int, int], vertex: int, nogood: set[int] | None = None) -> int:
    block = instance.partitions[vertex]
    visible_boundary_commitments = sum(1 for neighbor in adj[vertex] if neighbor in assignment and instance.partitions[neighbor] != block)
    return max(visible_boundary_commitments, len(nogood or set()))


def _wrong_target(instance_id: str, rho: float, register_d: int, step: int, register: list[dict[str, int]], target_index: int) -> tuple[int, bool]:
    if not register or _unit(instance_id, "wrong_culprit", rho, register_d, step, len(register), target_index) >= rho:
        return target_index, False
    target_agent = register[target_index]["agent"]
    candidates = [idx for idx, entry in enumerate(register) if entry["agent"] != target_agent]
    if not candidates:
        candidates = [idx for idx in range(len(register)) if idx != target_index]
    if not candidates:
        return target_index, False
    choice = int(_unit(instance_id, "wrong_culprit_choice", rho, register_d, step) * len(candidates))
    return candidates[min(choice, len(candidates) - 1)], True


def _team_trace(row: dict[str, Any], arm: str, rho_culprit: float, node_cap: int, register_d: int = REGISTER_CAPACITY_D, comm_budget: int = COMM_BUDGET_C) -> dict[str, Any]:
    instance = _instance_from_row(row)
    adj = _adjacency(instance.n, instance.edges)
    order = list(instance.order)
    position = {vertex: index for index, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    register: list[dict[str, int]] = []
    local_register_counts: Counter[int] = Counter()
    next_choice = {vertex: 0 for vertex in order}
    steps = 0
    retractions = 0
    recovery_events = 0
    recovery_comm_tokens = 0
    commit_messages = 0
    commit_comm_tokens = 0
    wrong_culprit_events = 0
    repeated_conflict_events = 0
    previous_conflict_signature: tuple[int, tuple[int, ...]] | None = None
    peak_shared_channel = 0
    peak_sum_local_register = 0
    peak_local_register_per_agent = 0
    cursor = 0
    while True:
        if steps >= node_cap:
            return _team_row(row, arm, rho_culprit, "NODE_CAP", False, steps, retractions, recovery_events, recovery_comm_tokens, commit_messages, commit_comm_tokens, wrong_culprit_events, repeated_conflict_events, peak_shared_channel, peak_sum_local_register, peak_local_register_per_agent, register_d, comm_budget)
        if cursor >= len(order):
            return _team_row(row, arm, rho_culprit, "SOLVED", True, steps, retractions, recovery_events, recovery_comm_tokens, commit_messages, commit_comm_tokens, wrong_culprit_events, repeated_conflict_events, peak_shared_channel, peak_sum_local_register, peak_local_register_per_agent, register_d, comm_budget)
        vertex = order[cursor]
        steps += 1
        peak_shared_channel = max(peak_shared_channel, _shared_channel_load(instance, adj, assignment, vertex))
        blockers_by_color: dict[int, list[int]] = {}
        boundary_blocker_by_color: dict[int, int] = {}
        feasible = set()
        for color in range(1, instance.k + 1):
            blockers = [neighbor for neighbor in adj[vertex] if assignment.get(neighbor) == color]
            if blockers:
                blockers_by_color[color] = blockers
                boundary = [neighbor for neighbor in blockers if instance.partitions[neighbor] != instance.partitions[vertex]]
                if boundary:
                    boundary_blocker_by_color[color] = min(boundary, key=lambda item: position[item])
            else:
                feasible.add(color)
        ordered = [color for color in instance.color_orders.get(vertex, tuple(range(1, instance.k + 1))) if color in feasible]
        choice_index = next_choice.get(vertex, 0)
        if choice_index < len(ordered):
            color = ordered[choice_index]
            next_choice[vertex] = choice_index + 1
            agent = instance.partitions[vertex]
            if len(register) >= register_d:
                return _team_row(row, arm, rho_culprit, "OVERFLOW_FAIL", False, steps, retractions, recovery_events, recovery_comm_tokens, commit_messages, commit_comm_tokens, wrong_culprit_events, repeated_conflict_events, peak_shared_channel, peak_sum_local_register, peak_local_register_per_agent, register_d, comm_budget)
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor, "agent": agent})
            local_register_counts[agent] += 1
            peak_local_register_per_agent = max(peak_local_register_per_agent, local_register_counts[agent])
            peak_sum_local_register = max(peak_sum_local_register, sum(local_register_counts.values()))
            commit_messages += 1
            commit_comm_tokens += 4
            cursor += 1
            continue
        nogood = set(boundary_blocker_by_color.values())
        recovery_events += 1
        event_comm = 2 + 2 * len(nogood)
        recovery_comm_tokens += event_comm
        peak_shared_channel = max(peak_shared_channel, _shared_channel_load(instance, adj, assignment, vertex, nogood))
        signature = (vertex, tuple(sorted(nogood)))
        if previous_conflict_signature == signature:
            repeated_conflict_events += 1
        previous_conflict_signature = signature
        if arm == "chronological_rollback_team" or not nogood:
            target_index = len(register) - 1
        else:
            target_vertex = max(nogood, key=lambda item: position[item])
            target_index = max((idx for idx, entry in enumerate(register) if entry["vertex"] == target_vertex), default=len(register) - 1)
            target_index, wrong = _wrong_target(row["instance_id"], rho_culprit, register_d, steps, register, target_index)
            wrong_culprit_events += int(wrong)
        if target_index < 0 or not register:
            return _team_row(row, arm, rho_culprit, "NO_RECOVERY_TARGET", False, steps, retractions, recovery_events, recovery_comm_tokens, commit_messages, commit_comm_tokens, wrong_culprit_events, repeated_conflict_events, peak_shared_channel, peak_sum_local_register, peak_local_register_per_agent, register_d, comm_budget)
        popped = register[target_index:]
        retractions += len(popped)
        recovery_comm_tokens += 2 * len(popped)
        for entry in popped:
            assignment.pop(entry["vertex"], None)
            local_register_counts[int(entry["agent"])] -= 1
            if local_register_counts[int(entry["agent"])] <= 0:
                local_register_counts.pop(int(entry["agent"]), None)
        for entry in popped[1:]:
            next_choice[entry["vertex"]] = 0
        next_choice[vertex] = 0
        cursor = register[target_index]["order_index"]
        register = register[:target_index]


def _team_row(row: dict[str, Any], arm: str, rho: float, status: str, solved: bool, steps: int, retractions: int, recovery_events: int, recovery_comm_tokens: int, commit_messages: int, commit_comm_tokens: int, wrong_culprit_events: int, repeated_conflict_events: int, peak_shared_channel: int, peak_sum_local_register: int, peak_local_register_per_agent: int, register_d: int, comm_budget: int) -> dict[str, Any]:
    return {
        "instance_id": row["instance_id"],
        "b": int(row["b"]),
        "d_global_reference": int(row["d_global_reference"]),
        "arm": arm,
        "rho_culprit": rho,
        "status": status,
        "solved": solved,
        "steps": steps,
        "total_retractions": retractions,
        "recovery_events": recovery_events,
        "recovery_comm_tokens": recovery_comm_tokens,
        "recovery_comm_per_event": recovery_comm_tokens / max(1, recovery_events),
        "commit_messages": commit_messages,
        "commit_comm_tokens": commit_comm_tokens,
        "comm_tokens": recovery_comm_tokens + commit_comm_tokens,
        "wrong_culprit_events": wrong_culprit_events,
        "wrong_culprit_rate_observed": wrong_culprit_events / max(1, recovery_events),
        "repeated_conflict_events": repeated_conflict_events,
        "peak_shared_channel": peak_shared_channel,
        "peak_sum_local_register": peak_sum_local_register,
        "peak_local_register_per_agent": peak_local_register_per_agent,
        "register_capacity_D": register_d,
        "comm_budget_C": comm_budget,
        "source": SOURCE,
        "provenance": "rung1_culprit_erosion_trace_v0",
    }


def _cell_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    keys = sorted({(row["rho_culprit"], row["arm"], row["b"], row["d_global_reference"]) for row in rows})
    for rho, arm, b, depth in keys:
        subset = [row for row in rows if row["rho_culprit"] == rho and row["arm"] == arm and row["b"] == b and row["d_global_reference"] == depth]
        eventful = [row for row in subset if row["recovery_events"] > 0]
        out.append({
            "rho_culprit": rho,
            "arm": arm,
            "b": b,
            "d_global_reference": depth,
            "n_instances": len(subset),
            "n_recovery_events": sum(row["recovery_events"] for row in subset),
            "status_counts": dict(Counter(row["status"] for row in subset)),
            "solve_rate": sum(row["solved"] for row in subset) / max(1, len(subset)),
            "mean_recovery_comm_per_event": mean([row["recovery_comm_per_event"] for row in eventful]) if eventful else 0.0,
            "mean_comm_tokens": mean([row["comm_tokens"] for row in subset]) if subset else 0.0,
            "mean_retractions": mean([row["total_retractions"] for row in subset]) if subset else 0.0,
            "mean_wrong_culprit_rate_observed": mean([row["wrong_culprit_rate_observed"] for row in eventful]) if eventful else 0.0,
            "source": SOURCE,
            "provenance": "rung1_culprit_erosion_cell_summary_v0",
        })
    return out


def _erosion_curve(cell_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    chrono_by_b = {}
    for b in B_VALUES:
        chrono_points = [(float(row["d_global_reference"]), float(row["mean_recovery_comm_per_event"])) for row in cell_rows if row["arm"] == "chronological_rollback_team" and row["b"] == b and row["n_recovery_events"] > 0]
        chrono_by_b[b] = _ols_slope_ci(chrono_points)
    for rho in RHO_CULPRIT_VALUES:
        for b in B_VALUES:
            points = [(float(row["d_global_reference"]), float(row["mean_recovery_comm_per_event"])) for row in cell_rows if row["arm"] == "cbj_bounded_team" and row["rho_culprit"] == rho and row["b"] == b and row["n_recovery_events"] > 0]
            fit = _ols_slope_ci(points)
            chrono = chrono_by_b[b]
            indistinguishable = fit["ci95"][0] is not None and chrono["ci95"][0] is not None and not (fit["ci95"][1] < chrono["ci95"][0] or chrono["ci95"][1] < fit["ci95"][0])
            out.append({"rho_culprit": rho, "b": b, "cbj_comm_vs_depth_slope": fit["slope"], "cbj_ci95": fit["ci95"], "cbj_n_depth_points": fit["n"], "chronological_reference_slope": chrono["slope"], "chronological_ci95": chrono["ci95"], "cbj_statistically_indistinguishable_from_chrono": indistinguishable, "n_recovery_events": sum(row["n_recovery_events"] for row in cell_rows if row["arm"] == "cbj_bounded_team" and row["rho_culprit"] == rho and row["b"] == b), "source": SOURCE, "provenance": "rung1_culprit_erosion_curve_v0"})
    return out


def _wrong_commit_trace(row: dict[str, Any], rho: float, register_d: int, node_cap: int, keff: float) -> dict[str, Any]:
    instance = _instance_from_row(row)
    adj = _adjacency(instance.n, instance.edges)
    order = list(instance.order)
    position = {vertex: idx for idx, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    register: list[dict[str, int]] = []
    next_choice = {vertex: 0 for vertex in order}
    steps = 0
    retractions = 0
    wrong_commitments = 0
    max_backjump = 0
    first_conflict_depth = int(instance.reference_depth)
    cursor = 0
    def occupancy() -> int:
        return math.ceil(max(1, first_conflict_depth, max_backjump) * math.log(max(keff, 1.0001)))
    while True:
        peak = occupancy()
        if steps >= node_cap:
            return _wrong_commit_row(row, rho, register_d, "NODE_CAP", False, steps, retractions, peak, wrong_commitments)
        if cursor >= len(order):
            if peak >= register_d:
                return _wrong_commit_row(row, rho, register_d, "OVERFLOW_FAIL", False, steps, retractions, peak, wrong_commitments)
            return _wrong_commit_row(row, rho, register_d, "SOLVED", True, steps, retractions, peak, wrong_commitments)
        vertex = order[cursor]
        steps += 1
        blockers_by_color: dict[int, list[int]] = {}
        feasible = []
        for color in range(1, instance.k + 1):
            blockers = [neighbor for neighbor in adj[vertex] if assignment.get(neighbor) == color]
            if blockers:
                blockers_by_color[color] = blockers
            else:
                feasible.append(color)
        ordered = [color for color in instance.color_orders.get(vertex, tuple(range(1, instance.k + 1))) if color in feasible]
        if len(ordered) > 1 and _unit(row["instance_id"], "wrong_commit", rho, register_d, steps, vertex) < rho:
            wrong_commitments += 1
            offset = 1 + int(_unit(row["instance_id"], "wrong_commit_choice", rho, register_d, steps, vertex) * (len(ordered) - 1))
            ordered = ordered[offset:] + ordered[:offset]
        choice_index = next_choice.get(vertex, 0)
        if choice_index < len(ordered):
            color = ordered[choice_index]
            next_choice[vertex] = choice_index + 1
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor})
            cursor += 1
            continue
        nogood = {min(blockers, key=lambda item: position[item]) for blockers in blockers_by_color.values()}
        earliest = min((position[item] for item in nogood), default=cursor)
        first_conflict_depth = max(first_conflict_depth, cursor - earliest)
        peak = occupancy()
        if peak >= register_d:
            return _wrong_commit_row(row, rho, register_d, "OVERFLOW_FAIL", False, steps, retractions, peak, wrong_commitments)
        if not register:
            return _wrong_commit_row(row, rho, register_d, "NO_RECOVERY_TARGET", False, steps, retractions, peak, wrong_commitments)
        target = max(nogood, key=lambda item: position[item]) if nogood else register[-1]["vertex"]
        target_index = max(index for index, entry in enumerate(register) if entry["vertex"] == target)
        popped = register[target_index:]
        max_backjump = max(max_backjump, len(popped))
        retractions += len(popped)
        for entry in popped:
            assignment.pop(entry["vertex"], None)
        for entry in popped[1:]:
            next_choice[entry["vertex"]] = 0
        next_choice[vertex] = 0
        cursor = register[target_index]["order_index"]
        register = register[:target_index]


def _wrong_commit_row(row: dict[str, Any], rho: float, register_d: int, status: str, solved: bool, steps: int, retractions: int, peak: int, wrong_commitments: int) -> dict[str, Any]:
    return {"instance_id": row["instance_id"], "d_global_reference": int(row["d_global_reference"]), "rho_commit": rho, "register_capacity_D": register_d, "status": status, "solved": solved, "steps": steps, "total_retractions": retractions, "peak_register_occupancy_proxy": peak, "wrong_commitments": wrong_commitments, "source": SOURCE, "provenance": "rung1_wrong_commit_trace_v0"}


def _run_wrong_commitment(selected_ids: list[str], manifest_by_id: dict[str, dict[str, Any]], real_rates: dict[str, float], keff: float, node_cap: int) -> dict[str, Any]:
    rows = []
    by_rho = []
    for rho in RHO_COMMIT_VALUES:
        subset = [_wrong_commit_trace(manifest_by_id[instance_id], rho, REGISTER_CAPACITY_D, node_cap, keff) for instance_id in selected_ids]
        rows.extend(subset)
        counts = Counter(row["status"] for row in subset)
        rates = {key: value / max(1, len(subset)) for key, value in counts.items()}
        l1 = sum(abs(rates.get(key, 0.0) - real_rates.get(key, 0.0)) for key in sorted(set(rates) | set(real_rates)))
        by_rho.append({"rho_commit": rho, "n_instances": len(subset), "failure_mode_mix": dict(counts), "failure_mode_rates": rates, "mean_wrong_commitments": mean([row["wrong_commitments"] for row in subset]) if subset else 0.0, "l1_distance_to_4b_stage1_mix": l1, "source": SOURCE, "provenance": "rung1_wrong_commit_summary_v0"})
    best = min(by_rho, key=lambda row: row["l1_distance_to_4b_stage1_mix"])
    return {"by_rho": by_rho, "instance_rows": rows, "best_match": best, "reproduces_4b_corruption": best["l1_distance_to_4b_stage1_mix"] <= 0.25, "source": SOURCE, "provenance": "rung1_wrong_commit_closure_v0"}


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _select_manifest(args.n_per_cell)
    operator_by_b = _operator_by_b(_read_json(GRADED_PATH))
    keff = float(operator_by_b[2]["k_eff_clean"])
    rows = []
    for row in manifest:
        for rho in RHO_CULPRIT_VALUES:
            rows.append(_team_trace(row, "cbj_bounded_team", rho, args.node_cap))
        rows.append(_team_trace(row, "chronological_rollback_team", 0.0, args.node_cap))
    cells = _cell_summary(rows)
    curve = _erosion_curve(cells)
    indist = [row["rho_culprit"] for row in curve if row["b"] == 2 and row["cbj_statistically_indistinguishable_from_chrono"]]
    rho_star = min(indist) if indist else None
    slopes = [row for row in curve if row["b"] == 2]
    slope_values = [row["cbj_comm_vs_depth_slope"] for row in slopes if row["cbj_comm_vs_depth_slope"] is not None]
    if not slope_values:
        verdict = "underpowered"
    elif max(slope_values) - min(slope_values) < 0.05:
        verdict = "no_erosion_decoupling_flat_across_rho"
    elif rho_star is not None:
        verdict = "erosion_confirmed_cbj_degrades_to_chrono_with_wrong_culprits"
    else:
        verdict = "underpowered"

    b_axis_points = [(float(row["b"]), float(row["mean_recovery_comm_per_event"])) for row in cells if row["arm"] == "cbj_bounded_team" and row["rho_culprit"] == 0.0 and row["n_recovery_events"] > 0]
    b_axis = {"rho_culprit": 0.0, "fit_comm_vs_b": _ols_slope_ci(b_axis_points), "cell_rows": [row for row in cells if row["arm"] == "cbj_bounded_team" and row["rho_culprit"] == 0.0], "source": SOURCE, "provenance": "rung1_culprit_erosion_b_axis_v0"}

    paired = _read_json(PAIRED_PATH)
    selected_ids = [row["instance_id"] for row in paired["piece1"]["clean_requirements"]]
    real_counts = paired["piece1"]["summary"]["stage1_status_counts"]
    real_n = sum(real_counts.values())
    real_rates = {key: value / max(1, real_n) for key, value in real_counts.items()}
    manifest_by_id = {row["instance_id"]: row for row in _load_separator_manifest()}
    wrong_commit = _run_wrong_commitment(selected_ids, manifest_by_id, real_rates, keff, args.node_cap)

    if verdict == "erosion_confirmed_cbj_degrades_to_chrono_with_wrong_culprits":
        determination = "multi_agent_wrong_culprit_erosion_confirmed"
        next_move = "After P1c concise-output redesign, place the real LLM culprit-error rate on the erosion curve."
    elif verdict == "no_erosion_decoupling_flat_across_rho":
        determination = "multi_agent_wrong_culprit_erosion_negative"
        next_move = "Report the falsification and inspect whether the comm observable or wrong-culprit instrument is too weak."
    else:
        determination = "multi_agent_wrong_culprit_erosion_underpowered"
        next_move = "Increase n/depth span or strengthen the wrong-culprit instrument before real-LLM placement."

    payload = {"schema_version": SCHEMA_VERSION, "status": "RUNG1_CULPRIT_EROSION_SWEEP_COMPLETE", "generated_at": datetime.now(timezone.utc).isoformat(), "pieceB1_erosion_curve": curve, "pieceB1_cell_summary": cells, "pieceB1_instance_rows": rows, "pieceB1_b_axis": b_axis, "pieceB1_verdict": verdict, "pieceB1_cbj_chrono_indistinguishable_rho": rho_star, "pieceB2_single_agent": wrong_commit, "headline": {"determination": determination, "pieceB1_verdict": verdict, "pieceB2_reproduces_4b_corruption": wrong_commit["reproduces_4b_corruption"], "single_next_move": next_move}, "source": SOURCE, "provenance": "rung1_culprit_erosion_sweep_v0"}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run controlled wrong-culprit erosion and wrong-commitment closure sweeps.")
    parser.add_argument("--output", type=Path, default=RESULTS_PATH)
    parser.add_argument("--n-per-cell", type=int, default=12)
    parser.add_argument("--node-cap", type=int, default=DEFAULT_NODE_CAP)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
