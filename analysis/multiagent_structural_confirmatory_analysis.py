"""Frozen statistical analysis for the structural confirmatory study."""

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

from experiments.capacity.stats import holm_bonferroni, mcnemar_exact
from experiments.multiagent_capacity_coupling import REPO_ROOT


EXPECTED_LOCK_SCHEMA = "multiagent_structural_confirmatory_execution_lock_v1"
PROPOSED = "independent_local_cbj_v1_exact"
CENTRAL_FACTOR = "factorized_central_cbj"
RANDOM_VALID = "independent_local_random_valid"
NO_CROSS = "independent_local_no_cross"
MONOLITH_MR = "monolith_MR"
SHARDED_MR = "centralized_sharded_MR"
BOOTSTRAP_REPLICATES = 100_000
ALPHA = 0.05


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _verify_lock(lock_path: Path) -> tuple[dict[str, Any], dict[str, bool]]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("schema") != EXPECTED_LOCK_SCHEMA or lock.get("status") != "EXECUTION_LOCKED":
        raise ValueError("invalid execution lock")
    checks = {
        name: _sha256(_resolve(item["path"])) == str(item["sha256"])
        for name, item in lock["files"].items()
    }
    if not all(checks.values()):
        raise ValueError(f"analysis lock mismatch: {checks}")
    return lock, checks


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    location = probability * (len(ordered) - 1)
    lower = int(location)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = location - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _binomial_cdf(k: int, n: int, p: float) -> float:
    return sum(comb(n, index) * p**index * (1.0 - p) ** (n - index) for index in range(k + 1))


def _clopper_pearson_upper(k: int, n: int, alpha: float = ALPHA) -> float:
    if n <= 0 or k < 0 or k > n:
        raise ValueError("invalid binomial count")
    if k == n:
        return 1.0
    low = k / n
    high = 1.0
    for _ in range(100):
        midpoint = (low + high) / 2.0
        if _binomial_cdf(k, n, midpoint) > alpha:
            low = midpoint
        else:
            high = midpoint
    return high


def _one_sided_sign_p(wins: int, losses: int) -> float:
    n = int(wins) + int(losses)
    if n == 0:
        return 1.0
    return sum(comb(n, value) for value in range(int(wins), n + 1)) / (2**n)


def _one_sided_mcnemar_p(left_only: int, right_only: int) -> float:
    discordant = int(left_only) + int(right_only)
    if discordant == 0:
        return 1.0
    return sum(comb(discordant, value) for value in range(int(left_only), discordant + 1)) / (2**discordant)


def _paired_ratio(
    left: list[float],
    right: list[float],
    seed: int,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    if len(left) != len(right) or not left:
        raise ValueError("paired ratio requires equal nonempty vectors")
    ratio = mean(left) / max(mean(right), 1e-12)
    generator = random.Random(int(seed))
    samples = []
    n = len(left)
    for _ in range(int(replicates)):
        indices = [generator.randrange(n) for _ in range(n)]
        samples.append(
            sum(left[index] for index in indices)
            / max(sum(right[index] for index in indices), 1e-12)
        )
    wins = sum(a < b for a, b in zip(left, right))
    ties = sum(a == b for a, b in zip(left, right))
    losses = sum(a > b for a, b in zip(left, right))
    return {
        "n": n,
        "left_mean": mean(left),
        "right_mean": mean(right),
        "ratio_of_means": ratio,
        "bootstrap_ci95": [_quantile(samples, 0.025), _quantile(samples, 0.975)],
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "one_sided_sign_p": _one_sided_sign_p(wins, losses),
    }


def _independent_ratio(
    numerator: list[float],
    denominator: list[float],
    seed: int,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    generator = random.Random(int(seed))
    samples = []
    for _ in range(int(replicates)):
        top = [numerator[generator.randrange(len(numerator))] for _ in range(len(numerator))]
        bottom = [denominator[generator.randrange(len(denominator))] for _ in range(len(denominator))]
        samples.append(mean(top) / max(mean(bottom), 1e-12))
    return {
        "numerator_mean": mean(numerator),
        "denominator_mean": mean(denominator),
        "ratio_of_means": mean(numerator) / max(mean(denominator), 1e-12),
        "bootstrap_ci95": [_quantile(samples, 0.025), _quantile(samples, 0.975)],
    }


def _permutation_high_greater(
    high: list[float],
    low: list[float],
    seed: int,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> float:
    observed = mean(high) - mean(low)
    pooled = list(high) + list(low)
    n_high = len(high)
    generator = random.Random(int(seed))
    extreme = 0
    for _ in range(int(replicates)):
        shuffled = list(pooled)
        generator.shuffle(shuffled)
        difference = mean(shuffled[:n_high]) - mean(shuffled[n_high:])
        extreme += int(difference >= observed)
    return (extreme + 1) / (int(replicates) + 1)


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
            "mean_requests": mean(float(row["requests_sent"]) for row in subset),
            "mean_communication_tokens": mean(float(row["communication_tokens"]) for row in subset),
            "status_counts": dict(Counter(str(row["status"]) for row in subset)),
        })
    return output


def _index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        (str(row["cell"]), str(row["instance_id"]), str(row["arm"])): row
        for row in rows
    }


