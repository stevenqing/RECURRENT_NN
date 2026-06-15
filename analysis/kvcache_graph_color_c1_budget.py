"""Graph-color C1 conflict-reasoning matched-budget A/C curves."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import glob
import json
from pathlib import Path
from statistics import mean
from typing import Any

from analysis.kvcache_backjump_lora import (
    _choose_backjump,
    _checkpoint_rows,
    _conflict_analysis_prompt,
    _load_lora_model,
    _make_dataset,
    _maybe_chat_prompt,
    _parse_bins,
    _select_eval_entries,
)
from analysis.kvcache_exactness_gate import _cache_seq_length, _crop_cache
from analysis.kvcache_graph_color_budget_curves import _wilson
from analysis.kvcache_graph_color_search import _feed, _write_json
from experiments.rung1_distributed_graph_coloring import SOURCE
from experiments.rung1_reasoning_gym_bounded_register import (
    _current_domain,
    _deadend_nogood,
    _graph_color_view,
    _official_answer,
    _official_score,
)


SCHEMA_VERSION = "kvcache_graph_color_c1_budget_v0"
STATUS_COMPLETE = "KVCACHE_GRAPH_COLOR_C1_BUDGET_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _budget_grid(anchor: int, scales: str) -> list[int]:
    return sorted({max(1, int(round(float(scale.strip()) * int(anchor)))) for scale in scales.split(",") if scale.strip()})


def _summarize(budget_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    curve = []
    for method, budget in sorted({(row["method"], int(row["budget_B"])) for row in budget_rows}):
        subset = [row for row in budget_rows if row["method"] == method and int(row["budget_B"]) == budget]
        successes = sum(int(row["solved"]) for row in subset)
        ci = _wilson(successes, len(subset))
        curve.append({
            "task": "graph_color",
            "variant": "c1_conflict_reasoning",
            "policy": "conflict_cot",
            "method": method,
            "budget_B": budget,
            "n": len(subset),
            "solve_count": successes,
            "solve_rate": ci["rate"],
            "solve_ci_low": ci["ci_low"],
            "solve_ci_high": ci["ci_high"],
            "mean_tokens_used": mean(float(row["tokens_used"]) for row in subset),
            "mean_depth_reached": mean(float(row["depth_reached"]) for row in subset),
            "mean_steps_reached": mean(float(row["steps_reached"]) for row in subset),
            "status_counts": dict(Counter(row["status_at_budget"] for row in subset)),
            "source": SOURCE,
            "provenance": "kvcache_graph_color_c1_budget_curve_v0",
        })
    gaps = []
    for budget in sorted({int(row["budget_B"]) for row in budget_rows}):
        a = next(row for row in curve if row["method"] == "A_cache" and int(row["budget_B"]) == budget)
        c = next(row for row in curve if row["method"] == "C_incontext" and int(row["budget_B"]) == budget)
        gap = float(a["solve_rate"] or 0.0) - float(c["solve_rate"] or 0.0)
        gaps.append({
            "task": "graph_color",
            "variant": "c1_conflict_reasoning",
            "policy": "conflict_cot",
            "budget_B": budget,
            "A_solve_rate": a["solve_rate"],
            "C_solve_rate": c["solve_rate"],
            "A_minus_C": gap,
            "gap_ci_low_conservative": float(a["solve_ci_low"] or 0.0) - float(c["solve_ci_high"] or 0.0),
            "gap_ci_high_conservative": float(a["solve_ci_high"] or 0.0) - float(c["solve_ci_low"] or 0.0),
            "promotion_midband_pass": bool(gap >= 0.10 and (float(a["solve_ci_low"] or 0.0) - float(c["solve_ci_high"] or 0.0)) > 0.0),
            "source": SOURCE,
            "provenance": "kvcache_graph_color_c1_budget_gap_v0",
        })
    c_curve = [row for row in curve if row["method"] == "C_incontext"]
    mid = [row for row in c_curve if 0.4 <= float(row["solve_rate"] or 0.0) <= 0.6]
    bstar = (mid[0] if mid else min(c_curve, key=lambda row: abs(float(row["solve_rate"] or 0.0) - 0.5))) if c_curve else None
    bstar_payload = {
        "budget_B": int(bstar["budget_B"]) if bstar else None,
        "C_solve_rate": bstar["solve_rate"] if bstar else None,
        "selection_rule_status": "MIDBAND_FOUND" if mid else "MIDBAND_NOT_FOUND_NEAREST",
        "source": SOURCE,
        "provenance": "kvcache_graph_color_c1_budget_bstar_v0",
    }
    shape = {
        "task": "graph_color",
        "variant": "c1_conflict_reasoning",
        "policy": "conflict_cot",
        "A_dominates_grid": all(float(row["A_minus_C"]) >= -1e-9 for row in gaps),
        "min_gap": min(float(row["A_minus_C"]) for row in gaps) if gaps else None,
        "max_gap": max(float(row["A_minus_C"]) for row in gaps) if gaps else None,
        "promotion_points": sum(int(row["promotion_midband_pass"]) for row in gaps),
        "source": SOURCE,
        "provenance": "kvcache_graph_color_c1_budget_shape_v0",
    }
    return curve, gaps, bstar_payload, shape


def _run_one(model: Any, tokenizer: Any, dataset: Any, selected: dict[str, Any], r_value: int, args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    entry = selected["entry"]
    view = _graph_color_view(entry, args.order_mode)
    position = {vertex: index for index, vertex in enumerate(view["order"])}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = {int(vertex): set() for vertex in view["order"]}
    register: list[dict[str, Any]] = []
    base_transcript = f"Graph_color C1 matched-budget condition=isolation.\nProblem:\n{entry.get('question','')}\n"
    transcript = base_transcript
    _, cache, base_used = _feed(model, tokenizer, base_transcript, None)
    a_cumulative = int(base_used)
    c_cumulative = 0
    event_rows = []
    decision_rows = []
    cursor = 0
    status = "RUNNING"
    max_depth = 0
    while True:
        if len(decision_rows) >= int(args.call_cap):
            status = "CALL_CAP"
            break
        if cursor >= len(view["order"]):
            status = "SOLVED"
            break
        vertex = int(view["order"][cursor])
        domain = _current_domain(view, vertex, assignment, tried)
        if domain:
            color = int(domain[0])
            checkpoint = _cache_seq_length(cache)
            tried[vertex].add(color)
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": int(cursor), "cache_pos": int(checkpoint)})
            event = f"\nBRANCH vertex={vertex} color={color} domain={list(map(int, domain))} tried={sorted(int(item) for item in tried[vertex])}\n"
            _, cache, event_used = _feed(model, tokenizer, event, cache)
            a_cumulative += int(event_used)
            c_step = len(tokenizer(transcript + event, add_special_tokens=False).input_ids)
            c_cumulative += int(c_step)
            transcript += event
            max_depth = max(max_depth, len(register))
            event_rows.append({"step_index": len(event_rows) + 1, "kind": "branch", "depth": len(register), "A_tokens_cumulative": a_cumulative, "C_tokens_cumulative": c_cumulative, "A_tokens_step": int(event_used), "C_tokens_step": int(c_step)})
            cursor += 1
            continue
        if r_value == 0 or not register:
            status = "FORWARD_DEAD_END"
            break
        nogood = _deadend_nogood(view, vertex, assignment, position)
        oracle_vertex = max(nogood, key=lambda item: position[item]) if nogood else int(register[-1]["vertex"])
        oracle_abs = max((index for index, item in enumerate(register) if int(item["vertex"]) == int(oracle_vertex)), default=len(register) - 1)
        start = max(0, len(register) - int(r_value))
        oracle_idx = oracle_abs - start
        if not (0 <= oracle_idx < len(register[start:])):
            status = "NO_RECOVERY_TARGET"
            break
        open_checkpoints = _checkpoint_rows(register, start)
        candidates = [int(item["idx"]) for item in open_checkpoints]
        prompt = "\nDEAD_END\n" + _conflict_analysis_prompt(entry, view, vertex, assignment, tried, register, open_checkpoints, args)
        chosen, cache, backjump_used, meta = _choose_backjump("conflict_cot", model, tokenizer, prompt, candidates, int(oracle_idx), cache, args)
        a_cumulative += int(meta.get("input_tokens", backjump_used))
        c_prompt = _maybe_chat_prompt(tokenizer, transcript + prompt, args)
        c_step = len(tokenizer(c_prompt, add_special_tokens=False).input_ids) + int(meta.get("output_tokens", 0))
        c_cumulative += int(c_step)
        decision_rows.append({"step_index": len(event_rows) + 1, "vertex": vertex, "oracle_idx": int(oracle_idx), "chosen_idx": int(chosen), "parseable": bool(meta.get("parseable")), "valid": bool(meta.get("valid")), "fallback": bool(meta.get("fallback")), "exact": bool(int(chosen) == int(oracle_idx)), "A_tokens_step": int(meta.get("input_tokens", backjump_used)), "C_tokens_step": int(c_step)})
        event = f"\nDEAD_END vertex={vertex} chosen={int(chosen)} oracle={int(oracle_idx)} popped={len(register) - (start + int(chosen))}\n"
        transcript += event
        event_rows.append({"step_index": len(event_rows) + 1, "kind": "c1_backjump", "depth": len(register), "A_tokens_cumulative": a_cumulative, "C_tokens_cumulative": c_cumulative, "A_tokens_step": int(meta.get("input_tokens", backjump_used)), "C_tokens_step": int(c_step)})
        if bool(meta.get("fatal")):
            status = "INVALID_BACKJUMP_DECISION"
            break
        target_abs = start + int(chosen)
        checkpoint = register[target_abs].get("cache_pos")
        if checkpoint is None:
            status = "CACHE_CHECKPOINT_MISSING"
            break
        cache, _ = _crop_cache(cache, int(checkpoint))
        popped = register[target_abs:]
        for item in popped:
            assignment.pop(int(item["vertex"]), None)
        for item in popped[1:]:
            tried[int(item["vertex"])] = set()
        tried[vertex] = set()
        cursor = int(register[target_abs]["order_index"])
        del register[target_abs:]
    score = _official_score(dataset, entry, assignment) if len(assignment) == len(entry["metadata"]["puzzle"]["vertices"]) else 0.0
    row = {"task": "graph_color", "variant": "c1_conflict_reasoning", "bin": selected["bin"], "split": selected["split"], "source_index": int(selected["source_index"]), "R": int(r_value), "status": "SOLVED" if score >= 1.0 else status, "solved": score >= 1.0, "official_score": score, "A_total_tokens": a_cumulative, "C_total_tokens": c_cumulative, "C_over_A": (c_cumulative / a_cumulative) if a_cumulative else None, "steps": len(event_rows), "max_depth": max_depth, "backtrack_decisions": len(decision_rows), "backtrack_exact": sum(int(item["exact"]) for item in decision_rows), "parseable_rate": (sum(int(item["parseable"]) for item in decision_rows) / len(decision_rows)) if decision_rows else None, "valid_rate": (sum(int(item["valid"]) for item in decision_rows) / len(decision_rows)) if decision_rows else None, "fallback_rate": (sum(int(item["fallback"]) for item in decision_rows) / len(decision_rows)) if decision_rows else None, "answer": _official_answer(assignment) if score >= 1.0 else None, "source": SOURCE, "provenance": "kvcache_graph_color_c1_budget_trace_v0"}
    return row, event_rows, decision_rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    model, tokenizer = _load_lora_model(args, training=False)
    bin_spec = _parse_bins(args.bins)[0]
    split = "ood_eval" if str(bin_spec["label"]).startswith("v18") else "val"
    dataset, selected = _select_eval_entries(args, bin_spec, split)
    trace_rows = []
    event_samples = []
    decision_samples = []
    if args.resume and args.checkpoint_path.exists():
        existing = json.loads(args.checkpoint_path.read_text(encoding="utf-8"))
        trace_rows = existing.get("trace_rows", [])
        event_samples = existing.get("event_samples", [])
        decision_samples = existing.get("decision_samples", [])
    done = {int(row["source_index"]) for row in trace_rows}
    for selected_index, item in enumerate(selected):
        if selected_index % int(args.num_shards) != int(args.shard_index):
            continue
        if int(item["source_index"]) in done:
            continue
        print(json.dumps({"source_index": int(item["source_index"]), "bin": item["bin"], "R": int(args.r_value)}), flush=True)
        row, events, decisions = _run_one(model, tokenizer, dataset, item, int(args.r_value), args)
        trace_rows.append(row)
        event_samples.extend({"source_index": int(item["source_index"]), **event} for event in events[: int(args.max_event_rows_per_trace)])
        decision_samples.extend({"source_index": int(item["source_index"]), **decision} for decision in decisions[: int(args.max_decision_rows_per_trace)])
        _write_json(args.checkpoint_path, {"trace_rows": trace_rows, "event_samples": event_samples, "decision_samples": decision_samples})
    c_thresholds = sorted(int(row["C_total_tokens"]) for row in trace_rows if row.get("solved"))
    if not c_thresholds:
        budget_grid = [1]
    else:
        mid = c_thresholds[len(c_thresholds) // 2]
        budget_grid = sorted({max(1, int(round(float(scale) * mid))) for scale in [0.25, 0.5, 1.0, 2.0, 4.0]})
    budget_rows = []
    for row in trace_rows:
        for budget in budget_grid:
            for method, total_key in [("A_cache", "A_total_tokens"), ("C_incontext", "C_total_tokens")]:
                solved = bool(row["solved"] and int(row[total_key]) <= int(budget))
                budget_rows.append({"task": "graph_color", "variant": "c1_conflict_reasoning", "policy": "conflict_cot", "method": method, "source_index": int(row["source_index"]), "budget_B": int(budget), "solved": solved, "tokens_used": int(row[total_key]) if solved else min(int(row[total_key]), int(budget)), "full_trace_tokens": int(row[total_key]), "depth_reached": int(row["max_depth"]) if solved else 0, "steps_reached": int(row["steps"]) if solved else 0, "status_at_budget": "SOLVED" if solved else "BUDGET_EXHAUSTED", "source": SOURCE, "provenance": "kvcache_graph_color_c1_budget_row_v0"})
    curve, gaps, bstar, shape = _summarize(budget_rows)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE, "generated_at": _now(), "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "preflight": {"selected": len(selected), "bin": bin_spec["label"], "split": split, "shard_index": int(args.shard_index), "num_shards": int(args.num_shards)}, "bstar": bstar, "budget_grid": budget_grid, "curve_summary": curve, "gap_summary": gaps, "shape_summary": shape, "trace_rows": trace_rows, "budget_rows": budget_rows, "event_samples": event_samples, "decision_samples": decision_samples, "source": SOURCE, "provenance": "kvcache_graph_color_c1_budget_v0"}
    _write_json(args.output, payload)
    return payload


def merge(args: argparse.Namespace) -> dict[str, Any]:
    trace_by_source: dict[int, dict[str, Any]] = {}
    event_samples: list[dict[str, Any]] = []
    decision_samples: list[dict[str, Any]] = []
    input_files = sorted(glob.glob(args.inputs))
    for path in input_files:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        for row in payload.get("trace_rows", []):
            trace_by_source[int(row["source_index"])] = row
        event_samples.extend(payload.get("event_samples", []))
        decision_samples.extend(payload.get("decision_samples", []))
    trace_rows = [trace_by_source[key] for key in sorted(trace_by_source)]
    c_thresholds = sorted(int(row["C_total_tokens"]) for row in trace_rows if row.get("solved"))
    if not c_thresholds:
        budget_grid = [1]
    else:
        mid = c_thresholds[len(c_thresholds) // 2]
        budget_grid = sorted({max(1, int(round(float(scale) * mid))) for scale in [0.25, 0.5, 1.0, 2.0, 4.0]})
    budget_rows = []
    for row in trace_rows:
        for budget in budget_grid:
            for method, total_key in [("A_cache", "A_total_tokens"), ("C_incontext", "C_total_tokens")]:
                solved = bool(row["solved"] and int(row[total_key]) <= int(budget))
                budget_rows.append({"task": "graph_color", "variant": "c1_conflict_reasoning", "policy": "conflict_cot", "method": method, "source_index": int(row["source_index"]), "budget_B": int(budget), "solved": solved, "tokens_used": int(row[total_key]) if solved else min(int(row[total_key]), int(budget)), "full_trace_tokens": int(row[total_key]), "depth_reached": int(row["max_depth"]) if solved else 0, "steps_reached": int(row["steps"]) if solved else 0, "status_at_budget": "SOLVED" if solved else "BUDGET_EXHAUSTED", "source": SOURCE, "provenance": "kvcache_graph_color_c1_budget_row_v0"})
    curve, gaps, bstar, shape = _summarize(budget_rows)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE, "generated_at": _now(), "input_files": input_files, "bstar": bstar, "budget_grid": budget_grid, "curve_summary": curve, "gap_summary": gaps, "shape_summary": shape, "trace_rows": trace_rows, "budget_rows": budget_rows, "event_samples": event_samples, "decision_samples": decision_samples, "source": SOURCE, "provenance": "kvcache_graph_color_c1_budget_merged_v0"}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run graph_color C1 matched-budget A/C curves.")
    parser.add_argument("--merge-inputs", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-path", type=Path, required=True)
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=1000)
    parser.add_argument("--n-instances", type=int, default=64)
    parser.add_argument("--min-backtracks", type=int, default=4)
    parser.add_argument("--node-cap", type=int, default=500)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--order-mode", default="degree_desc")
    parser.add_argument("--bins", default="v16_p04:16:0.4")
    parser.add_argument("--train-fraction", type=float, default=0.8)
    parser.add_argument("--r-value", type=int, default=16)
    parser.add_argument("--call-cap", type=int, default=160)
    parser.add_argument("--cot-max-new-tokens", type=int, default=256)
    parser.add_argument("--cot-fallback", choices=["chrono", "fail"], default="chrono")
    parser.add_argument("--cot-invalid-repair", choices=["none", "score"], default="none")
    parser.add_argument("--cot-prompt-style", choices=["blockers", "per_color"], default="per_color")
    parser.add_argument("--cot-chat-template", dest="cot_chat_template", action="store_true", default=True)
    parser.add_argument("--no-cot-chat-template", dest="cot_chat_template", action="store_false")
    parser.add_argument("--cot-trace-samples", type=int, default=2)
    parser.add_argument("--max-event-rows-per-trace", type=int, default=4)
    parser.add_argument("--max-decision-rows-per-trace", type=int, default=4)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    parser.add_argument("--adapter-path", type=Path, default=None)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    payload = merge(argparse.Namespace(inputs=args.merge_inputs, output=args.output)) if args.merge_inputs else run(args)
    print(json.dumps({"path": str(args.output), "status": payload["status"], "n": len(payload["trace_rows"])}, sort_keys=True))


if __name__ == "__main__":
    main()
