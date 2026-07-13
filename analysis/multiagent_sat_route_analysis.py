"""Frozen analysis for the independent SAT route-identifiability confirmation."""

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

from analysis.multiagent_sat_route_run import ARMS, verify_lock
from experiments.capacity.stats import mcnemar_exact
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.multiagent_community_sat import summarize_rows


DEEPEST = "independent_local_cbj_sat"
RANDOM = "independent_local_random_valid_sat"
NO_CROSS = "independent_local_no_cross_sat"
CENTRAL = "factorized_central_cbj_sat"
MONOLITH = "monolith_MR_sat"
BOOTSTRAPS = 100000
BOOTSTRAP_SEED = 2026071201


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    location = probability * (len(ordered) - 1)
    lower = int(location)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = location - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _mcnemar_one_sided(left_only: int, right_only: int) -> float:
    discordant = int(left_only) + int(right_only)
    if discordant == 0:
        return 1.0
    return sum(comb(discordant, value) for value in range(int(left_only), discordant + 1)) / (2**discordant)


def _solve_contrast(index: dict[tuple[str, str], dict[str, Any]], ids: list[str], left_arm: str, right_arm: str) -> dict[str, Any]:
    left = [bool(index[(instance_id, left_arm)]["solved"]) for instance_id in ids]
    right = [bool(index[(instance_id, right_arm)]["solved"]) for instance_id in ids]
    left_only = sum(a and not b for a, b in zip(left, right))
    right_only = sum(b and not a for a, b in zip(left, right))
    return {
        "left_arm": left_arm,
        "right_arm": right_arm,
        "n": len(ids),
        "left_solve_rate": mean(map(float, left)),
        "right_solve_rate": mean(map(float, right)),
        "solve_difference": mean(map(float, left)) - mean(map(float, right)),
        "left_only": left_only,
        "right_only": right_only,
        "mcnemar_two_sided": mcnemar_exact(left, right),
        "mcnemar_one_sided_left_superior": _mcnemar_one_sided(left_only, right_only),
    }


def _work_contrast(
    index: dict[tuple[str, str], dict[str, Any]],
    ids: list[str],
    left_arm: str,
    right_arm: str,
    seed: int,
) -> dict[str, Any]:
    left = [float(index[(instance_id, left_arm)]["penalized_work"]) for instance_id in ids]
    right = [float(index[(instance_id, right_arm)]["penalized_work"]) for instance_id in ids]
    generator = random.Random(int(seed))
    ratios: list[float] = []
    for _ in range(BOOTSTRAPS):
        sampled = [generator.randrange(len(ids)) for _ in ids]
        ratios.append(
            sum(left[item] for item in sampled)
            / max(sum(right[item] for item in sampled), 1e-12)
        )
    return {
        "left_arm": left_arm,
        "right_arm": right_arm,
        "field": "failure_penalized_work",
        "n": len(ids),
        "left_mean": mean(left),
        "right_mean": mean(right),
        "ratio_of_means": mean(left) / max(mean(right), 1e-12),
        "bootstrap_replicates": BOOTSTRAPS,
        "bootstrap_seed": int(seed),
        "bootstrap_ci95": [_quantile(ratios, 0.025), _quantile(ratios, 0.975)],
        "wins": sum(a < b for a, b in zip(left, right)),
        "ties": sum(a == b for a, b in zip(left, right)),
        "losses": sum(a > b for a, b in zip(left, right)),
    }


def analyze(raw_path: Path, lock_path: Path) -> dict[str, Any]:
    lock, lock_checks = verify_lock(lock_path)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    expected_hashes = {key: item["sha256"] for key, item in lock["files"].items()}
    if raw.get("input_hashes") != expected_hashes:
        raise ValueError("route-confirmation raw input hashes differ from execution lock")
    rows = list(raw.get("rows", []))
    index = {(str(row["instance_id"]), str(row["arm"])): row for row in rows}
    ids = sorted({str(row["instance_id"]) for row in rows})
    if len(rows) != 1000 or len(ids) != 200 or set(str(row["arm"]) for row in rows) != set(ARMS):
        raise ValueError("route-confirmation raw cardinality mismatch")

    primary_solve = _solve_contrast(index, ids, DEEPEST, RANDOM)
    primary_work = _work_contrast(index, ids, DEEPEST, RANDOM, BOOTSTRAP_SEED)
    secondary = {
        "deepest_vs_no_cross_solve": _solve_contrast(index, ids, DEEPEST, NO_CROSS),
        "deepest_vs_no_cross_work": _work_contrast(index, ids, DEEPEST, NO_CROSS, BOOTSTRAP_SEED + 1),
        "deepest_vs_central_solve": _solve_contrast(index, ids, DEEPEST, CENTRAL),
        "deepest_vs_central_work": _work_contrast(index, ids, DEEPEST, CENTRAL, BOOTSTRAP_SEED + 2),
        "deepest_vs_monolith_solve": _solve_contrast(index, ids, DEEPEST, MONOLITH),
        "deepest_vs_monolith_work": _work_contrast(index, ids, DEEPEST, MONOLITH, BOOTSTRAP_SEED + 3),
    }
    p0 = (
        raw.get("status") == "SAT_ROUTE_CONFIRMATION_RAW_COMPLETE"
        and bool(raw.get("protocol_audit", {}).get("pass"))
        and all(raw.get("cardinality", {}).values())
        and all(lock_checks.values())
    )
    p1 = primary_solve["solve_difference"] >= 0.10
    p2 = primary_solve["mcnemar_one_sided_left_superior"] <= 0.05
    p3 = primary_work["ratio_of_means"] <= 0.90 and primary_work["bootstrap_ci95"][1] < 1.00
    gates = {
        "P0_execution_integrity": p0,
        "P1_solve_difference_ge_0_10": p1,
        "P2_mcnemar_one_sided_le_0_05": p2,
        "P3_penalized_work_ratio_and_ci": p3,
    }
    if not p0:
        status = "SAT_ROUTE_CONFIRMATION_PROTOCOL_FAIL"
    elif all(gates.values()):
        status = "SAT_ROUTE_CONFIRMATION_GO_QWEN_DEV"
    else:
        status = "SAT_ROUTE_CONFIRMATION_NO_GO"

    return {
        "schema": "multiagent_sat_route_confirmation_analysis_v1",
        "status": status,
        "study_role": "independent_symbolic_prerequisite_for_sat_qwen_route_development",
        "headline_eligible": False,
        "qwen_development_authorized": status == "SAT_ROUTE_CONFIRMATION_GO_QWEN_DEV",
        "raw_results": str(raw_path.relative_to(REPO_ROOT)),
        "raw_results_sha256": _sha256(raw_path),
        "execution_lock": str(lock_path.relative_to(REPO_ROOT)),
        "execution_lock_sha256": _sha256(lock_path),
        "lock_checks": lock_checks,
        "gates": gates,
        "primary_solve": primary_solve,
        "primary_penalized_work": primary_work,
        "secondary_controls": secondary,
        "summary": summarize_rows(rows),
        "protocol_audit": raw["protocol_audit"],
        "claim_boundary": {
            "supported_if_go": "Rollback-route choice is an identifiable control variable in the frozen high-coupling owner-local SAT regime.",
            "not_supported": [
                "Qwen or LLM routing quality",
                "algorithm novelty",
                "multi-agent superiority over equal-memory monolith",
                "generalization beyond the frozen community-SAT regime",
            ],
        },
    }


