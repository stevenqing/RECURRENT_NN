"""Exposed-pool development test of graph deepest-over-window-valid routing."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from analysis.multiagent_sat_route_analysis import _solve_contrast, _work_contrast
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.multiagent_graph_route_controls import ARM, run_deepest_window_valid_graph


CONTRACT_SCHEMA = "multiagent_graph_matched_route_development_contract_v1"
RANDOM = "independent_local_random_valid"
FROZEN = "independent_local_cbj_v1_exact"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _trim(row: dict[str, Any]) -> dict[str, Any]:
    output = dict(row)
    samples = list(output.get("protocol_samples", []))
    output["protocol_sample_count"] = len(samples)
    output["protocol_samples"] = samples[:8]
    return output


def _protocol(rows: list[dict[str, Any]], r_value: int, channel_cap: int) -> dict[str, Any]:
    checks = {
        "official_scoring": all(row["status"] != "OFFICIAL_SCORE_FAIL" for row in rows),
        "no_direct_cross_agent_mutation": all(int(row["cross_agent_direct_mutations"]) == 0 for row in rows),
        "owner_only_mutation": all(int(row["ownership_violations"]) == 0 for row in rows),
        "acyclic_priority": all(int(row["priority_direction_violations"]) == 0 for row in rows),
        "no_out_of_window_execution": all(int(row["out_of_window_rollback_executions"]) == 0 for row in rows),
        "window_occupancy_bounded": all(int(row["max_local_register"]) <= int(r_value) for row in rows),
        "request_conservation": all(
            int(row["requests_sent"]) == int(row["requests_executed"]) + int(row["nacks"])
            and int(row["acknowledgements"]) == int(row["requests_sent"])
            and bool(row["request_lifecycle_valid"])
            for row in rows
        ),
        "channel_bounded": all(int(row["max_pending_requests"]) <= int(channel_cap) for row in rows),
        "no_global_trail": all(bool(row["no_global_trail"]) for row in rows),
        "independent_state": all(bool(row["independent_agent_state"]) for row in rows),
        "no_fallback": all(bool(row["no_oracle_or_model_fallback"]) for row in rows),
        "matched_filter": all(row.get("candidate_filter") == "target_owner_window_valid" for row in rows),
        "deepest_rank": all(row.get("candidate_ranking") == "maximum_fixed_order_position" for row in rows),
    }
    return {"pass": all(checks.values()), "checks": checks}


def _render(payload: dict[str, Any]) -> str:
    pooled = payload["pooled_over"]
    lines = [
        "# Graph-Color Matched-Window Route Development",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Evidence tier: exposed-pool cross-substrate mechanism development",
        "- Instances: 200 prior structural-confirmation instances",
        "- New arm outcomes were unseen when the contract was frozen",
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
    solve = pooled["vs_random_solve"]
    work_random = pooled["vs_random_work"]
    work_frozen = pooled["vs_frozen_work"]
    lines.extend([
        "",
        "## Pooled over-cell effect",
        "",
        f"- Proposed/random solve: `{solve['left_solve_rate']:.3f}` / `{solve['right_solve_rate']:.3f}`; difference `{solve['solve_difference']:.3f}`.",
        f"- Discordances: `{solve['left_only']}/{solve['right_only']}`; one-sided exact probability `{solve['mcnemar_one_sided_left_superior']:.6g}`.",
        f"- Proposed/random penalized-work ratio: `{work_random['ratio_of_means']:.3f}`; 95% CI `[{work_random['bootstrap_ci95'][0]:.3f}, {work_random['bootstrap_ci95'][1]:.3f}]`.",
        f"- Proposed/frozen-deepest penalized-work ratio: `{work_frozen['ratio_of_means']:.3f}`; 95% CI `[{work_frozen['bootstrap_ci95'][0]:.3f}, {work_frozen['bootstrap_ci95'][1]:.3f}]`.",
        "",
        "## Cell stability",
        "",
        "| Cell | Proposed solve | Random solve | Difference |",
        "|---|---:|---:|---:|",
    ])
    for cell, contrast in payload["cell_solve"].items():
        lines.append(
            f"| {cell} | {contrast['left_solve_rate']:.3f} | {contrast['right_solve_rate']:.3f} | {contrast['solve_difference']:.3f} |"
        )
    matching = payload["operational_matching"]
    lines.extend([
        "",
        "## Operational matching",
        "",
        f"- Mean requests/NACKs/window rejections: `{matching['mean_requests']:.2f}` / `{matching['mean_nacks']:.3f}` / `{matching['mean_window_rejections']:.3f}`.",
        f"- Status counts: `{json.dumps(payload['status_counts'], sort_keys=True)}`.",
        "",
        "## Decision",
        "",
        "A GO authorizes only a new untouched graph-color symbolic confirmation. It does not establish cross-substrate generality or authorize Qwen.",
        "",
        "## Artifacts",
        "",
        "- [Results JSON](results.json)",
        "- [Development contract](../../specs/multiagent_graph_matched_route_development_v1.md)",
        "- [SAT capacity-valid synthesis](../multiagent_capacity_valid_route_tail_control/SUMMARY.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run graph matched-window route development.")
    parser.add_argument("--contract", type=Path, default=Path("specs/multiagent_graph_matched_route_development_v1.json"))
    parser.add_argument("--manifest", type=Path, default=Path("results/multiagent_structural_confirmatory_manifest/instance_manifest.json"))
    parser.add_argument("--controls", type=Path, default=Path("results/multiagent_structural_confirmatory/raw_results.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_graph_matched_route_development"))
    args = parser.parse_args()

    contract_path = _resolve(args.contract)
    manifest_path = _resolve(args.manifest)
    controls_path = _resolve(args.controls)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "FROZEN_BEFORE_NEW_ARM_OUTCOMES":
        raise ValueError("graph matched-route development contract is not frozen")
    instances = list(json.loads(manifest_path.read_text(encoding="utf-8"))["rows"])
    controls = list(json.loads(controls_path.read_text(encoding="utf-8"))["rows"])
    resources = contract["resources"]
    if len(instances) != 200:
        raise ValueError("graph development manifest cardinality mismatch")

    rows = [
        _trim(run_deepest_window_valid_graph(
            row,
            r_value=int(resources["R"]),
            activation_cap=int(resources["activation_cap"]),
            channel_cap=int(resources["channel_cap"]),
            route_seed=int(resources["route_seed"]),
        ))
        for row in instances
    ]
    replay = [
        _trim(run_deepest_window_valid_graph(
            row,
            r_value=int(resources["R"]),
            activation_cap=int(resources["activation_cap"]),
            channel_cap=int(resources["channel_cap"]),
            route_seed=int(resources["route_seed"]),
        ))
        for row in instances[:16]
    ]
    deterministic = all(left == right for left, right in zip(rows[:16], replay))
    protocol = _protocol(rows, int(resources["R"]), int(resources["channel_cap"]))
    control_rows = [row for row in controls if row["arm"] in {RANDOM, FROZEN}]
    combined = rows + control_rows
    index = {(str(row["instance_id"]), str(row["arm"])): row for row in combined}
    over_ids = sorted(str(row["instance_id"]) for row in instances if str(row["cell"]).startswith("over_"))
    solve_random = _solve_contrast(index, over_ids, ARM, RANDOM)
    work_random = _work_contrast(index, over_ids, ARM, RANDOM, int(contract["statistics"]["bootstrap_seed_base"]))
    work_frozen = _work_contrast(index, over_ids, ARM, FROZEN, int(contract["statistics"]["bootstrap_seed_base"]) + 1)
    cell_solve = {}
    for cell in ("over_low", "over_high"):
        ids = sorted(str(row["instance_id"]) for row in instances if row["cell"] == cell)
        cell_solve[cell] = _solve_contrast(index, ids, ARM, RANDOM)
    matching = {
        "mean_requests": mean(float(row["requests_sent"]) for row in rows),
        "mean_nacks": mean(float(row["nacks"]) for row in rows),
        "mean_window_rejections": mean(float(row["window_rejections"]) for row in rows),
        "resources_matched": all(
            int(row["declared_per_agent_window"]) == int(resources["R"])
            and int(row["declared_total_window"]) == int(resources["MR"])
            and int(row["max_pending_requests"]) <= int(resources["channel_cap"])
            for row in rows
        ),
    }
    d0 = len(rows) == 200 and deterministic and protocol["pass"]
    d1 = matching["mean_nacks"] <= 1.0 and matching["mean_window_rejections"] <= 2.0 and matching["resources_matched"]
    d2 = solve_random["solve_difference"] >= 0.10 and solve_random["mcnemar_one_sided_left_superior"] <= 0.05
    d3 = all(contrast["solve_difference"] >= -0.05 for contrast in cell_solve.values())
    d4 = work_random["ratio_of_means"] <= 0.80 and work_random["bootstrap_ci95"][1] < 1.00
    d5 = work_frozen["ratio_of_means"] <= 0.80 and work_frozen["bootstrap_ci95"][1] < 1.00
    gates = {
        "D0_implementation_protocol": d0,
        "D1_operational_matching": d1,
        "D2_pooled_solve_effect": d2,
        "D3_cell_stability": d3,
        "D4_expected_work_vs_random": d4,
        "D5_repair_vs_frozen_deepest": d5,
    }
    if not d0:
        status = "GRAPH_MATCHED_ROUTE_DEV_PROTOCOL_FAIL"
    elif all(gates.values()):
        status = "GRAPH_MATCHED_ROUTE_DEV_GO_CONFIRMATION"
    else:
        status = "GRAPH_MATCHED_ROUTE_DEV_NO_GO"
    payload = {
        "schema": "multiagent_graph_matched_route_development_v1",
        "status": status,
        "headline_eligible": False,
        "qwen_authorized": False,
        "future_symbolic_confirmation_authorized": status == "GRAPH_MATCHED_ROUTE_DEV_GO_CONFIRMATION",
        "contract_sha256": _sha256(contract_path),
        "manifest_sha256": _sha256(manifest_path),
        "controls_sha256": _sha256(controls_path),
        "implementation_sha256": _sha256(REPO_ROOT / "experiments/multiagent_graph_route_controls.py"),
        "analysis_sha256": _sha256(Path(__file__)),
        "gates": gates,
        "deterministic_replay_16": deterministic,
        "protocol": protocol,
        "pooled_over": {
            "vs_random_solve": solve_random,
            "vs_random_work": work_random,
            "vs_frozen_work": work_frozen,
        },
        "cell_solve": cell_solve,
        "operational_matching": matching,
        "status_counts": dict(Counter(str(row["status"]) for row in rows)),
        "rows": rows,
        "honesty": {
            "development_only": True,
            "source_pool_previously_exposed": True,
            "new_arm_outcomes_unseen_before_contract": True,
            "no_gpu_or_llm": True,
        },
    }
    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "DEVELOPMENT.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "future_symbolic_confirmation_authorized": payload["future_symbolic_confirmation_authorized"],
        "report": str((output_dir / "DEVELOPMENT.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
