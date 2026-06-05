"""Diagnose whether the GRU baseline is a fair bounded-capacity limit or recency collapse."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import torch

from register.gru_stack import GRUStack, sample_batch


def _linear_fit(xs: list[float], ys: list[float]) -> dict[str, float | bool]:
    x_bar = mean(xs)
    y_bar = mean(ys)
    ss_xx = sum((x - x_bar) ** 2 for x in xs)
    if math.isclose(ss_xx, 0.0):
        return {"slope": 0.0, "intercept": y_bar, "r2": 0.0, "slope_statistically_positive": False}
    slope = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys)) / ss_xx
    intercept = y_bar - slope * x_bar
    fitted = [intercept + slope * x for x in xs]
    ss_res = sum((y - y_hat) ** 2 for y, y_hat in zip(ys, fitted))
    ss_tot = sum((y - y_bar) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if not math.isclose(ss_tot, 0.0) else 0.0
    if len(xs) > 2 and ss_res > 0:
        stderr = math.sqrt((ss_res / (len(xs) - 2)) / ss_xx)
        t_value = slope / stderr if stderr > 0 else float("inf")
    else:
        stderr = 0.0
        t_value = float("inf") if slope > 0 else 0.0
    return {"slope": slope, "intercept": intercept, "r2": r2, "slope_stderr": stderr, "slope_t": t_value, "slope_statistically_positive": bool(slope > 0 and t_value > 2.0)}


def _capacity_vs_d(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = sorted({(row["K_var"], row["K_val"], row["replacement"]) for row in summary})
    out = []
    for K_var, K_val, replacement in groups:
        rows = sorted([row for row in summary if (row["K_var"], row["K_val"], row["replacement"]) == (K_var, K_val, replacement)], key=lambda row: row["D"])
        xs = [float(row["D"]) for row in rows]
        ys = [float(row["mean_frontier_joint_095"]) for row in rows]
        fit = _linear_fit(xs, ys)
        out.append({"K_var": K_var, "K_val": K_val, "replacement": replacement, "Ds": xs, "capacities": ys, **fit})
    return out


def _load_checkpoint_model(checkpoint_path: str, device: str) -> GRUStack:
    checkpoint = torch.load(checkpoint_path, map_location=device)
    config = dict(checkpoint["config"])
    config.setdefault("cell_type", "gru")
    config.setdefault("decoder_type", "linear")
    config.setdefault("decoder_layers", 2)
    replacement = config.pop("replacement", "without_replacement")
    model = GRUStack(**config, seed=0, device=device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    model.replacement = replacement
    return model


def _seed_from_result(result: dict[str, Any], result_path: Path) -> int:
    if "seed" in result:
        return int(result["seed"])
    match = re.search(r"_seed(\d+)", str(result_path))
    return int(match.group(1)) if match else 0


@torch.no_grad()
def _shallow_sanity(input_dir: str, device: str, batch_size: int, batches: int) -> list[dict[str, Any]]:
    rows = []
    for result_path in sorted(Path(input_dir).glob("shard_*/cell_*/results.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result["D"] != 1024:
            continue
        seed = _seed_from_result(result, result_path)
        model = _load_checkpoint_model(result["checkpoint"], device)
        depth_metrics = []
        for depth in [1, 2, 3]:
            batch_metrics = []
            for batch in range(batches):
                vars_, vals = sample_batch(result["K_var"], result["K_val"], depth, batch_size, seed * 100003 + depth * 1009 + batch, device, result["replacement"])
                batch_metrics.append(model.accuracy(vars_, vals))
            depth_metrics.append({
                "depth": depth,
                "joint_accuracy": mean(row["joint_accuracy"] for row in batch_metrics),
                "var_accuracy": mean(row["var_accuracy"] for row in batch_metrics),
                "val_accuracy": mean(row["val_accuracy"] for row in batch_metrics),
            })
        rows.append({
            "result_path": str(result_path),
            "checkpoint": result["checkpoint"],
            "D": result["D"],
            "K_var": result["K_var"],
            "K_val": result["K_val"],
            "replacement": result["replacement"],
            "seed": seed,
            "frontier_joint_095": result["frontier_joint_095"],
            "depth_metrics": depth_metrics,
            "depth2_passes_095": next(row["joint_accuracy"] for row in depth_metrics if row["depth"] == 2) >= 0.95,
            "depth3_passes_095": next(row["joint_accuracy"] for row in depth_metrics if row["depth"] == 3) >= 0.95,
        })
    return rows


def diagnose(input_dir: str = "results/gru_stack_grid_full", output_dir: str = "results/gru_degeneracy_diagnostic", device: str = "cuda:0", batch_size: int = 1024, batches: int = 2) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    grid = json.loads((Path(input_dir) / "results.json").read_text(encoding="utf-8"))
    capacity_fits = _capacity_vs_d(grid["summary"])
    shallow_rows = _shallow_sanity(input_dir, device, batch_size, batches)
    flat_groups = [row for row in capacity_fits if abs(row["slope"]) < 0.002 or not row["slope_statistically_positive"]]
    depth2_fail_rate = mean([not row["depth2_passes_095"] for row in shallow_rows]) if shallow_rows else 1.0
    depth3_fail_rate = mean([not row["depth3_passes_095"] for row in shallow_rows]) if shallow_rows else 1.0
    mean_d1024_frontier = mean(row["frontier_joint_095"] for row in shallow_rows) if shallow_rows else 0.0
    if len(flat_groups) == len(capacity_fits) and depth3_fail_rate > 0.5:
        verdict = "degenerate_recency"
    elif depth2_fail_rate > 0.25 or depth3_fail_rate > 0.25:
        verdict = "undertrained"
    else:
        verdict = "genuine_limit_candidate"
    payload = {
        "module": "module1_gru_degeneracy_diagnostic",
        "input_dir": input_dir,
        "device": device,
        "capacity_vs_D": capacity_fits,
        "shallow_sanity_D1024": shallow_rows,
        "summary": {
            "n_capacity_groups": len(capacity_fits),
            "n_flat_or_not_positive_groups": len(flat_groups),
            "depth2_fail_rate": depth2_fail_rate,
            "depth3_fail_rate": depth3_fail_rate,
            "mean_D1024_frontier_joint_095": mean_d1024_frontier,
            "std_D1024_frontier_joint_095": pstdev([row["frontier_joint_095"] for row in shallow_rows]) if len(shallow_rows) > 1 else 0.0,
        },
        "verdict": verdict,
        "proceed_to_task_b": verdict in {"degenerate_recency", "undertrained"},
    }
    (root / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnose GRU recency collapse or undertraining.")
    parser.add_argument("--input-dir", default="results/gru_stack_grid_full")
    parser.add_argument("--output-dir", default="results/gru_degeneracy_diagnostic")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--batches", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.input_dir, args.output_dir, args.device, args.batch_size, args.batches), indent=2, sort_keys=True))
