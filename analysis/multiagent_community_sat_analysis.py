"""Frozen analysis for the independent community-SAT replication."""

from __future__ import annotations

import argparse
from collections import Counter
from math import comb
import hashlib
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any

from experiments.capacity.stats import mcnemar_exact
from experiments.multiagent_capacity_coupling import REPO_ROOT
from analysis.multiagent_community_sat_run import _verify_lock


PROPOSED = "independent_local_cbj_sat"
CENTRAL = "factorized_central_cbj_sat"
RANDOM = "independent_local_random_valid_sat"
NO_CROSS = "independent_local_no_cross_sat"
MONOLITH = "monolith_MR_sat"
SHARDED = "centralized_sharded_MR_sat"
BOOTSTRAPS = 100000


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    location = probability * (len(ordered) - 1)
    lower = int(location)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = location - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _binomial_cdf(k: int, n: int, p: float) -> float:
    return sum(comb(n, index) * p**index * (1.0 - p) ** (n - index) for index in range(k + 1))


def _cp_upper(k: int, n: int, alpha: float = 0.05) -> float:
    if k == n:
        return 1.0
    low = k / max(n, 1)
    high = 1.0
    for _ in range(100):
        middle = (low + high) / 2.0
        if _binomial_cdf(k, n, middle) > alpha:
            low = middle
        else:
            high = middle
    return high


def _paired_ratio(left: list[float], right: list[float], seed: int) -> dict[str, Any]:
    generator = random.Random(int(seed))
    n = len(left)
    samples = []
    for _ in range(BOOTSTRAPS):
        indices = [generator.randrange(n) for _ in range(n)]
        samples.append(sum(left[index] for index in indices) / max(sum(right[index] for index in indices), 1e-12))
    return {
        "n": n,
        "left_mean": mean(left),
        "right_mean": mean(right),
        "ratio_of_means": mean(left) / max(mean(right), 1e-12),
        "bootstrap_ci95": [_quantile(samples, 0.025), _quantile(samples, 0.975)],
        "wins": sum(a < b for a, b in zip(left, right)),
        "ties": sum(a == b for a, b in zip(left, right)),
        "losses": sum(a > b for a, b in zip(left, right)),
    }


def _independent_ratio(high: list[float], low: list[float], seed: int) -> dict[str, Any]:
    generator = random.Random(int(seed))
    samples = []
    for _ in range(BOOTSTRAPS):
        high_sample = [high[generator.randrange(len(high))] for _ in range(len(high))]
        low_sample = [low[generator.randrange(len(low))] for _ in range(len(low))]
        samples.append(mean(high_sample) / max(mean(low_sample), 1e-12))
    return {
        "high_mean": mean(high),
        "low_mean": mean(low),
        "ratio_of_means": mean(high) / max(mean(low), 1e-12),
        "bootstrap_ci95": [_quantile(samples, 0.025), _quantile(samples, 0.975)],
    }


def _summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for cell, arm in sorted({(str(row["cell"]), str(row["arm"])) for row in rows}):
        subset = [row for row in rows if row["cell"] == cell and row["arm"] == arm]
        output.append({
            "cell": cell,
            "arm": arm,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_aggregate_work": mean(float(row["aggregate_work"]) for row in subset),
            "mean_penalized_work": mean(float(row["penalized_work"]) for row in subset),
            "mean_parallel_rounds": mean(float(row["parallel_rounds"]) for row in subset),
            "mean_retractions": mean(float(row["retractions"]) for row in subset),
            "mean_requests": mean(float(row.get("requests_sent", 0)) for row in subset),
            "status_counts": dict(Counter(str(row["status"]) for row in subset)),
        })
    return output


def _lookup(summary: list[dict[str, Any]], cell: str, arm: str) -> dict[str, Any]:
    return next(row for row in summary if row["cell"] == cell and row["arm"] == arm)


