"""Pre-outcome lock for calibrated AppWorld 0.2 typed-provenance development v6."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_runtime_cache(path: Path) -> bool:
    return "__pycache__" in path.parts and path.suffix == ".pyc"


def tree_hash(path: Path, ignore_runtime_cache: bool = False) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path)
        if ignore_runtime_cache and is_runtime_cache(relative):
            continue
        digest.update(str(relative).encode())
        digest.update(hashlib.sha256(item.read_bytes()).digest())
    return digest.hexdigest()


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
            "specs/recurrent_parallel_appworld_generated_typed_provenance_development_v6.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "results/recurrent_parallel_appworld_generated_typed_provenance_development_v6"
        ),
    )
    args = parser.parse_args()

    contract_path = resolve(args.contract)
    contract_md_path = contract_path.with_suffix(".md")
    contract = load_json(contract_path)
    output_dir = resolve(args.output_dir)
    output_was_absent = not output_dir.exists()
    if not output_was_absent:
        raise RuntimeError(f"Refusing to overwrite preflight output: {output_dir}")

    capacity_status_path = resolve(contract["capacity_status"])
    capacity_manifest_path = resolve(contract["capacity_manifest"])
    capacity_lock_path = resolve(contract["capacity_lock"])
    capacity_binding_path = resolve(contract["capacity_binding"])
    capacity_status = load_json(capacity_status_path)
    capacity_manifest = load_json(capacity_manifest_path)
    capacity_lock = load_json(capacity_lock_path)
    capacity_binding = load_json(capacity_binding_path)
    calibration_results_path = resolve(
        "results/recurrent_parallel_appworld_generated_typed_provenance_calibration_v6/results.json"
    )
    calibration_binding_path = calibration_results_path.parent / "result_binding.json"
    calibration_lock_path = calibration_results_path.parent / "execution_lock.json"
    attempt_failure_path = resolve(
        "results/recurrent_parallel_appworld_generated_typed_provenance_preflight_v6_attempt1/failure.json"
    )
    calibration_results = load_json(calibration_results_path)
    calibration_binding = load_json(calibration_binding_path)
    attempt_failure = load_json(attempt_failure_path)
    source_root = resolve(contract["source_root"])
    appworld_root = resolve(contract["appworld_root"])

    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    import appworld

    appworld_module_path = Path(appworld.__file__).resolve()
    expected_python = (source_root / ".venv/bin/python").resolve()
    selected_rows = sorted(
        [row for row in capacity_manifest["rows"] if row["split"] == contract["open_split"]],
        key=lambda row: row["task_id"],
    )
    sealed_rows = sorted(
        [row for row in capacity_manifest["rows"] if row["split"] == contract["sealed_split"]],
        key=lambda row: row["task_id"],
    )
    selected_generators = sorted({row["generator_id"] for row in selected_rows})
    task_root = appworld_root / "data/tasks"
    all_manifest_semantic_hashes_match = all(
        (task_root / row["task_id"]).is_dir()
        and tree_hash(task_root / row["task_id"], ignore_runtime_cache=True)
        == row["tree_sha256"]
        for row in capacity_manifest["rows"]
    )
    runtime_cache_files = [
        item.relative_to(task_root)
        for item in task_root.rglob("*")
        if item.is_file() and is_runtime_cache(item.relative_to(task_root))
    ]
    raw_hash_mismatches = [
        row["task_id"]
        for row in capacity_manifest["rows"]
        if tree_hash(task_root / row["task_id"]) != row["tree_sha256"]
    ]
    cache_only_runtime_drift = (
        all_manifest_semantic_hashes_match
        and all(is_runtime_cache(path) for path in runtime_cache_files)
        and set(raw_hash_mismatches)
        == {path.parts[0] for path in runtime_cache_files}
    )

    immutable_paths = [
        contract_md_path,
        contract_path,
        capacity_status_path,
        capacity_manifest_path,
        capacity_lock_path,
        capacity_binding_path,
        calibration_results_path,
        calibration_binding_path,
        calibration_lock_path,
        attempt_failure_path,
        resolve("experiments/appworld_live_trace.py"),
        resolve("experiments/appworld_provenance.py"),
        resolve("experiments/appworld_trace_replay.py"),
        resolve("experiments/appworld_typed_provenance.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v2.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v3.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v4.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v5.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v6.py"),
        resolve("analysis/appworld_generated_typed_provenance_preflight_v6.py"),
    ]
    checks = {
        "contract_frozen": contract["status"]
        == "FROZEN_BEFORE_V6_CALIBRATION_AND_DEVELOPMENT_OUTCOMES",
        "output_absent": output_was_absent,
        "calibration_ready": calibration_results["status"]
        == "RPD_APPWORLD_GENERATED_TYPED_PROVENANCE_V6_CALIBRATION_READY",
        "calibration_binding": (
            file_hash(calibration_results_path) == calibration_binding["results_sha256"]
            and file_hash(calibration_lock_path) == calibration_binding["execution_lock_sha256"]
        ),
        "calibration_not_development": (
            calibration_results["development_outcomes_observed"] is False
            and calibration_results["guard_performance_used_for_acceptance"] is False
        ),
        "attempt1_failure_preserved": (
            attempt_failure["status"]
            == "RPD_APPWORLD_GENERATED_TYPED_PROVENANCE_V6_PREFLIGHT_FAIL"
            and attempt_failure["development_outcomes_observed"] is False
            and attempt_failure["non_cache_content_mismatch_observed"] is False
        ),
        "capacity_status": capacity_status["status"] == contract["capacity_required_status"],
        "capacity_development_authorized": capacity_status["development_authorized"] is True,
        "capacity_binding": (
            file_hash(capacity_status_path) == capacity_binding["status_sha256"]
            and file_hash(capacity_manifest_path) == capacity_binding["task_manifest_sha256"]
            and file_hash(capacity_lock_path) == capacity_binding["execution_lock_sha256"]
        ),
        "capacity_pre_outcome_lock": (
            capacity_lock["status"] == "LOCKED_BEFORE_GENERATED_TASK_GUARD_OUTCOMES"
            and capacity_lock["guard_outcomes_observed"] is False
        ),
        "source_commit": source_commit == contract["source_commit"],
        "source_environment": (
            Path(sys.executable).resolve() == expected_python
            and source_root in appworld_module_path.parents
        ),
        "data_version": (appworld_root / "data/version.txt").read_text().strip()
        == contract["data_version"],
        "selected_cardinality": len(selected_rows) == contract["expected_open_tasks"],
        "selected_generators": len(selected_generators) == contract["expected_generators"],
        "selected_variations": (
            {row["variation"] for row in selected_rows} == set(contract["open_variations"])
            and all(row["exists"] for row in selected_rows)
        ),
        "sealed_cardinality": len(sealed_rows) == contract["expected_sealed_tasks"],
        "sealed_variations": (
            {row["variation"] for row in sealed_rows} == set(contract["sealed_variations"])
            and all(row["exists"] for row in sealed_rows)
        ),
        "disjoint_splits": not (
            {row["task_id"] for row in selected_rows}
            & {row["task_id"] for row in sealed_rows}
        ),
        "all_task_semantic_hashes": all_manifest_semantic_hashes_match,
        "runtime_drift_cache_only": cache_only_runtime_drift,
        "immutable_files_exist": all(path.is_file() for path in immutable_paths),
        "results_absent": not (output_dir / "results.json").exists(),
        "confirmation_sealed": contract["confirmation_outcomes_sealed"] is True,
        "scope": (
            contract["model_gpu_docker_used"] is False
            and contract["external_process_actions"] is False
            and contract["headline_eligible"] is False
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(checks)

    output_dir.mkdir(parents=True)
    selected_tasks = [
        {
            "task_id": row["task_id"],
            "generator_id": row["generator_id"],
            "variation": row["variation"],
            "split": row["split"],
            "tree_sha256": row["tree_sha256"],
        }
        for row in selected_rows
    ]
    sealed_metadata = [
        {
            "task_id": row["task_id"],
            "variation": row["variation"],
            "tree_sha256": row["tree_sha256"],
        }
        for row in sealed_rows
    ]
    lock = {
        "schema": "recurrent_appworld_generated_typed_provenance_execution_lock_v6",
        "status": "LOCKED_BEFORE_GENERATED_DEVELOPMENT_OUTCOMES",
        "immutable_inputs": {
            str(path.relative_to(REPO_ROOT)): file_hash(path) for path in immutable_paths
        },
        "source_commit": source_commit,
        "selected_generator_ids": selected_generators,
        "selected_tasks": selected_tasks,
        "selected_task_ids_sha256": hashlib.sha256(
            json.dumps([row["task_id"] for row in selected_tasks], separators=(",", ":")).encode()
        ).hexdigest(),
        "sealed_task_metadata_sha256": hashlib.sha256(
            json.dumps(sealed_metadata, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "sealed_task_count": len(sealed_rows),
        "calibration_results_sha256": file_hash(calibration_results_path),
        "confirmation_outcomes_sealed": True,
        "guard_outcomes_observed": False,
        "external_process_actions": False,
    }
    lock_path = output_dir / "execution_lock.json"
    write_json(lock_path, lock)
    preflight = {
        "schema": "recurrent_appworld_generated_typed_provenance_preflight_v6",
        "status": "RPD_APPWORLD_GENERATED_TYPED_PROVENANCE_V6_EXECUTION_READY",
        "checks": checks,
        "execution_lock_sha256": file_hash(lock_path),
        "selected_tasks": len(selected_tasks),
        "selected_generators": len(selected_generators),
        "confirmation_tasks_sealed": len(sealed_rows),
        "guard_outcomes_observed": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "preflight.json", preflight)
    lines = [
        "# AppWorld 0.2 Generated Typed-Provenance v6 Preflight",
        "",
        f"## Status: **`{preflight['status']}`**",
        "",
        f"- Development tasks locked: {len(selected_tasks)}",
        f"- Generators: {len(selected_generators)}",
        f"- Confirmation tasks sealed: {len(sealed_rows)}",
        "- Calibration: READY",
        "- Guard outcomes observed: No",
        "- External process actions: No",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- `{name}`: **PASS**" for name in checks)
    (output_dir / "PREFLIGHT.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "status": preflight["status"],
                "development_tasks": len(selected_tasks),
                "confirmation_tasks_sealed": len(sealed_rows),
                "lock": str(lock_path.relative_to(REPO_ROOT)),
            }
        )
    )


if __name__ == "__main__":
    main()
