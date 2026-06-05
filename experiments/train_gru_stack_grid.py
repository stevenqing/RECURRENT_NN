"""Shardable tuned GRU stack training grid for Module 1 closeout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.train_gru_stack import train_one


def _cell_specs(mode: str) -> list[dict[str, Any]]:
    if mode == "quick":
        Ds = [128]
        K_vars = [60]
        K_vals = [2]
        replacements = ["without_replacement"]
        seeds = [42]
    else:
        Ds = [256, 512, 1024]
        K_vars = [60, 81, 256, 729]
        K_vals = [2, 9]
        replacements = ["without_replacement", "with_replacement"]
        seeds = [42, 137, 256]
    specs = []
    for D in Ds:
        for K_var in K_vars:
            for K_val in K_vals:
                for replacement in replacements:
                    for seed in seeds:
                        specs.append({"D": D, "K_var": K_var, "K_val": K_val, "replacement": replacement, "seed": seed})
    return specs


def run_grid(
    output_dir: str = "results/gru_stack_grid",
    mode: str = "full",
    device: str = "cuda:0",
    shard_index: int = 0,
    num_shards: int = 1,
    max_depth: int = 64,
    steps: int = 5000,
    batch_size: int = 1024,
    eval_every: int = 100,
    patience: int = 20,
    arch_grid: str = "gru:mlp:3,gru:replay:2,lstm:mlp:3",
    val_depths: str = "1,2,3,4,8,16,32,48,64",
    eval_batches: int = 1,
    final_eval_batches: int = 2,
) -> dict[str, Any]:
    if shard_index < 0 or shard_index >= num_shards:
        raise ValueError("shard_index must be in [0, num_shards)")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    all_specs = _cell_specs(mode)
    selected = [(idx, spec) for idx, spec in enumerate(all_specs) if idx % num_shards == shard_index]
    cells = []
    for local_index, (global_index, spec) in enumerate(selected, start=1):
        cell_name = f"D{spec['D']}_Kv{spec['K_var']}_Ku{spec['K_val']}_{spec['replacement']}_seed{spec['seed']}"
        cell_dir = root / f"cell_{global_index:04d}_{cell_name}"
        print(json.dumps({"event": "gru_cell_start", "mode": mode, "shard_index": shard_index, "num_shards": num_shards, "local_cell": local_index, "selected_cells": len(selected), "global_cell": global_index + 1, "total_cells": len(all_specs), **spec, "output_dir": str(cell_dir)}), flush=True)
        result = train_one(
            D=spec["D"],
            K_var=spec["K_var"],
            K_val=spec["K_val"],
            replacement=spec["replacement"],
            output_dir=str(cell_dir),
            device=device,
            max_depth=min(max_depth, spec["K_var"]),
            steps=steps if mode == "full" else min(steps, 80),
            batch_size=batch_size if mode == "full" else min(batch_size, 512),
            eval_every=eval_every,
            patience=patience,
            seed=spec["seed"],
            arch_grid=arch_grid,
            val_depths=val_depths,
            eval_batches=eval_batches,
            final_eval_batches=final_eval_batches,
        )
        result_summary = {key: value for key, value in result.items() if key not in {"trials"}}
        cells.append({"global_index": global_index, "result_path": str(cell_dir / "results.json"), **result_summary})
        print(json.dumps({"event": "gru_cell_done", "shard_index": shard_index, "local_cell": local_index, "selected_cells": len(selected), "global_cell": global_index + 1, "frontier_joint_095": result["frontier_joint_095"], "best_config": result["best_config"]}), flush=True)
    payload = {"module": "module1_gru_stack_grid", "mode": mode, "device": device, "shard_index": shard_index, "num_shards": num_shards, "selected_cells": len(selected), "total_cells": len(all_specs), "cells": cells}
    (root / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"results": str(root / "results.json"), "selected_cells": len(selected), "total_cells": len(all_specs)}, indent=2), flush=True)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run sharded tuned GRU stack training grid.")
    parser.add_argument("--output-dir", default="results/gru_stack_grid")
    parser.add_argument("--mode", choices=["quick", "full"], default="full")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--max-depth", type=int, default=64)
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--eval-every", type=int, default=100)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--arch-grid", default="gru:mlp:3,gru:replay:2,lstm:mlp:3")
    parser.add_argument("--val-depths", default="1,2,3,4,8,16,32,48,64")
    parser.add_argument("--eval-batches", type=int, default=1)
    parser.add_argument("--final-eval-batches", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(run_grid(args.output_dir, args.mode, args.device, args.shard_index, args.num_shards, args.max_depth, args.steps, args.batch_size, args.eval_every, args.patience, args.arch_grid, args.val_depths, args.eval_batches, args.final_eval_batches), indent=2, sort_keys=True))