def _fmt(value: float, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


def _render(payload: dict[str, Any]) -> str:
    solve = payload["primary_solve"]
    work = payload["primary_penalized_work"]
    lines = [
        "# Community-SAT Route Identifiability Confirmation",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Instances: 200 untouched high-coupling, over-local-fit community-SAT instances",
        "- Arms: deepest, random-valid, no-cross, central-deepest, and equal-memory monolith",
        "- GPU/LLM use: none",
        f"- Qwen development authorized: **{'Yes' if payload['qwen_development_authorized'] else 'No'}**",
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
        "## Primary deepest versus random-valid contrast",
        "",
        f"- Solve: `{_fmt(solve['left_solve_rate'])}` versus `{_fmt(solve['right_solve_rate'])}`; difference `{_fmt(solve['solve_difference'])}`.",
        f"- Paired discordances, deepest-only/random-only: `{solve['left_only']}/{solve['right_only']}`.",
        f"- One-sided exact McNemar probability: `{solve['mcnemar_one_sided_left_superior']:.6g}`.",
        f"- Failure-penalized work: `{_fmt(work['left_mean'], 1)}` versus `{_fmt(work['right_mean'], 1)}`.",
        f"- Penalized-work ratio: `{_fmt(work['ratio_of_means'])}`; paired-bootstrap 95% CI `[{_fmt(work['bootstrap_ci95'][0])}, {_fmt(work['bootstrap_ci95'][1])}]`.",
        f"- Paired work wins/ties/losses: `{work['wins']}/{work['ties']}/{work['losses']}`.",
        "",
        "## Arm summary",
        "",
        "| Arm | Solve | Penalized work | Raw work | Status |",
        "|---|---:|---:|---:|---|",
    ])
    for row in payload["summary"]:
        statuses = ", ".join(f"{key}={value}" for key, value in sorted(row["status_counts"].items()))
        lines.append(
            f"| `{row['arm']}` | {_fmt(row['solve_rate'])} | {_fmt(row['mean_penalized_work'], 1)} | "
            f"{_fmt(row['mean_aggregate_work'], 1)} | {statuses} |"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
    ])
    if payload["qwen_development_authorized"]:
        lines.append(
            "The preregistered route-identifiability prerequisite passed. A bounded, development-only SAT Qwen route gate may now be run against deepest, random-valid, and no-cross controls. This result is not itself an LLM claim."
        )
    else:
        lines.append(
            "The preregistered route-identifiability prerequisite failed. The SAT Qwen route premise is not authorized, regardless of secondary controls."
        )
    lines.extend([
        "",
        "## Claim boundary",
        "",
        "This study can identify route choice as a testable control variable. It cannot establish Qwen quality, algorithm novelty, equal-resource multi-agent superiority, or generalization beyond this SAT regime.",
        "",
        "## Artifacts",
        "",
        "- [Raw results](raw_results.json)",
        "- [Analysis JSON](analysis.json)",
        "- [Frozen manifest](../multiagent_sat_route_manifest/GENERATION.md)",
        "- [Preregistration](../../specs/multiagent_sat_route_confirmation_v1.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze SAT route-identifiability confirmation.")
    parser.add_argument("--raw", type=Path, default=Path("results/multiagent_sat_route_confirmation/raw_results.json"))
    parser.add_argument("--execution-lock", type=Path, default=Path("specs/multiagent_sat_route_confirmation_execution_lock_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_sat_route_confirmation"))
    args = parser.parse_args()
    raw_path = _resolve(args.raw)
    lock_path = _resolve(args.execution_lock)
    payload = analyze(raw_path, lock_path)
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "RESULTS.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "qwen_development_authorized": payload["qwen_development_authorized"],
        "report": str((output_dir / "RESULTS.md").relative_to(REPO_ROOT)),
        "analysis": str((output_dir / "analysis.json").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
