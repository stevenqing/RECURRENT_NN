"""One-shot locked execution of the independent community-SAT replication."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.multiagent_community_sat import ALL_ARMS, FACTOR_ARM_NAMES, run_sat_arm


LOCK_SCHEMA = "multiagent_community_sat_execution_lock_v1"
FACTOR_ARMS = set(FACTOR_ARM_NAMES.values())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _verify_lock(path: Path) -> tuple[dict[str, Any], dict[str, bool]]:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema") != LOCK_SCHEMA or lock.get("status") != "EXECUTION_LOCKED":
        raise ValueError("invalid SAT execution lock")
    checks = {
        key: _sha256(_resolve(item["path"])) == str(item["sha256"])
        for key, item in lock["files"].items()
    }
    if not all(checks.values()):
        raise ValueError(f"SAT execution hash mismatch: {checks}")
    return lock, checks


def _protocol_audit(rows: list[dict[str, Any]], r_value: int, channel_cap: int) -> dict[str, Any]:
    factorized = [row for row in rows if row["arm"] in FACTOR_ARMS]
    checks = {
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
        "planted_unavailable": True,
    }
    violations = []
    for row in factorized:
        failed = []
        if int(row["ownership_violations"]) != 0:
            failed.append("ownership")
        if int(row["priority_direction_violations"]) != 0:
            failed.append("priority")
        if int(row["out_of_window_rollback_executions"]) != 0:
            failed.append("out_of_window")
        if not bool(row["request_lifecycle_valid"]):
            failed.append("lifecycle")
        if row["status"] == "OFFICIAL_SCORE_FAIL":
            failed.append("official_score")
        if failed:
            violations.append({"instance_id": row["instance_id"], "arm": row["arm"], "failed": failed})
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
            "out_of_window_executions": sum(int(row["out_of_window_rollback_executions"]) for row in factorized),
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    lock_path = _resolve(args.execution_lock)
    lock, lock_checks = _verify_lock(lock_path)
    manifest_path = _resolve(lock["files"]["independent_manifest"]["path"])
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest_payload.get("status") != "SAT_INDEPENDENT_MANIFEST_FROZEN":
        raise ValueError("SAT manifest is not frozen")
    manifest = list(manifest_payload["rows"])
    expected_counts = Counter({"under_low": 50, "under_high": 50, "over_low": 50, "over_high": 50})
    if len(manifest) != 200 or Counter(str(row["cell"]) for row in manifest) != expected_counts:
        raise ValueError("SAT manifest cardinality mismatch")
    if any("planted_assignment" in row for row in manifest):
        raise ValueError("planted assignment leaked into SAT execution manifest")
    rows = []
    for index, instance in enumerate(manifest):
        for arm in ALL_ARMS:
            rows.append(
                run_sat_arm(
                    instance,
                    arm,
                    m_agents=int(args.agents),
                    r_value=int(args.register),
                    activation_cap=int(args.activation_cap),
                    channel_cap=int(args.channel_cap),
                    route_seed=int(args.route_seed),
                )
            )
        if (index + 1) % 10 == 0:
            print(json.dumps({"event": "sat_replication_progress", "instances_completed": index + 1}), flush=True)
    arm_counts = Counter(str(row["arm"]) for row in rows)
    cell_arm_counts = Counter((str(row["cell"]), str(row["arm"])) for row in rows)
    cardinality = {
        "rows_1600": len(rows) == 1600,
        "eight_arms": set(arm_counts) == set(ALL_ARMS),
        "two_hundred_per_arm": all(arm_counts[arm] == 200 for arm in ALL_ARMS),
        "fifty_per_cell_arm": len(cell_arm_counts) == 32 and all(value == 50 for value in cell_arm_counts.values()),
        "instances_200": len({str(row["instance_id"]) for row in rows}) == 200,
    }
    protocol = _protocol_audit(rows, int(args.register), int(args.channel_cap))
    complete = all(cardinality.values()) and protocol["pass"]
    return {
        "schema": "multiagent_community_sat_raw_v1",
        "status": "SAT_RAW_COMPLETE" if complete else "SAT_PROTOCOL_FAIL",
        "study_role": "one_shot_independent_second_substrate_replication",
        "headline_eligible": False,
        "execution_lock": str(args.execution_lock),
        "execution_lock_sha256": _sha256(lock_path),
        "lock_checks": lock_checks,
        "input_hashes": {key: item["sha256"] for key, item in lock["files"].items()},
        "config": {
            "agents": int(args.agents),
            "register": int(args.register),
            "activation_cap": int(args.activation_cap),
            "channel_cap": int(args.channel_cap),
            "route_seed": int(args.route_seed),
        },
        "cardinality": cardinality,
        "arm_counts": dict(sorted(arm_counts.items())),
        "protocol_audit": protocol,
        "rows": rows,
        "honesty": {
            "one_shot": True,
            "independent_instances_used_for_smoke": False,
            "planted_assignment_unavailable": True,
            "no_gpu_or_llm": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run locked community-SAT replication.")
    parser.add_argument("--execution-lock", type=Path, default=Path("specs/multiagent_community_sat_execution_lock_v1.json"))
    parser.add_argument("--output", type=Path, default=Path("results/multiagent_community_sat_replication/raw_results.json"))
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--activation-cap", type=int, default=20000)
    parser.add_argument("--channel-cap", type=int, default=16)
    parser.add_argument("--route-seed", type=int, default=20260712)
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
    if payload["status"] != "SAT_RAW_COMPLETE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
