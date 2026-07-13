"""Freeze the no-bytecode execution command for AppWorld development v6."""
from __future__ import annotations

import argparse
import hashlib
import json
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
        "--output-dir",
        type=Path,
        default=Path(
            "results/recurrent_parallel_appworld_generated_typed_provenance_development_v6"
        ),
    )
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    execution_lock_path = output_dir / "execution_lock.json"
    preflight_path = output_dir / "preflight.json"
    command_lock_path = output_dir / "command_lock.json"
    if command_lock_path.exists():
        raise RuntimeError(f"Refusing to overwrite command lock: {command_lock_path}")

    execution_lock = load_json(execution_lock_path)
    preflight = load_json(preflight_path)
    contract_path = resolve(
        "specs/recurrent_parallel_appworld_generated_typed_provenance_development_v6.json"
    )
    contract = load_json(contract_path)
    appworld_root = resolve(contract["appworld_root"])
    immutable_inputs_match = all(
        resolve(path).is_file() and file_hash(resolve(path)) == expected_hash
        for path, expected_hash in execution_lock["immutable_inputs"].items()
    )
    selected_raw_hashes_match = all(
        (appworld_root / "data/tasks" / row["task_id"]).is_dir()
        and tree_hash(appworld_root / "data/tasks" / row["task_id"])
        == row["tree_sha256"]
        for row in execution_lock["selected_tasks"]
    )
    selected_cache_files = [
        str(item.relative_to(appworld_root / "data/tasks"))
        for row in execution_lock["selected_tasks"]
        for item in (appworld_root / "data/tasks" / row["task_id"]).rglob("*.pyc")
    ]
    source_path = Path(__file__).resolve()
    runner_path = resolve(
        "analysis/recurrent_appworld_generated_typed_provenance_development_v6.py"
    )
    interpreter = resolve("external_repos/appworld_source/.venv/bin/python")
    checks = {
        "preflight_ready": preflight["status"]
        == "RPD_APPWORLD_GENERATED_TYPED_PROVENANCE_V6_EXECUTION_READY",
        "execution_lock": execution_lock["status"]
        == "LOCKED_BEFORE_GENERATED_DEVELOPMENT_OUTCOMES",
        "immutable_inputs": immutable_inputs_match,
        "selected_raw_hashes": selected_raw_hashes_match,
        "selected_cache_absent": not selected_cache_files,
        "interpreter_exists": interpreter.is_file(),
        "results_absent": not (output_dir / "results.json").exists(),
        "shards_absent": not (output_dir / "task_shards").exists(),
        "confirmation_sealed": execution_lock["confirmation_outcomes_sealed"] is True,
    }
    if not all(checks.values()):
        raise RuntimeError(checks)

    command_lock = {
        "schema": "recurrent_appworld_generated_typed_provenance_command_lock_v6",
        "status": "LOCKED_BEFORE_GENERATED_DEVELOPMENT_OUTCOMES",
        "checks": checks,
        "execution_lock_sha256": file_hash(execution_lock_path),
        "preflight_sha256": file_hash(preflight_path),
        "source_sha256": file_hash(source_path),
        "runner_sha256": file_hash(runner_path),
        "command": [
            str(interpreter.relative_to(REPO_ROOT)),
            "-B",
            "-m",
            "analysis.recurrent_appworld_generated_typed_provenance_development_v6",
        ],
        "environment": {
            "APPWORLD_ROOT": str(appworld_root),
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1"
        },
        "selected_task_count": len(execution_lock["selected_tasks"]),
        "selected_task_ids_sha256": execution_lock["selected_task_ids_sha256"],
        "confirmation_outcomes_sealed": True,
        "guard_outcomes_observed": False,
        "external_process_actions": False,
    }
    write_json(command_lock_path, command_lock)
    (output_dir / "COMMAND_LOCK.md").write_text(
        "\n".join(
            [
                "# AppWorld 0.2 Typed-Provenance v6 Command Lock",
                "",
                "## Status: **`LOCKED_BEFORE_GENERATED_DEVELOPMENT_OUTCOMES`**",
                "",
                "- Development tasks: 24",
                "- Python bytecode writes: Disabled",
                "- Selected task raw hashes: PASS",
                "- Selected task cache files before execution: 0",
                "- Confirmation outcomes: Sealed",
                "- External process actions: No",
                "",
                "The `-B` flag prevents runtime cache files from changing the frozen raw task hashes.",
            ]
        )
        + "\n"
    )
    print(json.dumps({"status": command_lock["status"], "checks": checks}))


if __name__ == "__main__":
    main()
