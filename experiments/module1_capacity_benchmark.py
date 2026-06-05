"""Task-free Module 1 capacity benchmark for K-direction tests."""

from __future__ import annotations

import argparse
import json
import math
import os
from statistics import mean, pstdev
from typing import Any

import torch

from analysis.capacity_theory import d_star_factored, d_star_product, fit_constant_factored, linear_fit_r2
from register.vsa_stack import BoundSingleRegister, FactoredRegister


def _depth_grid(D: int, K_var: int, K_val: int, variant: str, mode: str) -> list[int]:
    prediction = d_star_product(D, K_var * K_val) if variant == "bound_single" else d_star_factored(D, K_var, K_val, c=2.0)
    ceiling = min(K_var, max(1, int(math.ceil(1.5 * prediction))))
    if mode == "quick":
        candidates = {1, max(1, ceiling // 3), max(1, (2 * ceiling) // 3), ceiling}
    else:
        candidates = {1, max(1, ceiling // 4), max(1, ceiling // 2), max(1, (3 * ceiling) // 4), ceiling}
    return sorted(candidates)


def _build_register(variant: str, D: int, K_var: int, K_val: int, max_depth: int, seed: int, device: str):
    if variant == "bound_single":
        return BoundSingleRegister(D, K_var, K_val, max_depth, seed, device)
    if variant == "factored":
        return FactoredRegister(D, K_var, K_val, max_depth, seed, device)
    raise ValueError(f"unknown register variant: {variant}")


def _make_generator(seed: int, device: str) -> torch.Generator:
    if str(device).startswith("cuda"):
        return torch.Generator(device=device).manual_seed(seed)
    return torch.Generator().manual_seed(seed)


def _sample_stack(K_var: int, K_val: int, depth: int, seed: int, device: str) -> tuple[torch.Tensor, torch.Tensor]:
    generator = _make_generator(seed, device)
    vars_ = torch.rand(K_var, generator=generator, device=device).argsort()[:depth]
    vals = torch.randint(0, K_val, (depth,), generator=generator, device=device)
    return vars_, vals


def _sample_stack_batch(K_var: int, K_val: int, depth: int, batch_size: int, seed: int, device: str) -> tuple[torch.Tensor, torch.Tensor]:
    generator = _make_generator(seed, device)
    vars_ = torch.rand(batch_size, K_var, generator=generator, device=device).argsort(dim=-1)[:, :depth]
    vals = torch.randint(0, K_val, (batch_size, depth), generator=generator, device=device)
    return vars_, vals


def _decode_accuracy(register, vars_: torch.Tensor, vals: torch.Tensor, depth: int) -> dict[str, float]:
    predictions, margins, _h = register.decode(depth)
    targets = torch.stack([vars_, vals], dim=-1)
    correct = (predictions == targets).all(dim=-1).float()
    return {
        "decode_accuracy": float(correct.mean().item()),
        "mean_cleanup_margin": float(margins.mean().item()) if margins.numel() else 0.0,
        "min_cleanup_margin": float(margins.min().item()) if margins.numel() else 0.0,
    }


def _run_one(variant: str, D: int, K_var: int, K_val: int, depth: int, seed: int, n_trials: int, device: str) -> dict[str, Any]:
    accuracies = []
    margins = []
    min_margins = []
    for trial in range(n_trials):
        register = _build_register(variant, D, K_var, K_val, depth, seed * 100000 + trial, device)
        vars_, vals = _sample_stack(K_var, K_val, depth, seed * 1000003 + depth * 1009 + trial, device)
        for level, (var, val) in enumerate(zip(vars_.tolist(), vals.tolist())):
            register.push(level, int(var), int(val))
        result = _decode_accuracy(register, vars_, vals, depth)
        accuracies.append(result["decode_accuracy"])
        margins.append(result["mean_cleanup_margin"])
        min_margins.append(result["min_cleanup_margin"])
    return {
        "variant": variant,
        "D": D,
        "K_var": K_var,
        "K_val": K_val,
        "K_product": K_var * K_val,
        "depth": depth,
        "seed": seed,
        "decode_accuracy": mean(accuracies),
        "mean_cleanup_margin": mean(margins),
        "min_cleanup_margin": mean(min_margins),
    }


def _run_one_batched(variant: str, D: int, K_var: int, K_val: int, depth: int, seed: int, n_trials: int, device: str, batch_size: int) -> dict[str, Any]:
    register = _build_register(variant, D, K_var, K_val, depth, seed * 100000 + depth, device)
    accuracies = []
    margins = []
    min_margins = []
    for start in range(0, n_trials, batch_size):
        current_batch = min(batch_size, n_trials - start)
        vars_, vals = _sample_stack_batch(K_var, K_val, depth, current_batch, seed * 1000003 + depth * 1009 + start, device)
        if variant == "bound_single":
            pair_indices = vars_ * K_val + vals
            h = torch.zeros(current_batch, D, device=device)
            for level in range(depth):
                h = h + register.keys.roll(register.product_codebook[pair_indices[:, level]], level)
            predictions = []
            batch_margins = []
            for level in range(depth):
                query = register.keys.unroll(h, level)
                pred_pair, margin = _cleanup_batch(query, register.product_codebook)
                predictions.append(register.pair_ids[pred_pair])
                batch_margins.append(margin)
            pred = torch.stack(predictions, dim=1)
            margin_tensor = torch.stack(batch_margins, dim=1)
        else:
            h_var = torch.zeros(current_batch, D // 2, device=device)
            h_val = torch.zeros(current_batch, D // 2, device=device)
            for level in range(depth):
                h_var = h_var + register.var_keys.roll(register.var_codebook[vars_[:, level]], level)
                h_val = h_val + register.val_keys.roll(register.val_codebook[vals[:, level]], level)
            predictions = []
            batch_margins = []
            for level in range(depth):
                var_query = register.var_keys.unroll(h_var, level)
                val_query = register.val_keys.unroll(h_val, level)
                pred_var, var_margin = _cleanup_batch(var_query, register.var_codebook)
                pred_val, val_margin = _cleanup_batch(val_query, register.val_codebook)
                predictions.append(torch.stack([pred_var, pred_val], dim=-1))
                batch_margins.append(torch.minimum(var_margin, val_margin))
            pred = torch.stack(predictions, dim=1)
            margin_tensor = torch.stack(batch_margins, dim=1)
        target = torch.stack([vars_, vals], dim=-1)
        correct = (pred == target).all(dim=-1).float()
        per_trial = correct.mean(dim=-1)
        accuracies.extend(per_trial.detach().cpu().tolist())
        margins.extend(margin_tensor.mean(dim=-1).detach().cpu().tolist())
        min_margins.extend(margin_tensor.min(dim=-1).values.detach().cpu().tolist())
    return {
        "variant": variant,
        "D": D,
        "K_var": K_var,
        "K_val": K_val,
        "K_product": K_var * K_val,
        "depth": depth,
        "seed": seed,
        "decode_accuracy": mean(accuracies),
        "mean_cleanup_margin": mean(margins),
        "min_cleanup_margin": mean(min_margins),
    }


def _cleanup_batch(query: torch.Tensor, codebook: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    query_norm = query / query.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    codebook_norm = codebook / codebook.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    scores = query_norm @ codebook_norm.T
    top2 = torch.topk(scores, k=min(2, codebook.shape[0]), dim=-1)
    pred = top2.indices[..., 0]
    if codebook.shape[0] == 1:
        margin = torch.ones_like(top2.values[..., 0])
    else:
        margin = top2.values[..., 0] - top2.values[..., 1]
    return pred, margin


def _frontier(rows: list[dict[str, Any]], threshold: float = 0.95) -> int:
    passing = [row["depth"] for row in rows if row["mean_decode_accuracy"] >= threshold]
    return max(passing) if passing else 0


def _summaries(rows: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    summaries = []
    keys = sorted({(row["variant"], row["D"], row["K_var"], row["K_val"]) for row in rows})
    for variant, D, K_var, K_val in keys:
        subset = [row for row in rows if (row["variant"], row["D"], row["K_var"], row["K_val"]) == (variant, D, K_var, K_val)]
        curve = []
        for depth in sorted({row["depth"] for row in subset}):
            depth_rows = [row for row in subset if row["depth"] == depth]
            curve.append({
                "depth": depth,
                "mean_decode_accuracy": mean(row["decode_accuracy"] for row in depth_rows),
                "std_decode_accuracy": pstdev(row["decode_accuracy"] for row in depth_rows),
                "mean_cleanup_margin": mean(row["mean_cleanup_margin"] for row in depth_rows),
            })
        frontier = _frontier(curve, threshold)
        summaries.append({
            "variant": variant,
            "D": D,
            "K_var": K_var,
            "K_val": K_val,
            "K_product": K_var * K_val,
            "frontier_decode_095": frontier,
            "predicted_product": d_star_product(D, K_var * K_val),
            "predicted_factored_c2": d_star_factored(D, K_var, K_val, c=2.0),
            "curve": curve,
        })
    return summaries


def _k_direction(summaries: list[dict[str, Any]], variant: str, D: int, K_val: int = 2) -> dict[str, Any]:
    rows = sorted([row for row in summaries if row["variant"] == variant and row["D"] == D and row["K_val"] == K_val], key=lambda row: row["K_var"])
    signs = []
    for left, right in zip(rows, rows[1:]):
        delta = right["frontier_decode_095"] - left["frontier_decode_095"]
        signs.append(0 if delta == 0 else (1 if delta > 0 else -1))
    return {"variant": variant, "D": D, "K_val": K_val, "K_vars": [row["K_var"] for row in rows], "frontiers": [row["frontier_decode_095"] for row in rows], "signs": signs}


def _group_specs(variants: list[str], Ds: list[int], k_sweep: list[tuple[int, int]], seeds: list[int], mode: str) -> list[dict[str, Any]]:
    specs = []
    for variant in variants:
        for D in Ds:
            for K_var, K_val in k_sweep:
                depths = _depth_grid(D, K_var, K_val, variant, mode)
                for seed in seeds:
                    specs.append({"variant": variant, "D": D, "K_var": K_var, "K_val": K_val, "seed": seed, "depths": depths})
    return specs


def run(output_dir: str = "results/module1_capacity_benchmark", mode: str = "quick", device: str = "auto", n_trials: int = 32, shard_index: int = 0, num_shards: int = 1, batch_size: int = 8192) -> dict[str, Any]:
    if device == "auto":
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    if shard_index < 0 or shard_index >= num_shards:
        raise ValueError("shard_index must be in [0, num_shards)")
    os.makedirs(output_dir, exist_ok=True)
    variants = ["bound_single", "factored"]
    Ds = [64, 128, 256] if mode == "quick" else [64, 128, 256, 512, 1024]
    seeds = [42] if mode == "quick" else [42, 137, 256]
    k_sweep = [(K_var, 2) for K_var in [9, 20, 60, 81, 256, 729]] + [(81, K_val) for K_val in [3, 5, 9]] + [(20, 3), (81, 9)]
    k_sweep = sorted(set(k_sweep))
    rows: list[dict[str, Any]] = []
    specs = _group_specs(variants, Ds, k_sweep, seeds, mode)
    selected_specs = [(index, spec) for index, spec in enumerate(specs) if index % num_shards == shard_index]
    for local_group, (global_index, spec) in enumerate(selected_specs, start=1):
        print(json.dumps({"event": "capacity_group_start", "mode": mode, "device": device, "shard_index": shard_index, "num_shards": num_shards, "local_group": local_group, "selected_groups": len(selected_specs), "global_group": global_index + 1, "total_groups": len(specs), **spec}), flush=True)
        for depth in spec["depths"]:
            rows.append(_run_one_batched(spec["variant"], spec["D"], spec["K_var"], spec["K_val"], depth, spec["seed"], n_trials if mode == "full" else min(n_trials, 16), device, batch_size))
        print(json.dumps({"event": "capacity_group_done", "shard_index": shard_index, "local_group": local_group, "selected_groups": len(selected_specs), "global_group": global_index + 1, "rows_so_far": len(rows)}), flush=True)
    summaries = _summaries(rows, threshold=0.95)
    high_d = max(Ds)
    factored_rows = [row for row in summaries if row["variant"] == "factored" and row["D"] == high_d and row["frontier_decode_095"] > 0]
    calibration_source = max(factored_rows, key=lambda row: row["frontier_decode_095"]) if factored_rows else None
    calibrated_c = fit_constant_factored(calibration_source["D"], calibration_source["K_var"], calibration_source["K_val"], calibration_source["frontier_decode_095"]) if calibration_source else None
    linearity = {}
    for variant in variants:
        for K_var, K_val in [(20, 3), (81, 9)]:
            points = sorted([row for row in summaries if row["variant"] == variant and row["K_var"] == K_var and row["K_val"] == K_val], key=lambda row: row["D"])
            linearity[f"{variant}_K{K_var}x{K_val}"] = linear_fit_r2([row["D"] for row in points], [row["frontier_decode_095"] for row in points])
    k_direction = [_k_direction(summaries, variant, D=max(Ds), K_val=2) for variant in variants]
    decision = "open"
    if all(all(sign <= 0 for sign in item["signs"]) for item in k_direction if item["signs"]):
        decision = "theory_direction_holds"
    elif any(any(sign > 0 for sign in item["signs"]) for item in k_direction if item["signs"]):
        decision = "k_inversion_or_nonmonotonic_open"
    open_issue = decision != "theory_direction_holds"
    payload = {
        "module": "module1_capacity_benchmark",
        "mode": mode,
        "device": device,
        "threshold": 0.95,
        "variants": variants,
        "Ds": Ds,
        "seeds": seeds,
        "n_trials": n_trials if mode == "full" else min(n_trials, 16),
        "batch_size": batch_size,
        "shard_index": shard_index,
        "num_shards": num_shards,
        "selected_groups": len(selected_specs),
        "total_groups": len(specs),
        "rows": rows,
        "summary": summaries,
        "theory": {"calibrated_c": calibrated_c, "calibration_source": calibration_source, "linearity": linearity, "k_direction": k_direction, "decision": decision, "open": open_issue},
    }
    results_path = os.path.join(output_dir, "results.json")
    curves_path = os.path.join(output_dir, "curves.json")
    with open(results_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    with open(curves_path, "w", encoding="utf-8") as handle:
        json.dump({"summary": summaries, "theory": payload["theory"]}, handle, indent=2)
    print(json.dumps({"results": results_path, "curves": curves_path, "decision": decision, "n_rows": len(rows), "n_summary": len(summaries)}, indent=2), flush=True)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run task-free Module 1 capacity benchmark.")
    parser.add_argument("--output-dir", default="results/module1_capacity_benchmark")
    parser.add_argument("--mode", choices=["quick", "full"], default="quick")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--n-trials", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    args = parser.parse_args()
    run(args.output_dir, args.mode, args.device, args.n_trials, args.shard_index, args.num_shards, args.batch_size)