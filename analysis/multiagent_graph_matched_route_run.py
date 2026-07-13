"""One-shot execution of graph matched-window route confirmation."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.multiagent_factorization_controls import run_factorized_control
from experiments.multiagent_graph_route_controls import ARM as PROPOSED, run_deepest_window_valid_graph
from experiments.multiagent_independent_local import _run_baseline_rows, _run_independent


LOCK_SCHEMA = "multiagent_graph_matched_route_execution_lock_v1"
MANIFEST_STATUS = "GRAPH_MATCHED_ROUTE_CONFIRMATION_MANIFEST_FROZEN"
RANDOM = "independent_local_random_valid"
FROZEN = "independent_local_cbj_v1_exact"
NO_CROSS = "independent_local_no_cross"
MONOLITH = "monolith_MR"
ARMS = (PROPOSED, RANDOM, FROZEN, NO_CROSS, MONOLITH)
FACTOR_ARMS = set(ARMS) - {MONOLITH}


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lock(path: Path) -> tuple[dict[str, Any], dict[str, bool]]:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema") != LOCK_SCHEMA or lock.get("status") != "EXECUTION_LOCKED":
        raise ValueError("invalid graph matched-route execution lock")
    checks = {key: _sha256(_resolve(item["path"])) == str(item["sha256"]) for key, item in lock["files"].items()}
    if not all(checks.values()):
        raise ValueError(f"graph matched-route hash mismatch: {checks}")
    return lock, checks


def _trim(row: dict[str, Any]) -> dict[str, Any]:
    output = dict(row)
    samples = list(output.get("protocol_samples", []))
    output["protocol_sample_count"] = len(samples)
    output["protocol_samples"] = samples[:8]
    return output


def _penalize(row: dict[str, Any], cap: int) -> dict[str, Any]:
    output = dict(row)
    output["penalized_work"] = int(output["aggregate_work"]) if output["solved"] else max(int(output["aggregate_work"]), int(cap))
    return output


def _protocol(rows: list[dict[str, Any]], r_value: int, channel_cap: int) -> dict[str, Any]:
    factorized = [row for row in rows if row["arm"] in FACTOR_ARMS]
    checks = {
        "official_scoring": all(row["status"] != "OFFICIAL_SCORE_FAIL" for row in rows),
        "no_direct_cross_agent_mutation": all(int(row["cross_agent_direct_mutations"]) == 0 for row in factorized),
        "owner_only_mutation": all(int(row["ownership_violations"]) == 0 for row in factorized),
        "acyclic_priority": all(int(row.get("priority_direction_violations", 0)) == 0 for row in factorized),
        "no_out_of_window_execution": all(int(row.get("out_of_window_rollback_executions", 0)) == 0 for row in factorized),
        "window_occupancy_bounded": all(int(row["max_local_register"]) <= int(r_value) for row in factorized),
        "request_conservation": all(
            int(row["requests_sent"]) == int(row["requests_executed"]) + int(row["nacks"])
            and int(row["acknowledgements"]) == int(row["requests_sent"])
            and bool(row["request_lifecycle_valid"])
            for row in factorized
        ),
        "channel_bounded": all(int(row["max_pending_requests"]) <= int(channel_cap) for row in factorized),
        "no_global_trail": all(bool(row["no_global_trail"]) for row in factorized),
        "independent_state": all(bool(row["independent_agent_state"]) for row in factorized),
        "no_fallback": all(bool(row["no_oracle_or_model_fallback"]) for row in rows),
        "proposed_filter": all(row.get("candidate_filter") == "target_owner_window_valid" for row in factorized if row["arm"] == PROPOSED),
        "proposed_rank": all(row.get("candidate_ranking") == "maximum_fixed_order_position" for row in factorized if row["arm"] == PROPOSED),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "totals": {
            "factorized_rows": len(factorized),
            "requests_sent": sum(int(row["requests_sent"]) for row in factorized),
            "acknowledgements": sum(int(row["acknowledgements"]) for row in factorized),
            "nacks": sum(int(row["nacks"]) for row in factorized),
            "window_rejections": sum(int(row.get("window_rejections", 0)) for row in factorized),
            "out_of_window_executions": sum(int(row.get("out_of_window_rollback_executions", 0)) for row in factorized),
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    lock_path = _resolve(args.execution_lock)
    lock, lock_checks = verify_lock(lock_path)
    manifest_path = _resolve(lock["files"]["graph_manifest"]["path"])
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest_payload.get("status") != MANIFEST_STATUS:
        raise ValueError("graph matched-route manifest is not frozen")
    manifest = list(manifest_payload["rows"])
    expected_counts = Counter({"under_low": 50, "under_high": 50, "over_low": 50, "over_high": 50})
    if len(manifest) != 200 or Counter(str(row["cell"]) for row in manifest) != expected_counts:
        raise ValueError("graph matched-route manifest cardinality mismatch")

    rows: list[dict[str, Any]] = []
    for index, instance in enumerate(manifest):
        proposed = run_deepest_window_valid_graph(
            instance,
            r_value=int(args.register),
            activation_cap=int(args.activation_cap),
            channel_cap=int(args.channel_cap),
            route_seed=int(args.route_seed),
        )
        rows.append(_trim(_penalize(proposed, int(args.activation_cap))))
        random_valid = run_factorized_control(instance, "queued_random_valid", int(args.register), int(args.activation_cap), int(args.channel_cap), int(args.route_seed))
        rows.append(_trim(_penalize(random_valid, int(args.activation_cap))))
        frozen = _run_independent(instance, "independent_local_cbj", int(args.register), int(args.activation_cap), int(args.channel_cap))
        frozen = dict(frozen)
        frozen.update({
            "arm": FROZEN,
            "control_mode": "hash_locked_frozen_v1",
            "route_mode": "deepest_cbj",
            "penalized_work": int(frozen["aggregate_work"]) if frozen["solved"] else max(int(frozen["aggregate_work"]), int(args.activation_cap)),
        })
        rows.append(_trim(frozen))
        no_cross = run_factorized_control(instance, "queued_no_cross", int(args.register), int(args.activation_cap), int(args.channel_cap), int(args.route_seed))
        rows.append(_trim(_penalize(no_cross, int(args.activation_cap))))
        if (index + 1) % 10 == 0:
            print(json.dumps({"event": "graph_matched_route_progress", "instances_completed": index + 1}), flush=True)

    baseline = _run_baseline_rows(manifest, int(args.agents), int(args.register), int(args.activation_cap))
    monolith_rows = [_penalize(row, int(args.activation_cap)) for row in baseline if row["arm"] == MONOLITH]
    rows.extend(monolith_rows)
    replay = [
        _trim(_penalize(run_deepest_window_valid_graph(
            instance,
            r_value=int(args.register),
            activation_cap=int(args.activation_cap),
            channel_cap=int(args.channel_cap),
            route_seed=int(args.route_seed),
        ), int(args.activation_cap)))
        for instance in manifest[:16]
    ]
    proposed_first = [row for row in rows if row["arm"] == PROPOSED][:16]
    deterministic = all(left == right for left, right in zip(proposed_first, replay))
    arm_counts = Counter(str(row["arm"]) for row in rows)
    cell_arm_counts = Counter((str(row["cell"]), str(row["arm"])) for row in rows)
    cardinality = {
        "rows_1000": len(rows) == 1000,
        "five_arms": set(arm_counts) == set(ARMS),
        "two_hundred_per_arm": all(arm_counts[arm] == 200 for arm in ARMS),
        "fifty_per_cell_arm": len(cell_arm_counts) == 20 and all(value == 50 for value in cell_arm_counts.values()),
        "shadow_replay_16": deterministic,
    }
    protocol = _protocol(rows, int(args.register), int(args.channel_cap))
    complete = all(cardinality.values()) and protocol["pass"]
    return {
        "schema": "multiagent_graph_matched_route_confirmation_raw_v1",
        "status": "GRAPH_MATCHED_ROUTE_RAW_COMPLETE" if complete else "GRAPH_MATCHED_ROUTE_PROTOCOL_FAIL",
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
        "protocol_audit": protocol,
        "rows": rows,
        "honesty": {"one_shot": True, "no_gpu_or_llm": True, "qwen_not_authorized": True},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run graph matched-window route confirmation.")
    parser.add_argument("--execution-lock", type=Path, default=Path("specs/multiagent_graph_matched_route_execution_lock_v1.json"))
    parser.add_argument("--output", type=Path, default=Path("results/multiagent_graph_matched_route_confirmation/raw_results.json"))
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--activation-cap", type=int, default=20000)
    parser.add_argument("--channel-cap", type=int, default=16)
    parser.add_argument("--route-seed", type=int, default=20260711)
    args = parser.parse_args()
    output = _resolve(args.output)
    if output.exists():
        raise SystemExit(f"one-shot output already exists; refusing overwrite: {output}")
    payload = run(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "rows": len(payload["rows"]), "path": str(output.relative_to(REPO_ROOT)), "sha256": _sha256(output)}))
    if payload["status"] != "GRAPH_MATCHED_ROUTE_RAW_COMPLETE":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