def _ids(rows: list[dict[str, Any]], cell: str) -> list[str]:
    return sorted({str(row["instance_id"]) for row in rows if row["cell"] == cell})


def _solve_contrast(
    index: dict[tuple[str, str, str], dict[str, Any]],
    instance_ids: list[str],
    cell: str,
    left_arm: str,
    right_arm: str,
) -> dict[str, Any]:
    left = [bool(index[(cell, instance_id, left_arm)]["solved"]) for instance_id in instance_ids]
    right = [bool(index[(cell, instance_id, right_arm)]["solved"]) for instance_id in instance_ids]
    left_only = sum(a and not b for a, b in zip(left, right))
    right_only = sum(b and not a for a, b in zip(left, right))
    return {
        "cell": cell,
        "left_arm": left_arm,
        "right_arm": right_arm,
        "n": len(instance_ids),
        "left_solve_rate": mean(map(float, left)),
        "right_solve_rate": mean(map(float, right)),
        "solve_difference": mean(map(float, left)) - mean(map(float, right)),
        "left_only": left_only,
        "right_only": right_only,
        "mcnemar_two_sided": mcnemar_exact(left, right),
        "mcnemar_one_sided_left_greater": _one_sided_mcnemar_p(left_only, right_only),
        "control_only_discordance_cp_upper95": _clopper_pearson_upper(right_only, len(instance_ids)),
    }


def _work_contrast(
    index: dict[tuple[str, str, str], dict[str, Any]],
    instance_ids: list[str],
    cell: str,
    left_arm: str,
    right_arm: str,
    seed: int,
) -> dict[str, Any]:
    left = [float(index[(cell, instance_id, left_arm)]["penalized_work"]) for instance_id in instance_ids]
    right = [float(index[(cell, instance_id, right_arm)]["penalized_work"]) for instance_id in instance_ids]
    return {
        "cell": cell,
        "left_arm": left_arm,
        "right_arm": right_arm,
        **_paired_ratio(left, right, seed),
    }


def _lookup(summary: list[dict[str, Any]], cell: str, arm: str) -> dict[str, Any]:
    return next(row for row in summary if row["cell"] == cell and row["arm"] == arm)


