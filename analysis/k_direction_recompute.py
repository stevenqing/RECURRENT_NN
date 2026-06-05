"""Ceiling-aware K-direction reanalysis for Module 1 capacity results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _sweep_max_depth(summary_row: dict[str, Any]) -> int:
    return max(point["depth"] for point in summary_row["curve"])


def _is_ceiling_bound(summary_row: dict[str, Any], margin: int) -> bool:
    ceiling = min(summary_row["K_var"], _sweep_max_depth(summary_row))
    return summary_row["frontier_decode_095"] >= ceiling - margin


def _classify(frontiers: list[int]) -> dict[str, Any]:
    if len(frontiers) < 3:
        return {"classification": "insufficient", "signs": []}
    signs = []
    for left, right in zip(frontiers, frontiers[1:]):
        delta = right - left
        signs.append(0 if delta == 0 else (1 if delta > 0 else -1))
    if all(sign <= 0 for sign in signs) and any(sign < 0 for sign in signs):
        classification = "theory_consistent"
    elif all(sign >= 0 for sign in signs) and any(sign > 0 for sign in signs):
        classification = "inverted"
    elif any(sign > 0 for sign in signs) and any(sign < 0 for sign in signs):
        classification = "nonmonotonic"
    else:
        classification = "insufficient"
    return {"classification": classification, "signs": signs}


def _recompute_one(payload: dict[str, Any], margin: int) -> list[dict[str, Any]]:
    rows = []
    groups = sorted({(row["variant"], row["D"], row["K_val"]) for row in payload["summary"]})
    for variant, D, K_val in groups:
        group_rows = sorted([row for row in payload["summary"] if (row["variant"], row["D"], row["K_val"]) == (variant, D, K_val)], key=lambda row: row["K_var"])
        points = []
        kept = []
        dropped = []
        for row in group_rows:
            point = {
                "K_var": row["K_var"],
                "K_val": row["K_val"],
                "frontier": row["frontier_decode_095"],
                "sweep_max_depth": _sweep_max_depth(row),
                "ceiling": min(row["K_var"], _sweep_max_depth(row)),
                "ceiling_bound": _is_ceiling_bound(row, margin),
            }
            points.append(point)
            if point["ceiling_bound"]:
                dropped.append(point)
            else:
                kept.append(point)
        full = _classify([point["frontier"] for point in points])
        unconfounded = _classify([point["frontier"] for point in kept])
        rows.append({
            "variant": variant,
            "D": D,
            "K_val": K_val,
            "points": points,
            "kept_points": kept,
            "dropped_points": dropped,
            "full_classification": full["classification"],
            "full_signs": full["signs"],
            "classification": unconfounded["classification"],
            "signs": unconfounded["signs"],
            "changed_after_ceiling_drop": full["classification"] != unconfounded["classification"],
        })
    return rows


def recompute(
    benchmark_path: str = "results/module1_capacity_benchmark_full_shards/results.json",
    diagnostic_path: str = "results/module1_capacity_diagnostic_full_shards/results.json",
    output_path: str = "results/module1_capacity_benchmark_full_shards/k_direction_corrected.json",
    margin: int = 1,
) -> dict[str, Any]:
    benchmark = json.loads(Path(benchmark_path).read_text(encoding="utf-8"))
    diagnostic = json.loads(Path(diagnostic_path).read_text(encoding="utf-8")) if Path(diagnostic_path).exists() else None
    benchmark_reanalysis = _recompute_one(benchmark, margin)
    target = next((row for row in benchmark_reanalysis if row["variant"] == "bound_single" and row["D"] == 1024 and row["K_val"] == 2), None)
    result = {
        "margin": margin,
        "benchmark_path": benchmark_path,
        "diagnostic_path": diagnostic_path if diagnostic else None,
        "benchmark_reanalysis": benchmark_reanalysis,
        "expected_target": target,
        "expected_target_passed": target is not None and target["classification"] == "theory_consistent",
        "diagnostic_decision": diagnostic.get("decision") if diagnostic else None,
        "decision": "ceiling_aware_reanalysis_complete",
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"output": str(out), **result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recompute K-direction after dropping ceiling-bound points.")
    parser.add_argument("--benchmark-path", default="results/module1_capacity_benchmark_full_shards/results.json")
    parser.add_argument("--diagnostic-path", default="results/module1_capacity_diagnostic_full_shards/results.json")
    parser.add_argument("--output-path", default="results/module1_capacity_benchmark_full_shards/k_direction_corrected.json")
    parser.add_argument("--margin", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(recompute(args.benchmark_path, args.diagnostic_path, args.output_path, args.margin), indent=2, sort_keys=True))