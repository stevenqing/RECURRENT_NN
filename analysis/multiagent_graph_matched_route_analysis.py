"""Frozen analysis for graph matched-window route confirmation."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from analysis.multiagent_community_sat_analysis import _cp_upper
from analysis.multiagent_graph_matched_route_run import FROZEN, MONOLITH, NO_CROSS, PROPOSED, RANDOM, verify_lock
from analysis.multiagent_sat_route_analysis import _solve_contrast, _work_contrast
from experiments.multiagent_capacity_coupling import REPO_ROOT


BOOTSTRAP_SEED_BASE = 2026071230
FAILURE_CAP = 20000.0


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for cell, arm in sorted({(str(row["cell"]), str(row["arm"])) for row in rows}):
        subset = [row for row in rows if row["cell"] == cell and row["arm"] == arm]
        output.append({
            "cell": cell,
            "arm": arm,
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "mean_penalized_work": mean(float(row["penalized_work"]) for row in subset),
            "mean_aggregate_work": mean(float(row["aggregate_work"]) for row in subset),
            "mean_requests": mean(float(row.get("requests_sent", 0)) for row in subset),
            "mean_nacks": mean(float(row.get("nacks", 0)) for row in subset),
            "status_counts": dict(Counter(str(row["status"]) for row in subset)),
        })
    return output


def analyze(raw_path: Path, lock_path: Path) -> dict[str, Any]:
    lock, lock_checks = verify_lock(lock_path)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    expected_hashes = {key: item["sha256"] for key, item in lock["files"].items()}
    if raw.get("input_hashes") != expected_hashes:
        raise ValueError("graph matched-route raw hashes differ from lock")
    rows = list(raw.get("rows", []))
    ids_all = sorted({str(row["instance_id"]) for row in rows})
    if len(rows) != 1000 or len(ids_all) != 200:
        raise ValueError("graph matched-route raw cardinality mismatch")
    index = {(str(row["instance_id"]), str(row["arm"])): row for row in rows}
    over_ids = sorted({str(row["instance_id"]) for row in rows if str(row["cell"]).startswith("over_")})
    solve_random = _solve_contrast(index, over_ids, PROPOSED, RANDOM)
    work_random = _work_contrast(index, over_ids, PROPOSED, RANDOM, BOOTSTRAP_SEED_BASE)
    work_frozen = _work_contrast(index, over_ids, PROPOSED, FROZEN, BOOTSTRAP_SEED_BASE + 1)
    solve_monolith = _solve_contrast(index, over_ids, PROPOSED, MONOLITH)
    work_monolith = _work_contrast(index, over_ids, PROPOSED, MONOLITH, BOOTSTRAP_SEED_BASE + 2)
    solve_no_cross = _solve_contrast(index, over_ids, PROPOSED, NO_CROSS)
    work_no_cross = _work_contrast(index, over_ids, PROPOSED, NO_CROSS, BOOTSTRAP_SEED_BASE + 3)
    cell_random = {}
    cell_monolith = {}
    for cell in ("over_low", "over_high"):
        cell_ids = sorted({str(row["instance_id"]) for row in rows if row["cell"] == cell})
        cell_random[cell] = _solve_contrast(index, cell_ids, PROPOSED, RANDOM)
        cell_monolith[cell] = _solve_contrast(index, cell_ids, PROPOSED, MONOLITH)

    proposed_rows = [index[(instance_id, PROPOSED)] for instance_id in over_ids]
    monolith_rows = [index[(instance_id, MONOLITH)] for instance_id in over_ids]
    success_rows = [row for row in proposed_rows if row["solved"]]
    w_success = mean(float(row["aggregate_work"]) for row in success_rows) if success_rows else FAILURE_CAP
    w_monolith = mean(float(row["penalized_work"]) for row in monolith_rows)
    q = mean(float(not row["solved"]) for row in proposed_rows)
    q_star = (w_monolith - w_success) / (FAILURE_CAP - w_success) if w_success < w_monolith and w_success < FAILURE_CAP else None
    operational = {
        "mean_requests": mean(float(row["requests_sent"]) for row in proposed_rows),
        "mean_nacks": mean(float(row["nacks"]) for row in proposed_rows),
        "mean_window_rejections": mean(float(row.get("window_rejections", 0)) for row in proposed_rows),
        "out_of_window_executions": sum(int(row.get("out_of_window_rollback_executions", 0)) for row in proposed_rows),
        "resources_matched": all(int(row["declared_per_agent_window"]) == 8 and int(row["declared_total_window"]) == 32 and int(row["max_pending_requests"]) <= 16 for row in proposed_rows),
    }
    monolith_cp = _cp_upper(int(solve_monolith["right_only"]), len(over_ids))
    c0 = raw.get("status") == "GRAPH_MATCHED_ROUTE_RAW_COMPLETE" and all(raw.get("cardinality", {}).values()) and raw.get("protocol_audit", {}).get("pass") and all(lock_checks.values())
    c1 = solve_random["solve_difference"] >= 0.10 and solve_random["mcnemar_one_sided_left_superior"] <= 0.05
    c2 = work_random["ratio_of_means"] <= 0.80 and work_random["bootstrap_ci95"][1] < 1.00
    c3 = all(contrast["solve_difference"] >= -0.05 and contrast["left_solve_rate"] >= 0.95 for contrast in cell_random.values())
    c4 = operational["mean_nacks"] <= 1.0 and operational["mean_window_rejections"] <= 2.0 and operational["out_of_window_executions"] == 0 and operational["resources_matched"]
    c5 = work_frozen["ratio_of_means"] <= 0.80 and work_frozen["bootstrap_ci95"][1] < 1.00
    c6 = solve_monolith["solve_difference"] >= -0.05 and monolith_cp <= 0.05 and all(contrast["solve_difference"] >= -0.10 for contrast in cell_monolith.values())
    c7 = work_monolith["ratio_of_means"] <= 0.80 and work_monolith["bootstrap_ci95"][1] < 1.00
    gates = {
        "C0_execution_integrity": c0,
        "C1_route_solve_effect": c1,
        "C2_route_expected_work": c2,
        "C3_cell_stability": c3,
        "C4_operational_safety": c4,
        "C5_repair_mechanism": c5,
        "C6_equal_memory_solve_noninferiority": c6,
        "C7_equal_memory_expected_work": c7,
    }
    if not c0:
        status = "GRAPH_MATCHED_ROUTE_PROTOCOL_FAIL"
    elif all(gates.values()):
        status = "GRAPH_MATCHED_ROUTE_STRONG_CONFIRMATION"
    elif all(gates[key] for key in ("C0_execution_integrity", "C1_route_solve_effect", "C2_route_expected_work", "C3_cell_stability", "C4_operational_safety", "C5_repair_mechanism")):
        status = "GRAPH_MATCHED_ROUTE_CONFIRMATION_ONLY"
    else:
        status = "GRAPH_MATCHED_ROUTE_CONFIRMATION_NO_GO"
    return {
        "schema": "multiagent_graph_matched_route_confirmation_analysis_v1",
        "status": status,
        "headline_eligible": False,
        "qwen_authorized": False,
        "raw_results_sha256": _sha256(raw_path),
        "execution_lock_sha256": _sha256(lock_path),
        "lock_checks": lock_checks,
        "gates": gates,
        "primary_route": {"solve": solve_random, "penalized_work": work_random},
        "repair_mechanism": {"penalized_work": work_frozen},
        "equal_memory": {"solve": solve_monolith, "monolith_only_cp_upper95": monolith_cp, "penalized_work": work_monolith},
        "coordination": {"solve": solve_no_cross, "penalized_work": work_no_cross},
        "cell_random": cell_random,
        "cell_monolith": cell_monolith,
        "operational_safety": operational,
        "tail_boundary": {"W_success": w_success, "W_monolith_penalized": w_monolith, "q": q, "q_star": q_star, "q_below_q_star": q_star is not None and q < q_star},
        "summary": _summary(rows),
        "protocol_audit": raw["protocol_audit"],
    }


def _render(payload: dict[str, Any]) -> str:
    route_solve = payload["primary_route"]["solve"]
    route_work = payload["primary_route"]["penalized_work"]
    mono_solve = payload["equal_memory"]["solve"]
    mono_work = payload["equal_memory"]["penalized_work"]
    repair = payload["repair_mechanism"]["penalized_work"]
    operational = payload["operational_safety"]
    tail = payload["tail_boundary"]
    q_star = "NA" if tail["q_star"] is None else f"{tail['q_star']:.3f}"
    lines = [
        "# Graph-Color Matched-Window Independent Confirmation",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Instances: 200 untouched (50/cell)",
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
        "## Pooled over-cell route effect",
        "",
        f"- Proposed/random solve: `{route_solve['left_solve_rate']:.3f}` / `{route_solve['right_solve_rate']:.3f}`; difference `{route_solve['solve_difference']:.3f}`.",
        f"- Discordances: `{route_solve['left_only']}/{route_solve['right_only']}`; one-sided exact probability `{route_solve['mcnemar_one_sided_left_superior']:.6g}`.",
        f"- Proposed/random penalized-work ratio: `{route_work['ratio_of_means']:.3f}`; 95% CI `[{route_work['bootstrap_ci95'][0]:.3f}, {route_work['bootstrap_ci95'][1]:.3f}]`.",
        "",
        "## Equal-memory objective",
        "",
        f"- Proposed/monolith solve: `{mono_solve['left_solve_rate']:.3f}` / `{mono_solve['right_solve_rate']:.3f}`; difference `{mono_solve['solve_difference']:.3f}`.",
        f"- Monolith-only CP upper 95%: `{payload['equal_memory']['monolith_only_cp_upper95']:.3f}`.",
        f"- Proposed/monolith penalized-work ratio: `{mono_work['ratio_of_means']:.3f}`; 95% CI `[{mono_work['bootstrap_ci95'][0]:.3f}, {mono_work['bootstrap_ci95'][1]:.3f}]`.",
        "",
        "## Repair and safety",
        "",
        f"- Proposed/frozen-deepest penalized-work ratio: `{repair['ratio_of_means']:.3f}`; upper 95% `{repair['bootstrap_ci95'][1]:.3f}`.",
        f"- Mean requests/NACKs/window rejections: `{operational['mean_requests']:.2f}` / `{operational['mean_nacks']:.3f}` / `{operational['mean_window_rejections']:.3f}`.",
        f"- Tail: $q={tail['q']:.3f}$, $q^*={q_star}$.",
        "",
        "## Cell stability",
        "",
        "| Cell | Proposed | Random | Monolith |",
        "|---|---:|---:|---:|",
    ])
    for cell in ("over_low", "over_high"):
        lines.append(f"| {cell} | {payload['cell_random'][cell]['left_solve_rate']:.3f} | {payload['cell_random'][cell]['right_solve_rate']:.3f} | {payload['cell_monolith'][cell]['right_solve_rate']:.3f} |")
    lines.extend([
        "",
        "## Claim boundary",
        "",
        "A positive result confirms the capacity-valid-before-priority tail-control mechanism on graph coloring. Combined with SAT, this supports a cross-substrate symbolic mechanism, not algorithm novelty or an LLM claim.",
        "",
        "## Artifacts",
        "",
        "- [Raw results](raw_results.json)",
        "- [Analysis JSON](analysis.json)",
        "- [Frozen manifest](../multiagent_graph_matched_route_manifest/GENERATION.md)",
        "- [Confirmation contract](../../specs/multiagent_graph_matched_route_confirmation_v1.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze graph matched-window route confirmation.")
    parser.add_argument("--raw", type=Path, default=Path("results/multiagent_graph_matched_route_confirmation/raw_results.json"))
    parser.add_argument("--execution-lock", type=Path, default=Path("specs/multiagent_graph_matched_route_execution_lock_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_graph_matched_route_confirmation"))
    args = parser.parse_args()
    raw_path = _resolve(args.raw)
    lock_path = _resolve(args.execution_lock)
    payload = analyze(raw_path, lock_path)
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "RESULTS.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "qwen_authorized": False, "report": str((output_dir / "RESULTS.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()
