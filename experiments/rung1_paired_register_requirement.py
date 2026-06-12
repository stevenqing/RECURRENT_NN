"""Paired fallible-vs-clean register requirement test plus P1c token fix.

This runner intentionally excludes Track 4: Item065 already closed the clean
large-b structural-separator-limited branch. The hard guard here is that the
fallible call cap is floored by clean search length, not by register D.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _adjacency, _rel
from experiments.rung1_fallible_1d_rerun import (
    _checkpoint_dir,
    _clean_row,
    _first_json,
    _openai_call,
    _p1c_row_from_generation,
    _p1c_summary,
    _load_piece1_checkpoint,
    _read_checkpoint,
    _read_json,
    _run_episodes_checkpointed,
    _trace_clean,
    _write_checkpoint,
)
from experiments.rung1_separator_item062_execution import _competence_episodes
from experiments.rung1_separator_llm_inloop import (
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    InLoopEpisode,
    _initial_domains,
    _load_separator_manifest,
    _row_for_episode,
)
from experiments.rung1_separator_p1b_full_table import GRADED_PATH, _operator_by_b
from experiments.rung1_separator_p1c_truncation_pilot import OPERATOR_VERSION_V2, _prompt_for_operator
from experiments.rung1_separator_scaling import DEFAULT_NODE_CAP


RESULTS_DIR = REPO_ROOT / "results/rung1_paired_register_requirement"
RESULTS_PATH = RESULTS_DIR / "results.json"
SCHEMA_VERSION = "rung1_paired_register_requirement_v0"
STATUS_COMPLETE = "RUNG1_PAIRED_REGISTER_REQUIREMENT_COMPLETE"
STATUS_PREFLIGHT_FAIL = "RUNG1_PAIRED_REGISTER_REQUIREMENT_PREFLIGHT_FAIL"
PIECE1_STAGE1_D = 16
PIECE1_STAGE2_D = (24, 32)
CLEAN_REQUIREMENT_D = (12, 16, 24, 32)
DEFAULT_DEPTHS = (4, 5, 6, 7, 9, 10)
P1C_STOP_RATE_THRESHOLD = 0.90
P1C_FUNCTIONAL_GATE_THRESHOLD = 0.20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _select_b2_candidates(depths: tuple[int, ...], n_per_depth: int) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {depth: [] for depth in depths}
    for row in _load_separator_manifest():
        depth = int(row.get("d_global_reference", -1))
        if int(row.get("b", -1)) == 2 and depth in grouped:
            grouped[depth].append(row)
    selected: list[dict[str, Any]] = []
    for depth in depths:
        rows = sorted(grouped.get(depth, []), key=lambda row: (int(row["seed"]), int(row["source_index"]), str(row["instance_id"])))
        selected.extend(rows[:n_per_depth])
    return selected


def _clean_requirement(row: dict[str, Any], operator_by_b: dict[int, dict[str, Any]], node_cap: int) -> dict[str, Any]:
    keff = float(operator_by_b[int(row["b"])] ["k_eff_clean"])
    rows = [_trace_clean(row, register_d, keff, node_cap) for register_d in CLEAN_REQUIREMENT_D]
    solved = [clean_row for clean_row in rows if clean_row.get("solved")]
    min_row = min(solved, key=lambda clean_row: int(clean_row["register_capacity_D"])) if solved else None
    d16 = next(clean_row for clean_row in rows if int(clean_row["register_capacity_D"]) == PIECE1_STAGE1_D)
    return {
        "instance_id": row["instance_id"],
        "row": row,
        "clean_rows": rows,
        "clean_solved_at_stage1_D": bool(d16.get("solved")),
        "clean_stage1_steps": int(d16.get("steps", 0)),
        "clean_stage1_retractions": int(d16.get("total_retractions", 0)),
        "clean_min_solving_D": int(min_row["register_capacity_D"]) if min_row else None,
        "clean_min_steps": int(min_row["steps"]) if min_row else None,
        "clean_min_retractions": int(min_row["total_retractions"]) if min_row else None,
        "clean_status_at_D16": d16.get("status"),
        "source": SOURCE,
        "provenance": "rung1_paired_clean_requirement_v0",
    }


def _prepare_piece1_instances(args: argparse.Namespace, operator_by_b: dict[int, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    depths = tuple(int(item) for item in args.depths.split(",") if item.strip())
    candidates = _select_b2_candidates(depths, args.piece1_n_per_depth)
    requirements = [_clean_requirement(row, operator_by_b, args.node_cap) for row in candidates]
    clean_solvable = [item for item in requirements if item["clean_solved_at_stage1_D"] and item["clean_min_solving_D"] is not None]
    clean_solvable = sorted(clean_solvable, key=lambda item: (int(item["row"]["d_global_reference"]), int(item["row"]["seed"]), int(item["row"]["source_index"]), str(item["instance_id"])))
    max_clean_steps = max((int(item["clean_stage1_steps"]) for item in clean_solvable), default=0)
    floor = max(150, int(math.ceil(1.5 * max_clean_steps)))
    call_cap = floor if args.piece1_call_cap <= 0 else args.piece1_call_cap
    if call_cap < floor:
        preflight = {
            "status": "KILLED_PREFLIGHT_CALL_CAP_BELOW_SEARCH_LENGTH_FLOOR",
            "call_cap": call_cap,
            "call_cap_floor": floor,
            "max_clean_stage1_steps": max_clean_steps,
            "required": "call_cap >= max(150, ceil(1.5 * max clean D16 search length over selected instances))",
            "source": SOURCE,
            "provenance": "rung1_paired_preflight_v0",
        }
        return [], requirements, preflight
    max_stage1_fit = max(0, (args.max_budget_calls - args.p1c_smoke_episodes) // max(1, call_cap))
    selected = clean_solvable[: min(len(clean_solvable), args.piece1_max_instances, max_stage1_fit)]
    preflight = {
        "status": "PASS" if selected else "KILLED_PREFLIGHT_NO_STAGE1_BUDGET_OR_CLEAN_SOLVABLE_INSTANCES",
        "candidate_instances": len(candidates),
        "clean_solvable_at_D16": len(clean_solvable),
        "selected_instances": len(selected),
        "depths": list(depths),
        "call_cap": call_cap,
        "call_cap_floor": floor,
        "max_clean_stage1_steps": max_clean_steps,
        "budget_trade_direction": "shrink n_instances before lowering call_cap",
        "source": SOURCE,
        "provenance": "rung1_paired_preflight_v0",
    }
    return selected, requirements, preflight


def _episode_for(row: dict[str, Any], register_d: int) -> InLoopEpisode:
    return InLoopEpisode(
        row=row,
        arm="cbj_bounded_explicit_domains",
        register_capacity_D=int(register_d),
        adjacency=_adjacency(int(row["n_vertices"]), tuple(tuple(edge) for edge in row["edges"])),
        order=[int(vertex) for vertex in row["order"]],
        domains=_initial_domains(row),
    )


def _run_fallible_batch(args: argparse.Namespace, selected: list[dict[str, Any]], register_d: int, checkpoint_name: str, call_cap: int, keff_hat: float) -> list[dict[str, Any]]:
    episodes = [_episode_for(item["row"], register_d) for item in selected]
    checkpoint_path = _checkpoint_dir(args) / checkpoint_name
    if args.no_llm:
        return []
    episodes = _load_piece1_checkpoint(checkpoint_path, episodes, args.resume)
    episodes = _run_episodes_checkpointed(episodes, args, call_cap, args.max_new_tokens, keff_hat, checkpoint_path)
    rows = []
    for ep in episodes:
        row = _row_for_episode(ep)
        depth_component = max(1, int(ep.first_conflict_depth or 0), int(ep.max_backjump_distance or 0), int(ep.cursor), len(ep.register))
        row.update({
            "overflow_depth": depth_component if ep.status == "OVERFLOW_FAIL" else None,
            "k_eff_used": keff_hat,
            "paired_stage_register_D": int(register_d),
            "source": SOURCE,
            "provenance": "rung1_paired_fallible_instance_v0",
        })
        rows.append(row)
    return rows


def _run_piece1(args: argparse.Namespace, selected: list[dict[str, Any]], preflight: dict[str, Any], operator_by_b: dict[int, dict[str, Any]]) -> dict[str, Any]:
    if preflight.get("status") != "PASS":
        return {"status": preflight.get("status"), "budget_ledger": {}, "clean_requirements": selected, "stage1_rows": [], "stage2_rows": [], "paired_rows": [], "summary": {}}
    call_cap = int(preflight["call_cap"])
    stage1_max_calls = len(selected) * call_cap
    p1c_reserved = int(args.p1c_smoke_episodes)
    stage2_budget = max(0, args.max_budget_calls - stage1_max_calls - p1c_reserved)
    budget_ledger = {
        "piece": "piece1",
        "stage1_D": PIECE1_STAGE1_D,
        "stage2_D_ladder": list(PIECE1_STAGE2_D),
        "n_instances": len(selected),
        "call_cap": call_cap,
        "call_cap_floor": int(preflight["call_cap_floor"]),
        "max_clean_stage1_steps": int(preflight["max_clean_stage1_steps"]),
        "stage1_max_llm_calls": stage1_max_calls,
        "stage2_budget_after_stage1_and_p1c_smoke": stage2_budget,
        "max_budget_calls": args.max_budget_calls,
        "p1c_smoke_reserved_calls": p1c_reserved,
        "cost_ok_stage1_mandatory": stage1_max_calls + p1c_reserved <= args.max_budget_calls,
        "source": SOURCE,
        "provenance": "rung1_paired_budget_ledger_v0",
    }
    if not budget_ledger["cost_ok_stage1_mandatory"]:
        return {"status": "SKIPPED_BUDGET_STAGE1", "budget_ledger": budget_ledger, "clean_requirements": selected, "stage1_rows": [], "stage2_rows": [], "paired_rows": [], "summary": {}}
    if args.no_llm:
        return {"status": "SKIPPED_NO_LLM_FLAG", "budget_ledger": budget_ledger, "clean_requirements": selected, "stage1_rows": [], "stage2_rows": [], "paired_rows": [], "summary": {}}
    keff_hat = float(operator_by_b[2]["graded_keff_inflated"])
    stage1_rows = _run_fallible_batch(args, selected, PIECE1_STAGE1_D, "piece1_stage1_d16_episodes.json", call_cap, keff_hat)
    by_instance: dict[str, dict[int, dict[str, Any]]] = {item["instance_id"]: {} for item in selected}
    for row in stage1_rows:
        by_instance[str(row["instance_id"])][PIECE1_STAGE1_D] = row
    stage2_rows: list[dict[str, Any]] = []
    skipped_budget: list[dict[str, Any]] = []
    overflow_items = [item for item in selected if by_instance.get(item["instance_id"], {}).get(PIECE1_STAGE1_D, {}).get("status") == "OVERFLOW_FAIL"]
    remaining_stage2_budget = stage2_budget
    pending_stage2 = list(overflow_items)
    for register_d in PIECE1_STAGE2_D:
        if not pending_stage2:
            break
        fit_count = remaining_stage2_budget // call_cap
        if fit_count <= 0:
            for item in pending_stage2:
                skipped_budget.append({"instance_id": item["instance_id"], "register_capacity_D": register_d, "status": "SKIPPED_BUDGET", "source": SOURCE, "provenance": "rung1_paired_stage2_budget_skip_v0"})
            break
        batch_items = pending_stage2[:fit_count]
        for item in pending_stage2[fit_count:]:
            skipped_budget.append({"instance_id": item["instance_id"], "register_capacity_D": register_d, "status": "SKIPPED_BUDGET", "source": SOURCE, "provenance": "rung1_paired_stage2_budget_skip_v0"})
        rows = _run_fallible_batch(args, batch_items, register_d, f"piece1_stage2_d{register_d}_episodes.json", call_cap, keff_hat)
        remaining_stage2_budget -= len(batch_items) * call_cap
        stage2_rows.extend(rows)
        rows_by_instance = {str(row["instance_id"]): row for row in rows}
        pending_stage2 = [item for item in batch_items if rows_by_instance.get(item["instance_id"], {}).get("status") != "SOLVED"]
    for row in stage2_rows:
        by_instance.setdefault(str(row["instance_id"]), {})[int(row["register_capacity_D"])] = row
    paired_rows = [_paired_row(item, by_instance.get(item["instance_id"], {})) for item in selected]
    summary = _piece1_summary(paired_rows, stage1_rows, stage2_rows, skipped_budget)
    budget_ledger.update({
        "stage2_instances_overflowed_at_D16": len(overflow_items),
        "stage2_reruns_completed": len(stage2_rows),
        "stage2_reruns_skipped_budget": len(skipped_budget),
        "stage2_budget_remaining_reserved_calls": remaining_stage2_budget,
    })
    return {"status": "COMPLETE", "budget_ledger": budget_ledger, "clean_requirements": [_clean_public(item) for item in selected], "stage1_rows": stage1_rows, "stage2_rows": stage2_rows, "stage2_skipped_budget": skipped_budget, "paired_rows": paired_rows, "summary": summary}


def _clean_public(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "row"}


def _paired_row(item: dict[str, Any], fallible_by_d: dict[int, dict[str, Any]]) -> dict[str, Any]:
    clean_min = item["clean_min_solving_D"]
    fallible_solved_ds = [register_d for register_d, row in fallible_by_d.items() if row.get("status") == "SOLVED"]
    fallible_min = min(fallible_solved_ds) if fallible_solved_ds else None
    d16_row = fallible_by_d.get(PIECE1_STAGE1_D, {})
    gap = (fallible_min - clean_min) if fallible_min is not None and clean_min is not None else None
    lower_bound_gap = None if fallible_min is not None or clean_min is None else max(PIECE1_STAGE2_D) + 1 - clean_min
    matched_ratio_steps = None
    matched_ratio_retractions = None
    if d16_row.get("status") == "SOLVED" and int(PIECE1_STAGE1_D) == int(clean_min):
        matched_ratio_steps = int(d16_row.get("steps", 0)) / max(1, int(item["clean_min_steps"] or 0))
        matched_ratio_retractions = int(d16_row.get("total_retractions", 0)) / max(1, int(item["clean_min_retractions"] or 0))
    return {
        "instance_id": item["instance_id"],
        "b": int(item["row"]["b"]),
        "d_global_reference": int(item["row"]["d_global_reference"]),
        "clean_min_solving_D": clean_min,
        "clean_stage1_D": PIECE1_STAGE1_D,
        "clean_stage1_steps": item["clean_stage1_steps"],
        "clean_stage1_retractions": item["clean_stage1_retractions"],
        "fallible_status_by_D": {str(register_d): row.get("status") for register_d, row in sorted(fallible_by_d.items())},
        "fallible_steps_by_D": {str(register_d): row.get("steps") for register_d, row in sorted(fallible_by_d.items())},
        "fallible_retractions_by_D": {str(register_d): row.get("total_retractions") for register_d, row in sorted(fallible_by_d.items())},
        "fallible_min_solving_D": fallible_min,
        "register_requirement_gap": gap,
        "right_censored_gap_lower_bound": lower_bound_gap,
        "inflated_strict": bool(d16_row.get("status") == "OVERFLOW_FAIL" and (fallible_min is None or fallible_min > PIECE1_STAGE1_D)),
        "matched_D16_trail_length_ratio": matched_ratio_steps,
        "matched_D16_retraction_ratio": matched_ratio_retractions,
        "source": SOURCE,
        "provenance": "rung1_paired_instance_gap_v0",
    }


def _piece1_summary(paired_rows: list[dict[str, Any]], stage1_rows: list[dict[str, Any]], stage2_rows: list[dict[str, Any]], skipped_budget: list[dict[str, Any]]) -> dict[str, Any]:
    clean_solvable_n = len(paired_rows)
    inflated = [row for row in paired_rows if row.get("inflated_strict")]
    gaps = [row["register_requirement_gap"] for row in paired_rows if row.get("register_requirement_gap") is not None]
    censored = [row["right_censored_gap_lower_bound"] for row in paired_rows if row.get("right_censored_gap_lower_bound") is not None]
    stage1_counts = Counter(row.get("status") for row in stage1_rows)
    ratios = [row["matched_D16_trail_length_ratio"] for row in paired_rows if row.get("matched_D16_trail_length_ratio") is not None]
    retraction_ratios = [row["matched_D16_retraction_ratio"] for row in paired_rows if row.get("matched_D16_retraction_ratio") is not None]
    call_cap_dominated = stage1_counts.get("CALL_CAP", 0) > stage1_counts.get("OVERFLOW_FAIL", 0) + stage1_counts.get("SOLVED", 0)
    if call_cap_dominated:
        verdict = "stage1_call_cap_dominated_censored_non_result"
    elif inflated and len(inflated) / max(1, clean_solvable_n) >= 0.25:
        verdict = "fallibility_inflates_register_requirement"
    elif stage1_counts.get("SOLVED", 0) == clean_solvable_n and (not ratios or mean(ratios) <= 1.25):
        verdict = "no_distinct_fallible_register_inflation_at_scale"
    else:
        verdict = "mixed_or_inconclusive_paired_register_requirement"
    return {
        "n_clean_solvable_instances": clean_solvable_n,
        "stage1_status_counts": dict(stage1_counts),
        "stage2_status_counts": dict(Counter(row.get("status") for row in stage2_rows)),
        "stage2_skipped_budget": len(skipped_budget),
        "inflation_fraction": len(inflated) / max(1, clean_solvable_n),
        "register_requirement_gaps": gaps,
        "right_censored_gap_lower_bounds": censored,
        "mean_matched_D16_trail_length_ratio": mean(ratios) if ratios else None,
        "mean_matched_D16_retraction_ratio": mean(retraction_ratios) if retraction_ratios else None,
        "call_cap_dominated": call_cap_dominated,
        "piece1_verdict": verdict,
        "source": SOURCE,
        "provenance": "rung1_paired_piece1_summary_v0",
    }


def _p1c_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    manifest = [row for row in _load_separator_manifest() if int(row.get("b", -1)) == 12]
    rows = sorted(manifest, key=lambda row: (int(row["d_global_reference"]), int(row["seed"]), int(row["source_index"])))[: args.p1c_instances]
    return _competence_episodes(rows)


def _run_p1c_calls(args: argparse.Namespace, episodes: list[dict[str, Any]], max_tokens: int, checkpoint_name: str) -> list[dict[str, Any]]:
    checkpoint_path = _checkpoint_dir(args) / checkpoint_name
    completed_rows = _read_checkpoint(checkpoint_path, []) if args.resume else []
    completed_by_idx = {int(row["episode_index"]): row for row in completed_rows}
    pending = [(idx, episode) for idx, episode in enumerate(episodes) if idx not in completed_by_idx]
    if pending and not args.no_llm:
        with ThreadPoolExecutor(max_workers=max(1, min(args.batch_size, len(pending)))) as pool:
            futures = {pool.submit(_openai_call, args.openai_base_url, args.openai_model, _prompt_for_operator(episode, OPERATOR_VERSION_V2), max_tokens): (idx, episode) for idx, episode in pending}
            for future in as_completed(futures):
                idx, episode = futures[future]
                completed_by_idx[idx] = _p1c_row_from_generation(idx, episode, future.result())
                _write_checkpoint(checkpoint_path, [completed_by_idx[key] for key in sorted(completed_by_idx)])
    return [completed_by_idx[key] for key in sorted(completed_by_idx)]


def _p1c_finish_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row.get("finish_reason") for row in rows)
    stop_rate = counts.get("stop", 0) / max(1, len(rows))
    summary = _p1c_summary(rows) if rows else {}
    summary.update({
        "finish_counts": dict(counts),
        "finish_stop_rate": stop_rate,
        "finish_length_rate": counts.get("length", 0) / max(1, len(rows)),
        "output_tokens_total": sum(int(row.get("output_tokens", 0) or 0) for row in rows),
        "token_fix_gate_pass": stop_rate >= P1C_STOP_RATE_THRESHOLD,
        "token_fix_gate_threshold": P1C_STOP_RATE_THRESHOLD,
        "functional_gate_threshold": P1C_FUNCTIONAL_GATE_THRESHOLD,
        "functional_gate_pass": min(summary.get("conflict_precision", 0), summary.get("conflict_recall", 0), summary.get("culprit_accuracy", 0)) >= P1C_FUNCTIONAL_GATE_THRESHOLD if summary else False,
        "source": SOURCE,
        "provenance": "rung1_paired_p1c_token_fix_summary_v0",
    })
    return summary


def _run_piece2(args: argparse.Namespace, remaining_budget: int) -> dict[str, Any]:
    all_episodes = _p1c_rows(args)
    smoke_n = min(args.p1c_smoke_episodes, len(all_episodes), max(0, remaining_budget))
    budget_ledger = {
        "piece": "piece2_p1c_token_fix",
        "available_episodes": len(all_episodes),
        "smoke_episodes": smoke_n,
        "scale_target_episodes": args.p1c_scale_episodes,
        "max_tokens": args.p1c_max_tokens,
        "remaining_budget_entering_piece2": remaining_budget,
        "call_cap_per_episode": 1,
        "source": SOURCE,
        "provenance": "rung1_paired_p1c_budget_ledger_v0",
    }
    if smoke_n <= 0:
        return {"status": "SKIPPED_BUDGET", "budget_ledger": budget_ledger, "smoke_rows": [], "smoke_summary": {}, "scale_rows": [], "scale_summary": {}}
    if args.no_llm:
        return {"status": "SKIPPED_NO_LLM_FLAG", "budget_ledger": budget_ledger, "smoke_rows": [], "smoke_summary": {}, "scale_rows": [], "scale_summary": {}}
    smoke_episodes = all_episodes[:smoke_n]
    smoke_rows = _run_p1c_calls(args, smoke_episodes, args.p1c_max_tokens, "piece2_p1c_smoke_rows.json")
    smoke_summary = _p1c_finish_summary(smoke_rows)
    if not smoke_summary.get("token_fix_gate_pass"):
        return {"status": "TOKEN_FIX_PREFLIGHT_FAIL", "budget_ledger": budget_ledger, "smoke_rows": smoke_rows, "smoke_summary": smoke_summary, "scale_rows": [], "scale_summary": {}}
    scale_n = min(args.p1c_scale_episodes, len(all_episodes), max(0, remaining_budget - smoke_n))
    budget_ledger["scale_episodes"] = scale_n
    scale_rows = _run_p1c_calls(args, all_episodes[:scale_n], args.p1c_max_tokens, "piece2_p1c_scale_rows.json")
    return {"status": "COMPLETE", "budget_ledger": budget_ledger, "smoke_rows": smoke_rows, "smoke_summary": smoke_summary, "scale_rows": scale_rows, "scale_summary": _p1c_finish_summary(scale_rows)}


def run(args: argparse.Namespace) -> dict[str, Any]:
    operator_by_b = _operator_by_b(_read_json(GRADED_PATH))
    selected, all_requirements, preflight = _prepare_piece1_instances(args, operator_by_b)
    piece1 = _run_piece1(args, selected, preflight, operator_by_b)
    stage1_max = int(piece1.get("budget_ledger", {}).get("stage1_max_llm_calls", 0))
    stage2_reserved_spent = int(piece1.get("budget_ledger", {}).get("stage2_reruns_completed", 0)) * int(preflight.get("call_cap", 0))
    remaining_for_p1c = max(0, args.max_budget_calls - stage1_max - stage2_reserved_spent)
    piece2 = _run_piece2(args, remaining_for_p1c)
    piece1_verdict = piece1.get("summary", {}).get("piece1_verdict")
    p1c_status = piece2.get("status")
    if preflight.get("status") != "PASS":
        status = STATUS_PREFLIGHT_FAIL
        determination = "preflight_failed"
    else:
        status = STATUS_COMPLETE
        if piece1_verdict == "fallibility_inflates_register_requirement":
            determination = "claim4_confirmed_real_llm_in_loop"
        elif piece1_verdict == "stage1_call_cap_dominated_censored_non_result":
            determination = "not_a_result_call_cap_censored"
        else:
            determination = "claim4_not_confirmed_at_this_scale"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "generated_at": _now(),
        "headline": {
            "determination": determination,
            "piece1_verdict": piece1_verdict,
            "piece2_status": p1c_status,
            "single_next_move": "If Stage1 is uncensored, interpret paired gaps; if CALL_CAP appears, raise cap above the observed fallible search length before claiming a result.",
        },
        "preflight": preflight,
        "budget_ledger": [piece1.get("budget_ledger"), piece2.get("budget_ledger")],
        "piece1": piece1,
        "piece2": piece2,
        "all_clean_requirements_considered": [_clean_public(item) for item in all_requirements],
        "guards": [
            "call_cap floor is max(150, ceil(1.5 * max clean D16 search length over selected instances))",
            "Budget pressure shrinks n_instances or D rungs, never call_cap below floor",
            "CALL_CAP is right-censoring and not a fallible negative",
            "SOLVED, OVERFLOW, CALL_CAP, and NO_RECOVERY remain separate",
            "Comparison is per-instance paired by instance_id",
            "No Track4 rerun; Item065 closed Track4 as structural_separator_limited",
            "P1c scale runs only after smoke finish=stop rate passes the token-fix pre-gate",
        ],
        "source": SOURCE,
        "provenance": "rung1_paired_register_requirement_v0",
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paired fallible-vs-clean register requirement test plus P1c token fix.")
    parser.add_argument("--output", type=Path, default=RESULTS_PATH)
    parser.add_argument("--checkpoint-dir", type=Path, default=RESULTS_DIR / "checkpoints")
    parser.add_argument("--max-budget-calls", type=int, default=2200)
    parser.add_argument("--depths", default=",".join(str(item) for item in DEFAULT_DEPTHS))
    parser.add_argument("--piece1-n-per-depth", type=int, default=1)
    parser.add_argument("--piece1-max-instances", type=int, default=64)
    parser.add_argument("--piece1-call-cap", type=int, default=0, help="0 means use the clean-search floor")
    parser.add_argument("--node-cap", type=int, default=DEFAULT_NODE_CAP)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--p1c-instances", type=int, default=800)
    parser.add_argument("--p1c-smoke-episodes", type=int, default=16)
    parser.add_argument("--p1c-scale-episodes", type=int, default=512)
    parser.add_argument("--p1c-max-tokens", type=int, default=12288)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.set_defaults(resume=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
