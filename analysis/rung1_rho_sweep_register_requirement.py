"""Offline trail-ratio recompute and controlled rho sweep for Rung-1."""

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


RESULTS_DIR = REPO_ROOT / "results/rung1_rho_sweep_register_requirement"
RESULTS_PATH = RESULTS_DIR / "results.json"
PAIRED_PATH = REPO_ROOT / "results/rung1_paired_register_requirement/results.json"
SCHEMA_VERSION = "rung1_rho_sweep_register_requirement_v0"
RHO_VALUES = (0.0, 0.1, 0.2, 0.34, 0.5, 0.66)
D_LADDER = (16, 24, 32)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p10": None, "p25": None, "median": None, "p75": None, "p90": None, "max": None, "mean": None}
    xs = sorted(values)
    def q(frac: float) -> float:
        index = frac * (len(xs) - 1)
        low = math.floor(index)
        high = math.ceil(index)
        if low == high:
            return xs[low]
        return xs[low] * (high - index) + xs[high] * (index - low)
    return {"min": xs[0], "p10": q(0.10), "p25": q(0.25), "median": median(xs), "p75": q(0.75), "p90": q(0.90), "max": xs[-1], "mean": mean(xs)}


def _ratio_summary(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return {"n": len(values), "gt_1_count": sum(value > 1.0 for value in values), "gt_1_fraction": sum(value > 1.0 for value in values) / max(1, len(values)), "distribution": _quantiles(values)}


def _piece_a(paired: dict[str, Any]) -> dict[str, Any]:
    piece1 = paired["piece1"]
    clean_by_id = {row["instance_id"]: row for row in piece1["clean_requirements"]}
    rows = []
    for row in piece1["stage1_rows"]:
        if row.get("status") != "SOLVED":
            continue
        clean = clean_by_id[row["instance_id"]]
        fallible_trail = int(row.get("steps") or row.get("llm_calls") or row.get("propagation_opportunity_steps") or 0)
        fallible_retractions = int(row.get("total_retractions") or 0)
        clean_trail = int(clean["clean_stage1_steps"])
        clean_retractions = int(clean["clean_stage1_retractions"])
        rows.append({
            "instance_id": row["instance_id"],
            "d_global_reference": int(row["d_global_reference"]),
            "clean_stage1_steps": clean_trail,
            "fallible_trail_length": fallible_trail,
            "trail_length_ratio": fallible_trail / max(1, clean_trail),
            "clean_stage1_retractions": clean_retractions,
            "fallible_retractions": fallible_retractions,
            "retraction_ratio": fallible_retractions / max(1, clean_retractions),
            "fallible_llm_calls": int(row.get("llm_calls") or 0),
            "fallible_propagation_opportunity_steps": int(row.get("propagation_opportunity_steps") or 0),
            "source": SOURCE,
            "provenance": "rung1_trail_ratio_recompute_instance_v0",
        })
    trail_summary = _ratio_summary(rows, "trail_length_ratio")
    retraction_summary = _ratio_summary(rows, "retraction_ratio")
    verdict = "partial_subthreshold_inflation" if trail_summary["gt_1_fraction"] > 0.5 or retraction_summary["gt_1_fraction"] > 0.5 else "no_solved_subset_trail_inflation"
    return {
        "status": "COMPLETE",
        "matched_solved_D16_instances": len(rows),
        "fallible_trail_definition": "steps if present else llm_calls else propagation_opportunity_steps",
        "clean_trail_definition": "clean_stage1_steps from paired clean requirement",
        "trail_length_ratio": trail_summary,
        "retraction_ratio": retraction_summary,
        "verdict": verdict,
        "instance_rows": rows,
        "source": SOURCE,
        "provenance": "rung1_trail_ratio_recompute_v0",
    }


def _stable_unit(*parts: Any) -> float:
    text = "::".join(str(part) for part in parts)
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(2 ** 64)


def _rho_for_depth_profile(row: dict[str, Any]) -> float:
    depth = int(row["d_global_reference"])
    if depth <= 5:
        return 0.32
    if depth <= 7:
        return 0.50
    return 0.80


def _rho_trace(row: dict[str, Any], register_d: int, rho: float, keff: float, node_cap: int, profile: str = "constant") -> dict[str, Any]:
    instance = _instance_from_row(row)
    adj = _adjacency(instance.n, instance.edges)
    order = list(instance.order)
    position = {vertex: index for index, vertex in enumerate(order)}
    assignment: dict[int, int] = {}
    register: list[dict[str, int]] = []
    next_choice = {vertex: 0 for vertex in order}
    steps = 0
    retractions = 0
    cursor = 0
    first_conflict_depth = int(instance.reference_depth)
    max_backjump = 0
    dropped_prunes = 0
    sound_prunes = 0
    conflict_steps = 0

    def depth_component() -> int:
        return max(1, first_conflict_depth, max_backjump)

    def occupancy() -> int:
        return math.ceil(depth_component() * math.log(max(keff, 1.0001)))

    def current_rho() -> float:
        return _rho_for_depth_profile(row) if profile == "depth_profile" else rho

    while True:
        peak = occupancy()
        if steps >= node_cap:
            return _rho_row(row, register_d, rho, profile, keff, "NODE_CAP", False, steps, retractions, peak, None, sound_prunes, dropped_prunes, conflict_steps)
        if cursor >= len(order):
            if peak >= register_d:
                return _rho_row(row, register_d, rho, profile, keff, "OVERFLOW_FAIL", False, steps, retractions, peak, depth_component(), sound_prunes, dropped_prunes, conflict_steps)
            return _rho_row(row, register_d, rho, profile, keff, "SOLVED", True, steps, retractions, peak, None, sound_prunes, dropped_prunes, conflict_steps)
        vertex = order[cursor]
        steps += 1
        blockers_by_color: dict[int, list[int]] = {}
        feasible = set()
        for color in range(1, instance.k + 1):
            blockers = [neighbor for neighbor in adj[vertex] if assignment.get(neighbor) == color]
            if blockers:
                blockers_by_color[color] = blockers
            else:
                feasible.add(color)
        ordered = [color for color in instance.color_orders.get(vertex, tuple(range(1, instance.k + 1))) if color in feasible]
        choice_index = next_choice.get(vertex, 0)
        if choice_index < len(ordered):
            color = ordered[choice_index]
            next_choice[vertex] = choice_index + 1
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor})
            cursor += 1
            continue

        conflict_steps += 1
        nogood = set()
        for color, blockers in blockers_by_color.items():
            blocker = min(blockers, key=lambda item: position[item])
            sound_prunes += 1
            drop = _stable_unit(row["instance_id"], profile, rho, register_d, steps, vertex, color, blocker) < current_rho()
            if drop:
                dropped_prunes += 1
            else:
                nogood.add(blocker)
        earliest = min((position[item] for item in nogood), default=cursor)
        first_conflict_depth = max(first_conflict_depth, cursor - earliest)
        peak = occupancy()
        if peak >= register_d:
            return _rho_row(row, register_d, rho, profile, keff, "OVERFLOW_FAIL", False, steps, retractions, peak, depth_component(), sound_prunes, dropped_prunes, conflict_steps)
        if not register:
            return _rho_row(row, register_d, rho, profile, keff, "NO_RECOVERY_TARGET", False, steps, retractions, peak, None, sound_prunes, dropped_prunes, conflict_steps)
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


