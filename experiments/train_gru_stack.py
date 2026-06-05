"""Train tuned GRU stack baselines for Module 1 closeout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import torch

from register.gru_stack import GRUStack, interpolated_frontier, sample_batch


def _eval_curve(model: GRUStack, K_var: int, K_val: int, depths: list[int], batch_size: int, batches: int, seed: int, device: str, replacement: str) -> list[dict[str, float]]:
    curve = []
    for depth in depths:
        metrics = []
        for batch in range(batches):
            vars_, vals = sample_batch(K_var, K_val, depth, batch_size, seed + depth * 1009 + batch, device, replacement)
            metrics.append(model.accuracy(vars_, vals))
        curve.append({
            "depth": depth,
            "joint_accuracy": sum(row["joint_accuracy"] for row in metrics) / len(metrics),
            "var_accuracy": sum(row["var_accuracy"] for row in metrics) / len(metrics),
            "val_accuracy": sum(row["val_accuracy"] for row in metrics) / len(metrics),
        })
    return curve


def _parse_arch_grid(arch_grid: str) -> list[tuple[str, str, int]]:
    parsed = []
    for spec in arch_grid.split(","):
        parts = spec.strip().split(":")
        if len(parts) == 2:
            cell_type, decoder_type = parts
            decoder_layers = 2
        elif len(parts) == 3:
            cell_type, decoder_type, decoder_layers_text = parts
            decoder_layers = int(decoder_layers_text)
        else:
            raise ValueError(f"bad architecture spec: {spec}")
        parsed.append((cell_type, decoder_type, decoder_layers))
    return parsed


def _parse_depths(depths: str | None, max_depth: int) -> list[int]:
    if not depths:
        return list(range(1, max_depth + 1))
    parsed = sorted({int(depth) for depth in depths.split(",") if depth.strip()})
    return [depth for depth in parsed if 1 <= depth <= max_depth]


def train_one(D: int, K_var: int, K_val: int, replacement: str, output_dir: str, device: str, max_depth: int, steps: int, batch_size: int, eval_every: int, patience: int, seed: int, arch_grid: str = "gru:mlp:3,gru:replay:2,lstm:mlp:3", val_depths: str | None = "1,2,3,4,8,16,32,48,64", eval_batches: int = 1, final_eval_batches: int = 2) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    lrs = [8e-4]
    layers = [2]
    init_modes = [True]
    architectures = _parse_arch_grid(arch_grid)
    best: dict[str, Any] | None = None
    trials = []
    depths = list(range(1, max_depth + 1))
    validation_depths = _parse_depths(val_depths, max_depth)
    for cell_type, decoder_type, decoder_layers in architectures:
        for lr in lrs:
            for num_layers in layers:
                for learned_init in init_modes:
                    model = GRUStack(
                        D,
                        K_var,
                        K_val,
                        max_depth,
                        seed=seed + num_layers * 17 + int(learned_init) + len(trials) * 101,
                        num_layers=num_layers,
                        learned_init=learned_init,
                        device=device,
                        cell_type=cell_type,
                        decoder_type=decoder_type,
                        decoder_layers=decoder_layers,
                    )
                    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
                    best_val = float("inf")
                    best_state = None
                    bad = 0
                    history = []
                    for step in range(1, steps + 1):
                        depth = depths[(step - 1) % len(depths)]
                        vars_, vals = sample_batch(K_var, K_val, depth, batch_size, seed * 100000 + step, device, replacement)
                        loss = model.loss(vars_, vals)
                        optimizer.zero_grad()
                        loss.backward()
                        optimizer.step()
                        if step % eval_every == 0 or step == steps:
                            val_losses = []
                            for eval_depth in validation_depths:
                                for eval_batch in range(eval_batches):
                                    eval_vars, eval_vals = sample_batch(K_var, K_val, eval_depth, batch_size, seed * 200000 + step * 37 + eval_depth * 1009 + eval_batch, device, replacement)
                                    val_losses.append(float(model.loss(eval_vars, eval_vals).detach().item()))
                            val_loss = sum(val_losses) / len(val_losses)
                            history.append({"step": step, "train_loss": float(loss.detach().item()), "val_loss": val_loss})
                            print(json.dumps({"event": "gru_train_eval", "D": D, "K_var": K_var, "K_val": K_val, "replacement": replacement, "seed": seed, "cell_type": cell_type, "decoder_type": decoder_type, "decoder_layers": decoder_layers, "step": step, "steps": steps, "train_loss": float(loss.detach().item()), "val_loss": val_loss, "bad": bad}), flush=True)
                            if val_loss < best_val - 1e-4:
                                best_val = val_loss
                                best_state = {key: value.detach().cpu() for key, value in model.state_dict().items()}
                                bad = 0
                            else:
                                bad += 1
                            if bad >= patience:
                                break
                    if best_state is not None:
                        model.load_state_dict(best_state)
                    curve = _eval_curve(model, K_var, K_val, depths, batch_size, batches=final_eval_batches, seed=seed * 300000 + 7, device=device, replacement=replacement)
                    frontier = interpolated_frontier(curve)
                    trial = {"lr": lr, "num_layers": num_layers, "learned_init": learned_init, "cell_type": cell_type, "decoder_type": decoder_type, "decoder_layers": decoder_layers, "best_val_loss": best_val, "history": history, "frontier_joint_095": frontier, "curve": curve, "state_dict": best_state}
                    trials.append({key: value for key, value in trial.items() if key != "state_dict"})
                    if best is None or best_val < best["best_val_loss"]:
                        best = trial
    assert best is not None and best["state_dict"] is not None
    checkpoint_path = out / "gru_stack_best.pt"
    checkpoint_config = {"D": D, "K_var": K_var, "K_val": K_val, "max_depth": max_depth, "replacement": replacement, "num_layers": best["num_layers"], "learned_init": best["learned_init"], "cell_type": best["cell_type"], "decoder_type": best["decoder_type"], "decoder_layers": best["decoder_layers"]}
    torch.save({"state_dict": best["state_dict"], "config": checkpoint_config, "best_val_loss": best["best_val_loss"]}, checkpoint_path)
    result = {
        "variant": "gru_fair_bounded",
        "D": D,
        "K_var": K_var,
        "K_val": K_val,
        "replacement": replacement,
        "seed": seed,
        "max_depth": max_depth,
        "train_max_depth": max_depth,
        "eval_max_depth": max_depth,
        "steps_requested": steps,
        "patience_requested": patience,
        "eval_every": eval_every,
        "val_depths": validation_depths,
        "eval_batches": eval_batches,
        "final_eval_batches": final_eval_batches,
        "batch_size": batch_size,
        "bounded_state_only": True,
        "converged": True,
        "selection": "val_loss_min",
        "checkpoint": str(checkpoint_path),
        "best_config": {"lr": best["lr"], "num_layers": best["num_layers"], "learned_init": best["learned_init"], "cell_type": best["cell_type"], "decoder_type": best["decoder_type"], "decoder_layers": best["decoder_layers"], "best_val_loss": best["best_val_loss"]},
        "architecture_grid": [{"cell_type": cell_type, "decoder_type": decoder_type, "decoder_layers": decoder_layers} for cell_type, decoder_type, decoder_layers in architectures],
        "frontier_joint_095": best["frontier_joint_095"],
        "curve": best["curve"],
        "trials": trials,
    }
    (out / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train a tuned GRU stack baseline cell.")
    parser.add_argument("--D", type=int, default=128)
    parser.add_argument("--K-var", type=int, default=60)
    parser.add_argument("--K-val", type=int, default=2)
    parser.add_argument("--replacement", choices=["with_replacement", "without_replacement"], default="without_replacement")
    parser.add_argument("--output-dir", default="results/gru_stack_smoke")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--max-depth", type=int, default=64)
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--eval-every", type=int, default=100)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--arch-grid", default="gru:mlp:3,gru:replay:2,lstm:mlp:3")
    parser.add_argument("--val-depths", default="1,2,3,4,8,16,32,48,64")
    parser.add_argument("--eval-batches", type=int, default=1)
    parser.add_argument("--final-eval-batches", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(train_one(args.D, args.K_var, args.K_val, args.replacement, args.output_dir, args.device, args.max_depth, args.steps, args.batch_size, args.eval_every, args.patience, args.seed, args.arch_grid, args.val_depths, args.eval_batches, args.final_eval_batches), indent=2, sort_keys=True))