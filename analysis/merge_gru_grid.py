"""Merge tuned GRU stack grid cell outputs and compare to structured capacity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


def _load_cells(input_dir: str) -> list[dict[str, Any]]:
    root = Path(input_dir)
    paths = sorted(root.glob("shard_*/cell_*/results.json"))
    if not paths:
        raise FileNotFoundError(f"no GRU cell results under {input_dir}")
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _summarize(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    keys = sorted({(cell["D"], cell["K_var"], cell["K_val"], cell["replacement"]) for cell in cells})
    for D, K_var, K_val, replacement in keys:
        subset = [cell for cell in cells if (cell["D"], cell["K_var"], cell["K_val"], cell["replacement"]) == (D, K_var, K_val, replacement)]
        frontiers = [cell["frontier_joint_095"] for cell in subset]
        summary.append({
            "variant": "gru_tuned",
            "D": D,
            "K_var": K_var,
            "K_val": K_val,
            "replacement": replacement,
            "n_seeds": len(subset),
            "converged": all(cell["converged"] for cell in subset),
            "selection": sorted({cell["selection"] for cell in subset}),
            "mean_frontier_joint_095": mean(frontiers),
            "std_frontier_joint_095": pstdev(frontiers),
            "frontiers_by_seed": {str(cell.get("seed", index)): cell["frontier_joint_095"] for index, cell in enumerate(subset)},
            "best_configs": [cell["best_config"] for cell in subset],
        })
    return summary


def _structured_lookup(path: str) -> dict[tuple[int, int, int, str], dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    lookup = {}
    for row in data["summary"]:
        if row["variant"] in {"bound_single", "factored"}:
            key = (row["D"], row["K_var"], row["K_val"], row["replacement"])
            existing = lookup.get(key)
            if existing is None or row["capacity_joint_095"] > existing["structured_capacity_joint_095"]:
                lookup[key] = {"structured_variant": row["variant"], "structured_capacity_joint_095": row["capacity_joint_095"]}
    return lookup


def _compare(summary: list[dict[str, Any]], structured_path: str) -> list[dict[str, Any]]:
    lookup = _structured_lookup(structured_path)
    comparisons = []
    for row in summary:
        key = (row["D"], row["K_var"], row["K_val"], row["replacement"])
        structured = lookup.get(key)
        if structured is None:
            continue
        comparisons.append({
            **{field: row[field] for field in ["D", "K_var", "K_val", "replacement"]},
            "gru_capacity_joint_095": row["mean_frontier_joint_095"],
            **structured,
            "gru_below_structured": row["mean_frontier_joint_095"] < structured["structured_capacity_joint_095"],
        })
    return comparisons


def merge(input_dir: str = "results/gru_stack_grid_full", structured_path: str = "results/module1_capacity_perdepth_shards/results.json") -> dict[str, Any]:
    cells = _load_cells(input_dir)
    summary = _summarize(cells)
    comparisons = _compare(summary, structured_path)
    payload = {
        "module": "module1_gru_stack_grid",
        "input_dir": input_dir,
        "structured_path": structured_path,
        "n_cells": len(cells),
        "summary": summary,
        "comparisons": comparisons,
        "all_converged": all(row["converged"] for row in summary),
        "all_gru_below_structured": all(row["gru_below_structured"] for row in comparisons),
    }
    root = Path(input_dir)
    results_path = root / "results.json"
    curves_path = root / "curves.json"
    results_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    curves_path.write_text(json.dumps({"summary": summary, "comparisons": comparisons}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"results": str(results_path), "curves": str(curves_path), "n_cells": len(cells), "n_summary": len(summary), "all_converged": payload["all_converged"], "all_gru_below_structured": payload["all_gru_below_structured"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge tuned GRU stack grid results.")
    parser.add_argument("--input-dir", default="results/gru_stack_grid_full")
    parser.add_argument("--structured-path", default="results/module1_capacity_perdepth_shards/results.json")
    args = parser.parse_args()
    print(json.dumps(merge(args.input_dir, args.structured_path), indent=2, sort_keys=True))