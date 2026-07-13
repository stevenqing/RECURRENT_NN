"""Calibration-only full-path check for pristine AppWorld safety restoration v4."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import appworld

from analysis import recurrent_appworld_generated_typed_provenance_development as frozen_v1
from analysis.recurrent_appworld_generated_typed_provenance_development_v4 import (
    AppWorldV02PristineLifecycleAdapter,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(
            "specs/recurrent_parallel_appworld_generated_typed_provenance_development_v4.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "results/recurrent_parallel_appworld_generated_typed_provenance_calibration_v4"
        ),
    )
    args = parser.parse_args()

    contract_path = resolve(args.contract)
    contract = load_json(contract_path)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError(f"Refusing to overwrite calibration output: {output_dir}")

    parent_contract_path = resolve(contract["parent_contract"])
    v1_results_path = resolve(contract["v1_results"])
    parent_failure_path = resolve(contract["v3_calibration_failure"])
    parent_binding_path = resolve(contract["v3_calibration_binding"])
    parent_lock_path = parent_failure_path.parent / "execution_lock.json"
    capacity_manifest_path = resolve(contract["capacity_manifest"])
    capacity_status_path = resolve(contract["capacity_status"])
    capacity_lock_path = resolve(contract["capacity_lock"])
    capacity_binding_path = resolve(contract["capacity_binding"])
    v1_results = load_json(v1_results_path)
    parent_failure = load_json(parent_failure_path)
    parent_binding = load_json(parent_binding_path)
    capacity_manifest = load_json(capacity_manifest_path)
    capacity_status = load_json(capacity_status_path)
    capacity_binding = load_json(capacity_binding_path)
    calibration_rows = [
        row
        for row in capacity_manifest["rows"]
        if row["task_id"] == contract["calibration_task_id"]
        and row["split"] == contract["calibration_split"]
    ]
    source_root = resolve(contract["source_root"])
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    immutable_paths = [
        contract_path.with_suffix(".md"),
        contract_path,
        parent_contract_path,
        v1_results_path,
        parent_failure_path,
        parent_binding_path,
        parent_lock_path,
        capacity_manifest_path,
        capacity_status_path,
        capacity_lock_path,
        capacity_binding_path,
        resolve("experiments/appworld_live_trace.py"),
        resolve("experiments/appworld_provenance.py"),
        resolve("experiments/appworld_trace_replay.py"),
        resolve("experiments/appworld_typed_provenance.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v2.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v3.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v4.py"),
        resolve("analysis/appworld_generated_typed_provenance_calibration_v4.py"),
    ]
    preflight_checks = {
        "contract_frozen": contract["status"]
        == "FROZEN_BEFORE_V4_CALIBRATION_AND_DEVELOPMENT_OUTCOMES",
        "v1_failure_preserved": v1_results["status"] == contract["v1_required_status"],
        "parent_failure_preserved": parent_failure["status"]
        == contract["v3_required_status"],
        "parent_failure_binding": (
            file_hash(parent_failure_path) == parent_binding["failure_sha256"]
            and file_hash(parent_lock_path) == parent_binding["execution_lock_sha256"]
        ),
        "repair_scope": (
            contract["repair_scope"]["external_process_actions"] == 0
            and contract["repair_scope"]["other_method_changes"] == 0
        ),
        "capacity_status": capacity_status["status"] == contract["capacity_required_status"],
        "capacity_binding": (
            file_hash(capacity_status_path) == capacity_binding["status_sha256"]
            and file_hash(capacity_manifest_path) == capacity_binding["task_manifest_sha256"]
            and file_hash(capacity_lock_path) == capacity_binding["execution_lock_sha256"]
        ),
        "calibration_task_unique": len(calibration_rows) == 1,
        "calibration_task_exists": len(calibration_rows) == 1 and calibration_rows[0]["exists"],
        "source_commit": source_commit == contract["source_commit"],
        "immutable_files": all(path.is_file() for path in immutable_paths),
        "output_absent": not output_dir.exists(),
        "confirmation_sealed": contract["confirmation_outcomes_sealed"] is True,
    }
    if not all(preflight_checks.values()):
        raise RuntimeError(preflight_checks)

    output_dir.mkdir(parents=True)
    lock = {
        "schema": "recurrent_appworld_generated_typed_provenance_calibration_lock_v4",
        "status": "LOCKED_BEFORE_V4_CALIBRATION_OUTCOME",
        "immutable_inputs": {
            str(path.relative_to(REPO_ROOT)): file_hash(path) for path in immutable_paths
        },
        "task_id": calibration_rows[0]["task_id"],
        "task_tree_sha256": calibration_rows[0]["tree_sha256"],
        "confirmation_outcomes_sealed": True,
        "external_process_actions": False,
    }
    lock_path = output_dir / "execution_lock.json"
    write_json(lock_path, lock)
    lock_sha256 = file_hash(lock_path)

    appworld.AppWorld = AppWorldV02PristineLifecycleAdapter
    frozen_v1.SHARD_SCHEMA = "recurrent_appworld_generated_typed_provenance_calibration_shard_v4"
    appworld_root = resolve(contract["appworld_root"])
    appworld.update_root(str(appworld_root))
    shard = frozen_v1.process_task(calibration_rows[0], appworld_root, contract, lock_sha256)
    summary = shard["summary"]
    calibration_checks = {
        "baseline_pass": summary["baseline_pass"] is True,
        "live_calls": summary["live_calls"] >= 1,
        "write_checkpoints": summary["write_checkpoints"] >= 1,
        "no_harness_exception": summary["error_type"] is None,
        "task_scope": (
            summary["task_id"] == contract["calibration_task_id"]
            and summary["variation"] in [1, 2, 3]
        ),
        "immutable_inputs_still_match": all(
            file_hash(path) == lock["immutable_inputs"][str(path.relative_to(REPO_ROOT))]
            for path in immutable_paths
        ),
        "confirmation_sealed": True,
    }
    status = (
        "RPD_APPWORLD_GENERATED_TYPED_PROVENANCE_V4_CALIBRATION_READY"
        if all(calibration_checks.values())
        else "RPD_APPWORLD_GENERATED_TYPED_PROVENANCE_V4_CALIBRATION_FAIL"
    )
    safe_summary = {
        key: summary[key]
        for key in [
            "task_id",
            "generator_id",
            "variation",
            "baseline_pass",
            "live_calls",
            "write_checkpoints",
            "candidate_mutations",
            "strict_mutations",
            "selected_pairs",
            "error_type",
            "error_sha256",
        ]
    }
    result = {
        "schema": "recurrent_appworld_generated_typed_provenance_calibration_v4",
        "status": status,
        "preflight_checks": preflight_checks,
        "calibration_checks": calibration_checks,
        "summary": safe_summary,
        "execution_lock_sha256": lock_sha256,
        "v1_protocol_failure_preserved": True,
        "v2_v3_calibration_failures_preserved": True,
        "guard_performance_used_for_acceptance": False,
        "development_outcomes_observed": False,
        "confirmation_outcomes_sealed": True,
        "protected_content_exported": False,
        "external_process_actions": False,
        "model_gpu_docker_used": False,
        "headline_eligible": False,
    }
    result_path = output_dir / "results.json"
    write_json(result_path, result)
    write_json(
        output_dir / "result_binding.json",
        {
            "execution_lock_sha256": lock_sha256,
            "results_sha256": file_hash(result_path),
        },
    )
    lines = [
        "# AppWorld 0.2 Typed-Provenance v4 Calibration",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Calibration task: {safe_summary['task_id']}",
        f"- Baseline pass: {safe_summary['baseline_pass']}",
        f"- Live calls: {safe_summary['live_calls']}",
        f"- Write checkpoints: {safe_summary['write_checkpoints']}",
        f"- Candidate mutations: {safe_summary['candidate_mutations']}",
        f"- Strict mutations: {safe_summary['strict_mutations']}",
        f"- Selected pairs: {safe_summary['selected_pairs']}",
        f"- Harness error: {safe_summary['error_type']}",
        "- Guard performance used for acceptance: No",
        "- Development outcomes observed: No",
        "- Confirmation outcomes: Sealed",
        "- External process actions: No",
        "",
        "## Calibration checks",
        "",
    ]
    lines.extend(
        f"- `{name}`: **{'PASS' if value else 'FAIL'}**"
        for name, value in calibration_checks.items()
    )
    (output_dir / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"status": status, "summary": safe_summary}))


if __name__ == "__main__":
    main()
