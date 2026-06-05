"""Merge sharded Module 1 capacity benchmark outputs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from analysis.capacity_theory import fit_constant_factored, linear_fit_r2
from experiments.module1_capacity_benchmark import _k_direction, _summaries


def merge_shards(shard_root: str = "results/module1_capacity_benchmark_full_shards", output_dir: str = "results/module1_capacity_benchmark_full") -> dict[str, Any]:
    shard_paths = sorted(Path(shard_root).glob("shard_*/results.json"))
    if not shard_paths:
        raise FileNotFoundError(f"no shard results found under {shard_root}")
    shard_payloads = [json.load(open(path, "r", encoding="utf-8")) for path in shard_paths]
    rows = [row for payload in shard_payloads for row in payload["rows"]]
    summaries = _summaries(rows, threshold=0.95)
    Ds = sorted({row["D"] for row in rows})
    variants = sorted({row["variant"] for row in rows})
    high_d = max(Ds)
    factored_rows = [row for row in summaries if row["variant"] == "factored" and row["D"] == high_d and row["frontier_decode_095"] > 0]
    calibration_source = max(factored_rows, key=lambda row: row["frontier_decode_095"]) if factored_rows else None
    calibrated_c = fit_constant_factored(calibration_source["D"], calibration_source["K_var"], calibration_source["K_val"], calibration_source["frontier_decode_095"]) if calibration_source else None
    linearity = {}
    for variant in variants:
        for K_var, K_val in [(20, 3), (81, 9)]:
            points = sorted([row for row in summaries if row["variant"] == variant and row["K_var"] == K_var and row["K_val"] == K_val], key=lambda row: row["D"])
            linearity[f"{variant}_K{K_var}x{K_val}"] = linear_fit_r2([row["D"] for row in points], [row["frontier_decode_095"] for row in points])
    k_direction = [_k_direction(summaries, variant, D=high_d, K_val=2) for variant in variants]
    if all(all(sign <= 0 for sign in item["signs"]) for item in k_direction if item["signs"]):
        decision = "theory_direction_holds"
    elif any(any(sign > 0 for sign in item["signs"]) for item in k_direction if item["signs"]):
        decision = "k_inversion_or_nonmonotonic_open"
    else:
        decision = "open"
    payload = {
        "module": "module1_capacity_benchmark",
        "mode": shard_payloads[0]["mode"],
        "device": "multi_gpu_sharded",
        "threshold": 0.95,
        "variants": variants,
        "Ds": Ds,
        "seeds": sorted({seed for payload in shard_payloads for seed in payload["seeds"]}),
        "n_trials": shard_payloads[0]["n_trials"],
        "num_shards": len(shard_paths),
        "shard_root": shard_root,
        "rows": rows,
        "summary": summaries,
        "theory": {"calibrated_c": calibrated_c, "calibration_source": calibration_source, "linearity": linearity, "k_direction": k_direction, "decision": decision, "open": decision != "theory_direction_holds"},
    }
    os.makedirs(output_dir, exist_ok=True)
    results_path = os.path.join(output_dir, "results.json")
    curves_path = os.path.join(output_dir, "curves.json")
    with open(results_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    with open(curves_path, "w", encoding="utf-8") as handle:
        json.dump({"summary": summaries, "theory": payload["theory"]}, handle, indent=2)
    return {"results": results_path, "curves": curves_path, "decision": decision, "n_rows": len(rows), "n_summary": len(summaries), "n_shards": len(shard_paths)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge sharded Module 1 capacity benchmark outputs.")
    parser.add_argument("--shard-root", default="results/module1_capacity_benchmark_full_shards")
    parser.add_argument("--output-dir", default="results/module1_capacity_benchmark_full")
    args = parser.parse_args()
    print(json.dumps(merge_shards(args.shard_root, args.output_dir), indent=2, sort_keys=True))