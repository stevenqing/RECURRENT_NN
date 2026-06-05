"""Module 1: operator-free bounded reversible stack capacity probe."""

from __future__ import annotations

import argparse
import json
import math
import os
from statistics import mean, pstdev
from typing import Any

import torch

from register.vsa_stack import GRUProxyStack, RotationVSAStack, TapeStack, decode_accuracy, predicted_d_star


def _depth_grid(D: int, K: int) -> list[int]:
    ceiling = max(1, int(math.floor(predicted_d_star(D, K))))
    candidates = {1, max(1, ceiling // 4), max(1, ceiling // 2), ceiling, max(1, int(math.ceil(1.5 * ceiling)))}
    return sorted(candidates)


def _rotation_row(D: int, K: int, depth: int, seed: int, n_trials: int, device: str) -> dict[str, Any]:
    stack = RotationVSAStack(D, K, max_depth=max(depth, 1), seed=seed, device=device)
    accuracies = []
    margins = []
    for trial in range(n_trials):
        generator = torch.Generator().manual_seed(seed * 100000 + depth * 1000 + trial)
        symbols = torch.randint(0, K, (depth,), generator=generator)
        h = stack.encode(symbols)
        predictions, level_margins = stack.decode(h, depth)
        result = decode_accuracy(predictions, symbols, level_margins)
        accuracies.append(result.accuracy)
        margins.append(result.mean_margin)
    return {"method": "rotation_vsa", "D": D, "K": K, "depth": depth, "seed": seed, "decode_accuracy": mean(accuracies), "mean_cleanup_margin": mean(margins)}


def _tape_row(D: int, K: int, depth: int, seed: int) -> dict[str, Any]:
    return {"method": "tape", "D": D, "K": K, "depth": depth, "seed": seed, "decode_accuracy": 1.0, "mean_cleanup_margin": 1.0}


def _gru_proxy_rows(D: int, K: int, depths: list[int], seed: int, steps: int, n_trials: int, device: str) -> list[dict[str, Any]]:
    rows = []
    for depth in depths:
        model = GRUProxyStack(D, K, seed=seed + depth, device=device)
        model.train_probe(depth=depth, steps=steps, batch_size=64)
        accuracy = model.decode_last_accuracy(depth=depth, n_trials=n_trials)
        rows.append({"method": "gru_proxy_sequence", "D": D, "K": K, "depth": depth, "seed": seed, "decode_accuracy": accuracy, "mean_cleanup_margin": None})
    return rows


def _frontier(rows: list[dict[str, Any]], threshold: float = 0.95) -> int:
    passing = [row["depth"] for row in rows if row.get("decode_accuracy", row.get("mean_decode_accuracy", 0.0)) >= threshold]
    return max(passing) if passing else 0


def run(output_dir: str = "results/module1_stack_capacity", n_trials: int = 64, mode: str = "full", device: str = "auto") -> dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)
    if device == "auto":
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    if mode == "quick":
        Ds = [64, 128, 256]
        Ks = [60, 729]
        seeds = [42]
        n_trials = min(n_trials, 16)
        gru_steps = 8
        gru_eval_trials = 64
    else:
        Ds = [64, 128, 256, 512, 1024]
        Ks = [60, 729]
        seeds = [42, 137, 256]
        gru_steps = 60
        gru_eval_trials = 256
    rows: list[dict[str, Any]] = []
    total_groups = len(Ks) * len(Ds) * len(seeds)
    group_index = 0
    for K in Ks:
        for D in Ds:
            depths = _depth_grid(D, K)
            for seed in seeds:
                group_index += 1
                print(json.dumps({"event": "module1_group_start", "mode": mode, "device": device, "group": group_index, "total_groups": total_groups, "D": D, "K": K, "seed": seed, "depths": depths}), flush=True)
                for depth in depths:
                    rows.append(_rotation_row(D, K, depth, seed, n_trials, device))
                    rows.append(_tape_row(D, K, depth, seed))
                rows.extend(_gru_proxy_rows(D, K, depths, seed, gru_steps, gru_eval_trials, device))
                print(json.dumps({"event": "module1_group_done", "mode": mode, "group": group_index, "total_groups": total_groups, "D": D, "K": K, "seed": seed, "rows_so_far": len(rows)}), flush=True)

    summaries = []
    for method in sorted({row["method"] for row in rows}):
        for K in Ks:
            for D in Ds:
                subset = [row for row in rows if row["method"] == method and row["K"] == K and row["D"] == D]
                by_depth = []
                for depth in sorted({row["depth"] for row in subset}):
                    depth_rows = [row for row in subset if row["depth"] == depth]
                    by_depth.append({"depth": depth, "mean_decode_accuracy": mean(row["decode_accuracy"] for row in depth_rows), "std_decode_accuracy": pstdev(row["decode_accuracy"] for row in depth_rows)})
                summaries.append({
                    "method": method,
                    "D": D,
                    "K": K,
                    "predicted_d_star": predicted_d_star(D, K),
                    "frontier_decode_095": _frontier(by_depth),
                    "depth_curve": by_depth,
                })

    payload = {
        "module": "module1_bounded_reversible_stack",
        "claim": "rotation_vsa_frontier_tracks_D_over_2lnK_against_gru_proxy_and_tape",
        "threshold": 0.95,
        "mode": mode,
        "device": device,
        "n_trials": n_trials,
        "seeds": seeds,
        "rows": rows,
        "summary": summaries,
        "notes": "GRU is a lightweight trained full-sequence decoder from the bounded final state, not an exact inverse and not fully hyperparameter-tuned.",
    }
    results_path = os.path.join(output_dir, "results.json")
    with open(results_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(json.dumps({"results": results_path, "n_rows": len(rows), "n_summary": len(summaries)}, indent=2))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Module 1 stack capacity probe.")
    parser.add_argument("--output-dir", default="results/module1_stack_capacity")
    parser.add_argument("--n-trials", type=int, default=64)
    parser.add_argument("--mode", choices=["quick", "full"], default="full")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    run(args.output_dir, args.n_trials, args.mode, args.device)