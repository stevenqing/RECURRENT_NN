"""Ceiling-free per-depth Module 1 capacity benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import torch

from register.vsa_stack import BoundSingleRegister, FactoredRegister


def _make_generator(seed: int, device: str) -> torch.Generator:
    if str(device).startswith("cuda"):
        return torch.Generator(device=device).manual_seed(seed)
    return torch.Generator().manual_seed(seed)


def _cleanup_batch(query: torch.Tensor, codebook: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    query_norm = query / query.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    codebook_norm = codebook / codebook.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    scores = query_norm @ codebook_norm.T
    top2 = torch.topk(scores, k=min(2, codebook.shape[0]), dim=-1)
    pred = top2.indices[..., 0]
    margin = torch.ones_like(top2.values[..., 0]) if codebook.shape[0] == 1 else top2.values[..., 0] - top2.values[..., 1]
    return pred, margin


def _sample_batch(K_var: int, K_val: int, depth: int, batch_size: int, seed: int, device: str, replacement: str) -> tuple[torch.Tensor, torch.Tensor]:
    generator = _make_generator(seed, device)
    if replacement == "with_replacement":
        vars_ = torch.randint(0, K_var, (batch_size, depth), generator=generator, device=device)
    elif replacement == "without_replacement":
        vars_ = torch.rand(batch_size, K_var, generator=generator, device=device).argsort(dim=-1)[:, :depth]
    else:
        raise ValueError(f"unknown replacement mode: {replacement}")
    vals = torch.randint(0, K_val, (batch_size, depth), generator=generator, device=device)
    return vars_, vals


def _run_bound_single(D: int, K_var: int, K_val: int, depth: int, seed: int, trials: int, batch_size: int, device: str, replacement: str) -> dict[str, float]:
    register = BoundSingleRegister(D, K_var, K_val, depth, seed, device)
    joint_acc: list[float] = []
    var_acc: list[float] = []
    val_acc: list[float] = []
    margins: list[float] = []
    for start in range(0, trials, batch_size):
        current = min(batch_size, trials - start)
        vars_, vals = _sample_batch(K_var, K_val, depth, current, seed * 1000003 + depth * 997 + start, device, replacement)
        pair_indices = vars_ * K_val + vals
        h = torch.zeros(current, D, device=device)
        for level in range(depth):
            h = h + register.keys.roll(register.product_codebook[pair_indices[:, level]], level)
        preds = []
        level_margins = []
        for level in range(depth):
            pred_pair, margin = _cleanup_batch(register.keys.unroll(h, level), register.product_codebook)
            preds.append(register.pair_ids[pred_pair])
            level_margins.append(margin)
        pred = torch.stack(preds, dim=1)
        var_correct = (pred[..., 0] == vars_).float()
        val_correct = (pred[..., 1] == vals).float()
        joint_correct = var_correct * val_correct
        joint_acc.extend(joint_correct.mean(dim=-1).detach().cpu().tolist())
        var_acc.extend(var_correct.mean(dim=-1).detach().cpu().tolist())
        val_acc.extend(val_correct.mean(dim=-1).detach().cpu().tolist())
        margins.extend(torch.stack(level_margins, dim=1).mean(dim=-1).detach().cpu().tolist())
    return {"joint_accuracy": mean(joint_acc), "var_accuracy": mean(var_acc), "val_accuracy": mean(val_acc), "mean_margin": mean(margins)}


def _run_factored(D: int, K_var: int, K_val: int, depth: int, seed: int, trials: int, batch_size: int, device: str, replacement: str) -> dict[str, float]:
    register = FactoredRegister(D, K_var, K_val, depth, seed, device)
    joint_acc: list[float] = []
    var_acc: list[float] = []
    val_acc: list[float] = []
    margins: list[float] = []
    for start in range(0, trials, batch_size):
        current = min(batch_size, trials - start)
        vars_, vals = _sample_batch(K_var, K_val, depth, current, seed * 1000003 + depth * 997 + start, device, replacement)
        h_var = torch.zeros(current, D // 2, device=device)
        h_val = torch.zeros(current, D // 2, device=device)
        for level in range(depth):
            h_var = h_var + register.var_keys.roll(register.var_codebook[vars_[:, level]], level)
            h_val = h_val + register.val_keys.roll(register.val_codebook[vals[:, level]], level)
        pred_vars = []
        pred_vals = []
        level_margins = []
        for level in range(depth):
            pred_var, var_margin = _cleanup_batch(register.var_keys.unroll(h_var, level), register.var_codebook)
            pred_val, val_margin = _cleanup_batch(register.val_keys.unroll(h_val, level), register.val_codebook)
            pred_vars.append(pred_var)
            pred_vals.append(pred_val)
            level_margins.append(torch.minimum(var_margin, val_margin))
        pred_var_tensor = torch.stack(pred_vars, dim=1)
        pred_val_tensor = torch.stack(pred_vals, dim=1)
        var_correct = (pred_var_tensor == vars_).float()
        val_correct = (pred_val_tensor == vals).float()
        joint_correct = var_correct * val_correct
        joint_acc.extend(joint_correct.mean(dim=-1).detach().cpu().tolist())
        var_acc.extend(var_correct.mean(dim=-1).detach().cpu().tolist())
        val_acc.extend(val_correct.mean(dim=-1).detach().cpu().tolist())
        margins.extend(torch.stack(level_margins, dim=1).mean(dim=-1).detach().cpu().tolist())
    return {"joint_accuracy": mean(joint_acc), "var_accuracy": mean(var_acc), "val_accuracy": mean(val_acc), "mean_margin": mean(margins)}


def run(output_dir: str = "results/module1_capacity_perdepth", mode: str = "quick", device: str = "auto", batch_size: int = 8192, trials: int = 4096, shard_index: int = 0, num_shards: int = 1) -> dict[str, Any]:
    if device == "auto":
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    variants = ["bound_single", "factored"]
    Ds = [256] if mode == "quick" else [256, 512, 1024]
    K_vars = [60, 81] if mode == "quick" else [60, 81, 256, 729]
    K_vals = [2] if mode == "quick" else [2, 9]
    replacements = ["without_replacement", "with_replacement"]
    seeds = [42] if mode == "quick" else [42, 137, 256]
    depths = [1, 2, 4, 8, 16] if mode == "quick" else list(range(1, 59))
    groups = []
    for variant in variants:
        for replacement in replacements:
            for D in Ds:
                for K_var in K_vars:
                    for K_val in K_vals:
                        for seed in seeds:
                            groups.append({"variant": variant, "replacement": replacement, "D": D, "K_var": K_var, "K_val": K_val, "seed": seed})
    selected = [(index, group) for index, group in enumerate(groups) if index % num_shards == shard_index]
    rows = []
    for local_index, (global_index, group) in enumerate(selected, start=1):
        print(json.dumps({"event": "perdepth_group_start", "mode": mode, "device": device, "shard_index": shard_index, "num_shards": num_shards, "local_group": local_index, "selected_groups": len(selected), "global_group": global_index + 1, "total_groups": len(groups), **group}), flush=True)
        runner = _run_bound_single if group["variant"] == "bound_single" else _run_factored
        for depth in depths:
            if group["replacement"] == "without_replacement" and depth > group["K_var"]:
                continue
            result = runner(group["D"], group["K_var"], group["K_val"], depth, group["seed"], trials if mode == "full" else min(trials, 1024), batch_size, device, group["replacement"])
            rows.append({**group, "depth": depth, **result})
        print(json.dumps({"event": "perdepth_group_done", "shard_index": shard_index, "local_group": local_index, "rows_so_far": len(rows)}), flush=True)
    payload = {"module": "module1_capacity_perdepth", "mode": mode, "device": device, "batch_size": batch_size, "trials": trials if mode == "full" else min(trials, 1024), "shard_index": shard_index, "num_shards": num_shards, "rows": rows}
    result_path = out / "results.json"
    result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"results": str(result_path), "n_rows": len(rows)}, indent=2), flush=True)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ceiling-free per-depth capacity benchmark.")
    parser.add_argument("--output-dir", default="results/module1_capacity_perdepth")
    parser.add_argument("--mode", choices=["quick", "full"], default="quick")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--trials", type=int, default=4096)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    args = parser.parse_args()
    run(args.output_dir, args.mode, args.device, args.batch_size, args.trials, args.shard_index, args.num_shards)