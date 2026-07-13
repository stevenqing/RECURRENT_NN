"""Rotation/VSA structured reversible register."""

from __future__ import annotations

import math
import torch


def predicted_d_star(D: int, K: int) -> float:
    return D / (2.0 * math.log(K))


class StructuredRegister(torch.nn.Module):
    def __init__(self, dim: int, hidden_dim: int = 2560, max_keys: int = 1024):
        super().__init__()
        self.dim = dim
        self.hidden_dim = hidden_dim
        self.max_keys = max_keys
        permutations = []
        inverse_permutations = []
        signs = []
        base = torch.arange(dim)
        for _ in range(max_keys):
            permutation = torch.randperm(dim)
            inverse = torch.empty_like(permutation)
            inverse[permutation] = base
            sign = torch.randint(0, 2, (dim,), dtype=torch.float32).mul(2.0).sub(1.0)
            permutations.append(permutation)
            inverse_permutations.append(inverse)
            signs.append(sign)
        self.register_buffer("permutations", torch.stack(permutations))
        self.register_buffer("inverse_permutations", torch.stack(inverse_permutations))
        self.register_buffer("signs", torch.stack(signs))
        self.encoder = torch.nn.Linear(hidden_dim, dim)
        self.readout = torch.nn.Linear(dim, hidden_dim)
        self.decoder = torch.nn.Linear(dim, hidden_dim)

    def init_state(self, batch_size: int, device: torch.device) -> torch.Tensor:
        return torch.zeros(batch_size, self.dim, device=device)

    def push(self, h: torch.Tensor, branch_encoding: torch.Tensor, depth: int) -> torch.Tensor:
        key = depth % self.max_keys
        permutation = self.permutations[key].to(h.device)
        sign = self.signs[key].to(h.device)
        rotated = h[..., permutation] * sign
        return rotated + self.encoder(branch_encoding)

    def pop(self, h: torch.Tensor, branch_encoding: torch.Tensor, depth: int) -> torch.Tensor:
        key = depth % self.max_keys
        inverse = self.inverse_permutations[key].to(h.device)
        sign = self.signs[key].to(h.device)
        unencoded = h - self.encoder(branch_encoding)
        return (unencoded * sign)[..., inverse]

    def read(self, h: torch.Tensor) -> torch.Tensor:
        return self.readout(h)

    def decode_top(self, h: torch.Tensor) -> torch.Tensor:
        return self.decoder(h)
