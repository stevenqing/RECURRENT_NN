"""Merge Module 1 capacity diagnostic shard outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


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


def _summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    return summary


def merge(input_dir: str = "results/module1_capacity_diagnostic_full_shards", output_dir: str | None = None) -> dict[str, Any]:
    root = Path(input_dir)
    if output_dir is None:
        output_dir = input_dir
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    shard_paths = sorted(root.glob("shard_*/results.json"))
    if not shard_paths:
        raise FileNotFoundError(f"no shard results under {input_dir}")
    rows = []
    shards = []
    for path in shard_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(payload["rows"])
        shards.append({"path": str(path), "shard_index": payload.get("shard_index"), "num_shards": payload.get("num_shards"), "n_rows": len(payload["rows"])})
    first = json.loads(shard_paths[0].read_text(encoding="utf-8"))
    summary = _summary(rows)
    high_d = max({row["D"] for row in summary})
    variants = sorted({row["variant"] for row in summary})
    directions = []
    for variant in variants:
        for metric in ["joint", "var", "val"]:
            directions.append(_direction(summary, variant, metric, high_d, K_val=2))
    has_positive = any(any(sign > 0 for sign in item["signs"]) for item in directions)
    decision = "k_direction_negative" if not has_positive else "k_direction_open_or_inverted"
    payload = {"module": "module1_capacity_diagnostic", "mode": first["mode"], "device": "8x_cuda_sharded", "batch_size": first["batch_size"], "trials": first["trials"], "num_shards": len(shard_paths), "shards": shards, "rows": rows, "summary": summary, "directions": directions, "decision": decision, "open": decision != "k_direction_negative"}
    results_path = out / "results.json"
    curves_path = out / "curves.json"
    results_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    curves_path.write_text(json.dumps({"summary": summary, "directions": directions, "decision": decision, "open": payload["open"]}, indent=2) + "\n", encoding="utf-8")
    return {"results": str(results_path), "curves": str(curves_path), "decision": decision, "open": payload["open"], "n_rows": len(rows), "n_summary": len(summary), "n_shards": len(shard_paths)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge Module 1 diagnostic shards.")
    parser.add_argument("--input-dir", default="results/module1_capacity_diagnostic_full_shards")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    print(json.dumps(merge(args.input_dir, args.output_dir), indent=2, sort_keys=True))