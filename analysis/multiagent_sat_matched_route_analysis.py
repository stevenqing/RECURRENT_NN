"""Frozen analysis for independent matched-window SAT route confirmation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from analysis.multiagent_community_sat_analysis import _cp_upper
from analysis.multiagent_sat_matched_route_run import ARMS, PROPOSED, verify_lock
from analysis.multiagent_sat_route_analysis import _solve_contrast, _work_contrast
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.multiagent_community_sat import summarize_rows


RANDOM = "independent_local_random_valid_sat"
FROZEN_DEEPEST = "independent_local_cbj_sat"
NO_CROSS = "independent_local_no_cross_sat"
MONOLITH = "monolith_MR_sat"
BOOTSTRAP_SEED_BASE = 2026071210
FAILURE_CAP = 20000.0


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(raw_path: Path, lock_path: Path) -> dict[str, Any]:
    lock, lock_checks = verify_lock(lock_path)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    expected_hashes = {key: item["sha256"] for key, item in lock["files"].items()}
    if raw.get("input_hashes") != expected_hashes:
        raise ValueError("matched-route raw hashes differ from execution lock")
    rows = list(raw.get("rows", []))
    ids = sorted({str(row["instance_id"]) for row in rows})
    if len(rows) != 1000 or len(ids) != 200 or set(str(row["arm"]) for row in rows) != set(ARMS):
        raise ValueError("matched-route raw cardinality mismatch")
    index = {(str(row["instance_id"]), str(row["arm"])): row for row in rows}

    solve_random = _solve_contrast(index, ids, PROPOSED, RANDOM)
    work_random = _work_contrast(index, ids, PROPOSED, RANDOM, BOOTSTRAP_SEED_BASE)
    solve_monolith = _solve_contrast(index, ids, PROPOSED, MONOLITH)
    work_monolith = _work_contrast(index, ids, PROPOSED, MONOLITH, BOOTSTRAP_SEED_BASE + 1)
    solve_frozen = _solve_contrast(index, ids, PROPOSED, FROZEN_DEEPEST)
    work_frozen = _work_contrast(index, ids, PROPOSED, FROZEN_DEEPEST, BOOTSTRAP_SEED_BASE + 2)
    solve_no_cross = _solve_contrast(index, ids, PROPOSED, NO_CROSS)
    work_no_cross = _work_contrast(index, ids, PROPOSED, NO_CROSS, BOOTSTRAP_SEED_BASE + 3)

    proposed_rows = [index[(instance_id, PROPOSED)] for instance_id in ids]
    monolith_rows = [index[(instance_id, MONOLITH)] for instance_id in ids]
    successes = [row for row in proposed_rows if row["solved"]]
    failures = [row for row in proposed_rows if not row["solved"]]
    w_success = mean(float(row["aggregate_work"]) for row in successes) if successes else FAILURE_CAP
    w_monolith = mean(float(row["penalized_work"]) for row in monolith_rows)
    q = len(failures) / len(proposed_rows)
    q_star = (
        (w_monolith - w_success) / (FAILURE_CAP - w_success)
        if w_success < w_monolith and w_success < FAILURE_CAP
        else None
    )
    operational = {
        "mean_requests": mean(float(row["requests_sent"]) for row in proposed_rows),
        "mean_nacks": mean(float(row["nacks"]) for row in proposed_rows),
        "mean_window_rejections": mean(float(row["window_rejections"]) for row in proposed_rows),
        "out_of_window_executions": sum(int(row["out_of_window_rollback_executions"]) for row in proposed_rows),
        "resources_matched": all(
            int(row["declared_per_agent_window"]) == 8
            and int(row["declared_total_window"]) == 32
            and int(row["max_pending_requests"]) <= 16
            for row in proposed_rows
        ),
    }
    monolith_only_cp_upper = _cp_upper(int(solve_monolith["right_only"]), len(ids))
    c0 = (
        raw.get("status") == "SAT_MATCHED_ROUTE_RAW_COMPLETE"
        and all(raw.get("cardinality", {}).values())
        and bool(raw.get("protocol_audit", {}).get("pass"))
        and all(lock_checks.values())
    )
    c1 = (
        solve_random["solve_difference"] >= 0.10
        and solve_random["mcnemar_one_sided_left_superior"] <= 0.05
    )
    c2 = work_random["ratio_of_means"] <= 0.90 and work_random["bootstrap_ci95"][1] < 1.00
    c3 = (
        operational["mean_nacks"] <= 1.0
        and operational["mean_window_rejections"] <= 1.0
        and operational["out_of_window_executions"] == 0
        and operational["resources_matched"]
    )
    c4 = solve_monolith["solve_difference"] >= -0.05 and monolith_only_cp_upper <= 0.05
    c5 = work_monolith["ratio_of_means"] <= 0.80 and work_monolith["bootstrap_ci95"][1] < 1.00
    c6 = work_frozen["ratio_of_means"] <= 0.50 and work_frozen["bootstrap_ci95"][1] < 0.75
    gates = {
        "C0_execution_integrity": c0,
        "C1_ranking_solve_effect": c1,
        "C2_ranking_expected_work": c2,
        "C3_operational_safety": c3,
        "C4_equal_memory_solve_noninferiority": c4,
        "C5_equal_memory_expected_work_advantage": c5,
        "C6_repair_mechanism": c6,
    }
    if not c0:
        status = "SAT_MATCHED_ROUTE_PROTOCOL_FAIL"
    elif all(gates.values()):
        status = "SAT_MATCHED_ROUTE_STRONG_CONFIRMATION"
    elif c0 and c1 and c2 and c3 and c6:
        status = "SAT_MATCHED_ROUTE_CONFIRMATION_ONLY"
    else:
        status = "SAT_MATCHED_ROUTE_CONFIRMATION_NO_GO"

    return {
        "schema": "multiagent_sat_matched_route_confirmation_analysis_v1",
        "status": status,
        "study_role": "independent_capacity_valid_route_tail_control_confirmation",
        "headline_eligible": False,
        "qwen_authorized": False,
        "raw_results": str(raw_path.relative_to(REPO_ROOT)),
        "raw_results_sha256": _sha256(raw_path),
        "execution_lock": str(lock_path.relative_to(REPO_ROOT)),
        "execution_lock_sha256": _sha256(lock_path),
        "lock_checks": lock_checks,
        "gates": gates,
        "primary_ranking": {
            "solve": solve_random,
            "penalized_work": work_random,
        },
        "equal_memory": {
            "solve": solve_monolith,
            "monolith_only_discordance_cp_upper95": monolith_only_cp_upper,
            "penalized_work": work_monolith,
        },
        "repair_mechanism": {
            "solve": solve_frozen,
            "penalized_work": work_frozen,
        },
        "coordination_control": {
            "solve": solve_no_cross,
            "penalized_work": work_no_cross,
        },
        "operational_safety": operational,
        "tail_boundary": {
            "W_success": w_success,
            "W_monolith_penalized": w_monolith,
            "failure_cap": FAILURE_CAP,
            "q": q,
            "q_star": q_star,
            "q_below_q_star": q_star is not None and q < q_star,
        },
        "summary": summarize_rows(rows),
        "protocol_audit": raw["protocol_audit"],
        "claim_boundary": {
            "potential_symbolic_claim": "Capacity-valid filtering before conflict priority controls NACK tails and can restore expected-resource benefit in frozen community SAT.",
            "forbidden": [
                "algorithm novelty",
                "LLM or Qwen gain",
                "generalization beyond frozen SAT",
                "wall-clock or hardware efficiency",
            ],
        },
    }


def _render(payload: dict[str, Any]) -> str:
    ranking_solve = payload["primary_ranking"]["solve"]
    ranking_work = payload["primary_ranking"]["penalized_work"]
    mono_solve = payload["equal_memory"]["solve"]
    mono_work = payload["equal_memory"]["penalized_work"]
    repair = payload["repair_mechanism"]["penalized_work"]
    tail = payload["tail_boundary"]
    operational = payload["operational_safety"]
    q_star_text = "NA" if tail["q_star"] is None else f"{tail['q_star']:.3f}"
    lines = [
        "# Matched-Window Community-SAT Independent Confirmation",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Instances: 200 untouched high-coupling, over-local-fit community-SAT instances",
        "- Arms: matched-window deepest, random-valid, frozen deepest, no-cross, equal-memory monolith",
        "- GPU/LLM use: none",
        "- Qwen authorized: **No**",
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
        "## Candidate-matched route ranking",
        "",
        f"- Proposed/random solve: `{ranking_solve['left_solve_rate']:.3f}` / `{ranking_solve['right_solve_rate']:.3f}`; difference `{ranking_solve['solve_difference']:.3f}`.",
        f"- Discordances: `{ranking_solve['left_only']}/{ranking_solve['right_only']}`; one-sided exact probability `{ranking_solve['mcnemar_one_sided_left_superior']:.6g}`.",
        f"- Failure-penalized work ratio: `{ranking_work['ratio_of_means']:.3f}`; 95% CI `[{ranking_work['bootstrap_ci95'][0]:.3f}, {ranking_work['bootstrap_ci95'][1]:.3f}]`.",
        "",
        "## Equal-memory objective",
        "",
        f"- Proposed/monolith solve: `{mono_solve['left_solve_rate']:.3f}` / `{mono_solve['right_solve_rate']:.3f}`; difference `{mono_solve['solve_difference']:.3f}`.",
        f"- Monolith-only discordances: `{mono_solve['right_only']}`; one-sided CP upper 95% `{payload['equal_memory']['monolith_only_discordance_cp_upper95']:.3f}`.",
        f"- Failure-penalized proposed/monolith work ratio: `{mono_work['ratio_of_means']:.3f}`; 95% CI `[{mono_work['bootstrap_ci95'][0]:.3f}, {mono_work['bootstrap_ci95'][1]:.3f}]`.",
        "",
        "## Repair mechanism",
        "",
        f"- Proposed/frozen-deepest failure-penalized work ratio: `{repair['ratio_of_means']:.3f}`; 95% CI `[{repair['bootstrap_ci95'][0]:.3f}, {repair['bootstrap_ci95'][1]:.3f}]`.",
        f"- Proposed mean requests/NACKs/window rejections: `{operational['mean_requests']:.1f}` / `{operational['mean_nacks']:.3f}` / `{operational['mean_window_rejections']:.3f}`.",
        "",
        "## Tail boundary",
        "",
        f"- Successful proposed work $W_s$: `{tail['W_success']:.1f}`.",
        f"- Penalized monolith work $W_m$: `{tail['W_monolith_penalized']:.1f}`.",
        f"- Proposed failure rate $q$: `{tail['q']:.3f}`.",
        f"- Break-even $q^*$: `{q_star_text}`.",
        "",
        "## Arm summary",
        "",
        "| Arm | Solve | Penalized work | Raw work | Requests | Status |",
        "|---|---:|---:|---:|---:|---|",
    ])
    for row in payload["summary"]:
        statuses = ", ".join(f"{key}={value}" for key, value in sorted(row["status_counts"].items()))
        lines.append(
            f"| `{row['arm']}` | {row['solve_rate']:.3f} | {row['mean_penalized_work']:.1f} | "
            f"{row['mean_aggregate_work']:.1f} | {row['mean_requests']:.1f} | {statuses} |"
        )
    lines.extend([
        "",
        "## Claim boundary",
        "",
        "A strong confirmation supports capacity-valid filtering as a symbolic tail-risk control in this SAT regime. It does not establish algorithm novelty, an LLM/Qwen gain, cross-domain generality, or hardware speedup.",
        "",
        "## Artifacts",
        "",
        "- [Raw results](raw_results.json)",
        "- [Analysis JSON](analysis.json)",
        "- [Frozen manifest](../multiagent_sat_matched_route_manifest/GENERATION.md)",
        "- [Confirmation contract](../../specs/multiagent_sat_matched_route_confirmation_v1.md)",
        "- [Development gate](../multiagent_sat_matched_route_development/DEVELOPMENT.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze matched-window SAT route confirmation.")
    parser.add_argument("--raw", type=Path, default=Path("results/multiagent_sat_matched_route_confirmation/raw_results.json"))
    parser.add_argument("--execution-lock", type=Path, default=Path("specs/multiagent_sat_matched_route_execution_lock_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_sat_matched_route_confirmation"))
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
        "qwen_authorized": payload["qwen_authorized"],
        "report": str((output_dir / "RESULTS.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
