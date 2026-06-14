"""KM-3 exactness gate using real graph_color decision prompts."""

from __future__ import annotations

import argparse
import copy
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import torch

from analysis.kvcache_exactness_gate import _cache_inventory, _cache_seq_length, _crop_cache, _deviation, _different_token, _load
from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_reasoning_gym_bounded_register import (
    _backtrack_prompt,
    _branch_prompt,
    _clean_trace,
    _current_domain,
    _deadend_nogood,
    _ensure_reasoning_gym,
    _entry_for_register,
    _graph_color_view,
)


SCHEMA_VERSION = "kvcache_real_prompt_gate_v1"
STATUS_PASS = "KVCACHE_REAL_PROMPT_KM3_PASS"
STATUS_FAIL = "KVCACHE_REAL_PROMPT_KM3_FAIL"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


@torch.no_grad()
def _forward_logits(model: Any, input_ids: torch.Tensor, past: Any | None = None) -> tuple[torch.Tensor, Any]:
    out = model(input_ids=input_ids, past_key_values=past, use_cache=True)
    return out.logits[:, -1, :], out.past_key_values


@torch.no_grad()
def _greedy_extend(model: Any, prompt_ids: torch.Tensor, n_new: int) -> tuple[torch.Tensor, Any, list[torch.Tensor]]:
    logits, cache = _forward_logits(model, prompt_ids)
    generated: list[torch.Tensor] = []
    step_logits: list[torch.Tensor] = []
    for _ in range(n_new):
        step_logits.append(logits.detach().float().cpu())
        token = logits.argmax(dim=-1, keepdim=True)
        generated.append(token)
        logits, cache = _forward_logits(model, token, past=cache)
    return torch.cat([prompt_ids] + generated, dim=1), cache, step_logits


def _chat_prompt(tokenizer: Any, prompt: str) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True)
    return prompt


def _make_dataset(args: argparse.Namespace) -> Any:
    reasoning_gym = _ensure_reasoning_gym(args.reasoning_gym_repo)
    return reasoning_gym.create_dataset(
        "graph_color",
        size=args.scan_limit,
        seed=args.seed,
        num_colors=args.num_colors,
        min_num_vertices=args.num_vertices,
        max_num_vertices=args.num_vertices,
        edge_probability=args.edge_probability,
    )


