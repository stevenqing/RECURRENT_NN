"""Supervised controller/verifier wiring baseline over cached operator features."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import torch
import torch.nn.functional as F

from controller.controller_head import ControllerHead
from controller.verifier_head import VerifierHead


def _accuracy(logits: torch.Tensor, targets: torch.Tensor, ignore_index: int | None = None) -> float:
    if ignore_index is not None:
        mask = targets != ignore_index
        if not bool(mask.any()):
            return 0.0
        logits = logits[mask]
        targets = targets[mask]
    return float((logits.argmax(dim=-1) == targets).float().mean().item())


def _subset_metrics(controller: ControllerHead, verifier: VerifierHead, hidden: torch.Tensor, register_readout: torch.Tensor, action_targets: torch.Tensor, var_targets: torch.Tensor, val_targets: torch.Tensor, dead_end_targets: torch.Tensor, index: torch.Tensor, prefix: str) -> dict[str, float]:
    if index.numel() == 0:
        return {
            f"{prefix}_action_accuracy": 0.0,
            f"{prefix}_var_accuracy": 0.0,
            f"{prefix}_val_accuracy": 0.0,
            f"{prefix}_verifier_accuracy": 0.0,
            f"{prefix}_verifier_positive_rate": 0.0,
        }
    decision = controller(hidden[index], register_readout[index])
    verifier_pred = verifier(hidden[index])
    verifier_binary = (verifier_pred >= 0.5).float()
    return {
        f"{prefix}_action_accuracy": _accuracy(decision.action_logits, action_targets[index]),
        f"{prefix}_var_accuracy": _accuracy(decision.var_logits, var_targets[index], ignore_index=-100),
        f"{prefix}_val_accuracy": _accuracy(decision.val_logits, val_targets[index], ignore_index=-100),
        f"{prefix}_verifier_accuracy": float((verifier_binary == dead_end_targets[index]).float().mean().item()),
        f"{prefix}_verifier_positive_rate": float(verifier_binary.mean().item()),
    }


def run(
    cache_path: str = "results/operator_cache/operator_cache.pt",
    output_dir: str = "results/learned_wiring",
    epochs: int = 12,
    batch_size: int = 128,
    seed: int = 42,
    holdout_seed: int = 999,
) -> dict[str, Any]:
    torch.manual_seed(seed)
    cache = torch.load(cache_path, map_location="cpu")
    hidden = cache["hidden_states"].float()
    action_targets = cache["action_targets"]
    var_targets = cache["var_targets"]
    val_targets = cache["val_targets"]
    dead_end_targets = cache["dead_end_targets"].float()
    seed_targets = cache.get("seed_targets", torch.zeros_like(action_targets))
    hidden_dim = int(hidden.shape[-1])
    controller = ControllerHead(hidden_dim=hidden_dim, max_vars=81, max_vals=10)
    verifier = VerifierHead(hidden_dim=hidden_dim)
    optimizer = torch.optim.AdamW(list(controller.parameters()) + list(verifier.parameters()), lr=2e-3, weight_decay=1e-4)
    n_examples = int(hidden.shape[0])
    register_readout = torch.zeros_like(hidden)
    train_index = torch.nonzero(seed_targets != holdout_seed, as_tuple=False).squeeze(-1)
    holdout_index = torch.nonzero(seed_targets == holdout_seed, as_tuple=False).squeeze(-1)

    for _epoch in range(epochs):
        permutation = train_index[torch.randperm(train_index.numel())]
        for start in range(0, train_index.numel(), batch_size):
            index = permutation[start:start + batch_size]
            batch_hidden = hidden[index]
            batch_register = register_readout[index]
            decision = controller(batch_hidden, batch_register)
            verifier_pred = verifier(batch_hidden)
            loss = F.cross_entropy(decision.action_logits, action_targets[index])
            loss = loss + F.cross_entropy(decision.var_logits, var_targets[index], ignore_index=-100)
            loss = loss + F.cross_entropy(decision.val_logits, val_targets[index], ignore_index=-100)
            loss = loss + F.binary_cross_entropy(verifier_pred, dead_end_targets[index])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    with torch.no_grad():
        train_metrics = _subset_metrics(controller, verifier, hidden, register_readout, action_targets, var_targets, val_targets, dead_end_targets, train_index, "train")
        holdout_metrics = _subset_metrics(controller, verifier, hidden, register_readout, action_targets, var_targets, val_targets, dead_end_targets, holdout_index, "holdout")
        metrics = {
            "evaluation_mode": "supervised_cached_operator_features",
            "feature_source": cache["metadata"]["feature_source"],
            "n_examples": n_examples,
            "n_train_examples": int(train_index.numel()),
            "n_holdout_examples": int(holdout_index.numel()),
            "holdout_seed": holdout_seed,
            "hidden_dim": hidden_dim,
            "epochs": epochs,
            **train_metrics,
            **holdout_metrics,
        }
        metrics["action_accuracy"] = metrics["train_action_accuracy"]
        metrics["var_accuracy"] = metrics["train_var_accuracy"]
        metrics["val_accuracy"] = metrics["train_val_accuracy"]
        metrics["verifier_accuracy"] = metrics["train_verifier_accuracy"]
        metrics["verifier_positive_rate"] = metrics["train_verifier_positive_rate"]

    os.makedirs(output_dir, exist_ok=True)
    model_path = os.path.join(output_dir, "heads.pt")
    results_path = os.path.join(output_dir, "results.json")
    torch.save({"controller": controller.state_dict(), "verifier": verifier.state_dict(), "metrics": metrics}, model_path)
    metrics["model"] = model_path
    with open(results_path, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2, sort_keys=True)
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train supervised controller/verifier heads over cached operator features.")
    parser.add_argument("--cache-path", default="results/operator_cache/operator_cache.pt")
    parser.add_argument("--output-dir", default="results/learned_wiring")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--holdout-seed", type=int, default=999)
    args = parser.parse_args()
    print(json.dumps(run(args.cache_path, args.output_dir, args.epochs, args.batch_size, args.seed, args.holdout_seed), indent=2, sort_keys=True))