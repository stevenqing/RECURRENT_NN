"""Generate and smoke-test the community-SAT development substrate."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.multiagent_community_sat import (
    ALL_ARMS,
    FACTOR_ARM_NAMES,
    generate_structural_pool,
    run_sat_arm,
    summarize_rows,
)
from tasks.sat.community import verify_sat_assignment


FACTOR_ARMS = set(FACTOR_ARM_NAMES.values())
REPLAY_FIELDS = (
    "solved",
    "status",
    "failure_reason",
    "branch_attempts",
    "parallel_rounds",
    "recoveries",
    "retractions",
    "requests_sent",
    "requests_executed",
    "acknowledgements",
    "nacks",
    "communication_tokens",
    "aggregate_work",
    "max_pending_requests",
    "max_local_register",
    "ownership_violations",
    "priority_direction_violations",
    "window_rejections",
    "out_of_window_rollback_executions",
    "request_lifecycle_valid",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _protocol_checks(rows: list[dict[str, Any]], r_value: int, channel_cap: int) -> dict[str, bool]:
    factorized = [row for row in rows if row["arm"] in FACTOR_ARMS]
    return {
        "official_scoring": all(row["status"] != "OFFICIAL_SCORE_FAIL" for row in rows),
        "no_direct_cross_agent_mutation": all(int(row["cross_agent_direct_mutations"]) == 0 for row in factorized),
        "owner_only_mutation": all(int(row["ownership_violations"]) == 0 for row in factorized),
        "acyclic_priority": all(int(row["priority_direction_violations"]) == 0 for row in factorized),
        "no_out_of_window_execution": all(int(row["out_of_window_rollback_executions"]) == 0 for row in factorized),
        "window_occupancy_bounded": all(int(row["max_local_register"]) <= int(r_value) for row in factorized),
        "request_conservation": all(
            int(row["requests_sent"]) == int(row["requests_executed"]) + int(row["nacks"])
            and int(row["acknowledgements"]) == int(row["requests_sent"])
            and bool(row["request_lifecycle_valid"])
            for row in factorized
        ),
        "channel_bounded": all(int(row["max_pending_requests"]) <= int(channel_cap) for row in factorized),
        "no_fallback": all(bool(row["no_oracle_or_model_fallback"]) for row in rows),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest, generation = generate_structural_pool(
        split="development",
        base_seed=int(args.base_seed),
        max_candidates_per_coupling=int(args.max_candidates_per_coupling),
        instances_per_cell=int(args.instances_per_cell),
        r_value=int(args.register),
        reference_cap=int(args.reference_cap),
    )
    counts = Counter(str(row["cell"]) for row in manifest)
    expected = Counter({"under_low": 16, "under_high": 16, "over_low": 16, "over_high": 16})
    manifest_checks = {
        "pool_complete": bool(generation["complete"]) and counts == expected,
        "unique_ids": len({str(row["instance_id"]) for row in manifest}) == len(manifest),
        "unique_clause_hashes": len({str(row["clause_sha256"]) for row in manifest}) == len(manifest),
        "planted_removed": all("planted_assignment" not in row and bool(row["planted_assignment_removed"]) for row in manifest),
        "fixed_clause_count": all(int(row["n_clauses"]) == 192 for row in manifest),
        "exact_coupling": all(
            int(row["cross_clause_count"]) == (19 if row["coupling"] == "low" else 77)
            for row in manifest
        ),
        "reference_solved": all(bool(row["reference_solved"]) for row in manifest),
        "strata_exact": all(
            (row["capacity"] == "under" and int(row["global_recovery_distance"]) <= 8)
            or (
                row["capacity"] == "over_local_fit"
                and int(row["global_recovery_distance"]) > 8
                and int(row["local_recovery_distance"]) <= 8
            )
            for row in manifest
        ),
        "selection_no_arm_outcomes": all(
            str(row["selection_rule"]) == "reference_recovery_stratum_only_no_evaluated_arm_outcomes"
            for row in manifest
        ),
    }
    if not all(manifest_checks.values()):
        return {
            "schema": "multiagent_community_sat_development_v1",
            "status": "SAT_POOL_NO_GO",
            "headline_eligible": False,
            "generation": generation,
            "manifest_checks": manifest_checks,
            "manifest": manifest,
            "rows": [],
        }

    selected = []
    for cell in ("under_low", "under_high", "over_low", "over_high"):
        selected.extend(sorted((row for row in manifest if row["cell"] == cell), key=lambda row: row["candidate_index"])[: int(args.smoke_per_cell)])
    smoke_rows = []
    for instance in selected:
        for arm in ALL_ARMS:
            smoke_rows.append(
                run_sat_arm(
                    instance,
                    arm,
                    r_value=int(args.register),
                    activation_cap=int(args.activation_cap),
                    channel_cap=int(args.channel_cap),
                    route_seed=int(args.route_seed),
                )
            )
    replay_mismatches = []
    for instance in selected[:4]:
        for arm in FACTOR_ARMS:
            first = run_sat_arm(
                instance,
                arm,
                r_value=int(args.register),
                activation_cap=int(args.activation_cap),
                channel_cap=int(args.channel_cap),
                route_seed=int(args.route_seed),
            )
            second = run_sat_arm(
                instance,
                arm,
                r_value=int(args.register),
                activation_cap=int(args.activation_cap),
                channel_cap=int(args.channel_cap),
                route_seed=int(args.route_seed),
            )
            different = [field for field in REPLAY_FIELDS if first.get(field) != second.get(field)]
            if different:
                replay_mismatches.append({
                    "instance_id": instance["instance_id"],
                    "arm": arm,
                    "fields": different,
                })
    protocol_checks = _protocol_checks(smoke_rows, int(args.register), int(args.channel_cap))
    smoke_cardinality = Counter((str(row["cell"]), str(row["arm"])) for row in smoke_rows)
    gates = {
        "manifest": all(manifest_checks.values()),
        "smoke_cardinality": len(smoke_rows) == 4 * int(args.smoke_per_cell) * len(ALL_ARMS)
        and all(value == int(args.smoke_per_cell) for value in smoke_cardinality.values()),
        "protocol": all(protocol_checks.values()),
        "deterministic_replay": not replay_mismatches,
    }
    status = "SAT_DEVELOPMENT_GO" if all(gates.values()) else "SAT_DEVELOPMENT_NO_GO"
    return {
        "schema": "multiagent_community_sat_development_v1",
        "status": status,
        "headline_eligible": False,
        "config": vars(args),
        "generation": generation,
        "manifest_checks": manifest_checks,
        "manifest": manifest,
        "smoke_instance_ids": [str(row["instance_id"]) for row in selected],
        "rows": smoke_rows,
        "summary": summarize_rows(smoke_rows),
        "protocol_checks": protocol_checks,
        "replay_mismatches": replay_mismatches,
        "gates": gates,
        "honesty": {
            "development_only": True,
            "evaluated_outcomes_used_for_independent_selection": False,
            "no_gpu_or_llm": True,
        },
    }


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# Community SAT Development Gate",
        "",
        f"## Verdict: **`{payload['status']}`**",
        "",
        "- Evidence tier: development implementation/pool gate",
        "- GPU/LLM use: none",
        "- Independent SAT outcomes observed: No",
        "",
        "## Gates",
        "",
        "| Gate | Result |",
        "|---|---:|",
    ]
    for key, value in payload.get("gates", {}).items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")
    lines.extend(["", "## Manifest audit", ""])
    for key, value in payload["manifest_checks"].items():
        lines.append(f"- `{key}`: **{'PASS' if value else 'FAIL'}**")
    if payload.get("summary"):
        lines.extend([
            "",
            "## Smoke outcomes",
            "",
            "| Cell | Arm | n | Solve | Penalized work | Status |",
            "|---|---|---:|---:|---:|---|",
        ])
        for row in payload["summary"]:
            statuses = ", ".join(f"{key}={value}" for key, value in sorted(row["status_counts"].items()))
            lines.append(
                f"| {row['cell']} | `{row['arm']}` | {row['n']} | {row['solve_rate']:.3f} | "
                f"{row['mean_penalized_work']:.1f} | {statuses} |"
            )
    lines.extend([
        "",
        "## Protocol",
        "",
    ])
    for key, value in payload.get("protocol_checks", {}).items():
        lines.append(f"- `{key}`: **{'PASS' if value else 'FAIL'}**")
    lines.extend([
        "",
        "Smoke outcomes are implementation diagnostics only and do not select independent instances or alter any frozen threshold.",
        "",
        "## Artifacts",
        "",
        "- [Development manifest](instance_manifest.json)",
        "- [Smoke JSON](smoke_results.json)",
        "- [Frozen replication contract](../../specs/multiagent_community_sat_replication_contract_v1.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run community-SAT development gate.")
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_community_sat_development"))
    parser.add_argument("--base-seed", type=int, default=210000)
    parser.add_argument("--max-candidates-per-coupling", type=int, default=20000)
    parser.add_argument("--instances-per-cell", type=int, default=16)
    parser.add_argument("--smoke-per-cell", type=int, default=4)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--reference-cap", type=int, default=100000)
    parser.add_argument("--activation-cap", type=int, default=20000)
    parser.add_argument("--channel-cap", type=int, default=16)
    parser.add_argument("--route-seed", type=int, default=20260712)
    args = parser.parse_args()
    payload = run(args)
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "schema": "multiagent_community_sat_development_manifest_v1",
        "status": payload["status"],
        "headline_eligible": False,
        "rows": payload.pop("manifest"),
    }
    (output_dir / "instance_manifest.json").write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "smoke_results.json").write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_dir / "DEVELOPMENT.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "report": str((output_dir / "DEVELOPMENT.md").relative_to(REPO_ROOT)),
        "manifest_sha256": _sha256(output_dir / "instance_manifest.json"),
    }))
    if payload["status"] != "SAT_DEVELOPMENT_GO":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
