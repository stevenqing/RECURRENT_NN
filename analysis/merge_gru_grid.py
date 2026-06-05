"""Merge tuned GRU stack grid cell outputs and compare to structured capacity."""

from __future__ import annotations

import argparse
import json
import math
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
            "curves_by_seed": {str(cell.get("seed", index)): cell.get("curve", []) for index, cell in enumerate(subset)},
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


def _linear_fit(xs: list[float], ys: list[float]) -> dict[str, float | bool]:
    x_bar = mean(xs)
    y_bar = mean(ys)
    ss_xx = sum((x - x_bar) ** 2 for x in xs)
    if math.isclose(ss_xx, 0.0):
        return {"slope": 0.0, "intercept": y_bar, "r2": 0.0, "slope_positive": False}
    slope = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys)) / ss_xx
    intercept = y_bar - slope * x_bar
    fitted = [intercept + slope * x for x in xs]
    ss_res = sum((y - y_hat) ** 2 for y, y_hat in zip(ys, fitted))
    ss_tot = sum((y - y_bar) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if not math.isclose(ss_tot, 0.0) else 0.0
    return {"slope": slope, "intercept": intercept, "r2": r2, "slope_positive": slope > 0.002}


def _capacity_vs_d(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    keys = sorted({(row["K_var"], row["K_val"], row["replacement"]) for row in summary})
    for K_var, K_val, replacement in keys:
        rows = sorted([row for row in summary if (row["K_var"], row["K_val"], row["replacement"]) == (K_var, K_val, replacement)], key=lambda row: row["D"])
        xs = [float(row["D"]) for row in rows]
        ys = [float(row["mean_frontier_joint_095"]) for row in rows]
        out.append({"K_var": K_var, "K_val": K_val, "replacement": replacement, "Ds": xs, "capacities": ys, **_linear_fit(xs, ys)})
    return out


def _training_sufficiency(cells: list[dict[str, Any]], eval_depth_required: int) -> dict[str, Any]:
    checks = []
    for cell in cells:
        train_depth = int(cell.get("train_max_depth", cell.get("max_depth", 0)))
        eval_depth = int(cell.get("eval_max_depth", cell.get("max_depth", 0)))
        steps = int(cell.get("steps_requested", 0))
        patience = int(cell.get("patience_requested", 0))
        sufficient = steps >= 5000 and patience >= 20 and train_depth >= eval_depth and train_depth >= eval_depth_required and cell.get("bounded_state_only") is True
        checks.append({"D": cell["D"], "K_var": cell["K_var"], "K_val": cell["K_val"], "replacement": cell["replacement"], "seed": cell.get("seed"), "train_max_depth": train_depth, "eval_max_depth": eval_depth, "steps_requested": steps, "patience_requested": patience, "bounded_state_only": cell.get("bounded_state_only") is True, "sufficient": sufficient})
    return {"eval_depth_required": eval_depth_required, "all_training_sufficient": all(row["sufficient"] for row in checks), "min_steps_requested": min((row["steps_requested"] for row in checks), default=0), "min_patience_requested": min((row["patience_requested"] for row in checks), default=0), "min_train_max_depth": min((row["train_max_depth"] for row in checks), default=0), "checks": checks}


def _shallow_sanity(summary: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for row in summary:
        if row["D"] != 1024:
            continue
        depth2 = []
        depth3 = []
        for curve in row.get("curves_by_seed", {}).values():
            by_depth = {point["depth"]: point for point in curve}
            if 2 in by_depth:
                depth2.append(by_depth[2]["joint_accuracy"])
            if 3 in by_depth:
                depth3.append(by_depth[3]["joint_accuracy"])
        rows.append({"K_var": row["K_var"], "K_val": row["K_val"], "replacement": row["replacement"], "depth2_joint_accuracy": mean(depth2) if depth2 else None, "depth3_joint_accuracy": mean(depth3) if depth3 else None})
    depth2_values = [row["depth2_joint_accuracy"] for row in rows if row["depth2_joint_accuracy"] is not None]
    depth3_values = [row["depth3_joint_accuracy"] for row in rows if row["depth3_joint_accuracy"] is not None]
    return {"rows": rows, "min_depth2_joint_accuracy": min(depth2_values) if depth2_values else None, "min_depth3_joint_accuracy": min(depth3_values) if depth3_values else None, "depth2_passes_095": bool(depth2_values and min(depth2_values) >= 0.95), "depth3_passes_095": bool(depth3_values and min(depth3_values) >= 0.95)}


def merge(input_dir: str = "results/gru_stack_grid_full", structured_path: str = "results/module1_capacity_perdepth_shards/results.json") -> dict[str, Any]:
    cells = _load_cells(input_dir)
    summary = _summarize(cells)
    comparisons = _compare(summary, structured_path)
    capacity_vs_d = _capacity_vs_d(summary)
    training_sufficiency = _training_sufficiency(cells, eval_depth_required=58)
    shallow_sanity = _shallow_sanity(summary)
    payload = {
        "module": "module1_gru_stack_grid",
        "input_dir": input_dir,
        "structured_path": structured_path,
        "n_cells": len(cells),
        "summary": summary,
        "comparisons": comparisons,
        "capacity_vs_D": capacity_vs_d,
        "training_sufficiency": training_sufficiency,
        "shallow_sanity_D1024": shallow_sanity,
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