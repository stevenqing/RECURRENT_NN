"""Development evaluation of deepest ranking over matched window-valid targets."""

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
from experiments.multiagent_community_sat_route_controls import ARM, run_deepest_window_valid_sat


CONTRACT_SCHEMA = "multiagent_sat_matched_route_development_contract_v1"
RANDOM = "independent_local_random_valid_sat"
BOOTSTRAP_SEED = 2026071205


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        "no_fallback": all(bool(row["no_oracle_or_model_fallback"]) for row in rows),
        "matched_filter_declared": all(row.get("candidate_filter") == "target_owner_window_valid" for row in rows),
        "deepest_ranking_declared": all(row.get("candidate_ranking") == "maximum_fixed_order_position" for row in rows),
    }
    return {"pass": all(checks.values()), "checks": checks}


def _render(payload: dict[str, Any]) -> str:
    solve = payload["primary_solve"]
    work = payload["primary_work"]
    matching = payload["operational_matching"]
    lines = [
        "# Matched-Window SAT Route Development",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Evidence tier: exposed-pool mechanism development",
        "- New arm: deepest ranking over the exact frozen random-valid candidate set",
        "- Instances: 200 previously exposed route-confirmation instances",
        "- GPU/LLM use: none",
        "- Qwen authorized: **No**",
        "",
        "## Frozen development gates",
        "",
        "| Gate | Result |",
        "|---|---:|",
    ]
    for key, value in payload["gates"].items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")
    lines.extend([
        "",
        "## Matched-window deepest versus random-valid",
        "",
        f"- Solve: `{solve['left_solve_rate']:.3f}` versus `{solve['right_solve_rate']:.3f}`; difference `{solve['solve_difference']:.3f}`.",
        f"- Discordances: `{solve['left_only']}/{solve['right_only']}`; one-sided exact probability `{solve['mcnemar_one_sided_left_superior']:.6g}`.",
        f"- Failure-penalized work ratio: `{work['ratio_of_means']:.3f}`; 95% CI `[{work['bootstrap_ci95'][0]:.3f}, {work['bootstrap_ci95'][1]:.3f}]`.",
        f"- Paired work wins/ties/losses: `{work['wins']}/{work['ties']}/{work['losses']}`.",
        "",
        "## Operational matching",
        "",
        f"- Mean requests: `{matching['mean_requests']:.3f}`.",
        f"- Mean NACKs: `{matching['mean_nacks']:.3f}`.",
        f"- Mean window rejections: `{matching['mean_window_rejections']:.3f}`.",
        f"- Solve statuses: `{json.dumps(payload['status_counts'], sort_keys=True)}`.",
        "",
        "## Interpretation",
        "",
    ])
    if payload["status"] == "SAT_MATCHED_ROUTE_DEV_GO_CONFIRMATION":
        lines.append(
            "The clean candidate-matched deepest ranking passed all development gates. This authorizes only a new untouched symbolic confirmation; it does not authorize Qwen."
        )
    elif payload["status"] == "SAT_MATCHED_ROUTE_DEV_PROTOCOL_FAIL":
        lines.append("The shadow control failed implementation/protocol checks. No scientific interpretation or escalation is allowed.")
    else:
        lines.append(
            "The clean candidate-matched deepest ranking did not pass the frozen development gates. The route-ranking line closes and Qwen remains unauthorized."
        )
    lines.extend([
        "",
        "## Artifacts",
        "",
        "- [Results JSON](results.json)",
        "- [Development contract](../../specs/multiagent_sat_matched_route_development_v1.md)",
        "- [Parent route closeout](../multiagent_sat_route_confirmation/CLOSEOUT.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run matched-window SAT route development.")
    parser.add_argument("--contract", type=Path, default=Path("specs/multiagent_sat_matched_route_development_v1.json"))
    parser.add_argument("--manifest", type=Path, default=Path("results/multiagent_sat_route_manifest/instance_manifest.json"))
    parser.add_argument("--controls", type=Path, default=Path("results/multiagent_sat_route_confirmation/raw_results.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_sat_matched_route_development"))
    args = parser.parse_args()

    contract_path = _resolve(args.contract)
    manifest_path = _resolve(args.manifest)
    controls_path = _resolve(args.controls)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "FROZEN_BEFORE_NEW_ARM_OUTCOMES":
        raise ValueError("matched-route development contract is not frozen")
    instances = list(json.loads(manifest_path.read_text(encoding="utf-8"))["rows"])
    controls = json.loads(controls_path.read_text(encoding="utf-8"))
    resources = contract["resources"]
    if len(instances) != int(contract["instances"]):
        raise ValueError("matched-route development manifest cardinality mismatch")

    rows = [
        run_deepest_window_valid_sat(
            instance,
            r_value=int(resources["R"]),
            activation_cap=int(resources["activation_cap"]),
            channel_cap=int(resources["channel_cap"]),
            route_seed=int(resources["route_seed"]),
        )
        for instance in instances
    ]
    replay_rows = [
        run_deepest_window_valid_sat(
            instance,
            r_value=int(resources["R"]),
            activation_cap=int(resources["activation_cap"]),
            channel_cap=int(resources["channel_cap"]),
            route_seed=int(resources["route_seed"]),
        )
        for instance in instances[:16]
    ]
    deterministic = all(left == right for left, right in zip(rows[:16], replay_rows))
    protocol = _protocol(rows, int(resources["R"]), int(resources["channel_cap"]))

    random_rows = [row for row in controls["rows"] if row["arm"] == RANDOM]
    if len(random_rows) != 200:
        raise ValueError("expected 200 frozen random-valid control rows")
    combined = rows + random_rows
    index = {(str(row["instance_id"]), str(row["arm"])): row for row in combined}
    ids = sorted({str(row["instance_id"]) for row in rows})
    solve = _solve_contrast(index, ids, ARM, RANDOM)
    work = _work_contrast(index, ids, ARM, RANDOM, BOOTSTRAP_SEED)
    matching = {
        "mean_requests": mean(float(row["requests_sent"]) for row in rows),
        "mean_nacks": mean(float(row["nacks"]) for row in rows),
        "mean_window_rejections": mean(float(row["window_rejections"]) for row in rows),
        "mean_activations": mean(float(row["activations"]) for row in rows),
        "resources_match_random": all(
            int(row["declared_per_agent_window"]) == int(resources["R"])
            and int(row["declared_total_window"]) == int(resources["MR"])
            and int(row["max_pending_requests"]) <= int(resources["channel_cap"])
            for row in rows
        ),
    }
    d0 = len(rows) == 200 and deterministic and protocol["pass"]
    d1 = (
        matching["mean_nacks"] <= 1.0
        and matching["mean_window_rejections"] <= 1.0
        and matching["resources_match_random"]
    )
    d2 = solve["solve_difference"] >= 0.10
    d3 = solve["mcnemar_one_sided_left_superior"] <= 0.05
    d4 = work["ratio_of_means"] <= 0.90 and work["bootstrap_ci95"][1] < 1.00
    gates = {
        "D0_implementation_protocol": d0,
        "D1_operational_matching": d1,
        "D2_solve_difference_ge_0_10": d2,
        "D3_mcnemar_one_sided_le_0_05": d3,
        "D4_penalized_work_ratio_and_ci": d4,
    }
    if not d0:
        status = "SAT_MATCHED_ROUTE_DEV_PROTOCOL_FAIL"
    elif all(gates.values()):
        status = "SAT_MATCHED_ROUTE_DEV_GO_CONFIRMATION"
    else:
        status = "SAT_MATCHED_ROUTE_DEV_NO_GO"
    payload = {
        "schema": "multiagent_sat_matched_route_development_v1",
        "status": status,
        "study_role": "exposed_pool_control_repair_development",
        "headline_eligible": False,
        "qwen_authorized": False,
        "future_symbolic_confirmation_authorized": status == "SAT_MATCHED_ROUTE_DEV_GO_CONFIRMATION",
        "contract": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha256(contract_path),
        "manifest": str(manifest_path.relative_to(REPO_ROOT)),
        "manifest_sha256": _sha256(manifest_path),
        "controls": str(controls_path.relative_to(REPO_ROOT)),
        "controls_sha256": _sha256(controls_path),
        "implementation_sha256": _sha256(REPO_ROOT / "experiments/multiagent_community_sat_route_controls.py"),
        "analysis_sha256": _sha256(Path(__file__)),
        "gates": gates,
        "deterministic_replay_16": deterministic,
        "protocol": protocol,
        "primary_solve": solve,
        "primary_work": work,
        "operational_matching": matching,
        "status_counts": dict(Counter(str(row["status"]) for row in rows)),
        "rows": rows,
        "honesty": {
            "development_only": True,
            "manifest_previously_exposed": True,
            "new_arm_outcomes_unseen_before_contract": True,
            "no_gpu_or_llm": True,
            "qwen_requires_future_independent_confirmation": True,
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