def _solve_contrast(index: dict[tuple[str, str, str], dict[str, Any]], ids: list[str], cell: str, left_arm: str, right_arm: str) -> dict[str, Any]:
    left = [bool(index[(cell, instance_id, left_arm)]["solved"]) for instance_id in ids]
    right = [bool(index[(cell, instance_id, right_arm)]["solved"]) for instance_id in ids]
    left_only = sum(a and not b for a, b in zip(left, right))
    right_only = sum(b and not a for a, b in zip(left, right))
    return {
        "cell": cell,
        "left_arm": left_arm,
        "right_arm": right_arm,
        "n": len(ids),
        "left_solve_rate": mean(map(float, left)),
        "right_solve_rate": mean(map(float, right)),
        "solve_difference": mean(map(float, left)) - mean(map(float, right)),
        "left_only": left_only,
        "right_only": right_only,
        "mcnemar_two_sided": mcnemar_exact(left, right),
        "control_only_discordance_cp_upper95": _cp_upper(right_only, len(ids)),
    }


def _work_contrast(index: dict[tuple[str, str, str], dict[str, Any]], ids: list[str], cell: str, left_arm: str, right_arm: str, field: str, seed: int) -> dict[str, Any]:
    left = [float(index[(cell, instance_id, left_arm)][field]) for instance_id in ids]
    right = [float(index[(cell, instance_id, right_arm)][field]) for instance_id in ids]
    return {"cell": cell, "left_arm": left_arm, "right_arm": right_arm, "field": field, **_paired_ratio(left, right, seed)}