def _rho_row(row: dict[str, Any], register_d: int, rho: float, profile: str, keff: float, status: str, solved: bool, steps: int, retractions: int, peak: int, overflow_depth: int | None, sound_prunes: int, dropped_prunes: int, conflict_steps: int) -> dict[str, Any]:
    return {
        "instance_id": row["instance_id"],
        "b": int(row["b"]),
        "d_global_reference": int(row["d_global_reference"]),
        "register_capacity_D": int(register_d),
        "rho": rho,
        "rho_profile": profile,
        "k_eff": float(keff),
        "status": status,
        "solved": bool(solved),
        "steps": int(steps),
        "total_retractions": int(retractions),
        "peak_register_occupancy_proxy": int(peak),
        "overflowed": status == "OVERFLOW_FAIL",
        "overflow_depth": overflow_depth,
        "sound_prunes": int(sound_prunes),
        "dropped_prunes": int(dropped_prunes),
        "observed_drop_rate": dropped_prunes / max(1, sound_prunes),
        "conflict_steps": int(conflict_steps),
        "source": SOURCE,
        "provenance": "rung1_rho_sweep_trace_v0",
    }


def _run_ladder(row: dict[str, Any], clean_req: dict[str, Any], rho: float, keff: float, node_cap: int, profile: str = "constant") -> dict[str, Any]:
    ladder_rows = []
    final_status = None
    min_solving_d = None
    for register_d in D_LADDER:
        trace = _rho_trace(row, register_d, rho, keff, node_cap, profile)
        ladder_rows.append(trace)
        final_status = trace["status"]
        if trace["status"] == "SOLVED":
            min_solving_d = register_d
            break
        if trace["status"] != "OVERFLOW_FAIL":
            break
    clean_min = D_LADDER[0]
    gap = min_solving_d - clean_min if min_solving_d is not None else None
    return {
        "instance_id": row["instance_id"],
        "d_global_reference": int(row["d_global_reference"]),
        "rho": rho,
        "rho_profile": profile,
        "clean_min_solving_D": int(clean_req["clean_min_solving_D"]),
        "clean_ladder_baseline_D": clean_min,
        "clean_stage1_steps": int(clean_req["clean_stage1_steps"]),
        "clean_stage1_retractions": int(clean_req["clean_stage1_retractions"]),
        "rho_min_solving_D": min_solving_d,
        "register_requirement_gap": gap,
        "right_censored_gap_lower_bound": (max(D_LADDER) + 1 - clean_min) if min_solving_d is None else None,
        "inflated_strict": bool(min_solving_d is None or min_solving_d > clean_min),
        "final_status": final_status,
        "trail_length_ratio_at_final": ladder_rows[-1]["steps"] / max(1, int(clean_req["clean_stage1_steps"])),
        "retraction_ratio_at_final": ladder_rows[-1]["total_retractions"] / max(1, int(clean_req["clean_stage1_retractions"])),
        "ladder_rows": ladder_rows,
        "source": SOURCE,
        "provenance": "rung1_rho_sweep_ladder_instance_v0",
    }


