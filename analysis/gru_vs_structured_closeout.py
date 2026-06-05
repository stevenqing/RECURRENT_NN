"""Classify the fair bounded-GRU baseline against structured registers."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any


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


def _scaling(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = sorted({(row["K_var"], row["K_val"], row["replacement"]) for row in summary})
    out = []
    for K_var, K_val, replacement in groups:
        rows = sorted([row for row in summary if (row["K_var"], row["K_val"], row["replacement"]) == (K_var, K_val, replacement)], key=lambda row: row["D"])
        xs = [float(row["D"]) for row in rows]
        ys = [float(row["mean_frontier_joint_095"]) for row in rows]
        out.append({"K_var": K_var, "K_val": K_val, "replacement": replacement, "Ds": xs, "capacities": ys, **_linear_fit(xs, ys)})
    return out


def closeout(
    gru_path: str = "results/gru_stack_grid_fair/results.json",
    diagnostic_path: str = "results/gru_degeneracy_diagnostic/results.json",
    output_dir: str = "results/gru_vs_structured_closeout",
) -> dict[str, Any]:
    gru = json.loads(Path(gru_path).read_text(encoding="utf-8"))
    diagnostic = json.loads(Path(diagnostic_path).read_text(encoding="utf-8")) if Path(diagnostic_path).exists() else None
    scaling = _scaling(gru["summary"])
    positive_groups = [row for row in scaling if row["slope_positive"]]
    max_ratio = max((row["gru_capacity_joint_095"] / row["structured_capacity_joint_095"] for row in gru["comparisons"]), default=0.0)
    all_below = gru.get("all_gru_below_structured") is True
    training = gru.get("training_sufficiency", {})
    sufficient = training.get("all_training_sufficient") is True
    if sufficient and all_below and len(positive_groups) == len(scaling) and max_ratio < 0.5:
        classification = "CLEAN_NEGATIVE_SUBLINEAR"
        lock_headline = True
    elif sufficient and all_below and len(positive_groups) == 0 and max(row["capacities"][-1] for row in scaling) <= 2.0:
        classification = "RECENCY_COLLAPSE"
        lock_headline = True
    elif sufficient and not all_below:
        classification = "GRU_RISES"
        lock_headline = False
    else:
        classification = "NOT_READY"
        lock_headline = False
    payload = {
        "module": "module1_gru_vs_structured_closeout",
        "gru_path": gru_path,
        "diagnostic_path": diagnostic_path,
        "diagnostic_verdict": diagnostic.get("verdict") if diagnostic else None,
        "parent_sudoku_gru_reference": {"D": 128, "d_dyn_approx": 3, "note": "parent Sudoku GRU was sublinear but grew with D; fair baseline should not be flat at depth ~1 before classification"},
        "capacity_vs_D": scaling,
        "max_gru_to_structured_ratio": max_ratio,
        "all_gru_below_structured": all_below,
        "training_sufficiency": training,
        "classification": classification,
        "lock_structured_headline": lock_headline,
        "decision_rule": "Lock structured >> unstructured only for CLEAN_NEGATIVE_SUBLINEAR or strong-evidence RECENCY_COLLAPSE; under GRU_RISES reframe around scaling exponent.",
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify fair GRU vs structured outcome.")
    parser.add_argument("--gru-path", default="results/gru_stack_grid_fair/results.json")
    parser.add_argument("--diagnostic-path", default="results/gru_degeneracy_diagnostic/results.json")
    parser.add_argument("--output-dir", default="results/gru_vs_structured_closeout")
    args = parser.parse_args()
    print(json.dumps(closeout(args.gru_path, args.diagnostic_path, args.output_dir), indent=2, sort_keys=True))
