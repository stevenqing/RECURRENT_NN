"""Best-of-n direct no-train baseline under the shared matched-budget counter."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import glob
import json
from pathlib import Path
from statistics import mean
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from analysis.kvcache_gate2_csp_solver import _make_dataset as _make_csp_dataset
from analysis.kvcache_graph_color_search import _make_dataset as _make_graph_dataset, _write_json
from experiments.rung1_distributed_graph_coloring import SOURCE


SCHEMA_VERSION = "kvcache_best_of_n_baseline_v0"
STATUS_COMPLETE = "KVCACHE_BEST_OF_N_BASELINE_COMPLETE"
STATUS_MERGED = "KVCACHE_BEST_OF_N_BASELINE_MERGED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dtype(name: str, device: torch.device) -> torch.dtype:
    if name == "bf16" and device.type == "cuda":
        return torch.bfloat16
    if name == "fp16" and device.type == "cuda":
        return torch.float16
    return torch.float32


def _load_model(args: argparse.Namespace) -> tuple[Any, Any]:
    device = torch.device(args.device if torch.cuda.is_available() or not str(args.device).startswith("cuda") else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=_dtype(args.dtype, device), trust_remote_code=True).to(device).eval()
    model.config.use_cache = True
    return model, tokenizer


def _budget_grid(anchor: int, scales: str) -> list[int]:
    return sorted({max(1, int(round(float(scale.strip()) * int(anchor)))) for scale in scales.split(",") if scale.strip()})


def _budget_anchors(text: str) -> dict[str, int]:
    anchors = {}
    for item in text.split(","):
        if not item.strip():
            continue
        key, value = item.split(":", 1)
        anchors[key.strip()] = int(float(value.strip()))
    return anchors


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
        dtype=args.dtype,
        device=args.device,
        num_vertices=args.graph_num_vertices,
        num_colors=args.graph_num_colors,
        edge_probability=args.graph_edge_probability,
        difficulty_bin_label=args.graph_difficulty_bin_label,
        order_mode="degree_desc",
    )


def _make_dataset(task: str, args: argparse.Namespace) -> Any:
    if task == "graph_color":
        return _make_graph_dataset(_task_args(task, args))
    return _make_csp_dataset(task, _task_args(task, args))


def _prompt(task: str, entry: dict[str, Any]) -> str:
    question = str(entry.get("question", ""))
    if task == "graph_color":
        return "\n".join([
            "Solve this graph coloring puzzle.",
            question,
            "Return exactly one JSON object mapping every vertex string to an integer color. No prose.",
        ])
    return "\n".join([
        f"Solve this {task} puzzle.",
        question,
        "Return only the final answer in the task's expected format. No explanation.",
    ])


@torch.no_grad()
def _sample_once(model: Any, tokenizer: Any, prompt: str, max_new_tokens: int, temperature: float, top_p: float) -> tuple[str, int, int]:
    ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
    output = model.generate(
        ids,
        do_sample=True,
        temperature=float(temperature),
        top_p=float(top_p),
        max_new_tokens=int(max_new_tokens),
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
        use_cache=True,
    )
    generated = output[:, ids.shape[1]:]
    text = tokenizer.decode(generated[0], skip_special_tokens=True).strip()
    return text, int(ids.shape[1]), int(generated.shape[1])


@torch.no_grad()
def _sample_batch(model: Any, tokenizer: Any, prompt: str, batch_size: int, max_new_tokens: int, temperature: float, top_p: float) -> list[tuple[str, int, int]]:
    if batch_size <= 1:
        return [_sample_once(model, tokenizer, prompt, max_new_tokens, temperature, top_p)]
    ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
    batch_ids = ids.repeat(int(batch_size), 1)
    output = model.generate(
        batch_ids,
        do_sample=True,
        temperature=float(temperature),
        top_p=float(top_p),
        max_new_tokens=int(max_new_tokens),
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
        use_cache=True,
    )
    generated = output[:, batch_ids.shape[1]:]
    rows = []
    for index in range(generated.shape[0]):
        text = tokenizer.decode(generated[index], skip_special_tokens=True).strip()
        rows.append((text, int(ids.shape[1]), int(generated.shape[1])))
    return rows


def _wilson(successes: int, n: int, z: float = 1.959963984540054) -> dict[str, float | None]:
    if n <= 0:
        return {"rate": None, "ci_low": None, "ci_high": None}
    phat = successes / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return {"rate": phat, "ci_low": max(0.0, center - half), "ci_high": min(1.0, center + half)}


def _run_instance(model: Any, tokenizer: Any, dataset: Any, task: str, entry: dict[str, Any], source_index: int, budget: int, args: argparse.Namespace) -> dict[str, Any]:
    prompt = _prompt(task, entry)
    prompt_tokens = len(tokenizer(prompt, add_special_tokens=False).input_ids)
    tokens_used = 0
    best_score = 0.0
    best_text = ""
    attempts = 0
    status = "BUDGET_EXHAUSTED"
    sample_cap = int(args.max_samples_per_budget)
    while sample_cap <= 0 or attempts < sample_cap:
        remaining = int(budget) - int(tokens_used)
        if remaining <= prompt_tokens + 1:
            status = "BUDGET_EXHAUSTED"
            break
        max_new = min(int(args.max_new_tokens), max(1, remaining - prompt_tokens))
        remaining_attempt_cap = (sample_cap - attempts) if sample_cap > 0 else int(args.sample_batch_size)
        budget_batch_cap = max(1, remaining // max(1, prompt_tokens + max_new))
        batch_size = max(1, min(int(args.sample_batch_size), int(remaining_attempt_cap), int(budget_batch_cap)))
        sampled = _sample_batch(model, tokenizer, prompt, batch_size, max_new, float(args.temperature), float(args.top_p))
        made_progress = False
        for text, input_tokens, output_tokens in sampled:
            used = int(input_tokens) + int(output_tokens)
            if tokens_used + used > int(budget):
                status = "BUDGET_EXHAUSTED"
                break
            tokens_used += used
            attempts += 1
            made_progress = True
            try:
                score = float(dataset.score_answer(text, entry))
            except Exception:
                score = 0.0
            if score > best_score:
                best_score = score
                best_text = text
            if score >= 0.99:
                status = "SOLVED"
                break
        if status == "SOLVED":
            break
        if not made_progress:
            status = "BUDGET_EXHAUSTED"
            break
    if sample_cap > 0 and attempts >= sample_cap and status != "SOLVED" and tokens_used < int(budget):
        status = "ATTEMPT_CAP"
    return {
        "method": "best_of_n_parallel_sampling",
        "task": task,
        "source_index": int(source_index),
        "budget_B": int(budget),
        "solved": bool(best_score >= 0.99),
        "official_score": best_score,
        "tokens_used": int(tokens_used),
        "depth_reached": attempts,
        "attempts": attempts,
        "status": status,
        "best_text_tail": best_text[-300:],
        "source": SOURCE,
        "provenance": "kvcache_best_of_n_budget_run_v0",
    }


def run_shard(args: argparse.Namespace) -> dict[str, Any]:
    model, tokenizer = _load_model(args)
    anchors = _budget_anchors(args.budget_anchors)
    tasks = [item.strip() for item in args.tasks.split(",") if item.strip()]
    checkpoint_rows = []
    if args.resume and args.checkpoint_path.exists():
        checkpoint = json.loads(args.checkpoint_path.read_text(encoding="utf-8"))
        checkpoint_rows = list(checkpoint.get("rows", []))
    done = {(row["task"], int(row["source_index"]), int(row["budget_B"])) for row in checkpoint_rows}
    rows = list(checkpoint_rows)
    task_counter = 0
    for task in tasks:
        dataset = _make_dataset(task, args)
        budgets = _budget_grid(anchors[task], args.budget_scales)
        for source_index in range(int(args.n_instances)):
            entry = dataset[source_index]
            entry.setdefault("metadata", {})["source_index"] = source_index
            for budget in budgets:
                current_index = task_counter
                task_counter += 1
                if current_index % int(args.num_shards) != int(args.shard_index):
                    continue
                key = (task, int(source_index), int(budget))
                if key in done:
                    continue
                print(json.dumps({"task": task, "source_index": source_index, "budget_B": int(budget), "shard": int(args.shard_index)}), flush=True)
                row = _run_instance(model, tokenizer, dataset, task, entry, source_index, int(budget), args)
                row["shard_index"] = int(args.shard_index)
                row["num_shards"] = int(args.num_shards)
                rows.append(row)
                done.add(key)
                _write_json(args.checkpoint_path, {"rows": rows})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "rows": rows,
        "source": SOURCE,
        "provenance": "kvcache_best_of_n_baseline_shard_v0",
    }
    _write_json(args.output, payload)
    return payload


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for task, budget in sorted({(row["task"], int(row["budget_B"])) for row in rows}):
        subset = [row for row in rows if row["task"] == task and int(row["budget_B"]) == budget]
        successes = sum(int(row["solved"]) for row in subset)
        ci = _wilson(successes, len(subset))
        summary.append({
            "method": "best_of_n_parallel_sampling",
            "task": task,
            "budget_B": budget,
            "n": len(subset),
            "solve_count": successes,
            "solve_rate": ci["rate"],
            "solve_ci_low": ci["ci_low"],
            "solve_ci_high": ci["ci_high"],
            "mean_tokens_used": mean(float(row["tokens_used"]) for row in subset),
            "mean_attempts": mean(float(row["attempts"]) for row in subset),
            "status_counts": dict(Counter(row["status"] for row in subset)),
            "source": SOURCE,
            "provenance": "kvcache_best_of_n_curve_summary_v0",
        })
    return summary


def merge(args: argparse.Namespace) -> dict[str, Any]:
    row_by_key: dict[tuple[str, int, int], dict[str, Any]] = {}
    inputs = sorted(glob.glob(args.inputs))
    for path in inputs:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        for row in payload.get("rows", []):
            row_by_key[(row["task"], int(row["source_index"]), int(row["budget_B"]))] = row
    rows = [row_by_key[key] for key in sorted(row_by_key)]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_MERGED,
        "generated_at": _now(),
        "input_files": inputs,
        "summary": _summarize(rows),
        "rows": rows,
        "source": SOURCE,
        "provenance": "kvcache_best_of_n_baseline_merged_v0",
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run best-of-n no-train baseline under matched token budgets.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run-shard")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--checkpoint-path", type=Path, required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    run.add_argument("--device", default="cuda")
    run.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    run.add_argument("--reasoning-gym-repo", default=None)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--scan-limit", type=int, default=120)
    run.add_argument("--n-instances", type=int, default=64)
    run.add_argument("--tasks", default="sudoku,futoshiki,graph_color")
    run.add_argument("--budget-anchors", default="sudoku:28070,futoshiki:3206226,graph_color:32895")
    run.add_argument("--budget-scales", default="0.25,0.5,1,2,4")
    run.add_argument("--max-samples-per-budget", type=int, default=0, help="0 means exhaust budget; positive values are safety/pilot caps")
    run.add_argument("--sample-batch-size", type=int, default=8)
    run.add_argument("--max-new-tokens", type=int, default=512)
    run.add_argument("--temperature", type=float, default=0.8)
    run.add_argument("--top-p", type=float, default=0.95)
    run.add_argument("--futoshiki-size", type=int, default=7)
    run.add_argument("--futoshiki-difficulty", type=int, default=3)
    run.add_argument("--graph-num-vertices", type=int, default=16)
    run.add_argument("--graph-num-colors", type=int, default=3)
    run.add_argument("--graph-edge-probability", type=float, default=0.4)
    run.add_argument("--graph-difficulty-bin-label", default="v16_p04")
    run.add_argument("--num-shards", type=int, default=1)
    run.add_argument("--shard-index", type=int, default=0)
    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("--inputs", required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run-shard":
        payload = run_shard(args)
        print(json.dumps({"path": str(args.output), "status": payload["status"], "rows": len(payload["rows"])}, sort_keys=True))
    elif args.command == "merge":
        payload = merge(args)
        print(json.dumps({"path": str(args.output), "status": payload["status"], "rows": len(payload["rows"])}, sort_keys=True))


if __name__ == "__main__":
    main()
