"""GRU register negative baseline; not exactly reversible."""

from __future__ import annotations

import torch


class GRURegister(torch.nn.Module):
    def __init__(self, dim: int, hidden_dim: int = 2560):
        super().__init__()
        self.dim = dim
        self.hidden_dim = hidden_dim
        self.push_cell = torch.nn.GRUCell(hidden_dim, dim)
        self.pop_cell = torch.nn.GRUCell(hidden_dim, dim)
        self.readout = torch.nn.Linear(dim, hidden_dim)

    def init_state(self, batch_size: int, device: torch.device) -> torch.Tensor:
        return torch.zeros(batch_size, self.dim, device=device)

    def push(self, h: torch.Tensor, branch_encoding: torch.Tensor, depth: int) -> torch.Tensor:
        return self.push_cell(branch_encoding, h)

    def pop(self, h: torch.Tensor, branch_encoding: torch.Tensor, depth: int) -> torch.Tensor:
        return self.pop_cell(branch_encoding, h)

    def read(self, h: torch.Tensor) -> torch.Tensor:
        return self.readout(h)
