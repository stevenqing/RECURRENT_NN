"""M2.0 frozen generative operator competence probe."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

from llm_operator.qwen_operator import QwenGenerativeOperator
from llm_operator.symbolic_filter import build_tasks, forced_moves, propagation_fixpoint, sample_probe_nodes, status


TASK_TYPES = ["horn_sat", "general_sat", "graph_coloring", "sudoku_4x4"]


def _safe_div(num: float, den: float) -> float | None:
    return num / den if den else None


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_depth: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_task[row["task_type"]].append(row)
        by_depth[str(row["depth"])].append(row)

    def summarize_subset(subset: list[dict[str, Any]]) -> dict[str, Any]:
        proposed = sum(row["proposed_forced_n"] for row in subset)
        true = sum(row["truly_forced_n"] for row in subset)
        hits = sum(row["forced_hits"] for row in subset)
        parse_success = sum(1 for row in subset if row["parse_success"])
        contradictions = [row for row in subset if row["oracle_status"] == "CONTRADICTION"]
        contradiction_hits = sum(1 for row in contradictions if row["predicted_status"] == "CONTRADICTION")
        return {
            "n": len(subset),
            "parse_success_rate": _safe_div(parse_success, len(subset)),
            "forced_recall": _safe_div(hits, true),
            "raw_precision": _safe_div(hits, proposed),
            "filter_dropped": sum(row["filter_dropped"] for row in subset),
            "mean_fixpoint_rounds": _safe_div(sum(row["qwen_filter_rounds"] for row in subset), len(subset)),
            "fixpoint_reach_rate": _safe_div(sum(1 for row in subset if row["qwen_filter_reached_fixpoint"]), len(subset)),
            "status_contradiction_recall": _safe_div(contradiction_hits, len(contradictions)),
        }

    failures = Counter(mode for row in rows for mode in row["failure_modes"])
    confusion = Counter((row["oracle_status"], row["predicted_status"] or "PARSE_FAIL") for row in rows)
    return {
        "overall": summarize_subset(rows),
        "by_task": {task: summarize_subset(subset) for task, subset in sorted(by_task.items())},
        "by_depth": {depth: summarize_subset(subset) for depth, subset in sorted(by_depth.items(), key=lambda item: int(item[0]))},
        "failure_modes": dict(failures),
        "status_confusion": {f"{gold}->{pred}": count for (gold, pred), count in sorted(confusion.items())},
    }


def run_probe(output_dir: str, model_id: str, device: str, n_instances: int, max_nodes_per_task: int, seed: int, batch_size: int, max_rounds: int) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(TASK_TYPES, n_instances=n_instances, seed=seed)
    nodes = sample_probe_nodes(tasks, max_nodes_per_task=max_nodes_per_task, seed=seed)
    operator = QwenGenerativeOperator(model_id=model_id, device=device)
    rows = []
    for index, node in enumerate(nodes):
        prediction = operator.predict(node.task, node.partial_assignment, batch_size=batch_size)
        true_forced = forced_moves(node.task, node.partial_assignment)
        proposed = prediction.forced if prediction.parse_success else {}
        hits = sum(1 for var, value in proposed.items() if true_forced.get(var) == value)
        filtered = {var: value for var, value in proposed.items() if true_forced.get(var) == value}
        fix_assignment, oracle_rounds, oracle_fix_status = propagation_fixpoint(node.task, node.partial_assignment)
        current = dict(node.partial_assignment)
        qwen_rounds = 0
        reached = set(current.items()) >= set(fix_assignment.items())
        for _ in range(max_rounds):
            if reached or status(node.task, current) != "OPEN":
                break
            round_prediction = prediction if qwen_rounds == 0 else operator.predict(node.task, current, batch_size=batch_size)
            allowed = forced_moves(node.task, current)
            applied = {var: value for var, value in round_prediction.forced.items() if allowed.get(var) == value and var not in current}
            if not applied:
                break
            current.update(applied)
            qwen_rounds += 1
            reached = set(current.items()) >= set(fix_assignment.items())
        row = {
            "node_index": index,
            "task_id": node.task.task_id,
            "task_type": node.task.task_type,
            "depth": node.depth,
            "parse_success": prediction.parse_success,
            "reprompted": prediction.reprompted,
            "failure_modes": prediction.failure_modes,
            "predicted_status": prediction.status,
            "oracle_status": status(node.task, node.partial_assignment),
            "truly_forced": true_forced,
            "proposed_forced": proposed,
            "filtered_forced": filtered,
            "truly_forced_n": len(true_forced),
            "proposed_forced_n": len(proposed),
            "forced_hits": hits,
            "filter_dropped": max(0, len(proposed) - len(filtered)),
            "oracle_fixpoint_rounds": oracle_rounds,
            "oracle_fixpoint_status": oracle_fix_status,
            "qwen_filter_rounds": qwen_rounds,
            "qwen_filter_reached_fixpoint": reached,
            "raw_text": prediction.raw_text,
        }
        rows.append(row)
        print(json.dumps({"event": "m2_probe_node", "index": index + 1, "total": len(nodes), "task_type": node.task.task_type, "parse_success": prediction.parse_success, "forced_hits": hits, "true_forced": len(true_forced)}), flush=True)
    payload = {"module": "m2_operator_probe", "model_id": model_id, "device": device, "task_types": TASK_TYPES, "n_instances": n_instances, "max_nodes_per_task": max_nodes_per_task, "n_nodes": len(rows), "rows": rows, "summary": _summarize(rows)}
    (out / "operator_probe.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="results/m2_operator_probe")
    parser.add_argument("--model-id", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--n-instances", type=int, default=2)
    parser.add_argument("--max-nodes-per-task", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-rounds", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(run_probe(args.output_dir, args.model_id, args.device, args.n_instances, args.max_nodes_per_task, args.seed, args.batch_size, args.max_rounds), indent=2, sort_keys=True))