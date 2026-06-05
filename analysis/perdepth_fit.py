"""Fit capacity-law candidates on ceiling-free per-depth diagnostic curves."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from analysis.capacity_theory import capacity_features, fit_through_origin


def _ceiling_free_rows(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in summary:
        if row["K_var"] < 60:
            continue
        rows.append(row)
    return rows


def _fit_variant(rows: list[dict[str, Any]], variant: str, metric: str = "frontier_joint_095") -> dict[str, Any]:
    subset = [row for row in rows if row["variant"] == variant and row[metric] > 0]
    candidates = {"D_over_ln_Kvar": [], "D_over_ln_product": [], "halfD_over_ln_max_factor": []}
    y = []
    for row in subset:
        features = capacity_features(row["D"], row["K_var"], row["K_val"])
        for name, value in features.items():
            candidates[name].append(value)
        y.append(row[metric])
    fits = {name: fit_through_origin(values, y) for name, values in candidates.items()}
    best = max(fits.items(), key=lambda item: item[1]["r2"])[0] if fits else None
    return {"variant": variant, "metric": metric, "n_points": len(subset), "fits": fits, "best_k_eff": best}


def analyze(input_path: str = "results/module1_capacity_diagnostic_full_shards/results.json", output_dir: str = "results/module1_capacity_perdepth_shards") -> dict[str, Any]:
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    rows = _ceiling_free_rows(data["summary"])
    fits = []
    for variant in sorted({row["variant"] for row in rows}):
        for metric in ["frontier_joint_095", "frontier_var_095", "frontier_val_095"]:
            fits.append(_fit_variant(rows, variant, metric))
    crossover = []
    for D in sorted({row["D"] for row in rows}):
        for K_val in [2, 9]:
            for K_var in sorted({row["K_var"] for row in rows if row["D"] == D and row["K_val"] == K_val}):
                bound = next((row for row in rows if row["variant"] == "bound_single" and row["D"] == D and row["K_var"] == K_var and row["K_val"] == K_val), None)
                factored = next((row for row in rows if row["variant"] == "factored" and row["D"] == D and row["K_var"] == K_var and row["K_val"] == K_val), None)
                if bound and factored:
                    crossover.append({"D": D, "K_var": K_var, "K_val": K_val, "bound_single_joint": bound["frontier_joint_095"], "factored_joint": factored["frontier_joint_095"], "winner": "factored" if factored["frontier_joint_095"] > bound["frontier_joint_095"] else ("bound_single" if bound["frontier_joint_095"] > factored["frontier_joint_095"] else "tie")})
    payload = {
        "source": input_path,
        "note": "Uses existing fixed-depth diagnostic frontiers with K_var >= 60; this is per-depth-derived frontier fitting, not a rerun.",
        "fits": fits,
        "crossover": crossover,
        "decision": "fit_recorded_ceiling_free_rows",
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results_path = out / "results.json"
    curves_path = out / "curves.json"
    results_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    curves_path.write_text(json.dumps({"fits": fits, "crossover": crossover}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"results": str(results_path), "curves": str(curves_path), **payload}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fit ceiling-free Module 1 capacity-law candidates.")
    parser.add_argument("--input-path", default="results/module1_capacity_diagnostic_full_shards/results.json")
    parser.add_argument("--output-dir", default="results/module1_capacity_perdepth_shards")
    args = parser.parse_args()
    print(json.dumps(analyze(args.input_path, args.output_dir), indent=2, sort_keys=True))