def _select_entry(dataset: Any, args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    for index in range(args.scan_limit):
        entry = dataset[index]
        entry.setdefault("metadata", {})["source_index"] = index
        trace = _clean_trace(entry, args.order_mode, args.node_cap, dataset)
        if trace.get("solved") and int(trace.get("total_retractions", 0)) >= args.min_backtracks:
            return index, entry
    raise RuntimeError("No graph_color entry met min_backtracks in scan window")


def _real_prompts(entry: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    view = _graph_color_view(entry, args.order_mode)
    position = {vertex: index for index, vertex in enumerate(view["order"])}
    assignment: dict[int, int] = {}
    tried: dict[int, set[int]] = defaultdict(set)
    register: list[dict[str, Any]] = []
    cursor = 0
    branch_prompt_row: dict[str, Any] | None = None
    backtrack_prompt_row: dict[str, Any] | None = None
    while cursor < len(view["order"]):
        vertex = view["order"][cursor]
        domain = _current_domain(view, vertex, assignment, tried)
        if domain:
            assigned_neighbors = [{"neighbor": neighbor, "color": assignment[neighbor]} for neighbor in sorted(view["adjacency"][vertex]) if neighbor in assignment]
            prompt = _branch_prompt(entry, vertex, domain, assigned_neighbors)
            if branch_prompt_row is None and len(assignment) >= args.branch_after_assignments:
                branch_prompt_row = {
                    "prompt_kind": "branch",
                    "prompt": prompt,
                    "source_index": entry.get("metadata", {}).get("source_index"),
                    "current_variable": int(vertex),
                    "remaining_domain": [int(item) for item in domain],
                    "assigned_neighbors": assigned_neighbors,
                    "assignment_size": len(assignment),
                }
            color = domain[0]
            tried[vertex].add(color)
            assignment[vertex] = color
            register.append({"vertex": vertex, "color": color, "order_index": cursor})
            cursor += 1
            continue
        if register:
            nogood = _deadend_nogood(view, vertex, assignment, position)
            blockers = sorted(nogood)
            view_start = max(0, len(register) - args.r_value)
            bounded = [_entry_for_register(item, index - view_start) for index, item in enumerate(register[view_start:])]
            prompt = _backtrack_prompt(entry, vertex, blockers, bounded)
            backtrack_prompt_row = {
                "prompt_kind": "backtrack",
                "prompt": prompt,
                "source_index": entry.get("metadata", {}).get("source_index"),
                "conflict_variable": int(vertex),
                "conflict_blockers": [int(item) for item in blockers],
                "bounded_register_len": len(bounded),
                "assignment_size": len(assignment),
            }
            break
        break
    rows = [row for row in [branch_prompt_row, backtrack_prompt_row] if row is not None]
    if not rows:
        raise RuntimeError("Could not construct real branch/backtrack prompt rows")
    return rows


def _run_gate_for_prompt(model: Any, tokenizer: Any, prompt_text: str, args: argparse.Namespace) -> dict[str, Any]:
    rendered = _chat_prompt(tokenizer, prompt_text) if args.chat_template else prompt_text
    prompt_ids = tokenizer(rendered, return_tensors="pt").input_ids.to(model.device)
    prompt_len = int(prompt_ids.shape[1])
    full_ids, full_cache, step_logits = _greedy_extend(model, prompt_ids, args.depth)
    checkpoints = [int(item) for item in args.checkpoints.split(",") if item.strip()]
    avoid_ids = {token for token in [tokenizer.eos_token_id, tokenizer.pad_token_id, tokenizer.bos_token_id] if token is not None}
    tests = []
    overall = True
    crop_paths = set()
    for generated_prefix_len in checkpoints:
        checkpoint_len = prompt_len + generated_prefix_len
        if not (1 <= generated_prefix_len < args.depth - 1):
            continue
        same_token = full_ids[:, checkpoint_len : checkpoint_len + 1]
        cropped_same = copy.deepcopy(full_cache)
        cropped_same, crop_path = _crop_cache(cropped_same, checkpoint_len)
        crop_paths.add(crop_path)
        same_logits, same_after = _forward_logits(model, same_token, past=cropped_same)
        same_dev = _deviation(same_logits, step_logits[generated_prefix_len + 1])
        same_pass = _cache_seq_length(cropped_same) == checkpoint_len + 1 and _cache_seq_length(same_after) == checkpoint_len + 1 and same_dev["argmax_equal"] and same_dev["max_abs_logit_delta"] <= args.tol
        tests.append({"test": "resume_same", "checkpoint_generated_tokens": generated_prefix_len, "checkpoint_seq_len": checkpoint_len, "crop_path": crop_path, "pass": same_pass, **same_dev})
        overall = overall and same_pass
        diff_token_id = _different_token(int(same_token[0, 0].item()), int(model.config.vocab_size), avoid_ids)
        diff_token = torch.tensor([[diff_token_id]], dtype=full_ids.dtype, device=model.device)
        cropped_diff = copy.deepcopy(full_cache)
        cropped_diff, crop_path = _crop_cache(cropped_diff, checkpoint_len)
        diff_logits, diff_after = _forward_logits(model, diff_token, past=cropped_diff)
        fresh_ids = torch.cat([full_ids[:, :checkpoint_len], diff_token], dim=1)
        fresh_logits, fresh_cache = _forward_logits(model, fresh_ids)
        diff_dev = _deviation(diff_logits, fresh_logits)
        diff_pass = _cache_seq_length(cropped_diff) == checkpoint_len + 1 and _cache_seq_length(diff_after) == checkpoint_len + 1 and _cache_seq_length(fresh_cache) == checkpoint_len + 1 and diff_dev["argmax_equal"] and diff_dev["max_abs_logit_delta"] <= args.tol
        tests.append({"test": "resume_different_equals_fresh", "checkpoint_generated_tokens": generated_prefix_len, "checkpoint_seq_len": checkpoint_len, "crop_path": crop_path, "pass": diff_pass, "different_token_id": diff_token_id, **diff_dev})
        overall = overall and diff_pass
    return {
        "prompt_tokens": prompt_len,
        "rendered_prompt_chars": len(rendered),
        "full_cache_seq_len": _cache_seq_length(full_cache),
        "cache_type": type(full_cache).__name__,
        "cache_inventory": _cache_inventory(full_cache),
        "crop_paths": sorted(crop_paths),
        "max_abs_logit_delta": max((float(row.get("max_abs_logit_delta", 0.0)) for row in tests), default=0.0),
        "all_argmax_equal": all(bool(row.get("argmax_equal", True)) for row in tests),
        "overall_pass": overall,
        "tests": tests,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset = _make_dataset(args)
    source_index, entry = _select_entry(dataset, args)
    prompt_rows = _real_prompts(entry, args)
    model_args = argparse.Namespace(model=args.model, device=args.device, dtype=args.dtype)
    model, tokenizer, device = _load(model_args)
    prompt_results = []
    overall = True
    for row in prompt_rows:
        result = _run_gate_for_prompt(model, tokenizer, row["prompt"], args)
        prompt_results.append(row | result)
        overall = overall and bool(result["overall_pass"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_PASS if overall else STATUS_FAIL,
        "generated_at": _now(),
        "model": args.model,
        "device": str(device),
        "dtype": args.dtype,
        "benchmark": "graph_color",
        "source_index": source_index,
        "config": {key: (str(value) if isinstance(value, Path) else value) for key, value in vars(args).items() if key not in {"out"}},
        "overall_pass": overall,
        "max_abs_logit_delta": max((float(row.get("max_abs_logit_delta", 0.0)) for row in prompt_results), default=0.0),
        "all_argmax_equal": all(bool(row.get("all_argmax_equal", True)) for row in prompt_results),
        "prompt_results": prompt_results,
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.out, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run KM-3 on real graph_color decision prompts.")
    parser.add_argument("--out", type=Path, default=Path("results/kvcache_exactness/km3_real_graph_color_prompt_qwen3_fp32.json"))
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--reasoning-gym-repo", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scan-limit", type=int, default=200)
    parser.add_argument("--min-backtracks", type=int, default=4)
    parser.add_argument("--node-cap", type=int, default=80)
    parser.add_argument("--num-vertices", type=int, default=14)
    parser.add_argument("--num-colors", type=int, default=3)
    parser.add_argument("--edge-probability", type=float, default=0.4)
    parser.add_argument("--order-mode", default="degree_desc", choices=["degree_desc", "natural"])
    parser.add_argument("--r-value", type=int, default=8)
    parser.add_argument("--branch-after-assignments", type=int, default=4)
    parser.add_argument("--depth", type=int, default=16)
    parser.add_argument("--checkpoints", default="2,4,8,12")
    parser.add_argument("--tol", type=float, default=1e-3)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=["bf16", "fp16", "fp32"], default="fp32")
    parser.add_argument("--chat-template", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()