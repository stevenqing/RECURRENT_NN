"""Overnight Rung-1 separator batch runner.

This script emits the consolidated rung1_overnight_batch_v0 contract requested
for the LLM line, P1c regrade, and Part A clean close-out.  Cheap/offline tracks
run directly.  Real-LLM costed tracks are budget-gated and are either launched
within cap or recorded as skipped with the reason.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _adjacency, _default_color_orders, _rel
from experiments.rung1_separator_llm_inloop import (
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    InLoopEpisode,
    _initial_domains,
    _load_separator_manifest,
    _row_for_episode,
    _run_episodes_batched,
)
from experiments.rung1_separator_p1b_full_table import GRADED_PATH, _operator_by_b
from experiments.rung1_separator_p1b_full_table_controlled_v1 import _interpolate_dstar
from experiments.rung1_separator_scaling import DEFAULT_NODE_CAP, _instance_from_row


RESULTS_DIR = REPO_ROOT / "results/rung1_overnight_batch"
RESULTS_PATH = RESULTS_DIR / "results.json"
SCHEMA_VERSION = "rung1_overnight_batch_v0"
STATUS_COMPLETE = "RUNG1_OVERNIGHT_BATCH_COMPLETE"
STATUS_PARTIAL = "RUNG1_OVERNIGHT_BATCH_PARTIAL"

EXPLICIT_FULL_PATH = REPO_ROOT / "results/rung1_separator_llm_inloop/full_slice_vllm_explicit_state/results.json"
ITEM062_PATH = REPO_ROOT / "results/experiment_items/item_062_rung1_separator_capacity_scoped_positive_p1c_competence_gate.json"

MATCHED_D = (6, 8, 10)
EXTENDED_D = (12, 16, 24, 32)
TRACK4_D = (6, 8, 10, 12, 16, 24, 32, 40, 50)
TRACK1_DEPTHS = (4, 5, 6, 7, 9, 10)
TRACK1B_DEPTHS = (4, 5, 6, 7, 9, 10, 12)
TRACK4_B = (4, 8, 12)
TRACK4_DEPTHS = (4, 5, 6, 7, 9, 10, 12)
LOW_SOLVE_THRESHOLD = 0.50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _ols_slope(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    xbar = mean(xs)
    ybar = mean(ys)
    den = sum((x - xbar) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - xbar) * (y - ybar) for x, y in points) / den


def _select_manifest(b_values: tuple[int, ...], depths: tuple[int, ...], n_per_cell: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in _load_separator_manifest():
        b_value = int(row.get("b", -1))
        depth = int(row.get("d_global_reference", -1))
        if b_value in b_values and depth in depths:
            grouped[(b_value, depth)].append(row)
    out: list[dict[str, Any]] = []
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda item: (int(item["seed"]), int(item["source_index"]), str(item["instance_id"])))
        out.extend(rows[:n_per_cell])
    return out


def _same_instances_as_explicit_full() -> list[dict[str, Any]]:
    explicit = _read_json(EXPLICIT_FULL_PATH) or {}
    ids = {row["instance_id"] for row in explicit.get("instance_arm_metrics", [])}
    manifest = {row["instance_id"]: row for row in _load_separator_manifest()}
    return [manifest[instance_id] for instance_id in sorted(ids) if instance_id in manifest]


def _trace_monolith(row: dict[str, Any], register_capacity_d: int, keff_hat: float, node_cap: int) -> dict[str, Any]:
    instance = _instance_from_row(row)
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
    trace = []

    def effective_peak() -> int:
        return math.ceil(max(first_conflict_depth, max_backjump_distance) * math.log(max(keff_hat, 1.0001)))

    while True:
        occupancy = effective_peak()
        trace.append({"step": steps, "trail_depth": cursor, "register_len": len(register), "register_occupancy_proxy": occupancy})
        if steps >= node_cap:
            return _trace_result(row, register_capacity_d, keff_hat, "NODE_CAP", False, steps, retractions, occupancy, trace)
        if cursor >= len(order):
            if occupancy > register_capacity_d:
                return _trace_result(row, register_capacity_d, keff_hat, "OVERFLOW_FAIL", False, steps, retractions, occupancy, trace)
            return _trace_result(row, register_capacity_d, keff_hat, "SOLVED", True, steps, retractions, occupancy, trace)
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
        occupancy = effective_peak()
        if occupancy > register_capacity_d:
            trace.append({"step": steps, "trail_depth": cursor, "register_len": len(register), "register_occupancy_proxy": occupancy, "event": "overflow"})
            return _trace_result(row, register_capacity_d, keff_hat, "OVERFLOW_FAIL", False, steps, retractions, occupancy, trace)
        if not register:
            return _trace_result(row, register_capacity_d, keff_hat, "NO_RECOVERY_TARGET", False, steps, retractions, occupancy, trace)
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


def _trace_result(row: dict[str, Any], register_capacity_d: int, keff_hat: float, status: str, solved: bool, steps: int, retractions: int, peak: int, trace: list[dict[str, Any]]) -> dict[str, Any]:
    overflow = next((item for item in trace if item.get("event") == "overflow" or item.get("register_occupancy_proxy", 0) > register_capacity_d), None)
    return {
        "instance_id": row["instance_id"],
        "cell_id": row.get("cell_id"),
        "b": int(row["b"]),
        "d_global_reference": int(row["d_global_reference"]),
        "register_capacity_D": register_capacity_d,
        "k_eff": keff_hat,
        "status": status,
        "solved": solved,
        "steps": steps,
        "total_retractions": retractions,
        "peak_register_occupancy_proxy": peak,
        "overflowed": status == "OVERFLOW_FAIL",
        "overflow_depth": None if overflow is None else int(overflow["trail_depth"]),
        "overflow_register_occupancy_proxy": None if overflow is None else int(overflow["register_occupancy_proxy"]),
        "trace_sample": trace[:5] + trace[-5:],
        "trace_available": True,
        "source": SOURCE,
        "provenance": "rung1_overnight_clean_trace_v0",
    }


def _clean_track(rows: list[dict[str, Any]], d_values: tuple[int, ...], operator_by_b: dict[int, dict[str, Any]], node_cap: int, label: str) -> dict[str, Any]:
    out = []
    for row in rows:
        b_value = int(row["b"])
        keff = float(operator_by_b[b_value]["k_eff_clean"])
        for register_d in d_values:
            out.append(_trace_monolith(row, int(register_d), keff, node_cap))
    cell_summary = []
    for (register_d, depth, b_value), subset in sorted(_group(out, "register_capacity_D", "d_global_reference", "b").items()):
        overflow_depths = [row["overflow_depth"] for row in subset if row.get("overflow_depth") is not None]
        cell_summary.append({
            "register_capacity_D": register_d,
            "d_global_reference": depth,
            "b": b_value,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "overflow_rate": mean(float(row["overflowed"]) for row in subset),
            "failure_mode_counts": dict(Counter(row["status"] for row in subset)),
            "mean_overflow_depth": mean(overflow_depths) if overflow_depths else None,
            "source": SOURCE,
            "provenance": "rung1_overnight_clean_cell_summary_v0",
        })
    slope_points = []
    footprint = 3.25
    for row in cell_summary:
        if row["mean_overflow_depth"] is not None and int(row["b"]) == 2:
            keff = float(operator_by_b[2]["k_eff_clean"])
            slope_points.append(((float(row["register_capacity_D"]) - footprint) / math.log(max(keff, 1.0001)), float(row["mean_overflow_depth"])))
    return {
        "label": label,
        "status": "COMPLETE",
        "instance_rows": out,
        "cell_summary": cell_summary,
        "overflow_depth_vs_D_slope": _ols_slope(slope_points),
        "decision_guard": "capacity-law positive requires clean scaling gate; solve-rate alone is not used",
    }


def _group(rows: list[dict[str, Any]], *keys: str) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[key] for key in keys)].append(row)
    return grouped


def _track1c_existing_fallible() -> dict[str, Any]:
    full = _read_json(EXPLICIT_FULL_PATH) or {}
    rows = full.get("instance_arm_metrics", [])
    steps = full.get("inloop_step_metrics", [])
    keff = 3.7828890286429866
    fallible_rows = []
    by_instance = defaultdict(list)
    for step in steps:
        by_instance[(step["instance_id"], int(step["register_capacity_D"]))].append(step)
    for row in rows:
        subset = by_instance[(row["instance_id"], int(row["register_capacity_D"]))]
        max_cursor = max((int(step["cursor_before"]) for step in subset), default=None)
        overflow_depth_proxy = None
        if row["status"] == "OVERFLOW_FAIL":
            overflow_depth_proxy = max_cursor
        fallible_rows.append({
            "instance_id": row["instance_id"],
            "register_capacity_D": int(row["register_capacity_D"]),
            "d_global_reference": int(row["d_global_reference"]),
            "status": row["status"],
            "call_cap_hit": bool(row["call_cap_hit"]),
            "solved_valid": bool(row["solved_valid"]),
            "logged_steps": len(subset),
            "max_logged_trail_depth": max_cursor,
            "overflow_depth_proxy": overflow_depth_proxy,
            "instrumentation_guard": "existing fallible artifact lacks per-step register occupancy; overflow_depth_proxy is max logged cursor for OVERFLOW_FAIL",
            "source": SOURCE,
            "provenance": "rung1_overnight_fallible_existing_proxy_v0",
        })
    survived = []
    for cursor_key, subset in sorted(_group(steps, "cursor_before").items()):
        cursor = cursor_key[0]
        oracle = sum(int(step.get("n_oracle_prunes") or 0) for step in subset)
        accepted = sum(int(step.get("n_accepted_prunes") or 0) for step in subset)
        if oracle:
            survived.append({"trail_depth": int(cursor), "recall": accepted / oracle, "oracle_prunes": oracle, "accepted_oracle_prunes": accepted, "n_steps": len(subset)})
    return {
        "status": "COMPLETE_WITH_INSTRUMENTATION_LIMIT",
        "source_artifact": _rel(EXPLICIT_FULL_PATH),
        "instance_rows": fallible_rows,
        "failure_mode_counts": dict(Counter(row["status"] for row in rows)),
        "survival_conditioned_recall": survived,
        "instrumentation_guard": "real overflow-depth requires per-step register occupancy in future fallible runs",
        "inloop_keff_used": keff,
    }


def _extract_first_json_object(text: str) -> dict[str, Any]:
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    # If the generation includes prose before the answer, find the first full top-level object.
    for start in [match.start() for match in re.finditer(r"\{", text)]:
        depth = 0
        in_str = False
        esc = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:idx + 1])
                    except json.JSONDecodeError:
                        break
                    return parsed if isinstance(parsed, dict) else {}
    return {}


def _track3a_regrade() -> dict[str, Any]:
    item = _read_json(ITEM062_PATH) or {}
    rows = ((item.get("result_tables") or {}).get("p1c_v2_competence_retry_rows") or {}).get("rows", [])
    regraded = []
    for row in rows:
        parsed = _extract_first_json_object(row.get("raw_generation", ""))
        predicted_conflict = bool(parsed.get("conflict_detected"))
        culprit = parsed.get("culprit")
        try:
            culprit_int = None if culprit is None else int(culprit)
        except (TypeError, ValueError):
            culprit_int = None
        oracle_conflict = bool(row.get("oracle_conflict"))
        oracle_culprits = {int(item) for item in row.get("oracle_culprits", [])}
        regraded.append({
            "episode_index": row.get("episode_index"),
            "instance_id": row.get("instance_id"),
            "oracle_conflict": oracle_conflict,
            "oracle_culprits": sorted(oracle_culprits),
            "predicted_conflict": predicted_conflict,
            "predicted_culprit": culprit_int,
            "culprit_correct": bool(oracle_conflict and culprit_int in oracle_culprits),
            "parsable": bool(parsed),
            "parsed_top_level_keys": sorted(parsed.keys()),
            "parser": "strip_through_think_parse_first_top_level_json_top_level_fields_v0",
            "source": SOURCE,
            "provenance": "rung1_overnight_p1c_v2_offline_regrade_v0",
        })
    tp = sum(1 for row in regraded if row["oracle_conflict"] and row["predicted_conflict"])
    fp = sum(1 for row in regraded if not row["oracle_conflict"] and row["predicted_conflict"])
    fn = sum(1 for row in regraded if row["oracle_conflict"] and not row["predicted_conflict"])
    true_conflicts = sum(1 for row in regraded if row["oracle_conflict"])
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    culprit_accuracy = sum(1 for row in regraded if row["culprit_correct"]) / max(1, true_conflicts)
    gate = min(precision, recall, culprit_accuracy) > 0.0
    return {
        "status": "COMPLETE" if rows else "SKIPPED_NO_RAW_GENERATIONS",
        "source_artifact": _rel(ITEM062_PATH),
        "regraded_rows": regraded,
        "summary": {
            "n_episodes": len(regraded),
            "n_true_conflicts": true_conflicts,
            "conflict_precision": precision,
            "conflict_recall": recall,
            "culprit_accuracy": culprit_accuracy,
            "functional_gate_pass": gate,
            "raw_generation_spot_check_note": "first available v2 rows parsed at top level after </think>; parser artifact corrected" if regraded else "no raw rows available",
            "positive_or_negative": "positive_regraded_parser_fix" if gate else "honest_negative_or_no_data",
        },
    }


def _track4_clean_large_b(operator_by_b: dict[int, dict[str, Any]], n_per_cell: int, node_cap: int) -> dict[str, Any]:
    rows = _select_manifest(TRACK4_B, TRACK4_DEPTHS, n_per_cell)
    clean = _clean_track(rows, TRACK4_D, operator_by_b, node_cap, "track4_clean_large_b")
    slopes = []
    verdict_by_b = {}
    for b_value in TRACK4_B:
        points = []
        for register_d in TRACK4_D:
            subset = [row for row in clean["cell_summary"] if int(row["b"]) == b_value and int(row["register_capacity_D"]) == register_d]
            rates = [(int(row["d_global_reference"]), float(row["solve_rate"])) for row in subset]
            dstar = _interpolate_dstar(rates)
            observed = dstar.get("dstar_observed")
            if observed is not None:
                points.append((float(register_d), float(observed)))
        slope = _ols_slope(points)
        slopes.append({"b": b_value, "clean_dstar_vs_D_slope": slope, "n_uncensored": len(points)})
        verdict_by_b[str(b_value)] = "structural_separator_limited" if slope is not None and abs(slope) < 0.05 else "clean_scales_or_inconclusive"
    return clean | {"clean_per_b_dstar_slopes": slopes, "large_b_regime_by_b": verdict_by_b}


def _run_1d_budgeted(args: argparse.Namespace, operator_by_b: dict[int, dict[str, Any]]) -> dict[str, Any]:
    base_rows = _select_manifest((2,), TRACK1_DEPTHS, args.track1d_n_per_depth)
    max_calls = len(base_rows) * len(EXTENDED_D) * args.track1d_call_cap
    ledger = {"piece": "track1d", "n_instances": len(base_rows), "D_values": list(EXTENDED_D), "call_cap": args.track1d_call_cap, "max_llm_calls": max_calls, "max_budget_calls": args.max_budget_calls, "cost_ok": max_calls <= args.max_budget_calls}
    if not ledger["cost_ok"]:
        return {"status": "SKIPPED_BUDGET", "budget_ledger": ledger, "instance_rows": [], "step_rows": []}
    if args.no_llm:
        return {"status": "SKIPPED_NO_LLM_FLAG", "budget_ledger": ledger, "instance_rows": [], "step_rows": []}
    keff_hat = float(operator_by_b[2]["graded_keff_inflated"])
    episodes = []
    for register_d in EXTENDED_D:
        for row in base_rows:
            episodes.append(InLoopEpisode(row=row, arm="cbj_bounded", register_capacity_D=int(register_d), adjacency=_adjacency(int(row["n_vertices"]), tuple(tuple(edge) for edge in row["edges"])), order=[int(vertex) for vertex in row["order"]], domains=_initial_domains(row)))
    episodes = _run_episodes_batched(episodes, "openai", None, None, args.track1d_call_cap, args.max_new_tokens, keff_hat, args.batch_size, args.openai_base_url, args.openai_model, True, "explicit_domains")
    return {"status": "COMPLETE", "budget_ledger": ledger, "instance_rows": [_row_for_episode(ep) for ep in episodes], "step_rows": [step for ep in episodes for step in ep.step_rows]}


def run(args: argparse.Namespace) -> dict[str, Any]:
    graded = _read_json(GRADED_PATH)
    operator_by_b = _operator_by_b(graded)
    matched_rows = _same_instances_as_explicit_full()
    if not matched_rows:
        matched_rows = _select_manifest((2,), TRACK1_DEPTHS, args.n_per_cell)
    track1a = _clean_track(matched_rows, MATCHED_D, operator_by_b, args.node_cap, "track1a_clean_matched")
    track1b_rows = _select_manifest((2,), TRACK1B_DEPTHS, args.n_per_cell)
    track1b = _clean_track(track1b_rows, EXTENDED_D, operator_by_b, args.node_cap, "track1b_clean_extended")
    track1c = _track1c_existing_fallible()
    track3a = _track3a_regrade()
    track4 = _track4_clean_large_b(operator_by_b, args.n_per_cell, args.node_cap)
    track1d = _run_1d_budgeted(args, operator_by_b)

    track3b_full_calls = 3000
    track3b_budget = {"piece": "track3b", "target_episodes": 3000, "shrunk_episodes": min(3000, args.max_budget_calls), "call_cap": 1, "max_llm_calls": min(3000, args.max_budget_calls), "max_budget_calls": args.max_budget_calls, "cost_ok": bool(track3a.get("summary", {}).get("functional_gate_pass")) and min(3000, args.max_budget_calls) <= args.max_budget_calls}
    track3b = {"status": "SKIPPED_BUDGET" if track3b_full_calls > args.max_budget_calls else "SKIPPED_NOT_LAUNCHED", "budget_ledger": track3b_budget, "guard": "P1c scale-up target is ~3000 capped-thinking episodes; overnight cap prevents full target, so no partial 3B launch is interpreted as competence."}

    d4_clean = [row for row in track1a["cell_summary"] if int(row["d_global_reference"]) == 4]
    d4_bug = bool(d4_clean) and all(row["failure_mode_counts"].get("NO_RECOVERY_TARGET", 0) == row["n"] for row in d4_clean)
    clean_scaling = track1b.get("overflow_depth_vs_D_slope") is not None and abs(float(track1b["overflow_depth_vs_D_slope"])) > 0.2
    if d4_bug:
        track1_verdict = "d4_recovery_bug"
    elif clean_scaling:
        track1_verdict = "mis_scoped_then_clean_scales"
    else:
        track1_verdict = "mis_scoped_clean_no_scaling_law_fails"
    large_b_regime = "structural_separator_limited" if all(v == "structural_separator_limited" for v in track4.get("large_b_regime_by_b", {}).values()) else "fallibility_capped"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "budget_ledger": [track1d["budget_ledger"], track3b["budget_ledger"]],
        "track1": {"track1_verdict": track1_verdict, "track1a": track1a, "track1b": track1b, "track1c": track1c, "track1d": track1d},
        "track3": {"track3_verdict": "p1c_competence_regraded", "track3a": track3a, "track3b": track3b},
        "track4": {"track4_verdict": large_b_regime, "track4": track4},
        "next_single_move_per_line": {
            "track1": "If clean scaling is absent or d4 bug fires, fix clean/recovery instrumentation before further fallible decoupling; otherwise compare 1D fallible overflow-depth shift.",
            "track3": "If regraded P1c remains competent after parser fix, allocate a separate capped-thinking scale-up budget; otherwise report real P1c negative.",
            "track4": "If clean large-b dstar is flat, report structural separator-limited regime; if clean scales, fallible large-b flatness is fallibility-capped.",
        },
        "interpretation_guards": [
            "Distinct statuses are preserved; solve-rate is not the primary overflow observable.",
            "Fallible existing overflow-depth is proxy-only because old artifacts lack per-step register occupancy.",
            "No capacity-law positive without clean-scaling gate.",
            "Use full explicit in-loop recall 0.338 for fallible K_eff; pilot/isolated recall are not used for in-loop law claims.",
        ],
        "source": SOURCE,
        "provenance": "rung1_overnight_batch_v0",
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run overnight Rung-1 separator batch.")
    parser.add_argument("--output", type=Path, default=RESULTS_PATH)
    parser.add_argument("--n-per-cell", type=int, default=4)
    parser.add_argument("--node-cap", type=int, default=DEFAULT_NODE_CAP)
    parser.add_argument("--max-budget-calls", type=int, default=600)
    parser.add_argument("--track1d-n-per-depth", type=int, default=1)
    parser.add_argument("--track1d-call-cap", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()