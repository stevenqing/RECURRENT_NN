"""Merge ceiling-free per-depth Module 1 benchmark shards."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from analysis.capacity_theory import capacity_features, fit_through_origin


def _crossing(curve: list[dict[str, Any]], metric: str, threshold: float = 0.95) -> float:
    ordered = sorted(curve, key=lambda row: row["depth"])
    if not ordered:
        return 0.0
    if ordered[0][metric] < threshold:
        return 0.0
    last = ordered[0]
    for row in ordered[1:]:
        if row[metric] < threshold:
            denom = last[metric] - row[metric]
            if denom <= 0:
                return float(last["depth"])
            frac = (last[metric] - threshold) / denom
            return float(last["depth"] + frac * (row["depth"] - last["depth"]))
        last = row
    return float(ordered[-1]["depth"])


def _summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    keys = sorted({(row["variant"], row["replacement"], row["D"], row["K_var"], row["K_val"]) for row in rows})
    for variant, replacement, D, K_var, K_val in keys:
        subset = [row for row in rows if (row["variant"], row["replacement"], row["D"], row["K_var"], row["K_val"]) == (variant, replacement, D, K_var, K_val)]
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
            "replacement": replacement,
            "D": D,
            "K_var": K_var,
            "K_val": K_val,
            "capacity_joint_095": _crossing(curve, "joint_accuracy"),
            "capacity_var_095": _crossing(curve, "var_accuracy"),
            "capacity_val_095": _crossing(curve, "val_accuracy"),
            "curve": curve,
        })
    return summary


def _directions(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for variant in sorted({row["variant"] for row in summary}):
        for replacement in sorted({row["replacement"] for row in summary}):
            for metric in ["joint", "var", "val"]:
                rows = sorted([row for row in summary if row["variant"] == variant and row["replacement"] == replacement and row["D"] == 1024 and row["K_val"] == 2], key=lambda row: row["K_var"])
                caps = [row[f"capacity_{metric}_095"] for row in rows]
                signs = []
                for left, right in zip(caps, caps[1:]):
                    delta = right - left
                    signs.append(0 if abs(delta) < 1e-9 else (1 if delta > 0 else -1))
                out.append({"variant": variant, "replacement": replacement, "metric": metric, "D": 1024, "K_val": 2, "K_vars": [row["K_var"] for row in rows], "capacities": caps, "signs": signs})
    return out


def _fits(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fits = []
    for variant in sorted({row["variant"] for row in summary}):
        for replacement in sorted({row["replacement"] for row in summary}):
            subset = [row for row in summary if row["variant"] == variant and row["replacement"] == replacement and row["K_var"] >= 60 and row["capacity_joint_095"] > 0]
            y = [row["capacity_joint_095"] for row in subset]
            candidates = {"D_over_ln_Kvar": [], "D_over_ln_product": [], "halfD_over_ln_max_factor": []}
            for row in subset:
                features = capacity_features(row["D"], row["K_var"], row["K_val"])
                for name in candidates:
                    candidates[name].append(features[name])
            fit = {name: fit_through_origin(values, y) for name, values in candidates.items()}
            best = max(fit.items(), key=lambda item: item[1]["r2"])[0] if fit else None
            fits.append({"variant": variant, "replacement": replacement, "metric": "joint", "n_points": len(subset), "fits": fit, "best_k_eff": best})
    return fits


def merge(input_dir: str = "results/module1_capacity_perdepth_shards", output_dir: str | None = None) -> dict[str, Any]:
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
        shards.append({"path": str(path), "shard_index": payload.get("shard_index"), "n_rows": len(payload["rows"])})
    summary = _summary(rows)
    directions = _directions(summary)
    fits = _fits(summary)
    has_positive = any(any(sign > 0 for sign in item["signs"]) for item in directions if item["metric"] == "joint")
    decision = "k_direction_negative" if not has_positive else "k_direction_open_or_inverted"
    payload = {"module": "module1_capacity_perdepth", "device": "8x_cuda_sharded", "num_shards": len(shard_paths), "shards": shards, "rows": rows, "summary": summary, "directions": directions, "fits": fits, "decision": decision, "open": decision != "k_direction_negative"}
    results_path = out / "results.json"
    curves_path = out / "curves.json"
    results_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    curves_path.write_text(json.dumps({"summary": summary, "directions": directions, "fits": fits, "decision": decision, "open": payload["open"]}, indent=2) + "\n", encoding="utf-8")
    return {"results": str(results_path), "curves": str(curves_path), "decision": decision, "open": payload["open"], "n_rows": len(rows), "n_summary": len(summary), "n_shards": len(shard_paths)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge per-depth capacity benchmark shards.")
    parser.add_argument("--input-dir", default="results/module1_capacity_perdepth_shards")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    print(json.dumps(merge(args.input_dir, args.output_dir), indent=2, sort_keys=True))