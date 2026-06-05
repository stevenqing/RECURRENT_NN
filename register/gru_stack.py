"""Tuned GRU stack baseline for Module 1 capacity closeout."""

from __future__ import annotations

import math
from typing import Literal

import torch

from register.vsa_stack import bind, rand_vec


class GRUStack(torch.nn.Module):
    def __init__(
        self,
        D: int,
        K_var: int,
        K_val: int,
        max_depth: int,
        seed: int,
        num_layers: int = 1,
        learned_init: bool = False,
        device: str | torch.device = "cpu",
        cell_type: Literal["gru", "lstm"] = "gru",
        decoder_type: Literal["linear", "mlp", "replay"] = "linear",
        decoder_layers: int = 2,
    ):
        super().__init__()
        if num_layers < 1:
            raise ValueError("num_layers must be >= 1")
        if cell_type not in {"gru", "lstm"}:
            raise ValueError(f"unknown cell_type: {cell_type}")
        if decoder_type not in {"linear", "mlp", "replay"}:
            raise ValueError(f"unknown decoder_type: {decoder_type}")
        if cell_type == "lstm" and D % 2 != 0:
            raise ValueError("LSTM encoder requires even D so h_T and c_T concatenate to width D")
        self.D = D
        self.K_var = K_var
        self.K_val = K_val
        self.max_depth = max_depth
        self.num_layers = num_layers
        self.learned_init = learned_init
        self.cell_type = cell_type
        self.decoder_type = decoder_type
        self.decoder_layers = decoder_layers
        self.device = torch.device(device)
        self.encoder_width = D if cell_type == "gru" else D // 2
        generator = torch.Generator().manual_seed(seed)
        self.register_buffer("var_codebook", torch.stack([rand_vec(D, generator) for _ in range(K_var)]))
        self.register_buffer("val_codebook", torch.stack([rand_vec(D, generator) for _ in range(K_val)]))
        if cell_type == "gru":
            input_sizes = [D] + [D] * (num_layers - 1)
            self.cells = torch.nn.ModuleList([torch.nn.GRUCell(input_size, D) for input_size in input_sizes])
        else:
            input_sizes = [D] + [self.encoder_width] * (num_layers - 1)
            self.cells = torch.nn.ModuleList([torch.nn.LSTMCell(input_size, self.encoder_width) for input_size in input_sizes])
        self.position_embedding = torch.nn.Embedding(max_depth + 1, min(D, 128))
        pos_dim = min(D, 128)
        feature_dim = D + pos_dim
        if decoder_type == "mlp":
            layers = []
            for layer in range(max(1, decoder_layers)):
                layers.extend([
                    torch.nn.Linear(feature_dim if layer == 0 else D, D),
                    torch.nn.GELU(),
                    torch.nn.LayerNorm(D),
                ])
            self.decoder_mlp = torch.nn.Sequential(*layers)
            head_dim = D
        else:
            self.decoder_mlp = None
            head_dim = feature_dim if decoder_type == "linear" else D
        if decoder_type == "replay":
            self.replay_init = torch.nn.Linear(D, D)
            self.replay_cell = torch.nn.GRUCell(pos_dim, D)
        self.var_head = torch.nn.Linear(head_dim, K_var)
        self.val_head = torch.nn.Linear(head_dim, K_val)
        if learned_init:
            self.initial_state = torch.nn.Parameter(torch.zeros(num_layers, self.encoder_width))
            if cell_type == "lstm":
                self.initial_cell_state = torch.nn.Parameter(torch.zeros(num_layers, self.encoder_width))
        else:
            self.register_buffer("initial_state", torch.zeros(num_layers, self.encoder_width))
            if cell_type == "lstm":
                self.register_buffer("initial_cell_state", torch.zeros(num_layers, self.encoder_width))
        self.to(self.device)

    def item_embeddings(self, vars_: torch.Tensor, vals: torch.Tensor) -> torch.Tensor:
        var_items = self.var_codebook[vars_.to(self.device)]
        val_items = self.val_codebook[vals.to(self.device)]
        return bind(var_items, val_items)

    def encode(self, vars_: torch.Tensor, vals: torch.Tensor) -> torch.Tensor:
        items = self.item_embeddings(vars_, vals)
        batch_size = items.shape[0]
        states = self.initial_state.unsqueeze(0).expand(batch_size, -1, -1).contiguous()
        if self.cell_type == "lstm":
            cell_states = self.initial_cell_state.unsqueeze(0).expand(batch_size, -1, -1).contiguous()
        for level in range(items.shape[1]):
            x = items[:, level]
            next_states = []
            if self.cell_type == "gru":
                for layer, cell in enumerate(self.cells):
                    h = cell(x, states[:, layer])
                    next_states.append(h)
                    x = h
            else:
                next_cell_states = []
                for layer, cell in enumerate(self.cells):
                    h, c = cell(x, (states[:, layer], cell_states[:, layer]))
                    next_states.append(h)
                    next_cell_states.append(c)
                    x = h
                cell_states = torch.stack(next_cell_states, dim=1)
            states = torch.stack(next_states, dim=1)
        if self.cell_type == "lstm":
            return torch.cat([states[:, -1], cell_states[:, -1]], dim=-1)
        return states[:, -1]

    def decode_logits(self, hidden: torch.Tensor, depth: int) -> tuple[torch.Tensor, torch.Tensor]:
        positions = torch.arange(depth, device=hidden.device)
        pos = self.position_embedding(positions).unsqueeze(0).expand(hidden.shape[0], -1, -1)
        if self.decoder_type == "replay":
            decoder_state = self.replay_init(hidden)
            replay_features = []
            reverse_positions = torch.arange(depth - 1, -1, -1, device=hidden.device)
            for position in reverse_positions:
                pos_step = self.position_embedding(position).unsqueeze(0).expand(hidden.shape[0], -1)
                decoder_state = self.replay_cell(pos_step, decoder_state)
                replay_features.append(decoder_state)
            features = torch.stack(list(reversed(replay_features)), dim=1)
        else:
            hidden_expanded = hidden.unsqueeze(1).expand(-1, depth, -1)
            features = torch.cat([hidden_expanded, pos], dim=-1)
            if self.decoder_mlp is not None:
                features = self.decoder_mlp(features)
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