"""Branch encoders for live-width capacity experiments."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import torch


EncoderName = Literal["bind", "raw"]


@dataclass
class BranchRegister:
    D: int
    seed: int
    encoder: EncoderName = "bind"
    device: str | torch.device = "cpu"
    h: torch.Tensor | None = None
    value_codebook: torch.Tensor | None = None
    key_codebook: torch.Tensor | None = None


def _unit(x: torch.Tensor) -> torch.Tensor:
    return x / x.norm(dim=-1, keepdim=True).clamp_min(1e-12)


def _fit_dim(states: torch.Tensor, D: int) -> torch.Tensor:
    states = states.float()
    if states.shape[-1] == D:
        return states
    if states.shape[-1] > D:
        return states[..., :D]
    pad = torch.zeros(*states.shape[:-1], D - states.shape[-1], device=states.device, dtype=states.dtype)
    return torch.cat([states, pad], dim=-1)


def _bipolar_keys(count: int, D: int, seed: int, device: torch.device) -> torch.Tensor:
    generator = torch.Generator(device="cpu").manual_seed(seed)
    keys = torch.randint(0, 2, (count, D), generator=generator, dtype=torch.float32)
    return keys.mul(2.0).sub(1.0).to(device)


def _whiten_values(hidden_states: torch.Tensor, D: int) -> torch.Tensor:
    states = hidden_states.float()
    if states.numel() == 0:
        return torch.empty(0, D, dtype=torch.float32)
    centered = states - states.mean(dim=0, keepdim=True)
    rank = min(centered.shape[0] - 1, centered.shape[1], D)
    if rank <= 0 or float(centered.norm().item()) == 0.0:
        return _unit(_fit_dim(centered, D))
    _u, singular_values, vh = torch.linalg.svd(centered, full_matrices=False)
    keep = min(rank, int((singular_values > singular_values.max().clamp_min(1e-12) * 1e-6).sum().item()))
    keep = max(1, keep)
    basis = vh[:keep]
    projected = centered @ basis.T
    whitened = projected / singular_values[:keep].clamp_min(1e-6)
    generator = torch.Generator(device="cpu").manual_seed(7919 + 31 * int(D) + int(keep))
    dense_projection = torch.randint(0, 2, (keep, int(D)), generator=generator, dtype=torch.float32)
    dense_projection = dense_projection.mul(2.0).sub(1.0).to(whitened.device)
    dense = whitened @ dense_projection / math.sqrt(max(keep, 1))
    return _unit(dense)


def prepare_values(hidden_states: torch.Tensor, D: int, encoder: EncoderName) -> torch.Tensor:
    if encoder == "bind":
        return _whiten_values(hidden_states, D)
    if encoder == "raw":
        return _unit(_fit_dim(hidden_states, D))
    raise ValueError(f"unknown encoder: {encoder}")


def bind_branch(register: BranchRegister, key_id, hidden_state) -> torch.Tensor:
    if register.h is None or register.value_codebook is None or register.key_codebook is None:
        raise ValueError("register codebooks must be initialized before binding")
    key = register.key_codebook[int(key_id)]
    value = torch.as_tensor(hidden_state, dtype=torch.float32, device=key.device)
    register.h = register.h + key * value
    return register.h


def read_branch_bound(register: BranchRegister, key_id) -> int:
    if register.h is None or register.value_codebook is None or register.key_codebook is None:
        raise ValueError("register has not been encoded")
    probe = register.h * register.key_codebook[int(key_id)]
    scores = register.value_codebook @ probe
    return int(scores.argmax().item())


def branch_scores(register: BranchRegister, key_ids: torch.Tensor) -> torch.Tensor:
    """Return cleanup scores for a batch of bound-key queries."""
    if register.h is None or register.value_codebook is None or register.key_codebook is None:
        raise ValueError("register has not been encoded")
    indices = key_ids.to(device=register.key_codebook.device, dtype=torch.long)
    probes = register.h.unsqueeze(0) * register.key_codebook[indices]
    return probes @ register.value_codebook.T


def bundle_raw(register: BranchRegister, hidden_states) -> torch.Tensor:
    states = torch.as_tensor(hidden_states).detach().float()
    device = torch.device(register.device)
    values = prepare_values(states.to(device), int(register.D), "raw")
    register.encoder = "raw"
    register.value_codebook = values
    register.key_codebook = None
    register.h = values.sum(dim=0)
    return register.h


def encode_prepared_values(values, D: int, seed: int, device: str | torch.device = "cpu") -> BranchRegister:
    """Bind an already prepared value codebook to fresh near-orthogonal keys."""
    prepared = torch.as_tensor(values).detach().float().to(device)
    if prepared.ndim != 2 or int(prepared.shape[1]) != int(D):
        raise ValueError(f"prepared values must have shape (W, {int(D)})")
    register = BranchRegister(int(D), int(seed), encoder="bind", device=device)
    keys = _bipolar_keys(prepared.shape[0], int(D), int(seed) + 17, torch.device(device))
    register.value_codebook = prepared
    register.key_codebook = keys
    register.h = (keys * prepared).sum(dim=0)
    return register


def encode_branches(hidden_states, D: int, seed: int, encoder: EncoderName = "bind", device: str | torch.device = "cpu") -> BranchRegister:
    states = torch.as_tensor(hidden_states).detach().float().to(device)
    register = BranchRegister(int(D), int(seed), encoder=encoder, device=device)
    if encoder == "raw":
        bundle_raw(register, states)
        return register
    values = prepare_values(states, int(D), "bind").to(device)
    return encode_prepared_values(values, int(D), int(seed), device=device)


def read_branch(register: BranchRegister, index: int) -> int:
    if register.encoder == "bind":
        return read_branch_bound(register, index)
    if register.h is None or register.value_codebook is None:
        raise ValueError("register has not been encoded")
    scores = register.value_codebook @ register.h
    return int(scores.argmax().item())