def analyze(raw_path: Path, lock_path: Path) -> dict[str, Any]:
    lock, lock_checks = _verify_lock(lock_path)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if raw.get("status") != "SAT_RAW_COMPLETE" or not raw.get("protocol_audit", {}).get("pass"):
        raise ValueError("SAT raw artifact incomplete or protocol-invalid")
    expected_hashes = {key: item["sha256"] for key, item in lock["files"].items()}
    if raw.get("input_hashes") != expected_hashes:
        raise ValueError("SAT raw input hashes differ from lock")
    rows = list(raw["rows"])
    if len(rows) != 1600:
        raise ValueError("unexpected SAT raw row count")
    summary = _summary(rows)
    index = {(str(row["cell"]), str(row["instance_id"]), str(row["arm"])): row for row in rows}
    ids = {
        cell: sorted({str(row["instance_id"]) for row in rows if row["cell"] == cell})
        for cell in ("under_low", "under_high", "over_low", "over_high")
    }
    over_low = ids["over_low"]
    solve = {
        "proposed_vs_monolith": _solve_contrast(index, over_low, "over_low", PROPOSED, MONOLITH),
        "proposed_vs_sharded": _solve_contrast(index, over_low, "over_low", PROPOSED, SHARDED),
        "proposed_vs_central": _solve_contrast(index, over_low, "over_low", PROPOSED, CENTRAL),
    }
    penalized = {
        "proposed_vs_monolith": _work_contrast(index, over_low, "over_low", PROPOSED, MONOLITH, "penalized_work", 9101),
        "proposed_vs_sharded": _work_contrast(index, over_low, "over_low", PROPOSED, SHARDED, "penalized_work", 9102),
        "proposed_vs_central": _work_contrast(index, over_low, "over_low", PROPOSED, CENTRAL, "penalized_work", 9103),
    }
    jointly_solved = [
        instance_id for instance_id in over_low
        if index[("over_low", instance_id, PROPOSED)]["solved"]
        and index[("over_low", instance_id, MONOLITH)]["solved"]
    ]
    joint_raw = _work_contrast(index, jointly_solved, "over_low", PROPOSED, MONOLITH, "aggregate_work", 9104)
    f1 = joint_raw["ratio_of_means"] <= 0.80 and penalized["proposed_vs_monolith"]["wins"] >= 35

    proposed_rows = [index[("over_low", instance_id, PROPOSED)] for instance_id in over_low]
    monolith_rows = [index[("over_low", instance_id, MONOLITH)] for instance_id in over_low]
    successes = [row for row in proposed_rows if row["solved"]]
    failures = [row for row in proposed_rows if not row["solved"]]
    ws = mean(float(row["aggregate_work"]) for row in successes) if successes else 20000.0
    wm = mean(float(row["aggregate_work"]) for row in monolith_rows)
    q = len(failures) / len(proposed_rows)
    q_star = (wm - ws) / (20000.0 - ws) if ws < wm and ws < 20000.0 else None
    mono_only = solve["proposed_vs_monolith"]["right_only"]
    t1 = q_star is not None and q > q_star and mono_only >= 2 and penalized["proposed_vs_monolith"]["ratio_of_means"] >= 1.0
    tail = {
        "W_success": ws,
        "W_monolith": wm,
        "q": q,
        "q_star": q_star,
        "proposed_failures": len(failures),
        "monolith_only_solves": mono_only,
        "penalized_work_ratio": penalized["proposed_vs_monolith"]["ratio_of_means"],
    }

    central_rows = [index[("over_low", instance_id, CENTRAL)] for instance_id in over_low]
    proposed_failure_ids = {str(row["instance_id"]) for row in failures}
    central_failure_ids = {str(row["instance_id"]) for row in central_rows if not row["solved"]}
    shared = len(proposed_failure_ids & central_failure_ids)
    shared_fraction = shared / max(len(proposed_failure_ids), 1)
    central_solve = mean(float(row["solved"]) for row in central_rows)
    proposed_solve = mean(float(row["solved"]) for row in proposed_rows)
    t2 = abs(proposed_solve - central_solve) <= 0.05 and shared_fraction >= 0.50
    same_order = {
        "proposed_solve": proposed_solve,
        "central_solve": central_solve,
        "solve_difference_absolute": abs(proposed_solve - central_solve),
        "proposed_failures": len(proposed_failure_ids),
        "shared_failures": shared,
        "shared_failure_fraction": shared_fraction,
    }

    high_rows = [index[("over_high", instance_id, PROPOSED)] for instance_id in ids["over_high"]]
    low_penalized = [float(row["penalized_work"]) for row in proposed_rows]
    high_penalized = [float(row["penalized_work"]) for row in high_rows]
    coupling = _independent_ratio(high_penalized, low_penalized, 9201)
    coupling["solve_low"] = proposed_solve
    coupling["solve_high"] = mean(float(row["solved"]) for row in high_rows)
    coupling["solve_difference_high_minus_low"] = coupling["solve_high"] - coupling["solve_low"]
    solved_low = [float(row["aggregate_work"]) for row in proposed_rows if row["solved"]]
    solved_high = [float(row["aggregate_work"]) for row in high_rows if row["solved"]]
    coupling["solved_only_low_mean"] = mean(solved_low) if solved_low else None
    coupling["solved_only_high_mean"] = mean(solved_high) if solved_high else None
    c1 = coupling["ratio_of_means"] >= 1.20 or coupling["solve_high"] <= coupling["solve_low"] - 0.10

    mechanism_cells = {}
    n1 = False
    r1 = False
    for cell in ("over_low", "over_high"):
        cell_ids = ids[cell]
        no_cross_solve = _solve_contrast(index, cell_ids, cell, PROPOSED, NO_CROSS)
        no_cross_rows = [index[(cell, instance_id, NO_CROSS)] for instance_id in cell_ids]
        no_cross_failure_rate = mean(float(row["status"] == "NO_CROSS_RECOVERY") for row in no_cross_rows)
        necessary = no_cross_solve["solve_difference"] >= 0.20 or no_cross_failure_rate >= 0.25
        n1 = n1 or necessary
        random_solve = _solve_contrast(index, cell_ids, cell, PROPOSED, RANDOM)
        random_work = _work_contrast(index, cell_ids, cell, PROPOSED, RANDOM, "penalized_work", 9301 if cell == "over_low" else 9302)
        proposed_noninferior = random_solve["solve_difference"] >= -0.10
        random_noninferior = random_solve["solve_difference"] <= 0.10
        identifiable = abs(random_solve["solve_difference"]) >= 0.10 or (
            proposed_noninferior and random_work["ratio_of_means"] <= 0.80
        ) or (
            random_noninferior and random_work["ratio_of_means"] >= 1.25
        )
        r1 = r1 or identifiable
        mechanism_cells[cell] = {
            "proposed_vs_no_cross_solve": no_cross_solve,
            "no_cross_failure_rate": no_cross_failure_rate,
            "coordination_necessary": necessary,
            "proposed_vs_random_solve": random_solve,
            "proposed_vs_random_work": random_work,
            "route_identifiable": identifiable,
        }

    strong_solve = all(
        solve[key]["solve_difference"] >= -0.10
        and solve[key]["control_only_discordance_cp_upper95"] <= 0.10
        for key in ("proposed_vs_monolith", "proposed_vs_sharded")
    )
    strong_work = all(
        penalized[key]["bootstrap_ci95"][1] <= 0.80
        for key in ("proposed_vs_monolith", "proposed_vs_sharded")
    )
    strong_positive = strong_solve and strong_work and not t1

    protocol_pass = bool(raw["protocol_audit"]["pass"])
    if not protocol_pass:
        verdict = "SAT_PROTOCOL_FAIL"
    elif f1 and t1 and t2 and c1 and n1:
        verdict = "SAT_TAIL_RISK_REPLICATION"
    elif strong_positive:
        verdict = "SAT_STRONG_FACTORIZATION_POSITIVE"
    elif not f1:
        verdict = "SAT_NO_FREQUENT_FACTOR_GAIN"
    else:
        verdict = "SAT_MIXED_NO_REPLICATION"

    return {
        "schema": "multiagent_community_sat_analysis_v1",
        "status": verdict,
        "study_role": "independent_second_substrate_replication",
        "headline_eligible": False,
        "raw_results": str(raw_path.relative_to(REPO_ROOT)),
        "raw_results_sha256": _sha256(raw_path),
        "execution_lock": str(lock_path.relative_to(REPO_ROOT)),
        "execution_lock_sha256": _sha256(lock_path),
        "lock_checks": lock_checks,
        "summary": summary,
        "solve_contrasts": solve,
        "penalized_work_contrasts": penalized,
        "jointly_solved_raw_work": joint_raw,
        "tail_risk": tail,
        "same_order": same_order,
        "coupling": coupling,
        "mechanism_cells": mechanism_cells,
        "gates": {
            "protocol": protocol_pass,
            "F1_frequent_case_factorization": f1,
            "T1_tail_risk_reversal": t1,
            "T2_same_order_boundary": t2,
            "C1_coupling_boundary": c1,
            "N1_coordination_necessity": n1,
            "R1_route_identifiability_secondary": r1,
            "strong_positive_solve": strong_solve,
            "strong_positive_work": strong_work,
        },
        "protocol_audit": raw["protocol_audit"],
        "limitations": [
            "Symbolic planted community 3-SAT only; no LLM or wall-clock claim.",
            "Pure fixed-order search omits unit propagation to keep rollback dependencies matched and auditable.",
            "The algorithmic ingredients have classical DisCSP/DCOP and backtracking precedents.",
        ],
    }


