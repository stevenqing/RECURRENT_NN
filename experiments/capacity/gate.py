"""Restore and register gates for capacity experiments."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import torch
import torch.nn.functional as F

from analysis.kvcache_exactness_gate import _forward_logits
from register.structured import StructuredRegister


def _model_and_tokenizer(operator: Any) -> tuple[Any | None, Any | None]:
    model = getattr(operator, "model", None)
    tokenizer = getattr(operator, "tokenizer", None)
    return model, tokenizer


def _prefix_text(operator: Any, task_type: str, givens: Mapping[str, Any], checkpoint_prefix: Any) -> str:
    if isinstance(checkpoint_prefix, str):
        return checkpoint_prefix
    renderer = getattr(operator, "renderer", None)
    if renderer is not None and hasattr(renderer, "render"):
        partial = checkpoint_prefix if isinstance(checkpoint_prefix, Mapping) else {}
        return renderer.render(task_type, givens, partial)
    return str(checkpoint_prefix)


def _as_token_tensor(token_id: Any, device: torch.device) -> torch.Tensor:
    if torch.is_tensor(token_id):
        token = token_id.to(device=device, dtype=torch.long)
        if token.ndim == 0:
            token = token.view(1, 1)
        elif token.ndim == 1:
            token = token.view(1, -1)
        return token[:, -1:]
    return torch.tensor([[int(token_id)]], dtype=torch.long, device=device)


def _max_abs(left: torch.Tensor, right: torch.Tensor) -> float:
    left_cpu = left.detach().float().cpu()
    right_cpu = right.detach().float().cpu()
    return float((left_cpu - right_cpu).abs().max().item())


def _prob_deviation(left_logits: torch.Tensor, right_logits: torch.Tensor) -> dict[str, float | bool]:
    left = F.softmax(left_logits.detach().float().cpu(), dim=-1)
    right = F.softmax(right_logits.detach().float().cpu(), dim=-1)
    delta = (left - right).abs()
    return {
        "max_abs": float(delta.max().item()),
        "mean_abs": float(delta.mean().item()),
        "argmax_equal": bool(torch.equal(left.argmax(dim=-1), right.argmax(dim=-1))),
    }


@torch.no_grad()
def register_pop_exact(register, D, K, depth, tol=1e-9) -> tuple[bool, float]:
    """Check algebraic push/pop exactness without invoking the operator."""
    device = torch.device("cpu")
    hidden_dim = int(getattr(register, "hidden_dim", D))
    generator = torch.Generator(device="cpu").manual_seed(1009 + int(D) + int(K) + int(depth))
    register = register.to(device).double() if isinstance(register, torch.nn.Module) else register
    h0 = register.init_state(1, device).double()
    h = h0.clone()
    encodings = [torch.randn(1, hidden_dim, generator=generator, dtype=torch.float64, device=device) for _ in range(int(depth))]
    for level, encoding in enumerate(encodings):
        h = register.push(h, encoding, level)
    for level in reversed(range(int(depth))):
        h = register.pop(h, encodings[level], level)
    err = float((h - h0).abs().max().item())
    return bool(err <= tol), err


@torch.no_grad()
def operator_restore_gate(operator, task, givens, checkpoint_prefix, restored_state) -> dict:
    """Compare restored-state resume to full recompute at the measured noise floor."""
    state = restored_state if isinstance(restored_state, Mapping) else {"past_key_values": restored_state}
    model, tokenizer = _model_and_tokenizer(operator)
    if model is None or tokenizer is None:
        return {
            "gate_status": "unsupported_no_model_or_tokenizer",
            "decision_agreement": 0.0,
            "resume_divergence": {"max_abs": None, "mean_abs": None},
            "noise_floor": {"max_abs": None, "mean_abs": None},
            "within_noise_floor": False,
        }
    cache = state.get("past_key_values", state.get("cache"))
    token_id = state.get("feed_token_id", state.get("next_token_id", state.get("token_id")))
    task_type = str(task) if isinstance(task, str) else str(task.get("task_type", "graph_coloring")) if isinstance(task, Mapping) else "graph_coloring"
    if cache is None or token_id is None:
        return {
            "gate_status": "unsupported_missing_cache_or_feed_token",
            "decision_agreement": 0.0,
            "resume_divergence": {"max_abs": None, "mean_abs": None},
            "noise_floor": {"max_abs": None, "mean_abs": None},
            "within_noise_floor": False,
        }
    prefix_text = _prefix_text(operator, task_type, givens, checkpoint_prefix)
    prefix_ids = tokenizer(prefix_text, return_tensors="pt").input_ids.to(model.device)
    feed_token = _as_token_tensor(token_id, model.device)
    fresh_ids = torch.cat([prefix_ids, feed_token], dim=1)
    restored_logits, _ = _forward_logits(model, feed_token, past=copy.deepcopy(cache))
    fresh_logits, _ = _forward_logits(model, fresh_ids)
    repeat_logits, _ = _forward_logits(model, fresh_ids)
    _prefix_logits, recomputed_cache = _forward_logits(model, prefix_ids)
    baseline_resume_logits, _ = _forward_logits(model, feed_token, past=recomputed_cache)
    resume = _prob_deviation(restored_logits, fresh_logits)
    noise = _prob_deviation(baseline_resume_logits, fresh_logits)
    recompute_repeat = _prob_deviation(fresh_logits, repeat_logits)
    decision_agreement = 1.0 if resume["argmax_equal"] else 0.0
    native_floor = max(float(noise["max_abs"]), float(recompute_repeat["max_abs"]), 1e-12)
    within_noise_floor = bool(float(resume["max_abs"]) <= native_floor)
    return {
        "gate_status": "measured",
        "decision_agreement": decision_agreement,
        "resume_divergence": {"max_abs": resume["max_abs"], "mean_abs": resume["mean_abs"]},
        "noise_floor": {"max_abs": noise["max_abs"], "mean_abs": noise["mean_abs"]},
        "recompute_repeat": {"max_abs": recompute_repeat["max_abs"], "mean_abs": recompute_repeat["mean_abs"]},
        "within_noise_floor": within_noise_floor,
        "argmax_equal": bool(resume["argmax_equal"]),
    }


@torch.no_grad()
def bit_exact_restore(operator, task_type, givens, checkpoint_prefix, restored_state, tol: float = 1e-9) -> tuple[bool, float]:
    """Return whether restored-state logits match a full recompute at ``tol``.

    The strict path reuses the repository KV-cache gate primitive: given a restored
    ``past_key_values`` plus a feed token, compare resumed logits with a fresh
    full-prefix recompute. A lighter logits path is also supported for operators
    that capture the checkpoint logits directly. If the operator exposes neither
    model/tokenizer/cache nor logits, the gate fails closed with ``nan``.
    """
    custom_gate = getattr(operator, "bit_exact_restore", None)
    if callable(custom_gate):
        result = custom_gate(task_type, givens, checkpoint_prefix, restored_state, tol=tol)
        return bool(result[0]), float(result[1])

    state = restored_state if isinstance(restored_state, Mapping) else {"past_key_values": restored_state}
    if "is_bit_exact" in state and "max_abs_err" in state:
        return bool(state["is_bit_exact"]), float(state["max_abs_err"])

    if "logits" in state:
        fresh = operator.forward_step(task_type, givens, checkpoint_prefix if isinstance(checkpoint_prefix, Mapping) else {})
        fresh_logits = getattr(fresh, "logits", None)
        if fresh_logits is None:
            return False, float("nan")
        err = _max_abs(state["logits"], fresh_logits)
        return bool(err <= tol), err

    model, tokenizer = _model_and_tokenizer(operator)
    if model is None or tokenizer is None:
        return False, float("nan")

    cache = state.get("past_key_values", state.get("cache"))
    token_id = state.get("feed_token_id", state.get("next_token_id", state.get("token_id")))
    if cache is None or token_id is None:
        return False, float("nan")

    text = _prefix_text(operator, task_type, givens, checkpoint_prefix)
    prefix_ids = tokenizer(text, return_tensors="pt").input_ids.to(model.device)
    feed_token = _as_token_tensor(token_id, model.device)
    restored_logits, _ = _forward_logits(model, feed_token, past=copy.deepcopy(cache))
    fresh_ids = torch.cat([prefix_ids, feed_token], dim=1)
    fresh_logits, _ = _forward_logits(model, fresh_ids)
    err = _max_abs(restored_logits, fresh_logits)
    return bool(err <= tol), err
