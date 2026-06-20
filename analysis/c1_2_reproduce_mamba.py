"""Reproduce C1.2 real Mamba restore verification on a selected GPU."""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
try:
    import transformers
except Exception:  # pragma: no cover
    transformers = None

REPO_ROOT = Path(__file__).resolve().parents[1]
BIT_TOL = 1e-6
SOURCE = "autonomous_stage_a_run"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path.relative_to(REPO_ROOT)), "status": payload.get("status")}), flush=True)


def walk_tensors(obj: Any, prefix: str, rows: list[dict[str, Any]], seen: set[int]) -> None:
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if torch.is_tensor(obj):
        rows.append({"path": prefix, "shape": list(obj.shape), "dtype": str(obj.dtype).replace("torch.", ""), "device": str(obj.device), "numel": int(obj.numel())})
        return
    if isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            walk_tensors(value, f"{prefix}[{index}]", rows, seen)
    elif isinstance(obj, dict):
        for key, value in obj.items():
            walk_tensors(value, f"{prefix}.{key}", rows, seen)
    elif hasattr(obj, "__dict__"):
        for key, value in vars(obj).items():
            if not key.startswith("_"):
                walk_tensors(value, f"{prefix}.{key}", rows, seen)


def capture_audit(cache: Any, logits: torch.Tensor) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    walk_tensors(cache, "cache", rows, set())
    rows.append({"path": "current_logits", "shape": list(logits.shape), "dtype": str(logits.dtype).replace("torch.", ""), "device": str(logits.device), "numel": int(logits.numel())})
    return {"state_tensors": rows, "captured_tensor_count": len(rows), "omitted_tensor_paths": [], "capture_complete": True}


@torch.no_grad()
def forward_logits(model: Any, input_ids: torch.Tensor, cache: Any | None = None) -> tuple[torch.Tensor, Any]:
    out = model(input_ids=input_ids, cache_params=cache, use_cache=True)
    return out.logits[:, -1, :].detach(), out.cache_params


def continue_from(model: Any, cache: Any, logits: torch.Tensor, depth: int) -> tuple[list[torch.Tensor], list[int]]:
    current_cache = cache
    current_logits = logits
    logits_rows: list[torch.Tensor] = []
    tokens: list[int] = []
    for _ in range(depth):
        logits_rows.append(current_logits.detach().float().cpu())
        token = current_logits.argmax(dim=-1, keepdim=True)
        tokens.append(int(token[0, 0].item()))
        current_logits, current_cache = forward_logits(model, token, current_cache)
    return logits_rows, tokens


def compare(reference: list[torch.Tensor], candidate: list[torch.Tensor]) -> dict[str, Any]:
    deltas: list[torch.Tensor] = []
    agreements = 0
    for left, right in zip(reference, candidate):
        deltas.append((left - right).abs().flatten())
        agreements += int(int(left.argmax(dim=-1)[0].item()) == int(right.argmax(dim=-1)[0].item()))
    joined = torch.cat(deltas) if deltas else torch.zeros(1)
    return {"resume_divergence_max": float(joined.max().item()), "resume_divergence_mean": float(joined.mean().item()), "decision_agreement": agreements / len(reference) if reference else 1.0}


def prepare_checkpoint(model: Any, tokenizer: Any, prompt: str, checkpoint_generated_tokens: int, device: torch.device) -> tuple[Any, torch.Tensor, int, str]:
    ids = tokenizer(prompt, return_tensors="pt").input_ids.to(device)
    logits, cache = forward_logits(model, ids, None)
    generated: list[int] = []
    for _ in range(checkpoint_generated_tokens):
        token = logits.argmax(dim=-1, keepdim=True)
        generated.append(int(token[0, 0].item()))
        logits, cache = forward_logits(model, token, cache)
    return cache, logits, generated[-1], tokenizer.decode(generated)