def _fmt(value: float | None, digits: int = 3) -> str:
    return "NA" if value is None else f"{float(value):.{digits}f}"


def _phase_table(summary: list[dict[str, Any]]) -> str:
    lines = [
        "| Cell | Arm | Solve | Penalized work | Raw work | Rounds | Status |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in summary:
        statuses = ", ".join(f"{key}={value}" for key, value in sorted(row["status_counts"].items()))
        lines.append(
            f"| {row['cell']} | `{row['arm']}` | {_fmt(row['solve_rate'])} | "
            f"{_fmt(row['mean_penalized_work'], 1)} | {_fmt(row['mean_aggregate_work'], 1)} | "
            f"{_fmt(row['mean_parallel_rounds'], 1)} | {statuses} |"
        )
    return "\n".join(lines)


def _render(payload: dict[str, Any]) -> str:
    tail = payload["tail_risk"]
    joint = payload["jointly_solved_raw_work"]
    coupling = payload["coupling"]
    lines = [
        "# Community SAT Independent Replication",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Substrate: planted fixed-density community 3-SAT",
        "- Instances: 200 independent (50/cell)",
        "- GPU/LLM use: none",
        "",
        "## Frozen gates",
        "",
        "| Gate | Result |",
        "|---|---:|",
    ]
    for key, value in payload["gates"].items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")
    lines.extend([
        "",
        "## Over-low frequent-case and tail",
        "",
        f"- Jointly-solved proposed/monolith raw-work ratio: `{_fmt(joint['ratio_of_means'])}`; bootstrap 95% CI `[{_fmt(joint['bootstrap_ci95'][0])}, {_fmt(joint['bootstrap_ci95'][1])}]`.",
        f"- Failure-penalized paired wins/ties/losses: `{payload['penalized_work_contrasts']['proposed_vs_monolith']['wins']}/{payload['penalized_work_contrasts']['proposed_vs_monolith']['ties']}/{payload['penalized_work_contrasts']['proposed_vs_monolith']['losses']}`.",
        f"- Proposed failures: `{tail['proposed_failures']}/50`; monolith-only solves: `{tail['monolith_only_solves']}`.",
        f"- $W_s={_fmt(tail['W_success'],1)}$, $W_m={_fmt(tail['W_monolith'],1)}$, $q={_fmt(tail['q'])}$, $q^*={_fmt(tail['q_star'])}$.",
        f"- Failure-penalized proposed/monolith ratio: `{_fmt(tail['penalized_work_ratio'])}`.",
        "",
        "## Same-order boundary",
        "",
        f"- Proposed solve: `{_fmt(payload['same_order']['proposed_solve'])}`; central-factorized solve: `{_fmt(payload['same_order']['central_solve'])}`.",
        f"- Shared proposed failures: `{payload['same_order']['shared_failures']}/{payload['same_order']['proposed_failures']}`.",
        "",
        "## Coupling",
        "",
        f"- Over-high/over-low penalized-work ratio: `{_fmt(coupling['ratio_of_means'])}`; bootstrap CI `[{_fmt(coupling['bootstrap_ci95'][0])}, {_fmt(coupling['bootstrap_ci95'][1])}]`.",
        f"- Solve low/high: `{_fmt(coupling['solve_low'])}` / `{_fmt(coupling['solve_high'])}`.",
        f"- Solved-only work low/high: `{_fmt(coupling['solved_only_low_mean'],1)}` / `{_fmt(coupling['solved_only_high_mean'],1)}`.",
        "",
        "## Full phase table",
        "",
        _phase_table(payload["summary"]),
        "",
        "## Protocol",
        "",
    ])
    for key, value in payload["protocol_audit"]["checks"].items():
        lines.append(f"- `{key}`: **{'PASS' if value else 'FAIL'}**")
    lines.extend([
        "",
        "## Claim boundary",
        "",
        "A tail-risk replication supports a cross-substrate symbolic boundary result: local factorization can be much cheaper conditionally while remaining worse in expected work because rare failures dominate. It does not establish algorithm novelty, LLM-agent advantage, or measured parallel speedup.",
        "",
        "## Artifacts",
        "",
        "- [Raw results](raw_results.json)",
        "- [Analysis JSON](analysis.json)",
        "- [Independent manifest](../multiagent_community_sat_manifest/GENERATION.md)",
        "- [Frozen contract](../../specs/multiagent_community_sat_replication_contract_v1.md)",
        "- [Analysis amendment](../../specs/multiagent_community_sat_analysis_amendment_v1.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze independent community-SAT replication.")
    parser.add_argument("--raw", type=Path, default=Path("results/multiagent_community_sat_replication/raw_results.json"))
    parser.add_argument("--execution-lock", type=Path, default=Path("specs/multiagent_community_sat_execution_lock_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_community_sat_replication"))
    args = parser.parse_args()
    raw_path = _resolve(args.raw)
    lock_path = _resolve(args.execution_lock)
    payload = analyze(raw_path, lock_path)
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "RESULTS.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "report": str((output_dir / "RESULTS.md").relative_to(REPO_ROOT)),
        "analysis": str((output_dir / "analysis.json").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
