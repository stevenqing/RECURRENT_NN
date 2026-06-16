"""Multi-state batched LFS baseline under the shared matched-budget counter.

This is a throughput-oriented backend variant of the repo-grounded LFS adapter in
``analysis.kvcache_lfs_baseline``. It preserves the LFS control pattern per row,
but schedules multiple independent rows through batched Transformers generation.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import glob
import heapq
import json
from pathlib import Path
from statistics import mean
import time
from typing import Any

import torch

from analysis.kvcache_graph_color_search import _write_json
from analysis.kvcache_lfs_baseline import (
    CSPState,
    FrontierItem,
    LFS_COMMIT,
    LFS_REPO,
    LFS_URL,
    _budget_anchors,
    _budget_grid,
    _eval_prompt,
    _explore_prompt,
    _extract_json,
    _legal_actions,
    _load_model,
    _make_dataset,
    _make_env,
    _score_state,
    _task_args,
    _transition,
    _wilson,
)
from experiments.rung1_distributed_graph_coloring import SOURCE


SCHEMA_VERSION = "kvcache_lfs_multistate_baseline_v0"
STATUS_COMPLETE = "KVCACHE_LFS_MULTISTATE_BASELINE_COMPLETE"
STATUS_MERGED = "KVCACHE_LFS_MULTISTATE_BASELINE_MERGED"
METHOD = "LFS_repo_port_multistate_batch"
BACKEND = "transformers_batched"


@dataclass
class LFSRowState:
    task: str
    source_index: int
    budget_B: int
    env: dict[str, Any]
    current: CSPState = field(default_factory=lambda: CSPState(assignment={}, depth=0))
    frontier: list[FrontierItem] = field(default_factory=list)
    tie: int = 0
    tokens_used: int = 0
    expansions: int = 0
    parse_fails: int = 0
    best_score: float = 0.0
    max_depth_reached: int = 0
    status: str = "RUNNING"
    last_local_children: list[tuple[float, CSPState]] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.status != "RUNNING"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@torch.no_grad()
def _generate_batch(model: Any, tokenizer: Any, prompts: list[str], max_new_tokens: int) -> list[tuple[str, int, int]]:
    if not prompts:
        return []
    old_padding_side = getattr(tokenizer, "padding_side", "right")
    tokenizer.padding_side = "left"
    try:
        encoded = tokenizer(prompts, return_tensors="pt", padding=True, add_special_tokens=False)
        input_lengths = encoded.attention_mask.sum(dim=1).tolist()
        encoded = {key: value.to(model.device) for key, value in encoded.items()}
        output = model.generate(
            **encoded,
            do_sample=False,
            max_new_tokens=int(max_new_tokens),
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
            use_cache=True,
        )
        generated = output[:, encoded["input_ids"].shape[1]:]
        generated_tokens = int(generated.shape[1])
        rows = []
        for index in range(generated.shape[0]):
            text = tokenizer.decode(generated[index], skip_special_tokens=True).strip()
            rows.append((text, int(input_lengths[index]), generated_tokens))
        return rows
    finally:
        tokenizer.padding_side = old_padding_side


def _query_rows_batch(model: Any, tokenizer: Any, items: list[tuple[int, str, int, int]], max_new_tokens: int, batch_size: int) -> list[tuple[int, Any | None, int, str]]:
    """Generate JSON for rows.

    Each item is ``(index, prompt, budget_B, tokens_used)``. Returned used tokens
    are per row: input tokens plus generated output tokens. Padding tokens are not
    charged to rows.
    """

    outputs: list[tuple[int, Any | None, int, str]] = []
    cursor = 0
    while cursor < len(items):
        chunk: list[tuple[int, str, int, int, int]] = []
        batch_max_new: int | None = None
        for index, prompt, budget_B, tokens_used in items[cursor: cursor + int(batch_size)]:
            input_tokens = len(tokenizer(prompt, add_special_tokens=False).input_ids)
            remaining = int(budget_B) - int(tokens_used)
            if remaining <= input_tokens + 1:
                outputs.append((index, None, 0, "BUDGET_EXHAUSTED"))
                cursor += 1
                continue
            row_max_new = min(int(max_new_tokens), max(1, remaining - input_tokens))
            batch_max_new = row_max_new if batch_max_new is None else min(batch_max_new, row_max_new)
            chunk.append((index, prompt, int(budget_B), int(tokens_used), int(input_tokens)))
            cursor += 1
        if not chunk:
            continue
        assert batch_max_new is not None
        generated = _generate_batch(model, tokenizer, [item[1] for item in chunk], int(batch_max_new))
        for (index, _prompt, budget_B, tokens_used, _input_tokens), (text, in_tok, out_tok) in zip(chunk, generated):
            used = int(in_tok) + int(out_tok)
            if int(tokens_used) + used > int(budget_B):
                outputs.append((index, None, 0, "BUDGET_EXHAUSTED"))
                continue
            try:
                parsed = _extract_json(text)
                outputs.append((index, parsed, used, "OK"))
            except Exception:
                outputs.append((index, None, used, "PARSE_FAIL"))
    return outputs


def _finish_row(row: LFSRowState) -> dict[str, Any]:
    row.best_score = max(row.best_score, _score_state(row.task, row.env, row.current))
    if row.best_score >= 0.99:
        row.status = "SOLVED"
    return {
        "method": METHOD,
        "backend": BACKEND,
        "task": row.task,
        "source_index": int(row.source_index),
        "budget_B": int(row.budget_B),
        "solved": bool(row.best_score >= 0.99),
        "official_score": float(row.best_score),
        "tokens_used": int(row.tokens_used),
        "depth_reached": int(row.max_depth_reached),
        "expansions": int(row.expansions),
        "frontier_size": int(len(row.frontier)),
        "parse_fails": int(row.parse_fails),
        "status": "SOLVED" if row.best_score >= 0.99 else row.status,
        "repo": LFS_REPO,
        "repo_url": LFS_URL,
        "repo_commit": LFS_COMMIT,
        "source": SOURCE,
        "provenance": "kvcache_lfs_multistate_budget_run_v0",
    }


def _init_pending(args: argparse.Namespace) -> deque[tuple[str, int, int, dict[str, Any]]]:
    anchors = _budget_anchors(args.budget_anchors)
    tasks = [item.strip() for item in args.tasks.split(",") if item.strip()]
    pending: deque[tuple[str, int, int, dict[str, Any]]] = deque()
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
                pending.append((task, int(source_index), int(budget), entry))
    return pending


def run_shard(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    model, tokenizer = _load_model(args)
    pending = _init_pending(args)
    checkpoint_rows = []
    if args.resume and args.checkpoint_path.exists():
        checkpoint = json.loads(args.checkpoint_path.read_text(encoding="utf-8"))
        checkpoint_rows = list(checkpoint.get("rows", []))
    done = {(row["task"], int(row["source_index"]), int(row["budget_B"])) for row in checkpoint_rows}
    pending = deque(item for item in pending if (item[0], item[1], item[2]) not in done)
    rows = list(checkpoint_rows)
    active: list[LFSRowState] = []
    flush_every = max(1, int(args.checkpoint_every))

    def fill_active() -> None:
        while pending and len(active) < int(args.active_rows):
            task, source_index, budget, entry = pending.popleft()
            env = _make_env(task, _make_dataset(task, args), entry)
            active.append(LFSRowState(task=task, source_index=source_index, budget_B=budget, env=env))

    fill_active()
    completed_since_flush = 0
    while active:
        eval_items: list[tuple[int, str, int, int]] = []
        for index, row in enumerate(active):
            if row.complete:
                continue
            row.max_depth_reached = max(row.max_depth_reached, int(row.current.depth))
            row.best_score = max(row.best_score, _score_state(row.task, row.env, row.current))
            if row.best_score >= 0.99:
                row.status = "SOLVED"
                continue
            if int(args.max_expansions) > 0 and row.expansions >= int(args.max_expansions):
                row.status = "EXPANSION_CAP"
                continue
            _var, actions = _legal_actions(row.task, row.env, row.current)
            row.last_local_children = []
            if not actions:
                row.status = "NO_FRONTIER"
                continue
            prompt = _eval_prompt(row.task, row.env, row.current, actions)
            eval_items.append((index, prompt, row.budget_B, row.tokens_used))
        for index, parsed, used, status in _query_rows_batch(model, tokenizer, eval_items, int(args.max_new_tokens), int(args.state_batch_size)):
            row = active[index]
            if status == "BUDGET_EXHAUSTED":
                row.status = "BUDGET_EXHAUSTED"
                continue
            row.tokens_used += int(used)
            _var, actions = _legal_actions(row.task, row.env, row.current)
            values: dict[int, float] = {}
            if isinstance(parsed, dict):
                for action in actions:
                    try:
                        values[int(action)] = float(parsed.get(str(action), parsed.get(int(action), 0.0)))
                    except Exception:
                        values[int(action)] = 0.0
            else:
                row.parse_fails += 1
                values = {int(action): 0.0 for action in actions}
            for action in actions:
                child = _transition(row.current, int(action))
                value = float(values.get(int(action), 0.0))
                row.tie += 1
                row.last_local_children.append((value, child))
                heapq.heappush(row.frontier, FrontierItem(priority=-value, tie=row.tie, state=child))
            row.expansions += 1

        explore_items: list[tuple[int, str, int, int]] = []
        for index, row in enumerate(active):
            if row.complete:
                continue
            if not row.frontier:
                row.status = "NO_FRONTIER"
                continue
            prompt = _explore_prompt(row.task, row.env, row.current, len(row.frontier))
            explore_items.append((index, prompt, row.budget_B, row.tokens_used))
        for index, parsed, used, status in _query_rows_batch(model, tokenizer, explore_items, int(args.max_new_tokens), int(args.state_batch_size)):
            row = active[index]
            if status == "BUDGET_EXHAUSTED":
                row.status = "BUDGET_EXHAUSTED"
                continue
            row.tokens_used += int(used)
            explore = True
            if isinstance(parsed, dict) and "explore" in parsed:
                explore = bool(parsed.get("explore"))
            else:
                row.parse_fails += 1
            if explore:
                row.current = heapq.heappop(row.frontier).state
            else:
                row.current = max(row.last_local_children, key=lambda item: item[0])[1] if row.last_local_children else heapq.heappop(row.frontier).state
            row.max_depth_reached = max(row.max_depth_reached, int(row.current.depth))

        still_active: list[LFSRowState] = []
        for row in active:
            if row.complete:
                rows.append(_finish_row(row))
                completed_since_flush += 1
                print(json.dumps({"method": METHOD, "task": row.task, "source_index": row.source_index, "budget_B": row.budget_B, "status": row.status, "tokens_used": row.tokens_used}), flush=True)
            else:
                still_active.append(row)
        active = still_active
        fill_active()
        if completed_since_flush >= flush_every:
            _write_json(args.checkpoint_path, {"rows": rows})
            completed_since_flush = 0
    _write_json(args.checkpoint_path, {"rows": rows})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "elapsed_seconds": time.perf_counter() - started,
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items()},
        "rows": rows,
        "source": SOURCE,
        "provenance": "kvcache_lfs_multistate_baseline_shard_v0",
    }
    _write_json(args.output, payload)
    return payload


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for method, task, budget in sorted({(row["method"], row["task"], int(row["budget_B"])) for row in rows}):
        subset = [row for row in rows if row["method"] == method and row["task"] == task and int(row["budget_B"]) == budget]
        successes = sum(int(row["solved"]) for row in subset)
        ci = _wilson(successes, len(subset))
        summary.append({
            "method": method,
            "backend": BACKEND,
            "task": task,
            "budget_B": budget,
            "n": len(subset),
            "solve_count": successes,
            "solve_rate": ci["rate"],
            "solve_ci_low": ci["ci_low"],
            "solve_ci_high": ci["ci_high"],
            "mean_tokens_used": mean(float(row["tokens_used"]) for row in subset),
            "mean_depth_reached": mean(float(row["depth_reached"]) for row in subset),
            "mean_expansions": mean(float(row["expansions"]) for row in subset),
            "status_counts": dict(Counter(row["status"] for row in subset)),
            "source": SOURCE,
            "provenance": "kvcache_lfs_multistate_summary_v0",
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
        "provenance": "kvcache_lfs_multistate_baseline_merged_v0",
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-state batched LFS no-train baseline.")
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
    run.add_argument("--n-instances", type=int, default=4)
    run.add_argument("--tasks", default="sudoku,graph_color")
    run.add_argument("--budget-anchors", default="sudoku:28070,futoshiki:3206226,graph_color:32895")
    run.add_argument("--budget-scales", default="1")
    run.add_argument("--max-new-tokens", type=int, default=96)
    run.add_argument("--max-expansions", type=int, default=0)
    run.add_argument("--active-rows", type=int, default=8)
    run.add_argument("--state-batch-size", type=int, default=8)
    run.add_argument("--checkpoint-every", type=int, default=1)
    run.add_argument("--num-shards", type=int, default=1)
    run.add_argument("--shard-index", type=int, default=0)
    run.add_argument("--futoshiki-size", type=int, default=7)
    run.add_argument("--futoshiki-difficulty", type=int, default=3)
    run.add_argument("--graph-num-vertices", type=int, default=16)
    run.add_argument("--graph-num-colors", type=int, default=3)
    run.add_argument("--graph-edge-probability", type=float, default=0.4)
    run.add_argument("--graph-difficulty-bin-label", default="v16_p04")
    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("--inputs", required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run-shard":
        payload = run_shard(args)
    else:
        payload = merge(args)
    print(json.dumps({"path": str(args.output), "status": payload["status"], "rows": len(payload["rows"])}, sort_keys=True))


if __name__ == "__main__":
    main()
