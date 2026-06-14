"""KM-3 exactness gate for KV-cache checkpoint search."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel


SCHEMA_VERSION = "kvcache_exactness_gate_v1"
STATUS_PASS = "KVCACHE_EXACTNESS_GATE_PASS"
STATUS_FAIL = "KVCACHE_EXACTNESS_GATE_FAIL"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _cache_seq_length(cache: Any) -> int:
    if cache is None:
        return 0
    if hasattr(cache, "get_seq_length"):
        return int(cache.get_seq_length())
    if isinstance(cache, tuple):
        return int(cache[0][0].shape[-2])
    raise TypeError(f"unsupported cache type {type(cache)}")


def _cache_inventory(cache: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if hasattr(cache, "layers"):
        for layer_index, layer in enumerate(cache.layers):
            row: dict[str, Any] = {"layer": layer_index, "cache_layer_class": type(layer).__name__}
            for attr in ["keys", "values", "key_cache", "value_cache", "recurrent_states", "conv_states"]:
                value = getattr(layer, attr, None)
                if value is not None:
                    row[attr] = {"shape": list(value.shape), "dtype": str(value.dtype).replace("torch.", ""), "device": str(value.device)}
            rows.append(row)
        return rows
    if isinstance(cache, tuple):
        for layer_index, (key, value) in enumerate(cache):
            rows.append(
                {
                    "layer": layer_index,
                    "cache_layer_class": "legacy_tuple",
                    "key": {"shape": list(key.shape), "dtype": str(key.dtype).replace("torch.", ""), "device": str(key.device)},
                    "value": {"shape": list(value.shape), "dtype": str(value.dtype).replace("torch.", ""), "device": str(value.device)},
                }
            )
    return rows


def _crop_cache(cache: Any, length: int) -> tuple[Any, str]:
    if hasattr(cache, "crop"):
        cache.crop(length)
        return cache, "dynamic_cache_crop"
    if isinstance(cache, tuple):
        return tuple((k[:, :, :length, :].contiguous(), v[:, :, :length, :].contiguous()) for (k, v) in cache), "legacy_tuple_slice"
    raise TypeError(f"unsupported cache type {type(cache)}")


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
        next_token = logits.argmax(dim=-1, keepdim=True)
        generated.append(next_token)
        logits, cache = _forward_logits(model, next_token, past=cache)
    return torch.cat([prompt_ids] + generated, dim=1), cache, step_logits


def _deviation(left: torch.Tensor, right: torch.Tensor) -> dict[str, Any]:
    left_cpu = left.detach().float().cpu()
    right_cpu = right.detach().float().cpu()
    return {
        "max_abs_logit_delta": float((left_cpu - right_cpu).abs().max().item()),
        "argmax_equal": bool(torch.equal(left_cpu.argmax(dim=-1), right_cpu.argmax(dim=-1))),
        "left_argmax": int(left_cpu.argmax(dim=-1)[0].item()),
        "right_argmax": int(right_cpu.argmax(dim=-1)[0].item()),
    }


def _different_token(token_id: int, vocab_size: int, avoid_ids: set[int]) -> int:
    candidate = (int(token_id) + 1) % vocab_size
    while candidate in avoid_ids or candidate == int(token_id):
        candidate = (candidate + 1) % vocab_size
    return int(candidate)


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
    full_ids, full_cache, step_logits = _greedy_extend(model, prompt_ids, args.depth)
    cache_len = _cache_seq_length(full_cache)
    checkpoints = [int(item) for item in args.checkpoints.split(",") if item.strip()]
    tests: list[dict[str, Any]] = []
    overall = True
    crop_paths = set()
    avoid_ids = {token for token in [tokenizer.eos_token_id, tokenizer.pad_token_id, tokenizer.bos_token_id] if token is not None}
    for generated_prefix_len in checkpoints:
        checkpoint_len = prompt_len + generated_prefix_len
        checkpoint_ok = 1 <= generated_prefix_len < args.depth - 1
        if not checkpoint_ok:
            tests.append({"checkpoint_generated_tokens": generated_prefix_len, "status": "SKIP_INVALID_CHECKPOINT", "reason": f"requires 1 <= k < depth-1={args.depth - 1}"})
            continue
        same_token = full_ids[:, checkpoint_len : checkpoint_len + 1]
        cropped_same = copy.deepcopy(full_cache)
        cropped_same, crop_path = _crop_cache(cropped_same, checkpoint_len)
        crop_paths.add(crop_path)
        same_len_before = _cache_seq_length(cropped_same)
        same_logits, same_after = _forward_logits(model, same_token, past=cropped_same)
        same_len_after = _cache_seq_length(same_after)
        same_dev = _deviation(same_logits, step_logits[generated_prefix_len + 1])
        same_pass = same_len_before == checkpoint_len and same_len_after == checkpoint_len + 1 and same_dev["argmax_equal"] and same_dev["max_abs_logit_delta"] <= args.tol
        tests.append({
            "test": "resume_same",
            "checkpoint_generated_tokens": generated_prefix_len,
            "checkpoint_seq_len": checkpoint_len,
            "crop_path": crop_path,
            "cache_len_before_feed": same_len_before,
            "cache_len_after_feed": same_len_after,
            "same_token_id": int(same_token[0, 0].item()),
            "pass": same_pass,
            **same_dev,
        })
        overall = overall and same_pass

        diff_token_id = _different_token(int(same_token[0, 0].item()), int(model.config.vocab_size), avoid_ids)
        diff_token = torch.tensor([[diff_token_id]], dtype=full_ids.dtype, device=device)
        cropped_diff = copy.deepcopy(full_cache)
        cropped_diff, crop_path = _crop_cache(cropped_diff, checkpoint_len)
        crop_paths.add(crop_path)
        diff_len_before = _cache_seq_length(cropped_diff)
        diff_logits, diff_after = _forward_logits(model, diff_token, past=cropped_diff)
        diff_len_after = _cache_seq_length(diff_after)
        fresh_ids = torch.cat([full_ids[:, :checkpoint_len], diff_token], dim=1)
        fresh_logits, fresh_cache = _forward_logits(model, fresh_ids)
        fresh_len_after = _cache_seq_length(fresh_cache)
        diff_dev = _deviation(diff_logits, fresh_logits)
        diff_pass = diff_len_before == checkpoint_len and diff_len_after == checkpoint_len + 1 and fresh_len_after == checkpoint_len + 1 and diff_dev["argmax_equal"] and diff_dev["max_abs_logit_delta"] <= args.tol
        tests.append({
            "test": "resume_different_equals_fresh",
            "checkpoint_generated_tokens": generated_prefix_len,
            "checkpoint_seq_len": checkpoint_len,
            "crop_path": crop_path,
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
        "full_cache_seq_len": cache_len,
        "cache_type": type(full_cache).__name__,
        "cache_inventory": _cache_inventory(full_cache),
        "tol": args.tol,
        "crop_paths": sorted(crop_paths),
        "max_abs_logit_delta": max_delta,
        "all_argmax_equal": all(bool(row.get("argmax_equal", True)) for row in tests if row.get("test")),
        "overall_pass": overall,
        "tests": tests,
        "kill_rule": "No KV-cache checkpoint search arm may be read unless status is KVCACHE_EXACTNESS_GATE_PASS.",
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.out, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run KM-3 exactness gate for KV-cache checkpoint search.")
    parser.add_argument("--model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--prompt", default="Solve step by step. Variables A B C D E, colors 1 2 3.\nStep:")
    parser.add_argument("--depth", type=int, default=16)
    parser.add_argument("--checkpoints", default="2,4,8,12")
    parser.add_argument("--tol", type=float, default=1e-3)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=["bf16", "fp16", "fp32"], default="bf16")
    parser.add_argument("--out", type=Path, default=Path("results/kvcache_exactness/km3_result.json"))
    run(parser.parse_args())


if __name__ == "__main__":
    main()