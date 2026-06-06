"""M2.0 frozen generative operator probe with cheap prompt fixes."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from llm_operator.qwen_operator import QwenGenerativeOperator
from llm_operator.symbolic_filter import build_tasks, forced_moves, propagation_fixpoint, sample_probe_nodes, status


TASK_TYPES = ["horn_sat", "general_sat", "graph_coloring", "sudoku_4x4", "logic_grid"]
SUDOKU_RENDERINGS = ["grid", "cells", "candidates"]


def _safe_div(num: float, den: float) -> float | None:
    return num / den if den else None


def _mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _std(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def _list_all_episode(operator: QwenGenerativeOperator, node: Any, batch_size: int, sudoku_rendering: str) -> dict[str, Any]:
    prediction = operator.predict(node.task, node.partial_assignment, batch_size=batch_size, mode="list_all", sudoku_rendering=sudoku_rendering)
    true_forced = forced_moves(node.task, node.partial_assignment)
    proposed = prediction.forced if prediction.parse_success else {}
    hits = sum(1 for var, value in proposed.items() if true_forced.get(var) == value)
    filtered = {var: value for var, value in proposed.items() if true_forced.get(var) == value}
    return {
        "parse_success": prediction.parse_success,
        "reprompted": prediction.reprompted,
        "failure_modes": prediction.failure_modes,
        "predicted_status": prediction.status,
        "proposed_n": len(proposed),
        "true_n": len(true_forced),
        "hits": hits,
        "filter_dropped": max(0, len(proposed) - len(filtered)),
        "raw_text": prediction.raw_text,
    }


def _single_iterated_episode(operator: QwenGenerativeOperator, node: Any, batch_size: int, sudoku_rendering: str) -> dict[str, Any]:
    oracle_assignment, oracle_rounds, oracle_fix_status = propagation_fixpoint(node.task, node.partial_assignment)
    max_rounds = max(1, 2 * oracle_rounds)
    current = dict(node.partial_assignment)
    calls = 0
    parse_successes = 0
    accepted = 0
    rejected = 0
    failure_modes: list[str] = []
    raw_steps = []
    predicted_statuses = []
    reached = set(current.items()) >= set(oracle_assignment.items())
    for _ in range(max_rounds):
        if reached or status(node.task, current) != "OPEN":
            break
        prediction = operator.predict(node.task, current, batch_size=batch_size, mode="single", sudoku_rendering=sudoku_rendering)
        calls += 1
        parse_successes += int(prediction.parse_success)
        failure_modes.extend(prediction.failure_modes)
        predicted_statuses.append(prediction.status)
        raw_steps.append(prediction.raw_text)
        if not prediction.parse_success:
            break
        allowed = forced_moves(node.task, current)
        proposed = next(iter(prediction.forced.items())) if prediction.forced else None
        if proposed is None:
            break
        var, value = proposed
        if allowed.get(var) == value and var not in current:
            current[var] = value
            accepted += 1
            reached = set(current.items()) >= set(oracle_assignment.items())
        else:
            rejected += 1
            break
    return {
        "calls": calls,
        "parse_successes": parse_successes,
        "parse_success_rate": _safe_div(parse_successes, calls),
        "accepted_moves": accepted,
        "rejected_moves": rejected,
        "per_call_precision": _safe_div(accepted, accepted + rejected),
        "rounds_to_fixpoint": accepted if reached else None,
        "reached_fixpoint": reached,
        "oracle_fixpoint_rounds": oracle_rounds,
        "oracle_fixpoint_status": oracle_fix_status,
        "failure_modes": failure_modes,
        "predicted_statuses": predicted_statuses,
        "raw_steps": raw_steps,
    }


def _summarize_seed(rows: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    selected = [row for row in rows if row["mode"] == mode]
    for row in selected:
        by_task[row["task_type"]].append(row)

    def summarize_subset(subset: list[dict[str, Any]]) -> dict[str, Any]:
        if mode == "list_all":
            proposed = sum(row["proposed_n"] for row in subset)
            true = sum(row["true_n"] for row in subset)
            hits = sum(row["hits"] for row in subset)
            parse_success = sum(1 for row in subset if row["parse_success"])
            return {
                "n": len(subset),
                "parse_success_rate": _safe_div(parse_success, len(subset)),
                "forced_recall": _safe_div(hits, true),
                "raw_precision": _safe_div(hits, proposed),
                "filter_dropped": sum(row["filter_dropped"] for row in subset),
            }
        calls = sum(row["calls"] for row in subset)
        parse_successes = sum(row["parse_successes"] for row in subset)
        accepted = sum(row["accepted_moves"] for row in subset)
        rejected = sum(row["rejected_moves"] for row in subset)
        rounds = [row["rounds_to_fixpoint"] for row in subset if row["rounds_to_fixpoint"] is not None]
        return {
            "n": len(subset),
            "calls": calls,
            "parse_success_rate": _safe_div(parse_successes, calls),
            "per_call_precision": _safe_div(accepted, accepted + rejected),
            "fixpoint_reach_rate": _safe_div(sum(1 for row in subset if row["reached_fixpoint"]), len(subset)),
            "mean_rounds_to_fixpoint": _mean(rounds),
            "accepted_moves": accepted,
            "rejected_moves": rejected,
        }

    return {"overall": summarize_subset(selected), "by_task": {task: summarize_subset(subset) for task, subset in sorted(by_task.items())}}


def _combine_seed_summaries(seed_summaries: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    tasks = sorted({task for summary in seed_summaries for task in summary[mode]["by_task"]})

    def combine_metric(values: list[float]) -> dict[str, float | None]:
        return {"mean": _mean(values), "std": _std(values)}

    def combine(mapping_getter: Any) -> dict[str, dict[str, float | None]]:
        keys = set()
        values_by_key: dict[str, list[float]] = defaultdict(list)
        for summary in seed_summaries:
            mapping = mapping_getter(summary)
            for key, value in mapping.items():
                keys.add(key)
                if isinstance(value, (int, float)) and value is not None:
                    values_by_key[key].append(float(value))
        return {key: combine_metric(values_by_key[key]) for key in sorted(keys)}

    return {
        "overall": combine(lambda summary: summary[mode]["overall"]),
        "by_task": {task: combine(lambda summary, task=task: summary[mode]["by_task"][task]) for task in tasks},
    }


def _metric_mean(summary: dict[str, Any], key: str) -> float:
    value = summary.get(key)
    if isinstance(value, dict):
        return float(value.get("mean") or 0.0)
    return float(value or 0.0)


def _verdict(single_summary: dict[str, Any]) -> str:
    fixpoint = _metric_mean(single_summary, "fixpoint_reach_rate")
    parse = _metric_mean(single_summary, "parse_success_rate")
    precision = _metric_mean(single_summary, "per_call_precision")
    if parse < 0.9 or fixpoint < 0.5:
        return "NEEDS_OPERATOR_FIX"
    if precision >= 0.8 and fixpoint >= 0.7:
        return "PREMISE_HOLDS"
    return "VERIFIER_LOAD_BEARING"


def _rendering_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_rendering: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_rendering[row["sudoku_rendering"]].append(row)
    out = {}
    for rendering, subset in sorted(by_rendering.items()):
        calls = len(subset)
        parse = sum(1 for row in subset if row["parse_success"])
        accepted = sum(1 for row in subset if row["accepted"])
        rejected = sum(1 for row in subset if row["rejected"])
        out[rendering] = {
            "n": calls,
            "parse_success_rate": _safe_div(parse, calls),
            "per_call_precision": _safe_div(accepted, accepted + rejected),
            "accepted": accepted,
            "rejected": rejected,
        }
    best = sorted(out.items(), key=lambda item: ((item[1]["parse_success_rate"] or 0), (item[1]["per_call_precision"] or 0)), reverse=True)
    return {"by_rendering": out, "selected": best[0][0] if best else "grid"}


def run_probe(output_dir: str, model_id: str, device: str, n_instances: int, max_nodes_per_task: int, seeds: list[int], batch_size: int, sudoku_rendering: str) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    operator = QwenGenerativeOperator(model_id=model_id, device=device)
    all_rows: list[dict[str, Any]] = []
    rendering_rows: list[dict[str, Any]] = []
    seed_summaries = []
    for seed in seeds:
        tasks = build_tasks(TASK_TYPES, n_instances=n_instances, seed=seed)
        nodes = sample_probe_nodes(tasks, max_nodes_per_task=max_nodes_per_task, seed=seed)
        rows: list[dict[str, Any]] = []
        for index, node in enumerate(nodes):
            rendering = sudoku_rendering if node.task.task_type == "sudoku_4x4" else "grid"
            list_result = _list_all_episode(operator, node, batch_size, rendering)
            rows.append({"seed": seed, "node_index": index, "task_id": node.task.task_id, "task_type": node.task.task_type, "depth": node.depth, "mode": "list_all", "sudoku_rendering": rendering, "oracle_status": status(node.task, node.partial_assignment), **list_result})
            single_result = _single_iterated_episode(operator, node, batch_size, rendering)
            rows.append({"seed": seed, "node_index": index, "task_id": node.task.task_id, "task_type": node.task.task_type, "depth": node.depth, "mode": "single_iterated", "sudoku_rendering": rendering, "oracle_status": status(node.task, node.partial_assignment), **single_result})
            if node.task.task_type == "sudoku_4x4":
                for variant in SUDOKU_RENDERINGS:
                    prediction = operator.predict(node.task, node.partial_assignment, batch_size=batch_size, mode="single", sudoku_rendering=variant)
                    allowed = forced_moves(node.task, node.partial_assignment)
                    proposed = next(iter(prediction.forced.items())) if prediction.forced else None
                    accepted = bool(prediction.parse_success and proposed is not None and allowed.get(proposed[0]) == proposed[1])
                    rendering_rows.append({"seed": seed, "node_index": index, "sudoku_rendering": variant, "parse_success": prediction.parse_success, "accepted": accepted, "rejected": bool(prediction.parse_success and proposed is not None and not accepted), "failure_modes": prediction.failure_modes})
            print(json.dumps({"event": "m2_fix_probe_node", "seed": seed, "index": index + 1, "total": len(nodes), "task_type": node.task.task_type, "list_hits": list_result["hits"], "single_fixpoint": single_result["reached_fixpoint"]}), flush=True)
        all_rows.extend(rows)
        seed_summaries.append({"seed": seed, "list_all": _summarize_seed(rows, "list_all"), "single_iterated": _summarize_seed(rows, "single_iterated")})
    combined = {"list_all": _combine_seed_summaries(seed_summaries, "list_all"), "single_iterated": _combine_seed_summaries(seed_summaries, "single_iterated")}
    per_task_verdicts = {task: _verdict(summary) for task, summary in combined["single_iterated"]["by_task"].items()}
    payload = {
        "module": "m2_operator_probe_fix_rescale",
        "model_id": model_id,
        "device": device,
        "task_types": TASK_TYPES,
        "n_instances": n_instances,
        "max_nodes_per_task": max_nodes_per_task,
        "seeds": seeds,
        "n_rows": len(all_rows),
        "rows": all_rows,
        "seed_summaries": seed_summaries,
        "summary": combined,
        "rendering_comparison": _rendering_summary(rendering_rows),
        "per_task_verdicts": per_task_verdicts,
        "routing": {
            "pass_tasks": [task for task, verdict in per_task_verdicts.items() if verdict in {"PREMISE_HOLDS", "VERIFIER_LOAD_BEARING"}],
            "fix_tasks": [task for task, verdict in per_task_verdicts.items() if verdict == "NEEDS_OPERATOR_FIX"],
        },
    }
    (out / "operator_probe_fix_rescale.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="results/m2_operator_probe")
    parser.add_argument("--model-id", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--n-instances", type=int, default=50)
    parser.add_argument("--max-nodes-per-task", type=int, default=6)
    parser.add_argument("--seeds", default="42,137")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--sudoku-rendering", choices=SUDOKU_RENDERINGS, default="candidates")
    args = parser.parse_args()
    parsed_seeds = [int(seed) for seed in args.seeds.split(",") if seed.strip()]
    print(json.dumps(run_probe(args.output_dir, args.model_id, args.device, args.n_instances, args.max_nodes_per_task, parsed_seeds, args.batch_size, args.sudoku_rendering), indent=2, sort_keys=True))
