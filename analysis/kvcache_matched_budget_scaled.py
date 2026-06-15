"""Scaled matched-budget A-vs-C curves with sharding and C budget caps."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import glob
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any, Callable

from transformers import AutoTokenizer

from analysis.kvcache_graph_color_search import _write_json
from analysis.kvcache_gate2_csp_solver import (
    CSPInstance,
    _event_text,
    _legal_values,
    _make_dataset,
    backjump_oracle_cbj,
    branch_first_legal,
    parse_instance,
    render_answer,
)
from experiments.rung1_distributed_graph_coloring import SOURCE


SCHEMA_VERSION = "kvcache_matched_budget_scaled_v0"
STATUS_COMPLETE = "KVCACHE_MATCHED_BUDGET_SCALED_SHARD_COMPLETE"
STATUS_MERGED = "KVCACHE_MATCHED_BUDGET_SCALED_MERGED"


@dataclass(frozen=True)
class BudgetTrace:
    task: str
    source_index: int
    policy: str
    status: str
    solved: bool
    official_score: float
    base_tokens: int
    a_total_tokens: int
    c_total_tokens: int
    steps: int
    max_depth: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_args(task: str, args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        reasoning_gym_repo=args.reasoning_gym_repo,
        task=task,
        seed=args.seed,
        scan_limit=args.scan_limit,
        n_instances=args.n_instances,
        futoshiki_size=args.futoshiki_size,
        futoshiki_difficulty=args.futoshiki_difficulty,
        n_queens_n=8,
        n_queens_min_remove=1,
        n_queens_max_remove=7,
        output=Path("unused.json"),
        model=args.model,
        dtype="fp32",
        device="cpu",
    )


def _policy_fn(policy: str) -> Callable[[set[int], int, random.Random | None], int]:
    if policy == "symbolic_cbj":
        return backjump_oracle_cbj
    raise ValueError(f"unsupported scaled policy {policy}")


def _budget_anchors(text: str) -> dict[str, int]:
    anchors = {}
    for item in text.split(","):
        if not item.strip():
            continue
        key, value = item.split(":", 1)
        anchors[key.strip()] = int(float(value.strip()))
    return anchors


def _budget_grid(anchor: int, scales: str) -> list[int]:
    return sorted({max(1, int(round(float(scale.strip()) * int(anchor)))) for scale in scales.split(",") if scale.strip()})


def _wilson(successes: int, n: int, z: float = 1.959963984540054) -> dict[str, float | None]:
    if n <= 0:
        return {"rate": None, "ci_low": None, "ci_high": None}
    phat = successes / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return {"rate": phat, "ci_low": max(0.0, center - half), "ci_high": min(1.0, center + half)}


def _stream_trace(
    inst: CSPInstance,
    dataset: Any,
    tokenizer: Any,
    task: str,
    policy: str,
    budgets: list[int],
    node_cap: int,
) -> tuple[BudgetTrace, list[dict[str, Any]], list[dict[str, Any]]]:
    max_budget = max(int(budget) for budget in budgets)
    n_vars = len(inst.variables)
    assignment: dict[int, int] = {}
    tried: list[set[int]] = [set() for _ in range(n_vars)]
    conflict_sets: list[set[int]] = [set() for _ in range(n_vars)]
    backjump_policy = _policy_fn(policy)
    index = 0
    decisions = 0
    backtracks = 0
    status = "RUNNING"
    max_depth = 0
    base_text = f"Task={task}\nProblem:\n{inst.entry.get('question','')}\n"
    transcript = base_text
    base_tokens = len(tokenizer(base_text, add_special_tokens=False).input_ids)
    a_cumulative = int(base_tokens)
    c_cumulative = 0
    event_rows: list[dict[str, Any]] = []
    budget_rows: list[dict[str, Any]] = []
    budget_done = {("A_cache", budget): False for budget in budgets} | {("C_incontext", budget): False for budget in budgets}

    def record_budget_rows() -> None:
        for budget in budgets:
            if not budget_done[("A_cache", budget)] and a_cumulative > int(budget):
                budget_rows.append({"method": "A_cache", "budget_B": int(budget), "solved": False, "tokens_used": min(a_cumulative, int(budget)), "depth_reached": max_depth, "steps_reached": len(event_rows), "status_at_budget": "BUDGET_EXHAUSTED"})
                budget_done[("A_cache", budget)] = True
            if not budget_done[("C_incontext", budget)] and c_cumulative > int(budget):
                budget_rows.append({"method": "C_incontext", "budget_B": int(budget), "solved": False, "tokens_used": min(c_cumulative, int(budget)), "depth_reached": max_depth, "steps_reached": len(event_rows), "status_at_budget": "BUDGET_EXHAUSTED"})
                budget_done[("C_incontext", budget)] = True

    while True:
        if decisions + backtracks >= int(node_cap):
            status = "NODE_CAP"
            break
        if a_cumulative > max_budget and c_cumulative > max_budget:
            status = "BUDGET_CAP"
            break
        if index < 0:
            status = "EXHAUSTED"
            break
        if index >= n_vars:
            status = "SOLVED"
            break
        legal, local_conflict = _legal_values(inst, index, assignment, tried[index])
        if legal:
            value = int(branch_first_legal(legal, inst, index, None))
            assignment[index] = value
            event = {"kind": "branch", "index": index, "var": inst.variables[index], "value": value, "depth": len(assignment)}
            decisions += 1
            index += 1
        else:
            conflict = set(conflict_sets[index]) | set(local_conflict)
            if not conflict:
                status = "NO_CONFLICT_SET"
                break
            target = int(backjump_policy(conflict, index, None))
            if target < 0 or target >= index or target not in assignment:
                status = "INVALID_BACKJUMP_TARGET"
                break
            for clear_index in range(target + 1, index + 1):
                assignment.pop(clear_index, None)
                tried[clear_index].clear()
                conflict_sets[clear_index].clear()
            old_value = assignment.pop(target)
            tried[target].add(int(old_value))
            conflict_sets[target].update(conflict - {target})
            event = {"kind": "backjump", "index": index, "var": inst.variables[index], "target": int(target), "target_var": inst.variables[target], "depth": len(assignment), "popped": index - target}
            backtracks += 1
            index = target
        event_text = _event_text(event)
        a_step = len(tokenizer(event_text, add_special_tokens=False).input_ids)
        c_step = len(tokenizer(transcript + event_text, add_special_tokens=False).input_ids)
        a_cumulative += a_step
        c_cumulative += c_step
        transcript += event_text + "\n"
        max_depth = max(max_depth, int(event.get("depth", 0)))
        event_rows.append({"step_index": len(event_rows) + 1, "kind": event["kind"], "depth": int(event.get("depth", 0)), "A_tokens_cumulative": a_cumulative, "C_tokens_cumulative": c_cumulative, "A_tokens_step": a_step, "C_tokens_step": c_step})
        record_budget_rows()
    answer = render_answer(inst, assignment) if status == "SOLVED" else ""
    score = float(dataset.score_answer(answer, inst.entry)) if answer else 0.0
    solved = bool(score >= 0.99)
    if solved:
        status = "SOLVED"
    for budget in budgets:
        if not budget_done[("A_cache", budget)]:
            budget_rows.append({"method": "A_cache", "budget_B": int(budget), "solved": bool(solved and a_cumulative <= int(budget)), "tokens_used": a_cumulative if a_cumulative <= int(budget) else int(budget), "depth_reached": max_depth, "steps_reached": len(event_rows), "status_at_budget": "SOLVED" if solved and a_cumulative <= int(budget) else status})
        if not budget_done[("C_incontext", budget)]:
            budget_rows.append({"method": "C_incontext", "budget_B": int(budget), "solved": bool(solved and c_cumulative <= int(budget)), "tokens_used": c_cumulative if c_cumulative <= int(budget) else int(budget), "depth_reached": max_depth, "steps_reached": len(event_rows), "status_at_budget": "SOLVED" if solved and c_cumulative <= int(budget) else status})
    trace = BudgetTrace(task=task, source_index=int(inst.entry["metadata"].get("source_index", -1)), policy=policy, status=status, solved=solved, official_score=score, base_tokens=base_tokens, a_total_tokens=a_cumulative, c_total_tokens=c_cumulative, steps=len(event_rows), max_depth=max_depth)
    return trace, event_rows, budget_rows


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def run_shard(args: argparse.Namespace) -> dict[str, Any]:
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    anchors = _budget_anchors(args.budget_anchors)
    policies = [item.strip() for item in args.policies.split(",") if item.strip()]
    checkpoint_path = args.checkpoint_path
    trace_rows = []
    budget_rows = []
    event_samples = []
    if args.resume and checkpoint_path and checkpoint_path.exists():
        prior = _read_json(checkpoint_path)
        trace_rows = list(prior.get("trace_rows", []))
        budget_rows = list(prior.get("budget_rows", []))
        event_samples = list(prior.get("event_samples", []))
    done = {(row["task"], int(row["source_index"]), row["policy"]) for row in trace_rows}
    for task in [item.strip() for item in args.tasks.split(",") if item.strip()]:
        budgets = _budget_grid(anchors[task], args.budget_scales)
        dataset = _make_dataset(task, _task_args(task, args))
        for source_index in range(int(args.n_instances)):
            if source_index % int(args.num_shards) != int(args.shard_index):
                continue
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = source_index
            inst = parse_instance(task, entry)
            for policy in policies:
                key = (task, source_index, policy)
                if key in done:
                    continue
                print(json.dumps({"task": task, "source_index": source_index, "policy": policy, "shard": args.shard_index}), flush=True)
                trace, events, budgets_out = _stream_trace(inst, dataset, tokenizer, task, policy, budgets, int(args.node_cap))
                trace_rows.append({"task": task, "source_index": source_index, "policy": policy, "status": trace.status, "solved_full_trace": trace.solved, "official_score": trace.official_score, "A_total_tokens": trace.a_total_tokens, "C_total_tokens": trace.c_total_tokens, "C_over_A": (trace.c_total_tokens / trace.a_total_tokens) if trace.a_total_tokens else None, "steps": trace.steps, "max_depth": trace.max_depth, "source": SOURCE, "provenance": "kvcache_matched_budget_scaled_trace_v0"})
                for row in budgets_out:
                    budget_rows.append({"task": task, "source_index": source_index, "policy": policy, **row, "source": SOURCE, "provenance": "kvcache_matched_budget_scaled_budget_row_v0"})
                for event in events[: int(args.max_event_rows_per_trace)]:
                    event_samples.append({"task": task, "source_index": source_index, "policy": policy, **event, "source": SOURCE, "provenance": "kvcache_matched_budget_scaled_event_sample_v0"})
                done.add(key)
                if checkpoint_path:
                    _write_json(checkpoint_path, {"schema_version": SCHEMA_VERSION, "status": "CHECKPOINT", "trace_rows": trace_rows, "budget_rows": budget_rows, "event_samples": event_samples})
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_COMPLETE, "generated_at": _now(), "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()}, "trace_rows": trace_rows, "budget_rows": budget_rows, "event_samples": event_samples, "source": SOURCE, "provenance": "kvcache_matched_budget_scaled_shard_v0"}
    _write_json(args.output, payload)
    return payload


def _summarize(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    curve = []
    for key in sorted({(row["task"], row["policy"], row["method"], int(row["budget_B"])) for row in rows}):
        task, policy, method, budget = key
        subset = [row for row in rows if row["task"] == task and row["policy"] == policy and row["method"] == method and int(row["budget_B"]) == budget]
        successes = sum(int(row["solved"]) for row in subset)
        ci = _wilson(successes, len(subset))
        curve.append({"task": task, "policy": policy, "method": method, "budget_B": budget, "n": len(subset), "solve_count": successes, "solve_rate": ci["rate"], "solve_ci_low": ci["ci_low"], "solve_ci_high": ci["ci_high"], "mean_tokens_used": mean(float(row["tokens_used"]) for row in subset), "mean_depth_reached": mean(float(row["depth_reached"]) for row in subset), "mean_steps_reached": mean(float(row["steps_reached"]) for row in subset), "status_counts": dict(Counter(row["status_at_budget"] for row in subset)), "source": SOURCE, "provenance": "kvcache_matched_budget_scaled_curve_v0"})
    gaps = []
    for key in sorted({(row["task"], row["policy"], int(row["budget_B"])) for row in rows}):
        task, policy, budget = key
        a = next((row for row in curve if row["task"] == task and row["policy"] == policy and row["method"] == "A_cache" and int(row["budget_B"]) == budget), None)
        c = next((row for row in curve if row["task"] == task and row["policy"] == policy and row["method"] == "C_incontext" and int(row["budget_B"]) == budget), None)
        if not a or not c:
            continue
        gap = float(a["solve_rate"] or 0.0) - float(c["solve_rate"] or 0.0)
        gaps.append({"task": task, "policy": policy, "budget_B": budget, "A_solve_rate": a["solve_rate"], "C_solve_rate": c["solve_rate"], "A_minus_C": gap, "gap_ci_low_conservative": float(a["solve_ci_low"] or 0.0) - float(c["solve_ci_high"] or 0.0), "gap_ci_high_conservative": float(a["solve_ci_high"] or 0.0) - float(c["solve_ci_low"] or 0.0), "promotion_midband_pass": bool(gap >= 0.10 and (float(a["solve_ci_low"] or 0.0) - float(c["solve_ci_high"] or 0.0)) > 0.0), "source": SOURCE, "provenance": "kvcache_matched_budget_scaled_gap_v0"})
    shape = []
    for key in sorted({(row["task"], row["policy"]) for row in gaps}):
        task, policy = key
        subset = [row for row in gaps if row["task"] == task and row["policy"] == policy]
        shape.append({"task": task, "policy": policy, "A_dominates_grid": all(float(row["A_minus_C"]) >= -1e-9 for row in subset), "min_gap": min(float(row["A_minus_C"]) for row in subset), "max_gap": max(float(row["A_minus_C"]) for row in subset), "promotion_points": sum(int(row["promotion_midband_pass"]) for row in subset), "source": SOURCE, "provenance": "kvcache_matched_budget_scaled_shape_v0"})
    return curve, gaps, shape


def merge(args: argparse.Namespace) -> dict[str, Any]:
    inputs = sorted(glob.glob(args.inputs))
    trace_rows = []
    budget_rows = []
    event_samples = []
    for path in inputs:
        payload = _read_json(Path(path))
        trace_rows.extend(payload.get("trace_rows", []))
        budget_rows.extend(payload.get("budget_rows", []))
        event_samples.extend(payload.get("event_samples", []))
    curve, gaps, shape = _summarize(budget_rows)
    payload = {"schema_version": SCHEMA_VERSION, "status": STATUS_MERGED, "generated_at": _now(), "input_files": inputs, "curve_summary": curve, "gap_summary": gaps, "shape_summary": shape, "trace_rows": trace_rows, "budget_rows": budget_rows, "event_samples": event_samples, "source": SOURCE, "provenance": "kvcache_matched_budget_scaled_merged_v0"}
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaled matched-budget A-vs-C primary curves.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run-shard")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--checkpoint-path", type=Path, default=None)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    run.add_argument("--reasoning-gym-repo", default=None)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--scan-limit", type=int, default=120)
    run.add_argument("--n-instances", type=int, default=64)
    run.add_argument("--tasks", default="sudoku,futoshiki")
    run.add_argument("--policies", default="symbolic_cbj")
    run.add_argument("--node-cap", type=int, default=50000)
    run.add_argument("--futoshiki-size", type=int, default=7)
    run.add_argument("--futoshiki-difficulty", type=int, default=3)
    run.add_argument("--budget-anchors", default="sudoku:28070,futoshiki:3206226")
    run.add_argument("--budget-scales", default="0.25,0.5,1,2,4")
    run.add_argument("--shard-index", type=int, default=0)
    run.add_argument("--num-shards", type=int, default=1)
    run.add_argument("--max-event-rows-per-trace", type=int, default=8)
    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("--inputs", required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run-shard":
        payload = run_shard(args)
        print(json.dumps({"path": str(args.output), "status": payload["status"], "rows": len(payload["budget_rows"])}, sort_keys=True))
    elif args.command == "merge":
        payload = merge(args)
        print(json.dumps({"path": str(args.output), "status": payload["status"], "rows": len(payload["budget_rows"])}, sort_keys=True))


if __name__ == "__main__":
    main()