def _summarize_ladder(rows: list[dict[str, Any]], rho: float, profile: str) -> dict[str, Any]:
    statuses = Counter(row["final_status"] for row in rows)
    gaps = [row["register_requirement_gap"] for row in rows if row.get("register_requirement_gap") is not None]
    censored = [row["right_censored_gap_lower_bound"] for row in rows if row.get("right_censored_gap_lower_bound") is not None]
    trail_ratios = [row["trail_length_ratio_at_final"] for row in rows]
    ret_ratios = [row["retraction_ratio_at_final"] for row in rows]
    n = len(rows)
    return {
        "rho": rho,
        "rho_profile": profile,
        "n_instances": n,
        "inflation_fraction": sum(1 for row in rows if row.get("inflated_strict")) / max(1, n),
        "failure_mode_mix": dict(statuses),
        "failure_mode_rates": {key: value / max(1, n) for key, value in statuses.items()},
        "register_requirement_gap": {"n_observed": len(gaps), "distribution": _quantiles([float(value) for value in gaps]), "right_censored_count": len(censored), "right_censored_lower_bound_distribution": _quantiles([float(value) for value in censored])},
        "trail_length_ratio": {"distribution": _quantiles(trail_ratios), "gt_1_fraction": sum(value > 1.0 for value in trail_ratios) / max(1, n)},
        "retraction_ratio": {"distribution": _quantiles(ret_ratios), "gt_1_fraction": sum(value > 1.0 for value in ret_ratios) / max(1, n)},
        "source": SOURCE,
        "provenance": "rung1_rho_sweep_summary_v0",
    }


def _transition(by_rho: list[dict[str, Any]]) -> dict[str, Any]:
    corruption_candidates = []
    inflation_candidates = []
    for row in by_rho:
        rates = row["failure_mode_rates"]
        no_recovery = rates.get("NO_RECOVERY_TARGET", 0.0) + rates.get("NODE_CAP", 0.0)
        unsolved = 1.0 - rates.get("SOLVED", 0.0)
        if row["rho"] > 0 and row["inflation_fraction"] > 0 and no_recovery < 0.10:
            inflation_candidates.append(row["rho"])
        if row["rho"] > 0 and (no_recovery >= 0.10 or unsolved >= 0.35):
            corruption_candidates.append(row["rho"])
    rho_star = min(corruption_candidates) if corruption_candidates else None
    if inflation_candidates and corruption_candidates:
        shape = "bounded_inflation_to_corruption"
    elif inflation_candidates:
        shape = "bounded_inflation_no_corruption_in_range"
    elif corruption_candidates:
        shape = "corruption_without_low_rho_bounded_inflation"
    else:
        shape = "flat_or_null_in_range"
    return {"transition_rho": rho_star, "transition_shape": shape, "bounded_inflation_rhos": inflation_candidates, "corruption_rhos": corruption_candidates, "source": SOURCE, "provenance": "rung1_rho_sweep_transition_v0"}


