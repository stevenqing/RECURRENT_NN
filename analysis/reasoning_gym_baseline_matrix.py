"""Unified Reasoning Gym baseline matrix runner."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any

from analysis.externalization_power_calibration import _solve_budgeted, _view_for
from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_reasoning_gym_bounded_register import _ensure_reasoning_gym, _openai_text_call
from experiments.rung1_separator_llm_inloop import DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL


SCHEMA_VERSION = "reasoning_gym_baseline_matrix_v1"
STATUS_COMPLETE = "REASONING_GYM_BASELINE_MATRIX_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _benchmarks(args: argparse.Namespace) -> list[str]:
    return [item.strip() for item in args.benchmarks.split(",") if item.strip()]


def _make_dataset(reasoning_gym: Any, benchmark: str, args: argparse.Namespace) -> Any:
    if benchmark == "graph_color":
        return reasoning_gym.create_dataset(
            "graph_color",
            size=args.n_instances,
            seed=args.seed,
            num_colors=args.graph_num_colors,
            min_num_vertices=args.graph_vertices,
            max_num_vertices=args.graph_vertices,
            edge_probability=args.graph_edge_probability,
        )
    if benchmark == "sudoku":
        return reasoning_gym.create_dataset("sudoku", size=args.n_instances, seed=args.seed, min_empty=args.sudoku_empty, max_empty=args.sudoku_empty)
    if benchmark == "zebra_puzzles":
        return reasoning_gym.create_dataset("zebra_puzzles", size=args.n_instances, seed=args.seed)
    raise ValueError(f"unknown benchmark={benchmark}")


def _oracle_answer(benchmark: str, entry: dict[str, Any]) -> str | None:
    if benchmark == "graph_color":
        possible = entry.get("metadata", {}).get("possible_answer")
        if possible is None:
            return None
        return json.dumps({str(vertex): int(color) for vertex, color in sorted(possible.items())}, sort_keys=True)
    answer = entry.get("answer")
    return str(answer) if answer is not None else None


def _score(dataset: Any, entry: dict[str, Any], answer: str | None) -> float:
    if answer is None:
        return 0.0
    try:
        return float(dataset.score_answer(answer, entry))
    except Exception:
        return 0.0


def _oracle_row(dataset: Any, benchmark: str, entry: dict[str, Any], index: int) -> dict[str, Any]:
    answer = _oracle_answer(benchmark, entry)
    score = _score(dataset, entry, answer)
    return {
        "benchmark": benchmark,
        "source_index": index,
        "arm": "official_oracle_answer",
        "official_score": score,
        "solved": score >= 1.0,
        "status": "SOLVED" if score >= 1.0 else "SCORE_FAIL",
        "prompt_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "source": SOURCE,
        "provenance": "rg_baseline_oracle_answer_v1",
    }


def _empty_row(dataset: Any, benchmark: str, entry: dict[str, Any], index: int) -> dict[str, Any]:
    score = _score(dataset, entry, "")
    return {
        "benchmark": benchmark,
        "source_index": index,
        "arm": "empty_answer",
        "official_score": score,
        "solved": score >= 1.0,
        "status": "SOLVED" if score >= 1.0 else "SCORE_FAIL",
        "prompt_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "source": SOURCE,
        "provenance": "rg_baseline_empty_answer_v1",
    }


def _symbolic_rows(dataset: Any, benchmark: str, entry: dict[str, Any], index: int, args: argparse.Namespace) -> list[dict[str, Any]]:
    if benchmark not in {"graph_color", "sudoku"}:
        return [
            {
                "benchmark": benchmark,
                "source_index": index,
                "arm": "L0-symbolic-heuristic",
                "status": "ADAPTER_PENDING",
                "solved": False,
                "official_score": 0.0,
                "reason": "No structural adapter yet for this benchmark.",
                "source": SOURCE,
                "provenance": "rg_baseline_symbolic_adapter_pending_v1",
            },
            {
                "benchmark": benchmark,
                "source_index": index,
                "arm": "L0-symbolic-random",
                "status": "ADAPTER_PENDING",
                "solved": False,
                "official_score": 0.0,
                "reason": "No structural adapter yet for this benchmark.",
                "source": SOURCE,
                "provenance": "rg_baseline_symbolic_adapter_pending_v1",
            },
        ]
    node_budget = args.graph_node_budget if benchmark == "graph_color" else args.sudoku_node_budget
    view = _view_for(benchmark, entry)
    rows = []
    for arm in ["heuristic", "random"]:
        row = _solve_budgeted(dataset, entry, view, arm, node_budget, (SCHEMA_VERSION, benchmark, index, args.seed))
        row |= {"benchmark": benchmark, "source_index": index}
        rows.append(row)
    return rows


def _one_shot_prompt(entry: dict[str, Any], cot: bool) -> str:
    prompt = entry.get("question", "")
    if cot:
        prompt += "\nThink privately if needed, then give only the final answer in the requested format."
    return prompt


def _one_shot_row(dataset: Any, benchmark: str, entry: dict[str, Any], index: int, args: argparse.Namespace, cot: bool) -> dict[str, Any]:
    generation = _openai_text_call(args.openai_base_url, args.openai_model, _one_shot_prompt(entry, cot), args.max_new_tokens)
    answer = generation.get("text", "")
    score = _score(dataset, entry, answer)
    return {
        "benchmark": benchmark,
        "source_index": index,
        "arm": "L1-one_shot_cot" if cot else "L1-one_shot_direct",
        "official_score": score,
        "solved": score >= 1.0,
        "status": "SOLVED" if score >= 1.0 else "SCORE_FAIL",
        "finish_reason": generation.get("finish_reason"),
        "prompt_tokens": int(generation.get("prompt_tokens", 0)),
        "output_tokens": int(generation.get("output_tokens", 0)),
        "total_tokens": int(generation.get("total_tokens", 0)),
        "answer_prefix": answer[:240],
        "source": SOURCE,
        "provenance": "rg_baseline_one_shot_v1",
    }


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for benchmark, arm in sorted({(row["benchmark"], row["arm"]) for row in rows}):
        subset = [row for row in rows if row["benchmark"] == benchmark and row["arm"] == arm]
        summary.append(
            {
                "benchmark": benchmark,
                "arm": arm,
                "n": len(subset),
                "solve_rate": mean(float(row.get("solved", False)) for row in subset) if subset else 0.0,
                "mean_official_score": mean(float(row.get("official_score", 0.0)) for row in subset) if subset else None,
                "mean_total_tokens": mean(int(row.get("total_tokens", 0)) for row in subset) if subset else 0.0,
                "status_counts": dict(Counter(str(row.get("status")) for row in subset)),
                "source": SOURCE,
                "provenance": "rg_baseline_summary_v1",
            }
        )
    return summary


def run(args: argparse.Namespace) -> dict[str, Any]:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    rows: list[dict[str, Any]] = []
    llm_tasks = []
    for benchmark in _benchmarks(args):
        dataset = _make_dataset(reasoning_gym, benchmark, args)
        for index in range(args.n_instances):
            entry = dataset[index]
            rows.append(_oracle_row(dataset, benchmark, entry, index))
            rows.append(_empty_row(dataset, benchmark, entry, index))
            rows.extend(_symbolic_rows(dataset, benchmark, entry, index, args))
            if args.run_llm:
                llm_tasks.append((dataset, benchmark, entry, index, False))
                if args.run_cot:
                    llm_tasks.append((dataset, benchmark, entry, index, True))
    if llm_tasks:
        with ThreadPoolExecutor(max_workers=max(1, min(args.batch_size, len(llm_tasks)))) as pool:
            futures = [pool.submit(_one_shot_row, dataset, benchmark, entry, index, args, cot) for dataset, benchmark, entry, index, cot in llm_tasks]
            for future in as_completed(futures):
                rows.append(future.result())
    summary = _summarize(rows)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "baseline_policy": {
            "baseline_first": True,
            "method_after_baselines": True,
            "official_scoring_only": True,
            "benchmarks": _benchmarks(args),
            "source": SOURCE,
            "provenance": "rg_baseline_policy_v1",
        },
        "config": {key: value for key, value in vars(args).items() if key not in {"output"}},
        "coverage": {
            "official_oracle_answer": "all requested benchmarks",
            "empty_answer": "all requested benchmarks",
            "symbolic_heuristic_random": "graph_color and sudoku; zebra_puzzles adapter pending",
            "one_shot_direct": "optional via --run-llm",
            "one_shot_cot": "optional via --run-llm --run-cot",
            "source": SOURCE,
            "provenance": "rg_baseline_coverage_v1",
        },
        "summary_by_benchmark_arm": summary,
        "rows": rows,
        "honesty": {
            "does_not_establish": "This artifact builds and smoke-tests a baseline matrix. It does not evaluate the externalized M-register or multi-agent method, and it does not claim method superiority.",
            "zebra_limit": "Zebra symbolic baselines remain adapter-pending because RG metadata does not expose structural constraints in the same way as graph_color/sudoku.",
            "llm_limit": "LLM one-shot baselines are present only when --run-llm is used; token accounting is total prompt+output tokens.",
            "source": SOURCE,
            "provenance": "rg_baseline_honesty_v1",
        },
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run unified Reasoning Gym baseline matrix.")
    parser.add_argument("--output", type=Path, default=Path("results/reasoning_gym_baselines/baseline_matrix.json"))
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--benchmarks", default="graph_color,sudoku,zebra_puzzles")
    parser.add_argument("--n-instances", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--graph-vertices", type=int, default=14)
    parser.add_argument("--graph-num-colors", type=int, default=3)
    parser.add_argument("--graph-edge-probability", type=float, default=0.4)
    parser.add_argument("--graph-node-budget", type=int, default=80)
    parser.add_argument("--sudoku-empty", type=int, default=45)
    parser.add_argument("--sudoku-node-budget", type=int, default=320)
    parser.add_argument("--run-llm", action="store_true")
    parser.add_argument("--run-cot", action="store_true")
    parser.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=4)
    run(parser.parse_args())


if __name__ == "__main__":
    main()