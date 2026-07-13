"""Pre-outcome lock for held-out exclusive-provenance confirmation."""
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


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(str(item.relative_to(path)).encode())
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
        default=Path("specs/recurrent_parallel_appworld_exclusive_provenance_confirmation_v1.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/recurrent_parallel_appworld_exclusive_provenance_confirmation_v1"),
    )
    args = parser.parse_args()
    contract_path = resolve(args.contract)
    contract_md_path = contract_path.with_suffix(".md")
    contract = load_json(contract_path)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError(f"Refusing to overwrite confirmation preflight: {output_dir}")

    development_path = resolve(contract["development_results"])
    development_binding_path = resolve(contract["development_binding"])
    typed_certification_path = resolve(contract["typed_development_certification"])
    capacity_status_path = resolve(contract["capacity_status"])
    capacity_manifest_path = resolve(contract["capacity_manifest"])
    capacity_lock_path = resolve(contract["capacity_lock"])
    capacity_binding_path = resolve(contract["capacity_binding"])
    calibration_results_path = resolve(contract["calibration_results"])
    calibration_binding_path = resolve(contract["calibration_binding"])
    calibration_lock_path = calibration_results_path.parent / "execution_lock.json"
    development = load_json(development_path)
    development_binding = load_json(development_binding_path)
    typed_certification = load_json(typed_certification_path)
    capacity_status = load_json(capacity_status_path)
    capacity_manifest = load_json(capacity_manifest_path)
    capacity_lock = load_json(capacity_lock_path)
    capacity_binding = load_json(capacity_binding_path)
    calibration = load_json(calibration_results_path)
    calibration_binding = load_json(calibration_binding_path)

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

    expected_python = (source_root / ".venv/bin/python").resolve()
    appworld_module_path = Path(appworld.__file__).resolve()
    selected_rows = sorted(
        [row for row in capacity_manifest["rows"] if row["split"] == contract["open_split"]],
        key=lambda row: row["task_id"],
    )
    closed_rows = sorted(
        [row for row in capacity_manifest["rows"] if row["split"] == contract["closed_split"]],
        key=lambda row: row["task_id"],
    )
    selected_generators = sorted({row["generator_id"] for row in selected_rows})
    task_root = appworld_root / "data/tasks"
    selected_raw_hashes_match = all(
        (task_root / row["task_id"]).is_dir()
        and tree_hash(task_root / row["task_id"]) == row["tree_sha256"]
        for row in selected_rows
    )
    selected_cache_files = [
        str(item.relative_to(task_root))
        for row in selected_rows
        for item in (task_root / row["task_id"]).rglob("*.pyc")
    ]
    development_contract_path = resolve(
        "specs/recurrent_parallel_appworld_exclusive_provenance_development_v1.json"
    )
    development_source_path = resolve("analysis/appworld_exclusive_provenance_development.py")
    exclusive_rule_path = resolve("experiments/appworld_exclusive_provenance.py")

    immutable_paths = [
        contract_md_path,
        contract_path,
        development_contract_path.with_suffix(".md"),
        development_contract_path,
        development_source_path,
        development_path,
        development_binding_path,
        typed_certification_path,
        capacity_status_path,
        capacity_manifest_path,
        capacity_lock_path,
        capacity_binding_path,
        calibration_results_path,
        calibration_binding_path,
        calibration_lock_path,
        resolve("experiments/appworld_live_trace.py"),
        resolve("experiments/appworld_provenance.py"),
        resolve("experiments/appworld_trace_replay.py"),
        resolve("experiments/appworld_typed_provenance.py"),
        exclusive_rule_path,
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v2.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v3.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v4.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v5.py"),
        resolve("analysis/recurrent_appworld_generated_typed_provenance_development_v6.py"),
        resolve("analysis/appworld_exclusive_provenance_confirmation.py"),
        resolve("analysis/appworld_exclusive_provenance_confirmation_preflight.py"),
    ]
    checks = {
        "contract_frozen": contract["status"]
        == "FROZEN_BEFORE_EXCLUSIVE_PROVENANCE_CONFIRMATION_OUTCOMES",
        "development_go": development["status"] == contract["development_required_status"],
        "development_binding": file_hash(development_path)
        == development_binding["results_sha256"],
        "development_method_binding": (
            development["hashes"]["contract"] == file_hash(development_contract_path)
            and development["hashes"]["source"] == file_hash(development_source_path)
            and development["hashes"]["rule_source"] == file_hash(exclusive_rule_path)
        ),
        "typed_development_certified": typed_certification["status"]
        == "RPD_APPWORLD_GENERATED_TYPED_PROVENANCE_V6_RESULT_CERTIFIED",
        "calibration_ready": calibration["status"] == contract["calibration_required_status"],
        "calibration_binding": (
            file_hash(calibration_results_path) == calibration_binding["results_sha256"]
            and file_hash(calibration_lock_path) == calibration_binding["execution_lock_sha256"]
        ),
        "capacity_status": capacity_status["status"] == contract["capacity_required_status"],
        "capacity_binding": (
            file_hash(capacity_status_path) == capacity_binding["status_sha256"]
            and file_hash(capacity_manifest_path) == capacity_binding["task_manifest_sha256"]
            and file_hash(capacity_lock_path) == capacity_binding["execution_lock_sha256"]
        ),
        "capacity_pre_outcome": capacity_lock["guard_outcomes_observed"] is False,
        "source_commit": source_commit == contract["source_commit"],
        "source_environment": (
            Path(sys.executable).resolve() == expected_python
            and source_root in appworld_module_path.parents
        ),
        "data_version": (appworld_root / "data/version.txt").read_text().strip()
        == contract["data_version"],
        "confirmation_cardinality": len(selected_rows) == contract["expected_open_tasks"],
        "confirmation_generators": len(selected_generators) == contract["expected_generators"],
        "confirmation_variations": (
            {row["variation"] for row in selected_rows} == set(contract["open_variations"])
            and all(row["exists"] for row in selected_rows)
        ),
        "development_closed": (
            len(closed_rows) == contract["expected_closed_tasks"]
            and {row["variation"] for row in closed_rows} == set(contract["closed_variations"])
        ),
        "split_disjoint": not (
            {row["task_id"] for row in selected_rows} & {row["task_id"] for row in closed_rows}
        ),
        "selected_raw_hashes": selected_raw_hashes_match,
        "selected_cache_absent": not selected_cache_files,
        "immutable_files": all(path.is_file() for path in immutable_paths),
        "outcomes_absent": not (output_dir / "results.json").exists(),
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
    closed_metadata = [
        {
            "task_id": row["task_id"],
            "variation": row["variation"],
            "tree_sha256": row["tree_sha256"],
        }
        for row in closed_rows
    ]
    interpreter = resolve("external_repos/appworld_source/.venv/bin/python")
    execution_command = [
        str(interpreter.relative_to(REPO_ROOT)),
        "-B",
        "-m",
        "analysis.appworld_exclusive_provenance_confirmation",
    ]
    execution_environment = {
        "APPWORLD_ROOT": str(appworld_root),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    lock = {
        "schema": "recurrent_appworld_exclusive_provenance_confirmation_execution_lock_v1",
        "status": "LOCKED_BEFORE_EXCLUSIVE_PROVENANCE_CONFIRMATION_OUTCOMES",
        "immutable_inputs": {
            str(path.relative_to(REPO_ROOT)): file_hash(path) for path in immutable_paths
        },
        "source_commit": source_commit,
        "selected_generator_ids": selected_generators,
        "selected_tasks": selected_tasks,
        "selected_task_ids_sha256": hashlib.sha256(
            json.dumps([row["task_id"] for row in selected_tasks], separators=(",", ":")).encode()
        ).hexdigest(),
        "closed_development_metadata_sha256": hashlib.sha256(
            json.dumps(closed_metadata, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "development_results_sha256": file_hash(development_path),
        "execution_command": execution_command,
        "execution_environment": execution_environment,
        "confirmation_outcomes_observed": False,
        "external_process_actions": False,
    }
    lock_path = output_dir / "execution_lock.json"
    write_json(lock_path, lock)
    preflight = {
        "schema": "recurrent_appworld_exclusive_provenance_confirmation_preflight_v1",
        "status": "RPD_APPWORLD_EXCLUSIVE_PROVENANCE_CONFIRMATION_EXECUTION_READY",
        "checks": checks,
        "execution_lock_sha256": file_hash(lock_path),
        "confirmation_tasks": len(selected_tasks),
        "generators": len(selected_generators),
        "confirmation_outcomes_observed": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "preflight.json", preflight)
    report = [
        "# AppWorld Exclusive Causal Provenance — Confirmation Preflight",
        "",
        f"## Status: **`{preflight['status']}`**",
        "",
        f"- Confirmation tasks locked: {len(selected_tasks)}",
        f"- Generators: {len(selected_generators)}",
        "- Confirmation outcomes observed: No",
        "- Development method: Closed and hash-bound",
        "- Python bytecode writes: Disabled by frozen command",
        "- External process actions: No",
        "",
        "## Checks",
        "",
    ]
    report.extend(f"- `{name}`: **PASS**" for name in checks)
    (output_dir / "PREFLIGHT.md").write_text("\n".join(report) + "\n")
    print(
        json.dumps(
            {
                "status": preflight["status"],
                "tasks": len(selected_tasks),
                "lock": str(lock_path.relative_to(REPO_ROOT)),
            }
        )
    )


if __name__ == "__main__":
    main()
