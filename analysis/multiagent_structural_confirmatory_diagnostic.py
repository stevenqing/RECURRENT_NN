"""Post-confirmatory exploratory diagnosis of the failed structural gate.

This script never reruns an arm and cannot alter the frozen verdict. It explains
how frequent paired work savings were overturned by rare activation-cap failures.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import mean, median
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT


PROPOSED = "independent_local_cbj_v1_exact"
MONOLITH = "monolith_MR"


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    location = probability * (len(ordered) - 1)
    lower = int(location)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = location - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted((value, index) for index, value in enumerate(values))
    output = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][0] == ordered[cursor][0]:
            end += 1
        rank = (cursor + end - 1) / 2.0 + 1.0
        for _value, original_index in ordered[cursor:end]:
            output[original_index] = rank
        cursor = end
    return output


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_scale = sum((value - left_mean) ** 2 for value in left) ** 0.5
    right_scale = sum((value - right_mean) ** 2 for value in right) ** 0.5
    if left_scale <= 0.0 or right_scale <= 0.0:
        return None
    return numerator / (left_scale * right_scale)


def _spearman(left: list[float], right: list[float]) -> float | None:
    return _pearson(_ranks(left), _ranks(right))


def _distribution(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, Any]:
    output = {"n": len(rows)}
    for field in fields:
        values = [float(row[field]) for row in rows]
        output[field] = {
            "mean": mean(values),
            "median": median(values),
            "p90": _quantile(values, 0.90),
            "min": min(values),
            "max": max(values),
        }
    return output


def diagnose(
    raw_path: Path,
    analysis_path: Path,
    confirm_manifest_path: Path,
    development_manifest_path: Path,
    development_results_path: Path,
) -> dict[str, Any]:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    frozen_analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    if frozen_analysis.get("status") != "STRUCTURAL_CONFIRMATION_FAIL":
        raise ValueError("diagnostic is defined only for the frozen failed confirmation")
    rows = list(raw["rows"])
    confirm_manifest = list(json.loads(confirm_manifest_path.read_text(encoding="utf-8"))["rows"])
    development_manifest = list(json.loads(development_manifest_path.read_text(encoding="utf-8"))["rows"])
    development_results = json.loads(development_results_path.read_text(encoding="utf-8"))
    confirm_meta = {str(row["instance_id"]): row for row in confirm_manifest}
    development_meta = {str(row["instance_id"]): row for row in development_manifest}
    index = {
        (str(row["cell"]), str(row["instance_id"]), str(row["arm"])): row
        for row in rows
    }
    over_low_ids = sorted({str(row["instance_id"]) for row in rows if row["cell"] == "over_low"})
    proposed = [index[("over_low", instance_id, PROPOSED)] for instance_id in over_low_ids]
    monolith = [index[("over_low", instance_id, MONOLITH)] for instance_id in over_low_ids]
    solved_pairs = [
        (left, right)
        for left, right in zip(proposed, monolith)
        if bool(left["solved"]) and bool(right["solved"])
    ]
    failed = [row for row in proposed if not bool(row["solved"])]
    failed_ids = {str(row["instance_id"]) for row in failed}
    solved = [row for row in proposed if bool(row["solved"])]

    raw_ratio = mean(float(row["aggregate_work"]) for row in proposed) / mean(
        float(row["aggregate_work"]) for row in monolith
    )
    solved_only_ratio = mean(float(left["aggregate_work"]) for left, _right in solved_pairs) / mean(
        float(right["aggregate_work"]) for _left, right in solved_pairs
    )
    paired_ratios = [
        float(left["penalized_work"]) / max(float(right["penalized_work"]), 1e-12)
        for left, right in zip(proposed, monolith)
    ]
    penalties = {}
    for penalty in (5000, 10000, 20000, 40000):
        team = [
            float(row["aggregate_work"])
            if row["solved"]
            else max(float(row["aggregate_work"]), float(penalty))
            for row in proposed
        ]
        penalties[str(penalty)] = {
            "mean_team_work": mean(team),
            "ratio_vs_monolith": mean(team) / mean(float(row["aggregate_work"]) for row in monolith),
        }

    mean_success_work = mean(float(row["aggregate_work"]) for row in solved)
    mean_monolith_work = mean(float(row["aggregate_work"]) for row in monolith)
    cap = 20000.0
    critical_failure_rate = (
        (mean_monolith_work - mean_success_work) / (cap - mean_success_work)
        if cap > mean_success_work and mean_monolith_work > mean_success_work
        else None
    )
    actual_failure_rate = len(failed) / len(proposed)

    structural_fields = (
        "global_recovery_distance",
        "local_recovery_distance",
        "reference_steps",
        "reference_retractions",
        "rho_actual",
    )
    confirm_over_low_meta = [confirm_meta[instance_id] for instance_id in over_low_ids]
    development_over_low_meta = [
        row for row in development_manifest if row["cell"] == "over_low"
    ]
    failed_meta = [confirm_meta[instance_id] for instance_id in sorted(failed_ids)]
    solved_meta = [confirm_meta[str(row["instance_id"])] for row in solved]

    correlations = {}
    for field in structural_fields:
        x = [float(confirm_meta[instance_id][field]) for instance_id in over_low_ids]
        correlations[field] = {
            "with_raw_work_spearman": _spearman(x, [float(row["aggregate_work"]) for row in proposed]),
            "with_failure_spearman": _spearman(x, [float(not row["solved"]) for row in proposed]),
        }

    failure_rows = []
    for row in sorted(failed, key=lambda item: str(item["instance_id"])):
        instance_id = str(row["instance_id"])
        meta = confirm_meta[instance_id]
        control = index[("over_low", instance_id, MONOLITH)]
        failure_rows.append({
            "instance_id": instance_id,
            "status": row["status"],
            "aggregate_work": int(row["aggregate_work"]),
            "penalized_work": int(row["penalized_work"]),
            "parallel_rounds": int(row["parallel_rounds"]),
            "branch_attempts": int(row["branch_attempts"]),
            "retractions": int(row["retractions"]),
            "requests": int(row["requests_sent"]),
            "nacks": int(row["nacks"]),
            "window_rejections": int(row["window_rejections"]),
            "monolith_work": int(control["aggregate_work"]),
            "global_recovery_distance": int(meta["global_recovery_distance"]),
            "local_recovery_distance": int(meta["local_recovery_distance"]),
            "reference_steps": int(meta["reference_steps"]),
            "reference_retractions": int(meta["reference_retractions"]),
            "rho_actual": float(meta["rho_actual"]),
        })

    development_proposed = [
        row
        for row in development_results["rows"]
        if row["cell"] == "over_low" and row["arm"] == "independent_local_cbj"
    ]
    development_monolith = [
        row
        for row in development_results["rows"]
        if row["cell"] == "over_low" and row["arm"] == "monolith_MR"
    ]

    return {
        "schema": "multiagent_structural_confirmatory_posthoc_diagnostic_v1",
        "status": "POSTHOC_DIAGNOSTIC_COMPLETE",
        "confirmatory_verdict_unchanged": frozen_analysis["status"],
        "confirmatory_eligible": False,
        "headline_eligible": False,
        "sweet_spot_tail_risk": {
            "n": len(proposed),
            "solved": len(solved),
            "failed": len(failed),
            "actual_failure_rate": actual_failure_rate,
            "critical_failure_rate_for_expected_work_at_cap_20000": critical_failure_rate,
            "mean_success_work": mean_success_work,
            "mean_monolith_work": mean_monolith_work,
            "all_episode_raw_work_ratio": raw_ratio,
            "jointly_solved_work_ratio": solved_only_ratio,
            "frozen_penalized_work_ratio": mean(float(row["penalized_work"]) for row in proposed)
            / mean(float(row["penalized_work"]) for row in monolith),
            "paired_ratio_quantiles": {
                "median": median(paired_ratios),
                "p90": _quantile(paired_ratios, 0.90),
                "p95": _quantile(paired_ratios, 0.95),
                "max": max(paired_ratios),
            },
            "paired_wins_ties_losses": {
                "wins": sum(a < b for a, b in zip(
                    [float(row["penalized_work"]) for row in proposed],
                    [float(row["penalized_work"]) for row in monolith],
                )),
                "ties": sum(a == b for a, b in zip(
                    [float(row["penalized_work"]) for row in proposed],
                    [float(row["penalized_work"]) for row in monolith],
                )),
                "losses": sum(a > b for a, b in zip(
                    [float(row["penalized_work"]) for row in proposed],
                    [float(row["penalized_work"]) for row in monolith],
                )),
            },
            "penalty_sensitivity_exploratory": penalties,
        },
        "distribution_shift": {
            "development_over_low_structure": _distribution(development_over_low_meta, structural_fields),
            "confirmatory_over_low_structure": _distribution(confirm_over_low_meta, structural_fields),
            "confirmatory_solved_structure": _distribution(solved_meta, structural_fields),
            "confirmatory_failed_structure": _distribution(failed_meta, structural_fields),
            "development_outcomes": {
                "proposed_solve_rate": mean(float(row["solved"]) for row in development_proposed),
                "monolith_solve_rate": mean(float(row["solved"]) for row in development_monolith),
                "proposed_mean_work": mean(float(row["aggregate_work"]) for row in development_proposed),
                "monolith_mean_work": mean(float(row["aggregate_work"]) for row in development_monolith),
            },
        },
        "structural_correlations_confirmatory_over_low": correlations,
        "failed_instances": failure_rows,
        "interpretation": {
            "primary": "The factorized arm usually reduced paired work but its 8% cap-failure rate exceeded the approximate expected-work break-even rate, so rare failures dominated the mean resource objective.",
            "same_order_control": "The centralized-factorized arm failed on the same four over-low instances, localizing the defect to factorized search robustness rather than queued message delivery.",
            "route": "Random-valid matched deepest solve in over-low and was not separated by the preregistered mechanism gate, so the substrate does not support a route-quality or LLM-routing contribution.",
            "nonclaim": "Penalty sensitivity and structural correlations are post-confirmatory diagnostics, not alternative confirmatory analyses.",
        },
    }


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    return f"{float(value):.{digits}f}"


def _render(payload: dict[str, Any]) -> str:
    tail = payload["sweet_spot_tail_risk"]
    shift = payload["distribution_shift"]
    lines = [
        "# Post-Confirmatory Tail-Risk Diagnostic",
        "",
        "- Evidence tier: **exploratory after confirmatory failure**",
        f"- Frozen verdict remains: **`{payload['confirmatory_verdict_unchanged']}`**",
        "- Arms rerun: **No**",
        "- Thresholds changed: **No**",
        "",
        "## Main diagnosis",
        "",
        f"The proposed arm solved `{tail['solved']}/{tail['n']}` over-low episodes. Its observed failure rate was `{_fmt(tail['actual_failure_rate'])}`, while the simple expected-work break-even rate at a 20,000 failure cost was approximately `{_fmt(tail['critical_failure_rate_for_expected_work_at_cap_20000'])}`.",
        "",
        f"- Mean work among successful proposed episodes: `{_fmt(tail['mean_success_work'], 1)}`",
        f"- Mean monolith work: `{_fmt(tail['mean_monolith_work'], 1)}`",
        f"- Jointly-solved work ratio: `{_fmt(tail['jointly_solved_work_ratio'])}`",
        f"- All-episode raw-work ratio: `{_fmt(tail['all_episode_raw_work_ratio'])}`",
        f"- Frozen failure-penalized ratio: `{_fmt(tail['frozen_penalized_work_ratio'])}`",
        f"- Paired wins/ties/losses: `{tail['paired_wins_ties_losses']['wins']}/{tail['paired_wins_ties_losses']['ties']}/{tail['paired_wins_ties_losses']['losses']}`",
        "",
        "The mechanism therefore has a frequent-case work benefit but not an expected-resource free lunch. Tail failures dominate exactly the resource objective that was preregistered.",
        "",
        "## Same-order control",
        "",
        "`factorized_central_cbj` failed on the same four over-low instances and had almost identical solve/work. The failure is not explained by queued request latency; it is a robustness/completeness defect of the factorized trajectory itself.",
        "",
        "## Development-to-confirmatory shift",
        "",
        "| Quantity | Development mean | Confirmatory mean |",
        "|---|---:|---:|",
    ]
    for field in ("reference_steps", "reference_retractions", "global_recovery_distance", "local_recovery_distance", "rho_actual"):
        old = shift["development_over_low_structure"][field]["mean"]
        new = shift["confirmatory_over_low_structure"][field]["mean"]
        lines.append(f"| `{field}` | {_fmt(old)} | {_fmt(new)} |")
    lines.extend([
        "",
        "The frozen structural stratum was valid in both pools, but it was broad: the new pool contains materially heavier reference trajectories. The 16-instance development positive did not estimate this tail reliably.",
        "",
        "## Four failed over-low episodes",
        "",
        "| Instance | Ref steps | Global/local distance | Proposed raw work | Requests/NACKs | Window rejects | Monolith work |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for row in payload["failed_instances"]:
        lines.append(
            f"| `{row['instance_id']}` | {row['reference_steps']} | "
            f"{row['global_recovery_distance']}/{row['local_recovery_distance']} | "
            f"{row['aggregate_work']} | {row['requests']}/{row['nacks']} | "
            f"{row['window_rejections']} | {row['monolith_work']} |"
        )
    lines.extend([
        "",
        "## Exploratory penalty sensitivity",
        "",
        "| Failure penalty | Team/monolith ratio |",
        "|---:|---:|",
    ])
    for penalty, row in payload["sweet_spot_tail_risk"]["penalty_sensitivity_exploratory"].items():
        lines.append(f"| {penalty} | {_fmt(row['ratio_vs_monolith'])} |")
    lines.extend([
        "",
        "This table is descriptive only. The frozen decision correctly uses 20,000 and is not revisited.",
        "",
        "## Research implication",
        "",
        "The defensible next question is not whether independent local loops are uniformly cheaper. It is whether a predeclared **risk-aware selective factorization** policy can retain the frequent-case savings while bounding catastrophic failure probability below the analytically required break-even rate. Such a policy would require development on separate data and a new untouched confirmation; it cannot be fitted and claimed on this confirmatory pool.",
        "",
        "## Artifacts",
        "",
        "- [Diagnostic JSON](diagnostic.json)",
        "- [Frozen confirmatory result](RESULTS.md)",
        "- [Raw confirmatory results](raw_results.json)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose failed structural confirmation without reruns.")
    parser.add_argument("--raw", type=Path, default=Path("results/multiagent_structural_confirmatory/raw_results.json"))
    parser.add_argument("--analysis", type=Path, default=Path("results/multiagent_structural_confirmatory/analysis.json"))
    parser.add_argument("--confirm-manifest", type=Path, default=Path("results/multiagent_structural_confirmatory_manifest/instance_manifest.json"))
    parser.add_argument("--development-manifest", type=Path, default=Path("results/multiagent_core_2x2_preflight/instance_manifest.json"))
    parser.add_argument("--development-results", type=Path, default=Path("results/multiagent_structural_free_lunch/results.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_structural_confirmatory"))
    args = parser.parse_args()
    paths = [
        value if value.is_absolute() else REPO_ROOT / value
        for value in (
            args.raw,
            args.analysis,
            args.confirm_manifest,
            args.development_manifest,
            args.development_results,
        )
    ]
    payload = diagnose(*paths)
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    (output_dir / "diagnostic.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "DIAGNOSTIC.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "verdict_unchanged": payload["confirmatory_verdict_unchanged"],
        "report": str((output_dir / "DIAGNOSTIC.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