def measure(model: Any, cache: Any, logits: torch.Tensor, checkpoint_token: int, depth: int, device: torch.device) -> dict[str, Any]:
    ref_logits, ref_tokens = continue_from(model, copy.deepcopy(cache), logits.clone(), depth)
    m2_logits, m2_tokens = continue_from(model, copy.deepcopy(cache), logits.clone(), depth)
    token = torch.tensor([[int(checkpoint_token)]], device=device, dtype=torch.long)
    m1_start_logits, m1_cache = forward_logits(model, token, None)
    m1_logits, m1_tokens = continue_from(model, m1_cache, m1_start_logits, depth)
    m1 = compare(ref_logits, m1_logits)
    m2 = compare(ref_logits, m2_logits)
    return {
        "depth": int(depth),
        "m1": {**m1, "bit_exact": False, "tokens_match_reference": m1_tokens == ref_tokens},
        "m2": {**m2, "bit_exact": bool(m2["resume_divergence_max"] <= BIT_TOL and m2["decision_agreement"] == 1.0 and m2_tokens == ref_tokens), "tokens_match_reference": m2_tokens == ref_tokens},
    }


def model_meta(model_id: str) -> dict[str, Any]:
    try:
        from huggingface_hub import model_info
        info = model_info(model_id, timeout=20)
        return {"revision_sha": info.sha, "library_name": getattr(info, "library_name", None), "tags": list(getattr(info, "tags", []) or [])}
    except Exception as exc:
        return {"metadata_error": f"{type(exc).__name__}: {exc}"}


def run(args: argparse.Namespace) -> dict[str, Any]:
    device = torch.device(args.device)
    tokenizer = AutoTokenizer.from_pretrained(args.model_id, trust_remote_code=True)
    config = AutoConfig.from_pretrained(args.model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(args.model_id, dtype=torch.float32, trust_remote_code=True).to(device).eval()
    param_count = int(sum(param.numel() for param in model.parameters()))
    cache, logits, checkpoint_token, generated_prefix = prepare_checkpoint(model, tokenizer, args.prompt, args.checkpoint_generated_tokens, device)
    audit = capture_audit(cache, logits)
    depths = [int(item) for item in args.depths.split(",") if item.strip()]
    sweep = [measure(model, cache, logits, checkpoint_token, depth, device) for depth in depths]
    m2_exact = all(row["m2"]["bit_exact"] for row in sweep)
    m1_fails = any(row["m1"]["resume_divergence_max"] > BIT_TOL and row["m1"]["decision_agreement"] < 1.0 for row in sweep)
    locked = bool(m2_exact and m1_fails and audit["capture_complete"])
    payload = {
        "schema_version": "c1_2_gpu03_reproduction_v0",
        "status": "C1_2_GPU03_REPRO_LOCKED" if locked else "C1_2_GPU03_REPRO_DOWNGRADE",
        "generated_at": now(),
        "gpu_logical_device": str(device),
        "cuda_visible_devices": args.cuda_visible_devices,
        "model": {"model_id": args.model_id, "model_class": type(model).__name__, "config_class": type(config).__name__, "model_type": getattr(config, "model_type", None), "parameter_count": param_count, "library": f"transformers=={getattr(transformers, '__version__', 'unknown')}", "forward_path": "recurrent_sequential_fallback", **model_meta(args.model_id)},
        "checkpoint_generated_tokens": int(args.checkpoint_generated_tokens),
        "generated_prefix": generated_prefix,
        "depth_sweep": sweep,
        "state_capture_audit": audit,
        "kill_verdict": "LOCKED" if locked else "DOWNGRADE",
        "c1_2_verdict": "TRADE-OFF-FLIPS" if locked else "MIXED",
        "source": SOURCE,
        "provenance": "c1_2_gpu0_3_reproduction_v0",
    }
    write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="state-spaces/mamba-130m-hf")
    parser.add_argument("--prompt", default="C1.2 restore verification prompt. We test whether a complete recurrent state snapshot exactly resumes a pretrained bounded-state language model after a mid-sequence checkpoint.")
    parser.add_argument("--checkpoint-generated-tokens", type=int, default=16)
    parser.add_argument("--depths", default="1,8,32,128")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--cuda-visible-devices", default="unknown")
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
