"""Diagnostic Module 1 benchmark for K-direction failure analysis."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import torch

from register.vsa_stack import BoundSingleRegister, FactoredRegister


DEPTHS_FULL = [1, 2, 4, 8, 16, 32, 64]


def _make_generator(seed: int, device: str) -> torch.Generator:
    if str(device).startswith("cuda"):
        return torch.Generator(device=device).manual_seed(seed)
    return torch.Generator().manual_seed(seed)


def _cleanup_batch(query: torch.Tensor, codebook: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    query_norm = query / query.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    codebook_norm = codebook / codebook.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    scores = query_norm @ codebook_norm.T
    top2 = torch.topk(scores, k=min(2, codebook.shape[0]), dim=-1)
    if codebook.shape[0] == 1:
        margin = torch.ones_like(top2.values[..., 0])
    else:
        margin = top2.values[..., 0] - top2.values[..., 1]
    return top2.indices[..., 0], margin


def _sample_batch(K_var: int, K_val: int, depth: int, batch_size: int, seed: int, device: str) -> tuple[torch.Tensor, torch.Tensor]:
    generator = _make_generator(seed, device)
    vars_ = torch.rand(batch_size, K_var, generator=generator, device=device).argsort(dim=-1)[:, :depth]
    vals = torch.randint(0, K_val, (batch_size, depth), generator=generator, device=device)
    return vars_, vals


def _run_bound_single(D: int, K_var: int, K_val: int, depth: int, seed: int, trials: int, batch_size: int, device: str) -> dict[str, float]:
    register = BoundSingleRegister(D, K_var, K_val, depth, seed, device)
    joint_acc = []
    var_acc = []
    val_acc = []
    margins = []
    for start in range(0, trials, batch_size):
        current = min(batch_size, trials - start)
        vars_, vals = _sample_batch(K_var, K_val, depth, current, seed * 1000003 + depth * 997 + start, device)
        pair_indices = vars_ * K_val + vals
        h = torch.zeros(current, D, device=device)
        for level in range(depth):
            h = h + register.keys.roll(register.product_codebook[pair_indices[:, level]], level)
        pred_pairs = []
        level_margins = []
        for level in range(depth):
            query = register.keys.unroll(h, level)
            pred_pair, margin = _cleanup_batch(query, register.product_codebook)
            pred_pairs.append(register.pair_ids[pred_pair])
            level_margins.append(margin)
        pred = torch.stack(pred_pairs, dim=1)
        margin_tensor = torch.stack(level_margins, dim=1)
        var_correct = (pred[..., 0] == vars_).float()
        val_correct = (pred[..., 1] == vals).float()
        joint_correct = (var_correct * val_correct)
        joint_acc.extend(joint_correct.mean(dim=-1).detach().cpu().tolist())
        var_acc.extend(var_correct.mean(dim=-1).detach().cpu().tolist())
        val_acc.extend(val_correct.mean(dim=-1).detach().cpu().tolist())
        margins.extend(margin_tensor.mean(dim=-1).detach().cpu().tolist())
    return {"joint_accuracy": mean(joint_acc), "var_accuracy": mean(var_acc), "val_accuracy": mean(val_acc), "mean_margin": mean(margins)}


def _run_factored(D: int, K_var: int, K_val: int, depth: int, seed: int, trials: int, batch_size: int, device: str) -> dict[str, float]:
    register = FactoredRegister(D, K_var, K_val, depth, seed, device)
    joint_acc = []
    var_acc = []
    val_acc = []
    var_margins = []
    val_margins = []
    for start in range(0, trials, batch_size):
        current = min(batch_size, trials - start)
        vars_, vals = _sample_batch(K_var, K_val, depth, current, seed * 1000003 + depth * 997 + start, device)
        h_var = torch.zeros(current, D // 2, device=device)
        h_val = torch.zeros(current, D // 2, device=device)
        for level in range(depth):
            h_var = h_var + register.var_keys.roll(register.var_codebook[vars_[:, level]], level)
            h_val = h_val + register.val_keys.roll(register.val_codebook[vals[:, level]], level)
        pred_vars = []
        pred_vals = []
        v_margins = []
        x_margins = []
        for level in range(depth):
            pred_var, var_margin = _cleanup_batch(register.var_keys.unroll(h_var, level), register.var_codebook)
            pred_val, val_margin = _cleanup_batch(register.val_keys.unroll(h_val, level), register.val_codebook)
            pred_vars.append(pred_var)
            pred_vals.append(pred_val)
            v_margins.append(var_margin)
            x_margins.append(val_margin)
        pred_var_tensor = torch.stack(pred_vars, dim=1)
        pred_val_tensor = torch.stack(pred_vals, dim=1)
        var_correct = (pred_var_tensor == vars_).float()
        val_correct = (pred_val_tensor == vals).float()
        joint_correct = var_correct * val_correct
        joint_acc.extend(joint_correct.mean(dim=-1).detach().cpu().tolist())
        var_acc.extend(var_correct.mean(dim=-1).detach().cpu().tolist())
        val_acc.extend(val_correct.mean(dim=-1).detach().cpu().tolist())
        var_margins.extend(torch.stack(v_margins, dim=1).mean(dim=-1).detach().cpu().tolist())
        val_margins.extend(torch.stack(x_margins, dim=1).mean(dim=-1).detach().cpu().tolist())
    return {"joint_accuracy": mean(joint_acc), "var_accuracy": mean(var_acc), "val_accuracy": mean(val_acc), "var_margin": mean(var_margins), "val_margin": mean(val_margins), "mean_margin": min(mean(var_margins), mean(val_margins))}


def _frontier(curve: list[dict[str, Any]], metric: str, threshold: float = 0.95) -> int:
    passing = [row["depth"] for row in curve if row[metric] >= threshold]
    return max(passing) if passing else 0


def _direction(summary: list[dict[str, Any]], variant: str, metric: str, D: int, K_val: int = 2) -> dict[str, Any]:
    rows = sorted([row for row in summary if row["variant"] == variant and row["D"] == D and row["K_val"] == K_val], key=lambda row: row["K_var"])
    frontiers = [row[f"frontier_{metric}_095"] for row in rows]
    signs = []
    for left, right in zip(frontiers, frontiers[1:]):
        delta = right - left
        signs.append(0 if delta == 0 else (1 if delta > 0 else -1))
    return {"variant": variant, "metric": metric, "D": D, "K_val": K_val, "K_vars": [row["K_var"] for row in rows], "frontiers": frontiers, "signs": signs}


def run(output_dir: str = "results/module1_capacity_diagnostic", mode: str = "quick", device: str = "auto", batch_size: int = 8192, trials: int = 4096, shard_index: int = 0, num_shards: int = 1) -> dict[str, Any]:
    if device == "auto":
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    variants = ["bound_single", "factored"]
    Ds = [256] if mode == "quick" else [256, 512, 1024]
    K_vars = [9, 20, 60, 81, 256, 729]
    K_vals = [2]
    seeds = [42] if mode == "quick" else [42, 137, 256]
    depths = [1, 2, 4, 8, 16] if mode == "quick" else DEPTHS_FULL
    groups = []
    for variant in variants:
        for D in Ds:
            for K_var in K_vars:
                for K_val in K_vals:
                    for seed in seeds:
                        groups.append({"variant": variant, "D": D, "K_var": K_var, "K_val": K_val, "seed": seed})
    selected = [(index, group) for index, group in enumerate(groups) if index % num_shards == shard_index]
    rows = []
    for local_index, (global_index, group) in enumerate(selected, start=1):
        print(json.dumps({"event": "diagnostic_group_start", "mode": mode, "device": device, "shard_index": shard_index, "num_shards": num_shards, "local_group": local_index, "selected_groups": len(selected), "global_group": global_index + 1, "total_groups": len(groups), **group}), flush=True)
        valid_depths = [depth for depth in depths if depth <= group["K_var"]]
        for depth in valid_depths:
            runner = _run_bound_single if group["variant"] == "bound_single" else _run_factored
            result = runner(group["D"], group["K_var"], group["K_val"], depth, group["seed"], trials if mode == "full" else min(trials, 1024), batch_size, device)
            rows.append({**group, "depth": depth, **result})
        print(json.dumps({"event": "diagnostic_group_done", "shard_index": shard_index, "local_group": local_index, "rows_so_far": len(rows)}), flush=True)
    summary = []
    for key in sorted({(row["variant"], row["D"], row["K_var"], row["K_val"]) for row in rows}):
        variant, D, K_var, K_val = key
        subset = [row for row in rows if (row["variant"], row["D"], row["K_var"], row["K_val"]) == key]
        curve = []
        for depth in sorted({row["depth"] for row in subset}):
            depth_rows = [row for row in subset if row["depth"] == depth]
            curve.append({
                "depth": depth,
                "joint_accuracy": mean(row["joint_accuracy"] for row in depth_rows),
                "var_accuracy": mean(row["var_accuracy"] for row in depth_rows),
                "val_accuracy": mean(row["val_accuracy"] for row in depth_rows),
                "std_joint_accuracy": pstdev(row["joint_accuracy"] for row in depth_rows),
                "mean_margin": mean(row["mean_margin"] for row in depth_rows),
            })
        summary.append({
            "variant": variant,
            "D": D,
            "K_var": K_var,
            "K_val": K_val,
            "frontier_joint_095": _frontier(curve, "joint_accuracy"),
            "frontier_var_095": _frontier(curve, "var_accuracy"),
            "frontier_val_095": _frontier(curve, "val_accuracy"),
            "curve": curve,
        })
    high_d = max(Ds)
    directions = []
    for variant in variants:
        for metric in ["joint", "var", "val"]:
            directions.append(_direction(summary, variant, metric, high_d, K_val=2))
    has_positive = any(any(sign > 0 for sign in item["signs"]) for item in directions)
    decision = "k_direction_negative" if not has_positive else "k_direction_open_or_inverted"
    payload = {"module": "module1_capacity_diagnostic", "mode": mode, "device": device, "batch_size": batch_size, "trials": trials if mode == "full" else min(trials, 1024), "shard_index": shard_index, "num_shards": num_shards, "rows": rows, "summary": summary, "directions": directions, "decision": decision, "open": decision != "k_direction_negative"}
    result_path = Path(output_dir) / "results.json"
    curves_path = Path(output_dir) / "curves.json"
    result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    curves_path.write_text(json.dumps({"summary": summary, "directions": directions, "decision": decision, "open": payload["open"]}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"results": str(result_path), "curves": str(curves_path), "decision": decision, "open": payload["open"], "n_rows": len(rows), "n_summary": len(summary)}, indent=2), flush=True)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Module 1 K-direction diagnostic benchmark.")
    parser.add_argument("--output-dir", default="results/module1_capacity_diagnostic")
    parser.add_argument("--mode", choices=["quick", "full"], default="quick")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--trials", type=int, default=4096)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    args = parser.parse_args()
    run(args.output_dir, args.mode, args.device, args.batch_size, args.trials, args.shard_index, args.num_shards)