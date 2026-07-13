"""One-shot raw execution for the locked structural confirmatory study."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.multiagent_factorization_controls import (
    compare_shadow_to_frozen,
    run_factorized_control,
)
from experiments.multiagent_independent_local import (
    _run_baseline_rows,
    _run_independent,
)


EXPECTED_LOCK_SCHEMA = "multiagent_structural_confirmatory_execution_lock_v1"
FACTOR_ARMS = {
    "independent_local_cbj_v1_exact",
    "factorized_central_cbj",
    "independent_local_random_valid",
    "independent_local_no_cross",
}
ALL_ARMS = FACTOR_ARMS | {
    "global_trail_cbj",
    "centralized_sharded_MR",
    "monolith_MR",
    "monolith_R",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _verify_lock(lock_path: Path) -> tuple[dict[str, Any], dict[str, bool]]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("schema") != EXPECTED_LOCK_SCHEMA or lock.get("status") != "EXECUTION_LOCKED":
        raise ValueError("confirmatory execution lock is missing or invalid")
    checks = {
        name: _sha256(_resolve(item["path"])) == str(item["sha256"])
        for name, item in lock["files"].items()
    }
    if not all(checks.values()):
        raise ValueError(f"execution lock hash mismatch: {checks}")
    return lock, checks


def _trim_samples(row: dict[str, Any]) -> dict[str, Any]:
    output = dict(row)
    samples = list(output.get("protocol_samples", []))
    output["protocol_sample_count"] = len(samples)
    output["protocol_samples"] = samples[:8]
    return output


def _protocol_audit(rows: list[dict[str, Any]], channel_cap: int) -> dict[str, Any]:
    factorized = [row for row in rows if row["arm"] in FACTOR_ARMS]
    checks = {
        "no_direct_cross_agent_mutation": all(int(row["cross_agent_direct_mutations"]) == 0 for row in factorized),
        "owner_only_mutation": all(int(row["ownership_violations"]) == 0 for row in factorized),
        "acyclic_priority": all(int(row["priority_direction_violations"]) == 0 for row in factorized),
        "no_out_of_window_execution": all(
            int(row["out_of_window_rollback_executions"]) == 0 for row in factorized
        ),
        "window_occupancy_bounded": all(
            int(row["max_local_register"]) <= int(row["declared_per_agent_window"])
            for row in factorized
        ),
        "request_conservation": all(
            int(row["requests_sent"]) == int(row["requests_executed"]) + int(row["nacks"])
            and int(row["acknowledgements"]) == int(row["requests_sent"])
            and bool(row["request_lifecycle_valid"])
            for row in factorized
        ),
        "channel_bounded": all(
            int(row["max_pending_requests"]) <= int(channel_cap) for row in factorized
        ),
        "no_global_trail": all(bool(row["no_global_trail"]) for row in factorized),
        "independent_agent_state": all(bool(row["independent_agent_state"]) for row in factorized),
        "no_fallback": all(bool(row["no_oracle_or_model_fallback"]) for row in factorized),
        "official_scoring": all(row["status"] != "OFFICIAL_SCORE_FAIL" for row in rows),
        "shadow_equivalence": all(
            bool(row.get("shadow_equivalence", True))
            for row in factorized
            if row["arm"] == "independent_local_cbj_v1_exact"
        ),
    }
    violations = []
    for row in factorized:
        failed = []
        if int(row["cross_agent_direct_mutations"]) != 0:
            failed.append("direct_mutation")
        if int(row["ownership_violations"]) != 0:
            failed.append("ownership")
        if int(row["priority_direction_violations"]) != 0:
            failed.append("priority")
        if int(row["out_of_window_rollback_executions"]) != 0:
            failed.append("out_of_window_execution")
        if not bool(row["request_lifecycle_valid"]):
            failed.append("request_lifecycle")
        if row["status"] == "OFFICIAL_SCORE_FAIL":
            failed.append("official_scoring")
        if failed:
            violations.append({
                "instance_id": row["instance_id"],
                "cell": row["cell"],
                "arm": row["arm"],
                "failed": failed,
            })
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "violations": violations,
        "totals": {
            "factorized_rows": len(factorized),
            "requests_sent": sum(int(row["requests_sent"]) for row in factorized),
            "acknowledgements": sum(int(row["acknowledgements"]) for row in factorized),
            "nacks": sum(int(row["nacks"]) for row in factorized),
            "window_rejections": sum(int(row["window_rejections"]) for row in factorized),
            "out_of_window_executions": sum(
                int(row["out_of_window_rollback_executions"]) for row in factorized
            ),
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    lock_path = _resolve(args.execution_lock)
    lock, lock_checks = _verify_lock(lock_path)
    manifest_path = _resolve(lock["files"]["confirmatory_manifest"]["path"])
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest_payload.get("status") != "CONFIRMATORY_MANIFEST_FROZEN":
        raise ValueError("confirmatory manifest is not frozen")
    manifest = list(manifest_payload["rows"])
    expected_counts = Counter({"under_low": 50, "under_high": 50, "over_low": 50, "over_high": 50})
    if len(manifest) != 200 or Counter(str(row["cell"]) for row in manifest) != expected_counts:
        raise ValueError("confirmatory manifest cardinality mismatch")

    factor_rows: list[dict[str, Any]] = []
    shadow_mismatches = []
    for index, row in enumerate(manifest):
        frozen = _run_independent(
            row,
            "independent_local_cbj",
            int(args.register),
            int(args.activation_cap),
            int(args.channel_cap),
        )
        shadow = run_factorized_control(
            row,
            "queued_deepest",
            int(args.register),
            int(args.activation_cap),
            int(args.channel_cap),
            int(args.route_seed),
        )
        different = compare_shadow_to_frozen(frozen, shadow)
        if different:
            shadow_mismatches.append({
                "instance_id": row["instance_id"],
                "cell": row["cell"],
                "fields": different,
            })
            raise RuntimeError(f"frozen-shadow mismatch before row {index}: {shadow_mismatches[-1]}")
        proposed = dict(frozen)
        proposed.update({
            "arm": "independent_local_cbj_v1_exact",
            "control_mode": "hash_locked_frozen_v1",
            "delivery_mode": "queued_target_activation",
            "route_mode": "deepest_cbj",
            "penalized_work": (
                int(frozen["aggregate_work"])
                if bool(frozen["solved"])
                else max(int(frozen["aggregate_work"]), int(args.activation_cap))
            ),
            "preserved_global_suffix_assignments": int(shadow["preserved_global_suffix_assignments"]),
            "preserved_dependency_unrelated_assignments": int(
                shadow["preserved_dependency_unrelated_assignments"]
            ),
            "rollback_events_with_global_preservation": int(
                shadow["rollback_events_with_global_preservation"]
            ),
            "rollback_events_with_unrelated_preservation": int(
                shadow["rollback_events_with_unrelated_preservation"]
            ),
            "cross_agent_rollback_events": int(shadow["cross_agent_rollback_events"]),
            "local_rollback_events": int(shadow["local_rollback_events"]),
            "no_cross_failures": 0,
            "trace_sha256": shadow["trace_sha256"],
            "trace_event_count": shadow["trace_event_count"],
            "shadow_equivalence": True,
            "evaluation_mode": "hash_locked_frozen_v1_confirmatory",
        })
        factor_rows.append(_trim_samples(proposed))
        for mode in ("central_deepest", "queued_random_valid", "queued_no_cross"):
            control = run_factorized_control(
                row,
                mode,
                int(args.register),
                int(args.activation_cap),
                int(args.channel_cap),
                int(args.route_seed),
            )
            factor_rows.append(_trim_samples(control))
        if (index + 1) % 10 == 0:
            print(json.dumps({"event": "confirmatory_progress", "instances_completed": index + 1}), flush=True)

    baseline_rows = _run_baseline_rows(
        manifest,
        int(args.agents),
        int(args.register),
        int(args.activation_cap),
    )
    for row in baseline_rows:
        row["penalized_work"] = (
            int(row["aggregate_work"])
            if bool(row["solved"])
            else max(int(row["aggregate_work"]), int(args.activation_cap))
        )
        row["preserved_global_suffix_assignments"] = 0
        row["preserved_dependency_unrelated_assignments"] = 0
        row["rollback_events_with_global_preservation"] = 0
        row["rollback_events_with_unrelated_preservation"] = 0
        row["cross_agent_rollback_events"] = 0
        row["local_rollback_events"] = 0
        row["no_cross_failures"] = 0
        row["trace_sha256"] = None
        row["trace_event_count"] = None
        row["protocol_sample_count"] = 0

    rows = factor_rows + baseline_rows
    arm_counts = Counter(str(row["arm"]) for row in rows)
    cell_arm_counts = Counter((str(row["cell"]), str(row["arm"])) for row in rows)
    cardinality_checks = {
        "total_rows_1600": len(rows) == 1600,
        "eight_arms": set(arm_counts) == ALL_ARMS,
        "two_hundred_per_arm": all(arm_counts[arm] == 200 for arm in ALL_ARMS),
        "fifty_per_cell_arm": all(value == 50 for value in cell_arm_counts.values())
        and len(cell_arm_counts) == 32,
        "unique_instances_200": len({str(row["instance_id"]) for row in rows}) == 200,
    }
    protocol = _protocol_audit(rows, int(args.channel_cap))
    complete = all(cardinality_checks.values()) and protocol["pass"] and not shadow_mismatches
    return {
        "schema": "multiagent_structural_confirmatory_raw_v1",
        "status": "RAW_CONFIRMATORY_COMPLETE" if complete else "CONFIRMATORY_PROTOCOL_FAIL",
        "study_role": "one_shot_independent_symbolic_confirmation",
        "headline_eligible": False,
        "execution_lock": str(args.execution_lock),
        "lock_hash": _sha256(lock_path),
        "lock_checks": lock_checks,
        "input_hashes": {
            name: item["sha256"] for name, item in lock["files"].items()
        },
        "config": {
            "agents": int(args.agents),
            "register": int(args.register),
            "activation_cap": int(args.activation_cap),
            "channel_cap": int(args.channel_cap),
            "route_seed": int(args.route_seed),
        },
        "cardinality_checks": cardinality_checks,
        "arm_counts": dict(sorted(arm_counts.items())),
        "cell_arm_counts": {
            f"{cell}::{arm}": count for (cell, arm), count in sorted(cell_arm_counts.items())
        },
        "shadow_mismatches": shadow_mismatches,
        "protocol_audit": protocol,
        "rows": rows,
        "honesty": {
            "one_shot": True,
            "development_instances_used_for_smoke_only": True,
            "confirmatory_instances_used_for_smoke": False,
            "no_llm_or_gpu": True,
            "critical_path_is_idealized": True,
            "does_not_establish": "A complete raw symbolic run still requires the frozen statistical analysis and literature novelty audit before any contribution read.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run locked structural confirmation once.")
    parser.add_argument(
        "--execution-lock",
        type=Path,
        default=Path("specs/multiagent_structural_confirmatory_execution_lock_v1.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/multiagent_structural_confirmatory/raw_results.json"),
    )
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--activation-cap", type=int, default=20000)
    parser.add_argument("--channel-cap", type=int, default=16)
    parser.add_argument("--route-seed", type=int, default=20260711)
    args = parser.parse_args()
    payload = run(args)
    output = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "rows": len(payload["rows"]),
        "path": str(output.relative_to(REPO_ROOT)),
        "sha256": _sha256(output),
    }))
    if payload["status"] != "RAW_CONFIRMATORY_COMPLETE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
