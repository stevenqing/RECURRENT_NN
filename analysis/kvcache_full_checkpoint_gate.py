"""Full cache-state checkpoint exactness gate for Qwen-style non-pure-KV caches."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from analysis.kvcache_exactness_gate import _cache_inventory, _cache_seq_length, _deviation, _different_token
from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel


SCHEMA_VERSION = "kvcache_full_checkpoint_gate_v1"
STATUS_PASS = "KVCACHE_FULL_CHECKPOINT_GATE_PASS"
STATUS_FAIL = "KVCACHE_FULL_CHECKPOINT_GATE_FAIL"


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
def _greedy_extend_with_checkpoints(model: Any, prompt_ids: torch.Tensor, depth: int, checkpoints: set[int]) -> tuple[torch.Tensor, list[torch.Tensor], dict[int, Any], Any]:
    logits, cache = _forward_logits(model, prompt_ids)
    generated: list[torch.Tensor] = []
    step_logits: list[torch.Tensor] = []
    checkpoint_caches: dict[int, Any] = {0: copy.deepcopy(cache)} if 0 in checkpoints else {}
    for step in range(depth):
        step_logits.append(logits.detach().float().cpu())
        next_token = logits.argmax(dim=-1, keepdim=True)
        generated.append(next_token)
        logits, cache = _forward_logits(model, next_token, past=cache)
        generated_count = step + 1
        if generated_count in checkpoints:
            checkpoint_caches[generated_count] = copy.deepcopy(cache)
    return torch.cat([prompt_ids] + generated, dim=1), step_logits, checkpoint_caches, cache


def _load(args: argparse.Namespace) -> tuple[Any, Any, torch.device]:
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
    else:
        device = torch.device(args.device)
    dtype = torch.bfloat16 if args.dtype == "bf16" and device.type == "cuda" else torch.float16 if args.dtype == "fp16" and device.type == "cuda" else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=dtype, trust_remote_code=True).to(device).eval()
    if hasattr(model.config, "use_cache"):
        model.config.use_cache = True
    return model, tokenizer, device


def run(args: argparse.Namespace) -> dict[str, Any]:
    model, tokenizer, device = _load(args)
    prompt_ids = tokenizer(args.prompt, return_tensors="pt").input_ids.to(device)
    prompt_len = int(prompt_ids.shape[1])
    checkpoints = [int(item) for item in args.checkpoints.split(",") if item.strip()]
    needed_checkpoints = {item for item in checkpoints if 1 <= item < args.depth - 1}
    full_ids, step_logits, checkpoint_caches, full_cache = _greedy_extend_with_checkpoints(model, prompt_ids, args.depth, needed_checkpoints)
    avoid_ids = {token for token in [tokenizer.eos_token_id, tokenizer.pad_token_id, tokenizer.bos_token_id] if token is not None}
    tests: list[dict[str, Any]] = []
    overall = True
    for generated_prefix_len in checkpoints:
        checkpoint_len = prompt_len + generated_prefix_len
        if generated_prefix_len not in checkpoint_caches:
            tests.append({"checkpoint_generated_tokens": generated_prefix_len, "status": "SKIP_INVALID_CHECKPOINT", "reason": f"requires 1 <= k < depth-1={args.depth - 1}"})
            continue
        checkpoint_cache = checkpoint_caches[generated_prefix_len]
        same_token = full_ids[:, checkpoint_len : checkpoint_len + 1]
        same_cache = copy.deepcopy(checkpoint_cache)
        same_len_before = _cache_seq_length(same_cache)
        same_logits, same_after = _forward_logits(model, same_token, past=same_cache)
        same_len_after = _cache_seq_length(same_after)
        same_dev = _deviation(same_logits, step_logits[generated_prefix_len + 1])
        same_pass = same_len_before == checkpoint_len and same_len_after == checkpoint_len + 1 and same_dev["argmax_equal"] and same_dev["max_abs_logit_delta"] <= args.tol
        tests.append({
            "test": "full_checkpoint_resume_same",
            "checkpoint_generated_tokens": generated_prefix_len,
            "checkpoint_seq_len": checkpoint_len,
            "cache_len_before_feed": same_len_before,
            "cache_len_after_feed": same_len_after,
            "same_token_id": int(same_token[0, 0].item()),
            "pass": same_pass,
            **same_dev,
        })
        overall = overall and same_pass

        diff_token_id = _different_token(int(same_token[0, 0].item()), int(model.config.vocab_size), avoid_ids)
        diff_token = torch.tensor([[diff_token_id]], dtype=full_ids.dtype, device=device)
        diff_cache = copy.deepcopy(checkpoint_cache)
        diff_len_before = _cache_seq_length(diff_cache)
        diff_logits, diff_after = _forward_logits(model, diff_token, past=diff_cache)
        diff_len_after = _cache_seq_length(diff_after)
        fresh_ids = torch.cat([full_ids[:, :checkpoint_len], diff_token], dim=1)
        fresh_logits, fresh_cache = _forward_logits(model, fresh_ids)
        fresh_len_after = _cache_seq_length(fresh_cache)
        diff_dev = _deviation(diff_logits, fresh_logits)
        diff_pass = diff_len_before == checkpoint_len and diff_len_after == checkpoint_len + 1 and fresh_len_after == checkpoint_len + 1 and diff_dev["argmax_equal"] and diff_dev["max_abs_logit_delta"] <= args.tol
        tests.append({
            "test": "full_checkpoint_resume_different_equals_fresh",
            "checkpoint_generated_tokens": generated_prefix_len,
            "checkpoint_seq_len": checkpoint_len,
            "cache_len_before_feed": diff_len_before,
            "cache_len_after_feed": diff_len_after,
            "fresh_cache_len_after_feed": fresh_len_after,
            "same_token_id": int(same_token[0, 0].item()),
            "different_token_id": diff_token_id,
            "pass": diff_pass,
            **diff_dev,
        })
        overall = overall and diff_pass
    max_delta = max((float(row.get("max_abs_logit_delta", 0.0)) for row in tests), default=0.0)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_PASS if overall else STATUS_FAIL,
        "generated_at": _now(),
        "model": args.model,
        "device": str(device),
        "dtype": args.dtype,
        "prompt": args.prompt,
        "prompt_tokens": prompt_len,
        "depth": args.depth,
        "full_cache_seq_len": _cache_seq_length(full_cache),
        "cache_type": type(full_cache).__name__,
        "cache_inventory": _cache_inventory(full_cache),
        "restore_mode": "full_cache_state_deepcopy_at_checkpoint",
        "tol": args.tol,
        "max_abs_logit_delta": max_delta,
        "all_argmax_equal": all(bool(row.get("argmax_equal", True)) for row in tests if row.get("test")),
        "overall_pass": overall,
        "tests": tests,
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.out, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full cache-state checkpoint exactness gate.")
    parser.add_argument("--model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--prompt", default="Solve step by step. Variables A B C D E, colors 1 2 3.\nStep:")
    parser.add_argument("--depth", type=int, default=16)
    parser.add_argument("--checkpoints", default="2,4,8,12")
    parser.add_argument("--tol", type=float, default=1e-3)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=["bf16", "fp16", "fp32"], default="bf16")
    parser.add_argument("--out", type=Path, default=Path("results/kvcache_exactness/km3_full_checkpoint_qwen35.json"))
    run(parser.parse_args())


if __name__ == "__main__":
    main()