def analyze(raw_path: Path, lock_path: Path) -> dict[str, Any]:
    lock, lock_checks = _verify_lock(lock_path)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if raw.get("status") != "RAW_CONFIRMATORY_COMPLETE" or not raw.get("protocol_audit", {}).get("pass"):
        raise ValueError("raw confirmatory artifact is incomplete or protocol-invalid")
    if raw.get("input_hashes") != {name: item["sha256"] for name, item in lock["files"].items()}:
        raise ValueError("raw artifact input hashes differ from execution lock")
    rows = list(raw["rows"])
    if len(rows) != 1600:
        raise ValueError("unexpected raw row count")
    summary = _summary(rows)
    index = _index(rows)
    over_low_ids = _ids(rows, "over_low")
    over_high_ids = _ids(rows, "over_high")

    solve_contrasts = {
        "proposed_vs_monolith_MR": _solve_contrast(index, over_low_ids, "over_low", PROPOSED, MONOLITH_MR),
        "proposed_vs_sharded_MR": _solve_contrast(index, over_low_ids, "over_low", PROPOSED, SHARDED_MR),
        "central_factor_vs_monolith_MR": _solve_contrast(index, over_low_ids, "over_low", CENTRAL_FACTOR, MONOLITH_MR),
        "proposed_vs_central_factor": _solve_contrast(index, over_low_ids, "over_low", PROPOSED, CENTRAL_FACTOR),
    }
    work_contrasts = {
        "proposed_vs_monolith_MR": _work_contrast(index, over_low_ids, "over_low", PROPOSED, MONOLITH_MR, 8101),
        "proposed_vs_sharded_MR": _work_contrast(index, over_low_ids, "over_low", PROPOSED, SHARDED_MR, 8102),
        "central_factor_vs_monolith_MR": _work_contrast(index, over_low_ids, "over_low", CENTRAL_FACTOR, MONOLITH_MR, 8103),
        "proposed_vs_central_factor": _work_contrast(index, over_low_ids, "over_low", PROPOSED, CENTRAL_FACTOR, 8104),
    }

    proposed_low_work = [float(index[("over_low", instance_id, PROPOSED)]["penalized_work"]) for instance_id in over_low_ids]
    proposed_high_work = [float(index[("over_high", instance_id, PROPOSED)]["penalized_work"]) for instance_id in over_high_ids]
    coupling_effect = _independent_ratio(proposed_high_work, proposed_low_work, 8201)
    coupling_effect["permutation_p_high_greater"] = _permutation_high_greater(
        proposed_high_work,
        proposed_low_work,
        8202,
    )
    coupling_effect["over_low_solve"] = _lookup(summary, "over_low", PROPOSED)["solve_rate"]
    coupling_effect["over_high_solve"] = _lookup(summary, "over_high", PROPOSED)["solve_rate"]

    c1_parts = []
    for key in ("proposed_vs_monolith_MR", "proposed_vs_sharded_MR"):
        contrast = solve_contrasts[key]
        c1_parts.append(
            contrast["solve_difference"] >= -0.10
            and contrast["control_only_discordance_cp_upper95"] <= 0.10
        )
    c1 = all(c1_parts)
    c2 = all(
        work_contrasts[key]["ratio_of_means"] <= 0.80
        and work_contrasts[key]["bootstrap_ci95"][1] <= 0.80
        for key in ("proposed_vs_monolith_MR", "proposed_vs_sharded_MR")
    )
    central_solve = solve_contrasts["central_factor_vs_monolith_MR"]
    central_work = work_contrasts["central_factor_vs_monolith_MR"]
    decentral_solve = solve_contrasts["proposed_vs_central_factor"]
    decentral_work = work_contrasts["proposed_vs_central_factor"]
    c3 = (
        central_solve["solve_difference"] >= -0.10
        and central_solve["control_only_discordance_cp_upper95"] <= 0.10
        and central_work["ratio_of_means"] <= 0.80
        and central_work["bootstrap_ci95"][1] <= 0.80
        and decentral_solve["solve_difference"] >= -0.10
        and decentral_work["ratio_of_means"] <= 1.15
    )
    c4 = (
        coupling_effect["ratio_of_means"] >= 1.20
        and coupling_effect["over_high_solve"] <= coupling_effect["over_low_solve"]
    )

    route_cells = {}
    route_identifiable = False
    coordination_necessary = False
    for cell, ids in (("over_low", over_low_ids), ("over_high", over_high_ids)):
        route_solve = _solve_contrast(index, ids, cell, PROPOSED, RANDOM_VALID)
        route_work = _work_contrast(index, ids, cell, PROPOSED, RANDOM_VALID, 8301 if cell == "over_low" else 8302)
        solve_difference = abs(float(route_solve["solve_difference"]))
        proposed_noninferior = route_solve["solve_difference"] >= -0.10
        random_noninferior = route_solve["solve_difference"] <= 0.10
        work_identifiable = (
            proposed_noninferior and route_work["ratio_of_means"] <= 0.80
        ) or (
            random_noninferior and route_work["ratio_of_means"] >= 1.25
        )
        identifiable = solve_difference >= 0.10 or work_identifiable
        route_identifiable = route_identifiable or identifiable
        no_cross_solve = _solve_contrast(index, ids, cell, PROPOSED, NO_CROSS)
        no_cross_rows = [index[(cell, instance_id, NO_CROSS)] for instance_id in ids]
        no_cross_failure_rate = mean(float(row["status"] == "NO_CROSS_RECOVERY") for row in no_cross_rows)
        necessary = no_cross_solve["solve_difference"] >= 0.20 or no_cross_failure_rate >= 0.25
        coordination_necessary = coordination_necessary or necessary
        route_cells[cell] = {
            "deepest_vs_random_solve": route_solve,
            "deepest_vs_random_work": route_work,
            "route_identifiable": identifiable,
            "deepest_vs_no_cross_solve": no_cross_solve,
            "no_cross_recovery_failure_rate": no_cross_failure_rate,
            "coordination_necessary": necessary,
        }

    proposed_rows = [row for row in rows if row["arm"] == PROPOSED]
    recovery_rows = [row for row in proposed_rows if int(row["recoveries"]) > 0]
    preservation_fraction = mean(
        float(int(row["rollback_events_with_unrelated_preservation"]) > 0)
        for row in recovery_rows
    ) if recovery_rows else 0.0
    s1 = route_identifiable
    s2 = coordination_necessary
    s3 = preservation_fraction >= 0.25

    combined_over_ids = [("over_low", instance_id) for instance_id in over_low_ids] + [
        ("over_high", instance_id) for instance_id in over_high_ids
    ]
    proposed_only_no_cross = sum(
        bool(index[(cell, instance_id, PROPOSED)]["solved"])
        and not bool(index[(cell, instance_id, NO_CROSS)]["solved"])
        for cell, instance_id in combined_over_ids
    )
    no_cross_only = sum(
        bool(index[(cell, instance_id, NO_CROSS)]["solved"])
        and not bool(index[(cell, instance_id, PROPOSED)]["solved"])
        for cell, instance_id in combined_over_ids
    )
    p_values = {
        "H1_proposed_work_lt_monolith_MR": work_contrasts["proposed_vs_monolith_MR"]["one_sided_sign_p"],
        "H2_central_factor_work_lt_monolith_MR": work_contrasts["central_factor_vs_monolith_MR"]["one_sided_sign_p"],
        "H3_proposed_solve_gt_no_cross": _one_sided_mcnemar_p(proposed_only_no_cross, no_cross_only),
        "H4_high_coupling_work_gt_low": coupling_effect["permutation_p_high_greater"],
    }
    p_holm = holm_bonferroni(p_values)
    supporting_tests = [
        {
            "name": name,
            "p_raw": value,
            "p_holm": p_holm[name],
            "holm_significant_0_05": p_holm[name] < ALPHA,
        }
        for name, value in sorted(p_values.items())
    ]

    protocol_pass = bool(raw["protocol_audit"]["pass"])
    primary_pass = protocol_pass and c1 and c2 and c3 and c4
    if not protocol_pass:
        verdict = "CONFIRMATORY_PROTOCOL_FAIL"
    elif not primary_pass:
        verdict = "STRUCTURAL_CONFIRMATION_FAIL"
    elif s1 and s2 and s3:
        verdict = "SYMBOLIC_STRUCTURAL_CONFIRMATION_PASS"
    else:
        verdict = "FACTORIZATION_CONFIRMED_ROUTING_UNRESOLVED"

    return {
        "schema": "multiagent_structural_confirmatory_analysis_v1",
        "status": verdict,
        "study_role": "one_shot_independent_symbolic_confirmation",
        "headline_eligible": False,
        "raw_results": str(raw_path.relative_to(REPO_ROOT)),
        "raw_results_sha256": _sha256(raw_path),
        "execution_lock": str(lock_path.relative_to(REPO_ROOT)),
        "execution_lock_sha256": _sha256(lock_path),
        "lock_checks": lock_checks,
        "summary": summary,
        "solve_contrasts": solve_contrasts,
        "work_contrasts": work_contrasts,
        "coupling_effect": coupling_effect,
        "route_cells": route_cells,
        "preservation": {
            "recovery_episodes": len(recovery_rows),
            "episodes_with_unrelated_preservation": sum(
                int(row["rollback_events_with_unrelated_preservation"] > 0) for row in recovery_rows
            ),
            "fraction": preservation_fraction,
        },
        "primary_gates": {
            "C1_equal_memory_solve_noninferiority": c1,
            "C2_penalized_work_advantage": c2,
            "C3_same_order_factorization": c3,
            "C4_coupling_boundary": c4,
        },
        "secondary_gates": {
            "S1_route_identifiability": s1,
            "S2_coordination_necessity": s2,
            "S3_unrelated_work_preservation": s3,
        },
        "supporting_tests_holm": supporting_tests,
        "protocol_audit": raw["protocol_audit"],
        "limitations": [
            "Symbolic graph-coloring confirmation; no LLM decision quality is tested.",
            "The successful mechanism uses immediate shared current-assignment visibility and bounded owner-local rollback; it is not a fully asynchronous network protocol.",
            "Parallel rounds are idealized and are not measured wall-clock speedup.",
            "The factorization ingredients overlap classical distributed CSP and backtracking; novelty requires the separate literature audit and is scoped to the resource-controlled phase law.",
            "A second substrate is required before making a general capacity-coupling claim.",
        ],
    }


