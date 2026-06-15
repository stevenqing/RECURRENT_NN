"""Run graph_color A-vs-C oracle-search cost from fixed source indices."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from analysis.kvcache_graph_color_search import _load_model, _make_dataset, _run_arm, _summarize, _write_json
from experiments.rung1_distributed_graph_coloring import SOURCE


SCHEMA_VERSION = "kvcache_graph_color_cost_from_sources_v0"
STATUS_COMPLETE = "KVCACHE_GRAPH_COLOR_COST_FROM_SOURCES_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_indices(args: argparse.Namespace) -> list[int]:
    if args.source_indices:
        return [int(item.strip()) for item in args.source_indices.split(",") if item.strip()]
    if args.source_index_file:
        data = json.loads(Path(args.source_index_file).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "source_indices" in data:
            return [int(item) for item in data["source_indices"]]
        if isinstance(data, list):
            return [int(item) for item in data]
    raise ValueError("provide --source-indices or --source-index-file")


def _selected_for_index(dataset: Any, args: argparse.Namespace, source_index: int) -> dict[str, Any]:
    entry = dataset[int(source_index)]
    entry.setdefault("metadata", {})["source_index"] = int(source_index)
    return {
        "entry": entry,
        "source_index": int(source_index),
        "trace": {"selection_source": args.selection_source},
        "difficulty_bin": args.difficulty_bin_label,
        "edge_probability": float(args.edge_probability),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    source_indices = _source_indices(args)[: int(args.n_instances)]
    dataset = _make_dataset(args)
    model, tokenizer = _load_model(args)
    rows = []
    if args.resume and args.checkpoint_path.exists():
        existing = json.loads(args.checkpoint_path.read_text(encoding="utf-8"))
        rows = existing.get("rows", existing) if isinstance(existing, dict) else existing
    done = {(row["arm"], int(row["R"]), int(row["source_index"])) for row in rows}
    arms = [item.strip() for item in args.arms.split(",") if item.strip()]
    r_values = [int(item.strip()) for item in args.r_values.split(",") if item.strip()]
    task_index = 0
    for source_index in source_indices:
        selected = _selected_for_index(dataset, args, int(source_index))
        for arm in arms:
            for r_value in r_values:
                current_task = task_index
                task_index += 1
                if current_task % int(args.num_shards) != int(args.shard_index):
                    continue
                key = (arm, int(r_value), int(source_index))
                if key in done:
                    continue
                row = _run_arm(model, tokenizer, dataset, selected, arm, int(r_value), args)
                row["task_index"] = current_task
                row["shard_index"] = int(args.shard_index)
                row["num_shards"] = int(args.num_shards)
                row["selection_source"] = args.selection_source
                rows.append(row)
                done.add(key)
                _write_json(args.checkpoint_path, {"rows": rows})
                print(json.dumps({"source_index": int(source_index), "arm": arm, "R": int(r_value), "status": row["status"]}), flush=True)
    solve_by_R, quality, fallback_rate, context, a_vs_c_by_depth, tokens, fork = _summarize(rows)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "source_indices": source_indices,
        "planned_tasks_all_shards": task_index,
        "solve_by_R": solve_by_R,
        "decision_quality": quality,
        "fallback_rate": fallback_rate,
        "context_vs_depth": context,
        "A_vs_C_by_depth": a_vs_c_by_depth,
        "tokens": tokens,
        "fork_verdicts": fork,
        "rows": rows,
        "source": SOURCE,
        "provenance": "kvcache_graph_color_cost_from_sources_v0",
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run graph_color cost from fixed source indices.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-path", type=Path, required=True)
    parser.add_argument("--source-indices", default="")
    parser.add_argument("--source-index-file", default="")
    parser.add_argument("--selection-source", default="fixed_source_indices")
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=1000)
    parser.add_argument("--n-instances", type=int, default=24)
    parser.add_argument("--node-cap", type=int, default=160)
    parser.add_argument("--num-vertices", type=int, required=True)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--edge-probability", type=float, default=0.4)
    parser.add_argument("--difficulty-bin-label", required=True)
    parser.add_argument("--order-mode", default="degree_desc", choices=["degree_desc", "natural"])
    parser.add_argument("--r-values", default="2,4,8,16")
    parser.add_argument("--arms", default="A_cache_oracle_search,C_incontext_oracle_search")
    parser.add_argument("--invalid-branch-mode", choices=["first_legal", "fail"], default="fail")
    parser.add_argument("--invalid-backtrack-mode", choices=["chronological_latest", "fail"], default="fail")
    parser.add_argument("--call-cap", type=int, default=160)
    parser.add_argument("--max-new-tokens", type=int, default=32)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
