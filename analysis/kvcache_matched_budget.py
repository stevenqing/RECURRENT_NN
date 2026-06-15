"""Matched-budget cache-truncation vs in-context search curves.

The primary harness is policy-fixed: it replays the same verified CSP search
trace and varies only A-style retained-prefix/cache-truncation billing versus
C-style accumulated in-context billing.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
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
    backjump_chrono,
    backjump_oracle_cbj,
    branch_first_legal,
    parse_instance,
    render_answer,
)
from experiments.rung1_distributed_graph_coloring import SOURCE


SCHEMA_VERSION = "kvcache_matched_budget_v0"
STATUS_PREREG = "KVCACHE_MATCHED_BUDGET_PREREGISTERED"
STATUS_COMPLETE = "KVCACHE_MATCHED_BUDGET_COMPLETE"


@dataclass(frozen=True)
class TraceResult:
    task: str
    source_index: int
    policy: str
    status: str
    solved: bool
    official_score: float
    base_text: str
    base_tokens: int
    events: list[dict[str, Any]]
    final_depth: int
    max_depth: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mean(values: list[float]) -> float | None:
    return mean(values) if values else None


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
    if policy == "chrono":
        return backjump_chrono
    if policy == "symbolic_cbj":
        return backjump_oracle_cbj
    raise ValueError(policy)


def _trace_csp(inst: CSPInstance, dataset: Any, tokenizer: Any, policy: str, node_cap: int) -> TraceResult:
    n_vars = len(inst.variables)
    assignment: dict[int, int] = {}
    tried: list[set[int]] = [set() for _ in range(n_vars)]
    conflict_sets: list[set[int]] = [set() for _ in range(n_vars)]
    backjump_policy = _policy_fn(policy)
    index = 0
    decisions = 0
    backtracks = 0
    status = "RUNNING"
    events: list[dict[str, Any]] = []
    max_depth = 0
    while True:
        if decisions + backtracks >= int(node_cap):
            status = "NODE_CAP"
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
            events.append({"kind": "branch", "index": index, "var": inst.variables[index], "value": value, "depth": len(assignment)})
            max_depth = max(max_depth, len(assignment))
            decisions += 1
            index += 1
            continue
        conflict = set(conflict_sets[index]) | set(local_conflict)
        if not conflict:
            status = "NO_CONFLICT_SET"
            break
        target = int(backjump_policy(conflict, index, None))
        if target < 0 or target >= index:
            status = "INVALID_BACKJUMP_TARGET"
            break
        if target not in assignment:
            status = "TARGET_UNASSIGNED"
            break
        for clear_index in range(target + 1, index + 1):
            assignment.pop(clear_index, None)
            tried[clear_index].clear()
            conflict_sets[clear_index].clear()
        old_value = assignment.pop(target)
        tried[target].add(int(old_value))
        conflict_sets[target].update(conflict - {target})
        events.append({
            "kind": "backjump",
            "index": index,
            "var": inst.variables[index],
            "target": int(target),
            "target_var": inst.variables[target],
            "depth": len(assignment),
            "popped": index - target,
        })
        backtracks += 1
        index = target
    answer = render_answer(inst, assignment) if status == "SOLVED" else ""
    score = float(dataset.score_answer(answer, inst.entry)) if answer else 0.0
    if score >= 0.99:
        status = "SOLVED"
    base_text = f"Task={inst.task}\nProblem:\n{inst.entry.get('question','')}\n"
    base_tokens = len(tokenizer(base_text, add_special_tokens=False).input_ids)
    return TraceResult(
        task=inst.task,
        source_index=int(inst.entry["metadata"].get("source_index", -1)),
        policy=policy,
        status=status,
        solved=score >= 0.99,
        official_score=score,
        base_text=base_text,
        base_tokens=base_tokens,
        events=events,
        final_depth=len(assignment),
        max_depth=max_depth,
    )


def _bill_trace(trace: TraceResult, tokenizer: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    transcript = trace.base_text
    cumulative_a = int(trace.base_tokens)
    cumulative_c = 0
    rows: list[dict[str, Any]] = []
    max_depth_seen = 0
    for step_index, event in enumerate(trace.events, start=1):
        text = _event_text(event)
        a_tokens = len(tokenizer(text, add_special_tokens=False).input_ids)
        c_tokens = len(tokenizer(transcript + text, add_special_tokens=False).input_ids)
        cumulative_a += a_tokens
        cumulative_c += c_tokens
        transcript += text + "\n"
        max_depth_seen = max(max_depth_seen, int(event.get("depth", 0)))
        rows.append({
            "step_index": step_index,
            "kind": event["kind"],
            "depth": int(event.get("depth", 0)),
            "A_tokens_step": a_tokens,
            "C_tokens_step": c_tokens,
            "A_tokens_cumulative": cumulative_a,
            "C_tokens_cumulative": cumulative_c,
        })
    return rows, {
        "A_total_tokens": cumulative_a,
        "C_total_tokens": cumulative_c,
        "steps": len(trace.events),
        "max_depth_seen": max_depth_seen,
    }


def _budget_eval(trace: TraceResult, billed: list[dict[str, Any]], method: str, budget: int) -> dict[str, Any]:
    key = "A_tokens_cumulative" if method == "A_cache" else "C_tokens_cumulative"
    processed = [row for row in billed if int(row[key]) <= int(budget)]
    tokens_used = int(processed[-1][key]) if processed else 0
    depth_reached = max((int(row["depth"]) for row in processed), default=0)
    full_tokens = int(billed[-1][key]) if billed else (trace.base_tokens if method == "A_cache" else 0)
    solved = bool(trace.solved and full_tokens <= int(budget))
    return {
        "method": method,
        "budget_B": int(budget),
        "tokens_used": full_tokens if solved else tokens_used,
        "solved": solved,
        "depth_reached": trace.max_depth if solved else depth_reached,
        "steps_reached": len(billed) if solved else len(processed),
        "full_trace_tokens": full_tokens,
    }


def _budget_grid(c_totals: list[int], fallback: list[int]) -> list[int]:
    vals = sorted(int(value) for value in c_totals if int(value) > 0)
    if not vals:
        return sorted(set(int(value) for value in fallback if int(value) > 0))
    quantiles = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
    grid = set()
    for quantile in quantiles:
        idx = min(len(vals) - 1, max(0, int(round((len(vals) - 1) * quantile))))
        grid.add(vals[idx])
    median = vals[len(vals) // 2]
    for scale in [0.25, 0.5, 0.75, 1.25, 1.5, 2.0]:
        grid.add(max(1, int(median * scale)))
    return sorted(grid)


def _summarize_curve(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    groups = sorted({(row["task"], row["policy"], row["method"], int(row["budget_B"])) for row in rows})
    for task, policy, method, budget in groups:
        subset = [row for row in rows if row["task"] == task and row["policy"] == policy and row["method"] == method and int(row["budget_B"]) == budget]
        summary.append({
            "task": task,
            "policy": policy,
            "method": method,
            "budget_B": budget,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_tokens_used": mean(float(row["tokens_used"]) for row in subset),
            "mean_depth_reached": mean(float(row["depth_reached"]) for row in subset),
            "mean_steps_reached": mean(float(row["steps_reached"]) for row in subset),
            "source": SOURCE,
            "provenance": "kvcache_matched_budget_curve_summary_v0",
        })
    return summary


def _select_bstar(curve_summary: list[dict[str, Any]], task: str) -> dict[str, Any]:
    c_rows = [row for row in curve_summary if row["task"] == task and row["method"] == "C_incontext"]
    by_budget: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in c_rows:
        by_budget[int(row["budget_B"])].append(row)
    candidates = []
    for budget, rows in sorted(by_budget.items()):
        best = max(float(row["solve_rate"]) for row in rows)
        best_policy = sorted(row["policy"] for row in rows if float(row["solve_rate"]) == best)[0]
        candidates.append({"budget_B": budget, "best_baseline_solve": best, "best_policy": best_policy})
    mid = [row for row in candidates if 0.4 <= float(row["best_baseline_solve"]) <= 0.6]
    if mid:
        selected = mid[0] | {"selection_rule_status": "MIDBAND_FOUND"}
    else:
        selected = min(candidates, key=lambda row: abs(float(row["best_baseline_solve"]) - 0.5)) | {"selection_rule_status": "MIDBAND_NOT_FOUND_NEAREST"}
    return selected | {"task": task, "source": SOURCE, "provenance": "kvcache_matched_budget_bstar_v0"}


def _hb_rows(curve_summary: list[dict[str, Any]], bstars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for bstar in bstars:
        task = bstar["task"]
        budget = int(bstar["budget_B"])
        for policy in sorted({row["policy"] for row in curve_summary if row["task"] == task}):
            a = [row for row in curve_summary if row["task"] == task and row["policy"] == policy and row["method"] == "A_cache" and int(row["budget_B"]) == budget]
            c = [row for row in curve_summary if row["task"] == task and row["policy"] == policy and row["method"] == "C_incontext" and int(row["budget_B"]) == budget]
            if not a or not c:
                continue
            a_rate = float(a[0]["solve_rate"])
            c_rate = float(c[0]["solve_rate"])
            rows.append({
                "task": task,
                "policy": policy,
                "budget_B": budget,
                "A_solve_rate": a_rate,
                "C_solve_rate": c_rate,
                "A_minus_C_solve": a_rate - c_rate,
                "hb1_policy_read": policy == "symbolic_cbj",
                "hb1_pass_for_task": (a_rate - c_rate) >= 0.10 if policy == "symbolic_cbj" else None,
                "source": SOURCE,
                "provenance": "kvcache_matched_budget_hb_row_v0",
            })
    return rows


def _hb3_shape(curve_summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    groups = sorted({(row["task"], row["policy"]) for row in curve_summary})
    for task, policy in groups:
        budgets = sorted({int(row["budget_B"]) for row in curve_summary if row["task"] == task and row["policy"] == policy})
        diffs = []
        mid_diffs = []
        for budget in budgets:
            a = [row for row in curve_summary if row["task"] == task and row["policy"] == policy and row["method"] == "A_cache" and int(row["budget_B"]) == budget]
            c = [row for row in curve_summary if row["task"] == task and row["policy"] == policy and row["method"] == "C_incontext" and int(row["budget_B"]) == budget]
            if not a or not c:
                continue
            diff = float(a[0]["solve_rate"]) - float(c[0]["solve_rate"])
            diffs.append(diff)
            if 0.2 <= float(c[0]["solve_rate"]) <= 0.8:
                mid_diffs.append(diff)
        rows.append({
            "task": task,
            "policy": policy,
            "n_budgets": len(diffs),
            "all_A_ge_C": bool(diffs and all(diff >= -1e-9 for diff in diffs)),
            "midband_A_ge_C": bool(mid_diffs and all(diff >= -1e-9 for diff in mid_diffs)),
            "min_gap": min(diffs) if diffs else None,
            "max_gap": max(diffs) if diffs else None,
            "midband_min_gap": min(mid_diffs) if mid_diffs else None,
            "midband_max_gap": max(mid_diffs) if mid_diffs else None,
            "source": SOURCE,
            "provenance": "kvcache_matched_budget_hb3_shape_v0",
        })
    return rows


def _trace_summary(trace_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for task, policy in sorted({(row["task"], row["policy"]) for row in trace_rows}):
        subset = [row for row in trace_rows if row["task"] == task and row["policy"] == policy]
        solved = [row for row in subset if row["solved"]]
        summary.append({
            "task": task,
            "policy": policy,
            "n": len(subset),
            "full_trace_solve_rate": mean(float(row["solved"]) for row in subset),
            "status_counts": dict(Counter(row["status"] for row in subset)),
            "mean_A_total_tokens_solved": _mean([float(row["A_total_tokens"]) for row in solved]),
            "mean_C_total_tokens_solved": _mean([float(row["C_total_tokens"]) for row in solved]),
            "mean_C_over_A_solved": _mean([float(row["C_over_A"]) for row in solved if row["C_over_A"] is not None]),
            "mean_steps_solved": _mean([float(row["steps"]) for row in solved]),
            "source": SOURCE,
            "provenance": "kvcache_matched_budget_trace_summary_v0",
        })
    return summary


def write_prereg(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "schema_version": "kvcache_matched_budget_prereg_v0",
        "status": STATUS_PREREG,
        "generated_at": _now(),
        "name": "Matched-budget cache-truncation vs in-context search preregistration",
        "source": SOURCE,
        "provenance": "kvcache_matched_budget_prereg_v0",
        "parent_items": ["104", "117", "118"],
        "headline_metric": "solve@budget curve over budget grid; B* selected by first C-baseline mid-band [0.4,0.6] solve rate per task",
        "hb1_primary": "A_cache minus C_incontext solve >= 0.10 at B* on deep-search tasks under matched symbolic-CBJ policy",
        "hb2_secondary": "external baselines are not claimed unless faithful upstream/reimplementation is integrated and billed by same token counter",
        "hb3_shape": "A solve@B dominates C over mid-budget band",
        "accounting": "A counts retained prefix once plus event tokens; C counts growing in-context prompt tokens per event, matching Item117 A_tokens/C_tokens semantics",
        "honesty": "No external SOTA curve is fabricated; not-run baselines remain not-run.",
    }
    _write_json(args.output, payload)
    return payload


def run_primary(args: argparse.Namespace) -> dict[str, Any]:
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    tasks = [task.strip() for task in args.tasks.split(",") if task.strip()]
    policies = [policy.strip() for policy in args.policies.split(",") if policy.strip()]
    trace_rows = []
    event_rows = []
    budget_rows = []
    budget_grids: dict[str, list[int]] = {}
    for task in tasks:
        task_args = _task_args(task, args)
        dataset = _make_dataset(task, task_args)
        task_traces: list[tuple[TraceResult, list[dict[str, Any]], dict[str, Any]]] = []
        for source_index in range(int(args.n_instances)):
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = source_index
            inst = parse_instance(task, entry)
            for policy in policies:
                trace = _trace_csp(inst, dataset, tokenizer, policy=policy, node_cap=int(args.node_cap))
                billed, totals = _bill_trace(trace, tokenizer)
                task_traces.append((trace, billed, totals))
                trace_rows.append({
                    "task": task,
                    "source_index": source_index,
                    "policy": policy,
                    "status": trace.status,
                    "solved": trace.solved,
                    "official_score": trace.official_score,
                    "A_total_tokens": totals["A_total_tokens"],
                    "C_total_tokens": totals["C_total_tokens"],
                    "C_over_A": (totals["C_total_tokens"] / totals["A_total_tokens"]) if totals["A_total_tokens"] else None,
                    "steps": totals["steps"],
                    "max_depth_seen": totals["max_depth_seen"],
                    "source": SOURCE,
                    "provenance": "kvcache_matched_budget_trace_row_v0",
                })
                for event in billed[: int(args.max_event_rows_per_trace)]:
                    event_rows.append({"task": task, "source_index": source_index, "policy": policy, **event, "source": SOURCE, "provenance": "kvcache_matched_budget_event_row_v0"})
        c_totals = [totals["C_total_tokens"] for trace, _billed, totals in task_traces if trace.solved]
        a_totals = [totals["A_total_tokens"] for trace, _billed, totals in task_traces if trace.solved]
        grid = _budget_grid(c_totals, a_totals)
        if args.extra_budget_scales:
            base = sorted(c_totals)[len(c_totals) // 2] if c_totals else 1000
            for scale in [float(item) for item in args.extra_budget_scales.split(",") if item.strip()]:
                grid.append(max(1, int(base * scale)))
            grid = sorted(set(grid))
        budget_grids[task] = grid
        for trace, billed, _totals in task_traces:
            for budget in grid:
                for method in ["A_cache", "C_incontext"]:
                    row = _budget_eval(trace, billed, method, budget)
                    budget_rows.append({
                        "task": trace.task,
                        "source_index": trace.source_index,
                        "policy": trace.policy,
                        "status_full_trace": trace.status,
                        **row,
                        "source": SOURCE,
                        "provenance": "kvcache_matched_budget_run_row_v0",
                    })
    curve_summary = _summarize_curve(budget_rows)
    bstars = [_select_bstar(curve_summary, task) for task in tasks]
    hb_rows = _hb_rows(curve_summary, bstars)
    hb3_rows = _hb3_shape(curve_summary)
    hb1_task_rows = [row for row in hb_rows if row.get("hb1_policy_read")]
    hb1_pass = bool(hb1_task_rows and all(row["hb1_pass_for_task"] for row in hb1_task_rows))
    external_baselines = [
        {"method": "LFS", "status": "NOT_RUN", "reason": "faithful upstream/model-matched implementation not integrated in this repo for item119"},
        {"method": "ReST-MCTS*", "status": "NOT_RUN", "reason": "PRM rollout/scoring implementation not integrated; no fabricated curve"},
        {"method": "Beyond-the-Frontier", "status": "NOT_RUN", "reason": "faithful upstream/model-matched implementation not integrated"},
        {"method": "To-Backtrack-or-Not", "status": "NOT_RUN", "reason": "faithful backtracking-decision baseline not integrated"},
    ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "job": "primary_csp_matched_budget",
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "budget_grids": budget_grids,
        "bstar": bstars,
        "hb1_pass": hb1_pass,
        "hb1_read": "PASS" if hb1_pass else "FAIL_COST_DOES_NOT_CONVERT_TO_SOLVE_SUPERIORITY_UNDER_THIS_TRACE_SET",
        "hb1_rows": hb_rows,
        "hb3_shape": hb3_rows,
        "external_baselines": external_baselines,
        "trace_summary": _trace_summary(trace_rows),
        "curve_summary": curve_summary,
        "budget_rows": budget_rows,
        "trace_rows": trace_rows,
        "event_rows_sample": event_rows,
        "source": SOURCE,
        "provenance": "kvcache_matched_budget_primary_csp_v0",
    }
    _write_json(args.output, payload)
    print(json.dumps({"path": str(args.output), "status": payload["status"], "hb1_pass": hb1_pass}, sort_keys=True))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Matched-budget cache vs in-context budget curves.")
    sub = parser.add_subparsers(dest="command", required=True)

    prereg = sub.add_parser("preregister")
    prereg.add_argument("--output", type=Path, required=True)

    primary = sub.add_parser("primary-csp")
    primary.add_argument("--output", type=Path, required=True)
    primary.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    primary.add_argument("--reasoning-gym-repo", default=None)
    primary.add_argument("--seed", type=int, default=42)
    primary.add_argument("--scan-limit", type=int, default=120)
    primary.add_argument("--n-instances", type=int, default=24)
    primary.add_argument("--tasks", default="sudoku,futoshiki")
    primary.add_argument("--policies", default="chrono,symbolic_cbj")
    primary.add_argument("--node-cap", type=int, default=100000)
    primary.add_argument("--futoshiki-size", type=int, default=7)
    primary.add_argument("--futoshiki-difficulty", type=int, default=3)
    primary.add_argument("--extra-budget-scales", default="")
    primary.add_argument("--max-event-rows-per-trace", type=int, default=16)

    args = parser.parse_args()
    if args.command == "preregister":
        write_prereg(args)
    elif args.command == "primary-csp":
        run_primary(args)


if __name__ == "__main__":
    main()
