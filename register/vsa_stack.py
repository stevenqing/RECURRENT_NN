"""Operator-free VSA stack primitives for Module 1 capacity probes."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

import torch


def predicted_d_star(D: int, K: int) -> float:
    return D / (2.0 * math.log(K))


def rand_vec(n: int, generator: Optional[torch.Generator] = None, device: str | torch.device = "cpu") -> torch.Tensor:
    return torch.randn(n, generator=generator).to(device) / math.sqrt(n)


def bind(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    n = a.shape[-1]
    return torch.fft.irfft(torch.fft.rfft(a, n=n) * torch.fft.rfft(b, n=n), n=n)


def involution(a: torch.Tensor) -> torch.Tensor:
    if a.shape[-1] <= 1:
        return a.clone()
    return torch.cat([a[..., :1], torch.flip(a[..., 1:], dims=[-1])], dim=-1)


def unbind(c: torch.Tensor, a: torch.Tensor) -> torch.Tensor:
    return bind(c, involution(a))


def cleanup(query: torch.Tensor, codebook: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    query_norm = query / query.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    codebook_norm = codebook / codebook.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    scores = query_norm @ codebook_norm.T
    top2 = torch.topk(scores, k=min(2, codebook.shape[0]), dim=-1)
    prediction = top2.indices[..., 0]
    if codebook.shape[0] == 1:
        margin = torch.ones_like(top2.values[..., 0])
    else:
        margin = top2.values[..., 0] - top2.values[..., 1]
    return prediction, margin


def make_permutation_powers(n: int, max_depth: int, seed: int, device: str | torch.device = "cpu") -> tuple[torch.Tensor, torch.Tensor]:
    generator = torch.Generator().manual_seed(seed)
    perm = torch.randperm(n, generator=generator)
    powers = [torch.arange(n)]
    for _ in range(max_depth):
        powers.append(powers[-1][perm])
    pow_index = torch.stack(powers).to(device)
    inv_index = torch.empty_like(pow_index)
    base = torch.arange(n, device=device)
    for level in range(max_depth + 1):
        inv_index[level, pow_index[level]] = base
    return pow_index, inv_index


class PermutationKeys:
    def __init__(self, n: int, max_depth: int, seed: int, device: str | torch.device = "cpu"):
        self.n = n
        self.max_depth = max_depth
        self.device = torch.device(device)
        self.pow_index, self.inv_index = make_permutation_powers(n, max_depth, seed, self.device)

    def roll(self, x: torch.Tensor, level: int) -> torch.Tensor:
        return x[..., self.pow_index[level]]

    def unroll(self, x: torch.Tensor, level: int) -> torch.Tensor:
        return x[..., self.inv_index[level]]


class BoundSingleRegister:
    def __init__(self, D: int, K_var: int, K_val: int, max_depth: int, seed: int, device: str | torch.device = "cpu"):
        self.D = D
        self.K_var = K_var
        self.K_val = K_val
        self.max_depth = max_depth
        self.device = torch.device(device)
        generator = torch.Generator().manual_seed(seed)
        self.var_codebook = torch.stack([rand_vec(D, generator) for _ in range(K_var)]).to(self.device)
        self.val_codebook = torch.stack([rand_vec(D, generator) for _ in range(K_val)]).to(self.device)
        pairs = []
        pair_ids = []
        for var in range(K_var):
            for val in range(K_val):
                pairs.append(bind(self.var_codebook[var], self.val_codebook[val]))
                pair_ids.append((var, val))
        self.product_codebook = torch.stack(pairs)
        self.pair_ids = torch.tensor(pair_ids, dtype=torch.long, device=self.device)
        self.keys = PermutationKeys(D, max_depth, seed + 7919, self.device)
        self.h = torch.zeros(D, device=self.device)

    def reset(self) -> None:
        self.h.zero_()

    def item(self, var: int, val: int) -> torch.Tensor:
        return bind(self.var_codebook[var], self.val_codebook[val])

    def push(self, level: int, var: int, val: int) -> None:
        self.h = self.h + self.keys.roll(self.item(var, val), level)

    def decode_level(self, level: int) -> tuple[int, int, float]:
        query = self.keys.unroll(self.h, level)
        pair_index, margin = cleanup(query, self.product_codebook)
        var, val = self.pair_ids[int(pair_index.item())].tolist()
        return int(var), int(val), float(margin.item())

    def pop(self, level: int) -> tuple[int, int, float]:
        var, val, margin = self.decode_level(level)
        self.h = self.h - self.keys.roll(self.item(var, val), level)
        return var, val, margin

    def decode(self, depth: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        predictions = []
        margins = []
        for level in range(depth):
            var, val, margin = self.decode_level(level)
            predictions.append((var, val))
            margins.append(margin)
        return torch.tensor(predictions, device=self.device), torch.tensor(margins, device=self.device), self.h


class FactoredRegister:
    def __init__(self, D: int, K_var: int, K_val: int, max_depth: int, seed: int, device: str | torch.device = "cpu"):
        if D % 2 != 0:
            raise ValueError("FactoredRegister requires even total D")
        self.D = D
        self.m = D // 2
        self.K_var = K_var
        self.K_val = K_val
        self.max_depth = max_depth
        self.device = torch.device(device)
        generator = torch.Generator().manual_seed(seed)
        self.var_codebook = torch.stack([rand_vec(self.m, generator) for _ in range(K_var)]).to(self.device)
        self.val_codebook = torch.stack([rand_vec(self.m, generator) for _ in range(K_val)]).to(self.device)
        self.var_keys = PermutationKeys(self.m, max_depth, seed + 104729, self.device)
        self.val_keys = PermutationKeys(self.m, max_depth, seed + 130363, self.device)
        self.h_var = torch.zeros(self.m, device=self.device)
        self.h_val = torch.zeros(self.m, device=self.device)

    def reset(self) -> None:
        self.h_var.zero_()
        self.h_val.zero_()

    @property
    def h(self) -> torch.Tensor:
        return torch.cat([self.h_var, self.h_val])

    def push(self, level: int, var: int, val: int) -> None:
        self.h_var = self.h_var + self.var_keys.roll(self.var_codebook[var], level)
        self.h_val = self.h_val + self.val_keys.roll(self.val_codebook[val], level)

    def decode_level(self, level: int) -> tuple[int, int, float]:
        var_query = self.var_keys.unroll(self.h_var, level)
        val_query = self.val_keys.unroll(self.h_val, level)
        var, var_margin = cleanup(var_query, self.var_codebook)
        val, val_margin = cleanup(val_query, self.val_codebook)
        return int(var.item()), int(val.item()), float(torch.minimum(var_margin, val_margin).item())

    def pop(self, level: int) -> tuple[int, int, float]:
        var, val, margin = self.decode_level(level)
        self.h_var = self.h_var - self.var_keys.roll(self.var_codebook[var], level)
        self.h_val = self.h_val - self.val_keys.roll(self.val_codebook[val], level)
        return var, val, margin

    def decode(self, depth: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        predictions = []
        margins = []
        for level in range(depth):
            var, val, margin = self.decode_level(level)
            predictions.append((var, val))
            margins.append(margin)
        return torch.tensor(predictions, device=self.device), torch.tensor(margins, device=self.device), self.h


@dataclass
class DecodeResult:
    accuracy: float
    mean_margin: float
    min_margin: float


class RotationVSAStack:
    def __init__(self, D: int, K: int, max_depth: int, seed: int, device: str | torch.device = "cpu"):
        generator = torch.Generator().manual_seed(seed)
        self.D = D
        self.K = K
        self.max_depth = max_depth
        self.device = torch.device(device)
        self.codebook = self._unit(torch.randn(K, D, generator=generator)).to(self.device)
        self.level_keys = self._unit(torch.randn(max_depth, D, generator=generator)).to(self.device)

    @staticmethod
    def _unit(x: torch.Tensor) -> torch.Tensor:
        return x / x.norm(dim=-1, keepdim=True).clamp_min(1e-12)

    def encode(self, symbols: torch.Tensor) -> torch.Tensor:
        symbols = symbols.to(self.device)
        h = torch.zeros(self.D, device=self.device)
        for level, symbol in enumerate(symbols.tolist()):
            h = h + self.level_keys[level] * self.codebook[int(symbol)]
        return h

    def decode(self, h: torch.Tensor, depth: int) -> tuple[torch.Tensor, torch.Tensor]:
        predictions = []
        margins = []
        for level in range(depth):
            probe = h * self.level_keys[level]
            scores = self.codebook @ probe
            top2 = torch.topk(scores, k=2)
            predictions.append(int(top2.indices[0].item()))
            margins.append(float((top2.values[0] - top2.values[1]).item()))
        return torch.tensor(predictions, dtype=torch.long), torch.tensor(margins, dtype=torch.float32)


class TapeStack:
    def encode(self, symbols: torch.Tensor) -> torch.Tensor:
        return symbols.clone()

    def decode(self, h: torch.Tensor, depth: int) -> tuple[torch.Tensor, torch.Tensor]:
        return h[:depth].clone(), torch.ones(depth)


class GRUProxyStack(torch.nn.Module):
    """Small trained bounded-state negative baseline for capacity probing."""

    def __init__(self, D: int, K: int, seed: int, device: str | torch.device = "cpu"):
        super().__init__()
        torch.manual_seed(seed)
        self.D = D
        self.K = K
        self.device = torch.device(device)
        embed_dim = min(D, 128)
        pos_dim = min(D, 128)
        self.embedding = torch.nn.Embedding(K, embed_dim)
        self.cell = torch.nn.GRUCell(embed_dim, D)
        self.decoder = torch.nn.Linear(D, K)
        self.position_embedding = torch.nn.Embedding(512, pos_dim)
        self.sequence_decoder = torch.nn.Linear(D + pos_dim, K)
        self.to(self.device)

    def encode_batch(self, symbols: torch.Tensor) -> torch.Tensor:
        symbols = symbols.to(self.device)
        h = torch.zeros(symbols.shape[0], self.D, device=self.device)
        for level in range(symbols.shape[1]):
            h = self.cell(self.embedding(symbols[:, level]), h)
        return h

    def train_probe(self, depth: int, steps: int = 80, batch_size: int = 64) -> None:
        optimizer = torch.optim.AdamW(self.parameters(), lr=2e-3)
        for _ in range(steps):
            symbols = torch.randint(0, self.K, (batch_size, depth), device=self.device)
            h = self.encode_batch(symbols)
            positions = torch.arange(depth, device=self.device)
            pos = self.position_embedding(positions).unsqueeze(0).expand(batch_size, -1, -1)
            h_expanded = h.unsqueeze(1).expand(-1, depth, -1)
            logits = self.sequence_decoder(torch.cat([h_expanded, pos], dim=-1))
            loss = torch.nn.functional.cross_entropy(logits.reshape(-1, self.K), symbols.reshape(-1))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    @torch.no_grad()
    def decode_last_accuracy(self, depth: int, n_trials: int = 256) -> float:
        symbols = torch.randint(0, self.K, (n_trials, depth), device=self.device)
        h = self.encode_batch(symbols)
        positions = torch.arange(depth, device=self.device)
        pos = self.position_embedding(positions).unsqueeze(0).expand(n_trials, -1, -1)
        h_expanded = h.unsqueeze(1).expand(-1, depth, -1)
        predictions = self.sequence_decoder(torch.cat([h_expanded, pos], dim=-1)).argmax(dim=-1)
        return float((predictions == symbols).float().mean().item())


def decode_accuracy(predictions: torch.Tensor, targets: torch.Tensor, margins: torch.Tensor) -> DecodeResult:
    if targets.numel() == 0:
        return DecodeResult(0.0, 0.0, 0.0)
    correct = (predictions == targets).float()
    return DecodeResult(float(correct.mean().item()), float(margins.mean().item()), float(margins.min().item()))