def _fmt(value: float, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


def _table(summary: list[dict[str, Any]]) -> str:
    selected = {PROPOSED, CENTRAL_FACTOR, RANDOM_VALID, NO_CROSS, MONOLITH_MR, SHARDED_MR, "monolith_R"}
    lines = [
        "| Cell | Arm | Solve | Penalized work | Raw work | Rounds | Requests | Status |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in summary:
        if row["arm"] not in selected:
            continue
        statuses = ", ".join(f"{key}={value}" for key, value in sorted(row["status_counts"].items()))
        lines.append(
            f"| {row['cell']} | `{row['arm']}` | {_fmt(row['solve_rate'])} | "
            f"{_fmt(row['mean_penalized_work'], 1)} | {_fmt(row['mean_aggregate_work'], 1)} | "
            f"{_fmt(row['mean_parallel_rounds'], 1)} | {_fmt(row['mean_requests'], 1)} | {statuses} |"
        )
    return "\n".join(lines)


def _render(payload: dict[str, Any]) -> str:
    c = payload["primary_gates"]
    s = payload["secondary_gates"]
    work = payload["work_contrasts"]["proposed_vs_monolith_MR"]
    solve = payload["solve_contrasts"]["proposed_vs_monolith_MR"]
    central_work = payload["work_contrasts"]["central_factor_vs_monolith_MR"]
    coupling = payload["coupling_effect"]
    lines = [
        "# Independent Symbolic Structural Confirmation",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "This is a one-shot symbolic confirmation on a new 200-instance manifest. It is not an LLM or general-novelty headline.",
        "",
        "- [Raw results](raw_results.json)",
        "- [Analysis JSON](analysis.json)",
        "- [Preregistration](../../specs/multiagent_structural_confirmatory_preregistration_v1.md)",
        "- [Manifest generation](../multiagent_structural_confirmatory_manifest/GENERATION.md)",
        "- [Control preflight](../multiagent_structural_confirmatory_preflight/PREFLIGHT.md)",
        "",
        "## Primary gates",
        "",
        "| Gate | Result |",
        "|---|---:|",
    ]
    for key, value in c.items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")
    lines.extend([
        "",
        "## Secondary mechanism gates",
        "",
        "| Gate | Result |",
        "|---|---:|",
    ])
    for key, value in s.items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")
    lines.extend([
        "",
        "## Equal-resource sweet spot (`over_low`)",
        "",
        f"- Proposed solve: `{_fmt(solve['left_solve_rate'])}`; monolith-MR solve: `{_fmt(solve['right_solve_rate'])}`; difference: `{_fmt(solve['solve_difference'])}`.",
        f"- Control-only discordance upper 95% bound: `{_fmt(solve['control_only_discordance_cp_upper95'])}`.",
        f"- Proposed/monolith penalized-work ratio: `{_fmt(work['ratio_of_means'])}`; bootstrap 95% CI `[{_fmt(work['bootstrap_ci95'][0])}, {_fmt(work['bootstrap_ci95'][1])}]`.",
        f"- Paired work wins/ties/losses: `{work['wins']}/{work['ties']}/{work['losses']}`.",
        f"- Central-factorized/monolith work ratio: `{_fmt(central_work['ratio_of_means'])}`; CI upper `{_fmt(central_work['bootstrap_ci95'][1])}`.",
        "",
        "## Coupling boundary",
        "",
        f"- Over-high/over-low penalized-work ratio: `{_fmt(coupling['ratio_of_means'])}`; bootstrap 95% CI `[{_fmt(coupling['bootstrap_ci95'][0])}, {_fmt(coupling['bootstrap_ci95'][1])}]`.",
        f"- Solve low/high: `{_fmt(coupling['over_low_solve'])}` / `{_fmt(coupling['over_high_solve'])}`.",
        "",
        "## Full phase table",
        "",
        _table(payload["summary"]),
        "",
        "## Protocol audit",
        "",
    ])
    for key, value in payload["protocol_audit"]["checks"].items():
        lines.append(f"- `{key}`: **{'PASS' if value else 'FAIL'}**")
    totals = payload["protocol_audit"]["totals"]
    lines.extend([
        "",
        f"Requests sent/acknowledged: `{totals['requests_sent']}` / `{totals['acknowledgements']}`; out-of-window executions: `{totals['out_of_window_executions']}`.",
        "",
        "## Holm-corrected supporting tests",
        "",
        "| Test | Raw p | Holm p | Significant |",
        "|---|---:|---:|---:|",
    ])
    for row in payload["supporting_tests_holm"]:
        lines.append(
            f"| `{row['name']}` | {row['p_raw']:.6g} | {row['p_holm']:.6g} | "
            f"{'yes' if row['holm_significant_0_05'] else 'no'} |"
        )
    lines.extend([
        "",
        "## Claim boundary",
        "",
        "A PASS supports a graph-coloring-specific symbolic claim that owner-local factorization changes rollback geometry and can reduce aggregate work under equal total recovery memory in the preregistered sweet spot. It does not show that the classical distributed-search ingredients are novel, that Qwen routing helps, that wall-clock speed improves, or that the law generalizes beyond this substrate.",
        "",
        "## Required next evidence",
        "",
        "1. Complete the literature audit and phrase novelty around the resource-controlled phase law rather than distributed backtracking itself.",
        "2. Replicate the direction on a second decomposable substrate.",
        "3. Only then test sparse Qwen routing against deepest, random-valid, no-cross, and symbolic controls under matched budgets.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze locked structural confirmation.")
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path("results/multiagent_structural_confirmatory/raw_results.json"),
    )
    parser.add_argument(
        "--execution-lock",
        type=Path,
        default=Path("specs/multiagent_structural_confirmatory_execution_lock_v1.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/multiagent_structural_confirmatory"),
    )
    args = parser.parse_args()
    raw_path = args.raw if args.raw.is_absolute() else REPO_ROOT / args.raw
    lock_path = args.execution_lock if args.execution_lock.is_absolute() else REPO_ROOT / args.execution_lock
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    payload = analyze(raw_path, lock_path)
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
