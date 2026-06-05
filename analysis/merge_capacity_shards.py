"""Merge Module 1 capacity benchmark shard outputs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from analysis.capacity_theory import d_star_factored, d_star_product, fit_constant_factored, linear_fit_r2


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
        summaries.append({
            "variant": variant,
            "D": D,
            "K_var": K_var,
            "K_val": K_val,
            "K_product": K_var * K_val,
            "frontier_decode_095": _frontier(curve, threshold),
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


def merge_shards(input_dir: str = "results/module1_capacity_benchmark_full_shards", output_dir: str | None = None) -> dict[str, Any]:
    root = Path(input_dir)
    if output_dir is None:
        output_dir = input_dir
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    shard_paths = sorted(root.glob("shard_*/results.json"))
    if not shard_paths:
        raise FileNotFoundError(f"no shard result files under {input_dir}")
    shard_payloads = []
    rows: list[dict[str, Any]] = []
    for path in shard_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        shard_payloads.append({
            "path": str(path),
            "shard_index": payload.get("shard_index"),
            "num_shards": payload.get("num_shards"),
            "selected_groups": payload.get("selected_groups"),
            "n_rows": len(payload.get("rows", [])),
        })
        rows.extend(payload["rows"])
    first = json.loads(shard_paths[0].read_text(encoding="utf-8"))
    summaries = _summaries(rows, threshold=0.95)
    high_d = max(first["Ds"])
    factored_rows = [row for row in summaries if row["variant"] == "factored" and row["D"] == high_d and row["frontier_decode_095"] > 0]
    calibration_source = max(factored_rows, key=lambda row: row["frontier_decode_095"]) if factored_rows else None
    calibrated_c = fit_constant_factored(calibration_source["D"], calibration_source["K_var"], calibration_source["K_val"], calibration_source["frontier_decode_095"]) if calibration_source else None
    linearity = {}
    for variant in first["variants"]:
        for K_var, K_val in [(20, 3), (81, 9)]:
            points = sorted([row for row in summaries if row["variant"] == variant and row["K_var"] == K_var and row["K_val"] == K_val], key=lambda row: row["D"])
            linearity[f"{variant}_K{K_var}x{K_val}"] = linear_fit_r2([row["D"] for row in points], [row["frontier_decode_095"] for row in points])
    k_direction = [_k_direction(summaries, variant, D=high_d, K_val=2) for variant in first["variants"]]
    decision = "open"
    if all(all(sign <= 0 for sign in item["signs"]) for item in k_direction if item["signs"]):
        decision = "theory_direction_holds"
    elif any(any(sign > 0 for sign in item["signs"]) for item in k_direction if item["signs"]):
        decision = "k_inversion_or_nonmonotonic_open"
    payload = {
        "module": "module1_capacity_benchmark",
        "mode": first["mode"],
        "device": "8x_cuda_sharded",
        "threshold": 0.95,
        "variants": first["variants"],
        "Ds": first["Ds"],
        "seeds": first["seeds"],
        "n_trials": first["n_trials"],
        "batch_size": first.get("batch_size"),
        "num_shards": len(shard_paths),
        "shards": shard_payloads,
        "rows": rows,
        "summary": summaries,
        "theory": {"calibrated_c": calibrated_c, "calibration_source": calibration_source, "linearity": linearity, "k_direction": k_direction, "decision": decision, "open": decision != "theory_direction_holds"},
    }
    results_path = out / "results.json"
    curves_path = out / "curves.json"
    results_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    curves_path.write_text(json.dumps({"summary": summaries, "theory": payload["theory"]}, indent=2) + "\n", encoding="utf-8")
    return {"results": str(results_path), "curves": str(curves_path), "decision": decision, "n_rows": len(rows), "n_summary": len(summaries), "n_shards": len(shard_paths)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge Module 1 capacity benchmark shards.")
    parser.add_argument("--input-dir", default="results/module1_capacity_benchmark_full_shards")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    print(json.dumps(merge_shards(args.input_dir, args.output_dir), indent=2, sort_keys=True))