def run(args: argparse.Namespace) -> dict[str, Any]:
    paired = _read_json(PAIRED_PATH)
    piece_a = _piece_a(paired)
    manifest_by_id = {row["instance_id"]: row for row in _load_separator_manifest()}
    clean_requirements = {row["instance_id"]: row for row in paired["piece1"]["clean_requirements"]}
    selected_ids = [row["instance_id"] for row in paired["piece1"]["clean_requirements"]]
    operator_by_b = _operator_by_b(_read_json(GRADED_PATH))
    keff = float(operator_by_b[2]["k_eff_clean"])

    piece_b_rows = []
    piece_b_by_rho = []
    for rho in args.rhos:
        rows = [_run_ladder(manifest_by_id[instance_id], clean_requirements[instance_id], rho, keff, args.node_cap, "constant") for instance_id in selected_ids]
        piece_b_rows.extend(rows)
        piece_b_by_rho.append(_summarize_ladder(rows, rho, "constant"))

    depth_rows = [_run_ladder(manifest_by_id[instance_id], clean_requirements[instance_id], 0.66, keff, args.node_cap, "depth_profile") for instance_id in selected_ids]
    depth_summary = _summarize_ladder(depth_rows, 0.66, "depth_profile")
    real_counts = paired["piece1"]["summary"]["stage1_status_counts"]
    real_n = sum(real_counts.values())
    real_rates = {key: value / max(1, real_n) for key, value in real_counts.items()}
    depth_rates = depth_summary["failure_mode_rates"]
    match_l1 = sum(abs(depth_rates.get(key, 0.0) - real_rates.get(key, 0.0)) for key in sorted(set(depth_rates) | set(real_rates)))
    depth_match = {"profile": "depth<=5 rho=0.32, depth 6-7 rho=0.50, depth>=9 rho=0.80", "summary": depth_summary, "real_4b_stage1_rates": real_rates, "l1_distance_to_4b_stage1_mix": match_l1, "matches_4b_failure_mix": match_l1 <= 0.25, "source": SOURCE, "provenance": "rung1_rho_sweep_depth_profile_match_v0"}

    transition = _transition(piece_b_by_rho)
    high = next((row for row in piece_b_by_rho if abs(row["rho"] - 0.66) < 1e-9), piece_b_by_rho[-1])
    four_b_placement = {"real_4b_miss_rate_approx": 0.66, "real_4b_stage1_status_counts": real_counts, "real_4b_stage1_rates": real_rates, "rho_0_66_controlled_summary": high, "depth_dependent_profile_summary": depth_summary, "placement": "corruption_regime" if high["failure_mode_rates"].get("SOLVED", 0.0) < 0.80 or high["failure_mode_rates"].get("NO_RECOVERY_TARGET", 0.0) >= 0.10 else "bounded_inflation_regime", "source": SOURCE, "provenance": "rung1_rho_sweep_4b_placement_v0"}

    if transition["transition_shape"] == "bounded_inflation_to_corruption":
        determination = "claim4_holds_above_operator_quality_threshold"
        next_move = "Use rho* to target real-LLM levers that keep propagation quality above the bounded-inflation regime before rerunning claim 4."
    elif transition["transition_shape"] == "corruption_without_low_rho_bounded_inflation":
        determination = "mechanism_absent_or_needs_wider_low_rho_sweep"
        next_move = "Sweep lower rho values and inspect the rho operator before concluding the register-inflation mechanism is absent."
    else:
        determination = "needs_wider_sweep"
        next_move = "Extend rho range/resolution and validate the rho injection instrument."

    payload = {"schema_version": SCHEMA_VERSION, "status": "RUNG1_RHO_SWEEP_REGISTER_REQUIREMENT_COMPLETE", "generated_at": _now(), "pieceA_trail_ratio": piece_a, "pieceB_by_rho": piece_b_by_rho, "pieceB_instance_rows": piece_b_rows, "pieceB_transition_rho": transition, "pieceB_depth_dependent_match": depth_match, "pieceB_4b_placement": four_b_placement, "headline": {"determination": determination, "transition_rho": transition.get("transition_rho"), "transition_shape": transition.get("transition_shape"), "pieceA_verdict": piece_a["verdict"], "single_next_move": next_move}, "source": SOURCE, "provenance": "rung1_rho_sweep_register_requirement_v0"}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline trail-ratio recompute and controlled rho sweep.")
    parser.add_argument("--output", type=Path, default=RESULTS_PATH)
    parser.add_argument("--node-cap", type=int, default=DEFAULT_NODE_CAP)
    parser.add_argument("--rhos", type=float, nargs="*", default=list(RHO_VALUES))
    run(parser.parse_args())


if __name__ == "__main__":
    main()
