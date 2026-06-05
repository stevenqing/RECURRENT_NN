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
        rotations = []
        for _ in range(max_keys):
            q, _ = torch.linalg.qr(torch.randn(dim, dim))
            rotations.append(q)
        self.register_buffer("rotations", torch.stack(rotations))
        self.encoder = torch.nn.Linear(hidden_dim, dim)
        self.readout = torch.nn.Linear(dim, hidden_dim)
        self.decoder = torch.nn.Linear(dim, hidden_dim)

    def init_state(self, batch_size: int, device: torch.device) -> torch.Tensor:
        return torch.zeros(batch_size, self.dim, device=device)

    def push(self, h: torch.Tensor, branch_encoding: torch.Tensor, depth: int) -> torch.Tensor:
        R = self.rotations[depth % self.max_keys].to(h.device)
        return h @ R.T + self.encoder(branch_encoding)

    def pop(self, h: torch.Tensor, branch_encoding: torch.Tensor, depth: int) -> torch.Tensor:
        R = self.rotations[depth % self.max_keys].to(h.device)
        return (h - self.encoder(branch_encoding)) @ R

    def read(self, h: torch.Tensor) -> torch.Tensor:
        return self.readout(h)

    def decode_top(self, h: torch.Tensor) -> torch.Tensor:
        return self.decoder(h)
