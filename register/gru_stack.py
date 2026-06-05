"""Tuned GRU stack baseline for Module 1 capacity closeout."""

from __future__ import annotations

import math

import torch

from register.vsa_stack import bind, rand_vec


class GRUStack(torch.nn.Module):
    def __init__(self, D: int, K_var: int, K_val: int, max_depth: int, seed: int, num_layers: int = 1, learned_init: bool = False, device: str | torch.device = "cpu"):
        super().__init__()
        if num_layers < 1:
            raise ValueError("num_layers must be >= 1")
        self.D = D
        self.K_var = K_var
        self.K_val = K_val
        self.max_depth = max_depth
        self.num_layers = num_layers
        self.learned_init = learned_init
        self.device = torch.device(device)
        generator = torch.Generator().manual_seed(seed)
        self.register_buffer("var_codebook", torch.stack([rand_vec(D, generator) for _ in range(K_var)]))
        self.register_buffer("val_codebook", torch.stack([rand_vec(D, generator) for _ in range(K_val)]))
        self.cells = torch.nn.ModuleList([torch.nn.GRUCell(D, D) for _ in range(num_layers)])
        self.position_embedding = torch.nn.Embedding(max_depth + 1, min(D, 128))
        self.var_head = torch.nn.Linear(D + min(D, 128), K_var)
        self.val_head = torch.nn.Linear(D + min(D, 128), K_val)
        if learned_init:
            self.initial_state = torch.nn.Parameter(torch.zeros(num_layers, D))
        else:
            self.register_buffer("initial_state", torch.zeros(num_layers, D))
        self.to(self.device)

    def item_embeddings(self, vars_: torch.Tensor, vals: torch.Tensor) -> torch.Tensor:
        var_items = self.var_codebook[vars_.to(self.device)]
        val_items = self.val_codebook[vals.to(self.device)]
        return bind(var_items, val_items)

    def encode(self, vars_: torch.Tensor, vals: torch.Tensor) -> torch.Tensor:
        items = self.item_embeddings(vars_, vals)
        batch_size = items.shape[0]
        states = self.initial_state.unsqueeze(0).expand(batch_size, -1, -1).contiguous()
        for level in range(items.shape[1]):
            x = items[:, level]
            next_states = []
            for layer, cell in enumerate(self.cells):
                h = cell(x, states[:, layer])
                next_states.append(h)
                x = h
            states = torch.stack(next_states, dim=1)
        return states[:, -1]

    def decode_logits(self, hidden: torch.Tensor, depth: int) -> tuple[torch.Tensor, torch.Tensor]:
        positions = torch.arange(depth, device=hidden.device)
        pos = self.position_embedding(positions).unsqueeze(0).expand(hidden.shape[0], -1, -1)
        hidden_expanded = hidden.unsqueeze(1).expand(-1, depth, -1)
        features = torch.cat([hidden_expanded, pos], dim=-1)
        return self.var_head(features), self.val_head(features)

    def loss(self, vars_: torch.Tensor, vals: torch.Tensor) -> torch.Tensor:
        hidden = self.encode(vars_, vals)
        var_logits, val_logits = self.decode_logits(hidden, vars_.shape[1])
        var_loss = torch.nn.functional.cross_entropy(var_logits.reshape(-1, self.K_var), vars_.to(self.device).reshape(-1))
        val_loss = torch.nn.functional.cross_entropy(val_logits.reshape(-1, self.K_val), vals.to(self.device).reshape(-1))
        return var_loss + val_loss

    @torch.no_grad()
    def accuracy(self, vars_: torch.Tensor, vals: torch.Tensor) -> dict[str, float]:
        hidden = self.encode(vars_, vals)
        var_logits, val_logits = self.decode_logits(hidden, vars_.shape[1])
        pred_var = var_logits.argmax(dim=-1)
        pred_val = val_logits.argmax(dim=-1)
        vars_ = vars_.to(self.device)
        vals = vals.to(self.device)
        var_correct = (pred_var == vars_).float()
        val_correct = (pred_val == vals).float()
        joint = var_correct * val_correct
        return {"joint_accuracy": float(joint.mean().item()), "var_accuracy": float(var_correct.mean().item()), "val_accuracy": float(val_correct.mean().item())}


def sample_batch(K_var: int, K_val: int, depth: int, batch_size: int, seed: int, device: str, replacement: str) -> tuple[torch.Tensor, torch.Tensor]:
    generator = torch.Generator(device=device if str(device).startswith("cuda") else "cpu").manual_seed(seed)
    if replacement == "with_replacement":
        vars_ = torch.randint(0, K_var, (batch_size, depth), generator=generator, device=device)
    elif replacement == "without_replacement":
        vars_ = torch.rand(batch_size, K_var, generator=generator, device=device).argsort(dim=-1)[:, :depth]
    else:
        raise ValueError(f"unknown replacement mode: {replacement}")
    vals = torch.randint(0, K_val, (batch_size, depth), generator=generator, device=device)
    return vars_, vals


def interpolated_frontier(curve: list[dict], metric: str = "joint_accuracy", threshold: float = 0.95) -> float:
    ordered = sorted(curve, key=lambda row: row["depth"])
    if not ordered or ordered[0][metric] < threshold:
        return 0.0
    last = ordered[0]
    for row in ordered[1:]:
        if row[metric] < threshold:
            denom = last[metric] - row[metric]
            if math.isclose(denom, 0.0):
                return float(last["depth"])
            frac = (last[metric] - threshold) / denom
            return float(last["depth"] + frac * (row["depth"] - last["depth"]))
        last = row
    return float(ordered[-1]["depth"])