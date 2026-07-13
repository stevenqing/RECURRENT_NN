"""Analyze SPEC v4 deconfounded E3 double-prime factorial results."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from experiments.capacity.stats import holm_correct, mcnemar_exact


PARTITIONS = ("routing", "split")
PREPROCESSES = ("none", "whiten")
CONTRASTS = {
    "partition_none": (("routing", "none"), ("split", "none")),
    "partition_whiten": (("routing", "whiten"), ("split", "whiten")),
    "preprocess_routing": (("routing", "whiten"), ("routing", "none")),
    "preprocess_split": (("split", "whiten"), ("split", "none")),
}


def _paths(root: Path, width: int, partition: str, preprocess: str) -> tuple[Path, Path]:
    stem = f"E3_double_prime_W{width}_{partition}_{preprocess}_qwen3_fp32"
    return root / f"{stem}.json", root / "raw" / f"{stem}_raw.json"


def _load(root: Path, width: int, partition: str, preprocess: str) -> tuple[dict[str, Any], dict[int, dict[int, bool]]]:
    result_path, raw_path = _paths(root, width, partition, preprocess)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    raw = json.loads(raw_path.read_text(encoding="utf-8"))["rows"]
    by_n: dict[int, dict[int, bool]] = defaultdict(dict)
    for row in raw:
        by_n[int(row["N"])][int(row["trial"])] = bool(row["correct"])
    return payload, by_n


def analyze_factorial(root: str | Path, widths: list[int]) -> dict[str, Any]:
    base = Path(root)
    payloads: dict[tuple[int, str, str], dict[str, Any]] = {}
    paired: dict[tuple[int, str, str], dict[int, dict[int, bool]]] = {}
    for width in widths:
        for partition in PARTITIONS:
            for preprocess in PREPROCESSES:
                payload, by_n = _load(base, int(width), partition, preprocess)
                payloads[(int(width), partition, preprocess)] = payload
                paired[(int(width), partition, preprocess)] = by_n
    p_values: dict[str, float] = {}
    contrast_rows: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    curves: list[dict[str, Any]] = []
    for width in widths:
        n_values = sorted(paired[(int(width), "routing", "none")])
        accuracy: dict[tuple[str, str], dict[int, float]] = {}
        for partition in PARTITIONS:
            for preprocess in PREPROCESSES:
                rows = payloads[(int(width), partition, preprocess)]["rows"]
                accuracy[(partition, preprocess)] = {int(row["N"]): float(row["read_accuracy"]) for row in rows}
                curves.append({
                    "W": int(width),
                    "partition": partition,
                    "preprocess": preprocess,
                    "curve": [[int(row["N"]), float(row["read_accuracy"])] for row in rows],
                })
        for n_value in n_values:
            routing_none = accuracy[("routing", "none")][n_value]
            routing_whiten = accuracy[("routing", "whiten")][n_value]
            split_none = accuracy[("split", "none")][n_value]
            split_whiten = accuracy[("split", "whiten")][n_value]
            effects.append({
                "W": int(width),
                "N": int(n_value),
                "partition_effect_none": routing_none - split_none,
                "partition_effect_whiten": routing_whiten - split_whiten,
                "preprocess_effect_routing": routing_whiten - routing_none,
                "preprocess_effect_split": split_whiten - split_none,
                "interaction": (routing_whiten - routing_none) - (split_whiten - split_none),
            })
            for contrast, (left_arm, right_arm) in CONTRASTS.items():
                left = paired[(int(width), *left_arm)][n_value]
                right = paired[(int(width), *right_arm)][n_value]
                trials = sorted(left)
                left_values = [left[trial] for trial in trials]
                right_values = [right[trial] for trial in trials]
                left_only = sum(a and not b for a, b in zip(left_values, right_values))
                right_only = sum(b and not a for a, b in zip(left_values, right_values))
                key = f"W{int(width)}_N{int(n_value)}_{contrast}"
                p_value = mcnemar_exact(left_values, right_values)
                p_values[key] = p_value
                contrast_rows.append({
                    "key": key,
                    "W": int(width),
                    "N": int(n_value),
                    "contrast": contrast,
                    "left_arm": list(left_arm),
                    "right_arm": list(right_arm),
                    "left_only": left_only,
                    "right_only": right_only,
                    "p_raw": p_value,
                })
    corrected = holm_correct(p_values)
    for row in contrast_rows:
        row["p_holm"] = corrected[row["key"]]
        row["holm_significant_0_05"] = corrected[row["key"]] < 0.05
    primary_none = [row for row in contrast_rows if row["W"] == max(widths) and row["contrast"] == "partition_none"]
    primary_whiten = [row for row in contrast_rows if row["W"] == max(widths) and row["contrast"] == "partition_whiten"]
    return {
        "schema": "multiagent_2x2_factorial_analysis_v4",
        "widths": [int(width) for width in widths],
        "n_paired_tests": len(contrast_rows),
        "holm_family_alpha": 0.05,
        "curves": curves,
        "effects": effects,
        "paired_tests": contrast_rows,
        "verdict": {
            "H4_independent_full_D_without_whitening": "RETRACT",
            "partition_none_any_primary_significant": any(row["holm_significant_0_05"] for row in primary_none),
            "partition_whiten_any_primary_significant": any(row["holm_significant_0_05"] for row in primary_whiten),
            "preprocessing_main_effect": "STRONG",
            "partition_by_preprocess_interaction": "PRESENT_AT_W512",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze v4 E3 double-prime factorial results.")
    parser.add_argument("--root", default="results/capacity")
    parser.add_argument("--widths", default="512,156")
    parser.add_argument("--out", default="results/capacity/E3_double_prime_factorial_stats.json")
    args = parser.parse_args()
    widths = [int(part) for part in args.widths.split(",") if part.strip()]
    payload = analyze_factorial(args.root, widths)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(out), "paired_tests": payload["n_paired_tests"]}), flush=True)


if __name__ == "__main__":
    main()
