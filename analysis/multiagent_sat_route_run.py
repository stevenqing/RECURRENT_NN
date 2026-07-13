"""One-shot locked execution of the SAT route-identifiability confirmation."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.multiagent_community_sat_run import _protocol_audit
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.multiagent_community_sat import run_sat_arm


LOCK_SCHEMA = "multiagent_sat_route_confirmation_execution_lock_v1"
MANIFEST_SCHEMA = "multiagent_sat_route_confirmation_manifest_v1"
MANIFEST_STATUS = "SAT_ROUTE_CONFIRMATION_MANIFEST_FROZEN"
ARMS = (
    "independent_local_cbj_sat",
    "independent_local_random_valid_sat",
    "independent_local_no_cross_sat",
    "factorized_central_cbj_sat",
    "monolith_MR_sat",
)


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lock(path: Path) -> tuple[dict[str, Any], dict[str, bool]]:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema") != LOCK_SCHEMA or lock.get("status") != "EXECUTION_LOCKED":
        raise ValueError("invalid SAT route-confirmation execution lock")
    checks = {
        key: _sha256(_resolve(item["path"])) == str(item["sha256"])
        for key, item in lock["files"].items()
    }
    if not all(checks.values()):
        raise ValueError(f"SAT route-confirmation hash mismatch: {checks}")
    return lock, checks


def run(args: argparse.Namespace) -> dict[str, Any]:
    lock_path = _resolve(args.execution_lock)
    lock, lock_checks = verify_lock(lock_path)
    manifest_path = _resolve(lock["files"]["route_manifest"]["path"])
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest_payload.get("schema") != MANIFEST_SCHEMA or manifest_payload.get("status") != MANIFEST_STATUS:
        raise ValueError("SAT route-confirmation manifest is not frozen")
    manifest = list(manifest_payload["rows"])
    if len(manifest) != 200 or len({str(row["instance_id"]) for row in manifest}) != 200:
        raise ValueError("SAT route-confirmation manifest cardinality mismatch")
    if any(str(row.get("cell")) != "over_high" for row in manifest):
        raise ValueError("route-confirmation manifest contains a non-over-high row")
    if any("planted_assignment" in row for row in manifest):
        raise ValueError("planted assignment leaked into route-confirmation manifest")

    rows: list[dict[str, Any]] = []
    for index, instance in enumerate(manifest):
        for arm in ARMS:
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
            print(json.dumps({"event": "sat_route_progress", "instances_completed": index + 1}), flush=True)

    arm_counts = Counter(str(row["arm"]) for row in rows)
    instance_counts = Counter(str(row["instance_id"]) for row in rows)
    cardinality = {
        "rows_1000": len(rows) == 1000,
        "five_arms": set(arm_counts) == set(ARMS),
        "two_hundred_per_arm": all(arm_counts[arm] == 200 for arm in ARMS),
        "five_per_instance": len(instance_counts) == 200 and all(value == 5 for value in instance_counts.values()),
        "over_high_only": all(str(row["cell"]) == "over_high" for row in rows),
    }
    protocol = _protocol_audit(rows, int(args.register), int(args.channel_cap))
    complete = all(cardinality.values()) and protocol["pass"]
    return {
        "schema": "multiagent_sat_route_confirmation_raw_v1",
        "status": "SAT_ROUTE_CONFIRMATION_RAW_COMPLETE" if complete else "SAT_ROUTE_CONFIRMATION_PROTOCOL_FAIL",
        "study_role": "one_shot_independent_symbolic_route_confirmation",
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
            "arms": list(ARMS),
        },
        "cardinality": cardinality,
        "arm_counts": dict(sorted(arm_counts.items())),
        "protocol_audit": protocol,
        "rows": rows,
        "honesty": {
            "one_shot": True,
            "manifest_not_used_for_smoke": True,
            "planted_assignment_unavailable": True,
            "no_gpu_or_llm": True,
            "qwen_authorized_only_by_future_frozen_analysis": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run locked SAT route confirmation.")
    parser.add_argument("--execution-lock", type=Path, default=Path("specs/multiagent_sat_route_confirmation_execution_lock_v1.json"))
    parser.add_argument("--output", type=Path, default=Path("results/multiagent_sat_route_confirmation/raw_results.json"))
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--activation-cap", type=int, default=20000)
    parser.add_argument("--channel-cap", type=int, default=16)
    parser.add_argument("--route-seed", type=int, default=20260712)
    args = parser.parse_args()
    output = _resolve(args.output)
    if output.exists():
        raise SystemExit(f"one-shot output already exists; refusing overwrite: {output}")
    payload = run(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "rows": len(payload["rows"]),
        "path": str(output.relative_to(REPO_ROOT)),
        "sha256": _sha256(output),
    }))
    if payload["status"] != "SAT_ROUTE_CONFIRMATION_RAW_COMPLETE":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
