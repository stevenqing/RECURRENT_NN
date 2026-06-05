"""Answer-free dead-end verifier with oracle/learned/noisy/disabled modes."""

from __future__ import annotations

from enum import Enum

import torch


class VerifierMode(str, Enum):
    ORACLE = "oracle"
    LEARNED = "learned"
    NOISY = "noisy"
    DISABLED = "disabled"


class VerifierHead(torch.nn.Module):
    def __init__(self, hidden_dim: int = 2560, mode: VerifierMode = VerifierMode.LEARNED, noise_std: float = 0.25):
        super().__init__()
        self.mode = mode
        self.noise_std = noise_std
        self.net = torch.nn.Sequential(
            torch.nn.Linear(hidden_dim, hidden_dim // 2),
            torch.nn.ReLU(),
            torch.nn.Linear(hidden_dim // 2, 1),
            torch.nn.Sigmoid(),
        )

    def forward(self, hidden: torch.Tensor, oracle_signal: torch.Tensor | None = None) -> torch.Tensor:
        if self.mode == VerifierMode.ORACLE:
            if oracle_signal is None:
                raise ValueError("oracle verifier mode requires oracle_signal")
            return oracle_signal
        if self.mode == VerifierMode.DISABLED:
            return torch.zeros(hidden.shape[0], 1, device=hidden.device)
        out = self.net(hidden)
        if self.mode == VerifierMode.NOISY:
            out = (out + torch.randn_like(out) * self.noise_std).clamp(0, 1)
        return out
