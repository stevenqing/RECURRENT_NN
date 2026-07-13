"""One-shot locked graph confirmation for recurrent correction signal noise."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_core import SIGNAL_SYSTEMS, run_noisy_recurrent_correction


LOCK_SCHEMA = "recurrent_parallel_signal_graph_execution_lock_v1"
MANIFEST_STATUS = "RPD_SIGNAL_GRAPH_MANIFEST_FROZEN"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lock(path: Path) -> tuple[dict[str, Any], dict[str, bool]]:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema") != LOCK_SCHEMA or lock.get("status") != "EXECUTION_LOCKED":
        raise ValueError("invalid recurrent graph signal execution lock")
    checks = {key: _sha256(_resolve(item["path"])) == str(item["sha256"]) for key, item in lock["files"].items()}
    if not all(checks.values()):
        raise ValueError(f"graph signal execution hash mismatch: {checks}")
    return lock, checks


def run(args: argparse.Namespace) -> dict[str, Any]:
    lock_path = _resolve(args.execution_lock)
    lock, lock_checks = verify_lock(lock_path)
    contract = json.loads(_resolve(lock["files"]["contract_json"]["path"]).read_text(encoding="utf-8"))
    execution = contract["execution"]
    manifest = json.loads(_resolve(lock["files"]["confirmatory_manifest"]["path"]).read_text(encoding="utf-8"))
    if manifest.get("status") != MANIFEST_STATUS:
        raise ValueError("graph signal manifest is not frozen")
    instances = list(manifest["rows"])
    if len(instances) != 200 or any("planted_assignment" in row for row in instances):
        raise ValueError("graph signal manifest cardinality/privacy mismatch")

    rows = []
    for index, instance in enumerate(instances):
        for eta in map(float, execution["eta_fp"]):
            for system in map(str, execution["systems"]):
                rows.append(run_noisy_recurrent_correction(instance, system=system, eta_fp=eta, eta_fn=float(execution["eta_fn"]), round_cap=int(execution["round_cap"]), noise_seed=int(execution["noise_seed"])))
        if (index + 1) % 10 == 0:
            print(json.dumps({"event": "graph_signal_confirmation_progress", "instances_completed": index + 1}), flush=True)

    counts = Counter((int(row["partition_diameter"]), float(row["eta_fp"]), str(row["system"])) for row in rows)
    cardinality = {
        "rows_3600": len(rows) == int(execution["expected_rows"]),
        "all_cells_50": len(counts) == 72 and all(value == 50 for value in counts.values()),
        "instances_200": len({str(row["instance_id"]) for row in rows}) == 200,
    }
    semantics = {
        "same_round_reads_zero": all(int(row["same_round_cross_agent_reads"]) == 0 for row in rows),
        "message_age_one": all(int(row["messages_delivered"]) == 0 or int(row["maximum_message_age"]) == 1 for row in rows),
        "local_candidates_valid": all(bool(row["local_candidates_valid"]) for row in rows),
        "official_scoring": all(not row["solved"] or bool(row["official_verification"]) for row in rows),
        "planted_unused": all(not bool(row["planted_assignment_used"]) for row in rows),
    }
    complete = all(cardinality.values()) and all(semantics.values())
    return {
        "schema": "recurrent_parallel_signal_graph_raw_v1",
        "status": "RPD_SIGNAL_GRAPH_RAW_COMPLETE" if complete else "RPD_SIGNAL_GRAPH_PROTOCOL_FAIL",
        "headline_eligible": False,
        "execution_lock": str(args.execution_lock),
        "execution_lock_sha256": _sha256(lock_path),
        "lock_checks": lock_checks,
        "input_hashes": {key: item["sha256"] for key, item in lock["files"].items()},
        "cardinality": cardinality,
        "semantics": semantics,
        "config": execution,
        "rows": rows,
        "honesty": {"one_shot": True, "independent_graph_pool": True, "no_gpu_or_llm": True, "cross_substrate_claim": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run locked recurrent graph signal confirmation.")
    parser.add_argument("--execution-lock", type=Path, default=Path("specs/recurrent_parallel_signal_graph_execution_lock_v1.json"))
    parser.add_argument("--output", type=Path, default=Path("results/recurrent_parallel_signal_graph_confirmation/raw_results.json"))
    args = parser.parse_args()
    output = _resolve(args.output)
    if output.exists():
        raise SystemExit(f"one-shot output already exists; refusing overwrite: {output}")
    payload = run(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "rows": len(payload["rows"]), "sha256": _sha256(output), "path": str(output.relative_to(REPO_ROOT))}))
    if payload["status"] != "RPD_SIGNAL_GRAPH_RAW_COMPLETE":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
