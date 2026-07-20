"""Preflight lock for targeted hard-residual held-out AppWorld generation."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_ebw_hard_residual_heldout_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v39_hard_heldout_preflight"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v39 hard heldout preflight")

    contract_path = resolve(args.contract)
    contract = load_json(contract_path)
    source_root = resolve(contract["source_root"])
    base_root = resolve(contract["base_source_root"])
    audit_root = resolve(contract["audit_parent_root"])
    fresh_root = resolve(contract["fresh_generated_root"])
    rebuild = load_json(contract["base_rebuild_status"])
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source_root, text=True).strip()
    files = [
        contract_path,
        contract_path.with_suffix(".md"),
        resolve("analysis/ebw_track_a_v39_hard_heldout_preflight.py"),
        resolve("analysis/ebw_track_a_v39_hard_heldout_generate.py"),
        resolve(contract["base_rebuild_status"]),
    ]
    checks = {
        "contract_frozen": contract["status"] == "FROZEN_BEFORE_HARD_RESIDUAL_HELDOUT_OUTCOMES",
        "source_commit": source_commit == contract["source_commit"],
        "source_environment": (source_root / ".venv/bin/python").is_file(),
        "base_rebuild": rebuild["status"] == "APPWORLD_DATA_V02_REBUILD_PASS",
        "base_components": all((base_root / "data" / name).exists() for name in ["base_dbs", "api_docs"]),
        "audit_parent_tasks": all((audit_root / "data/tasks" / f"{generator}_{variation}").is_dir() for generator in contract["generator_ids"] for variation in contract["audit_variations"]),
        "fresh_root_absent": not fresh_root.exists(),
        "output_absent": not output_dir.exists(),
        "scope": contract["model_gpu_docker_used"] is False and contract["external_process_actions"] is False and contract["guard_outcomes_observed"] is False,
        "files_exist": all(path.is_file() for path in files),
    }
    status = contract["verdicts"]["preflight_ready"] if all(checks.values()) else contract["verdicts"]["blocked"]
    if not checks["contract_frozen"] or not checks["scope"]:
        status = contract["verdicts"]["protocol_fail"]

    output_dir.mkdir(parents=True)
    lock = {
        "schema": "ebw_track_a_v39_hard_heldout_execution_lock_v1",
        "status": "LOCKED_BEFORE_HARD_HELDOUT_GENERATION_OUTCOMES",
        "files": {str(path.relative_to(REPO_ROOT)): file_hash(path) for path in files},
        "contract_sha256": file_hash(contract_path),
        "source_commit": source_commit,
        "generator_tree_sha256": tree_hash(source_root / "generate/tasks/task_generators"),
        "base_dbs_tree_sha256": tree_hash(base_root / "data/base_dbs"),
        "api_docs_tree_sha256": tree_hash(base_root / "data/api_docs"),
        "fresh_root": contract["fresh_generated_root"],
        "generator_ids": contract["generator_ids"],
        "fresh_variations": contract["fresh_variations"],
        "generation_outcomes_observed": False,
        "guard_outcomes_observed": False,
        "external_process_actions": False,
    }
    lock_path = output_dir / "execution_lock.json"
    write_json(lock_path, lock)
    payload = {
        "schema": "ebw_track_a_v39_hard_heldout_preflight_v1",
        "status": status,
        "checks": checks,
        "execution_lock_sha256": file_hash(lock_path),
        "generator_ids": contract["generator_ids"],
        "fresh_variations": contract["fresh_variations"],
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "preflight.json", payload)
    report = [
        "# EBW Track A v39 Hard Held-Out Preflight",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Generators: {', '.join(contract['generator_ids'])}",
        "- Fresh variations: 10-12",
        "- Model/GPU/Docker actions: No",
        "",
        "## Checks",
        "",
    ]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "PREFLIGHT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "report": str((output_dir / "PREFLIGHT.md").relative_to(REPO_ROOT))}))
    if status != contract["verdicts"]["preflight_ready"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()