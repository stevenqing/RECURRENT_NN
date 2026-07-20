"""Generate targeted hard-residual held-out AppWorld variations 10-12."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def included_files(path: Path) -> dict[str, Path]:
    return {str(item.relative_to(path)): item for item in path.rglob("*") if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc"}


def normalized_bytes(path: Path, relative: str, metadata_path: str, ignored_keys: set[str]) -> bytes:
    if relative != metadata_path:
        return path.read_bytes()
    payload = json.loads(path.read_text())
    for key in ignored_keys:
        payload.pop(key, None)
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def semantic_tree_hash(path: Path, metadata_path: str, ignored_keys: set[str]) -> str:
    digest = hashlib.sha256()
    for relative, item in sorted(included_files(path).items()):
        digest.update(relative.encode())
        digest.update(hashlib.sha256(normalized_bytes(item, relative, metadata_path, ignored_keys)).digest())
    return digest.hexdigest()


def raw_tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for relative, item in sorted(included_files(path).items()):
        digest.update(relative.encode())
        digest.update(hashlib.sha256(item.read_bytes()).digest())
    return digest.hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def passed_generators(path: Path) -> set[str]:
    clean = ANSI_RE.sub("", path.read_text(errors="replace"))
    match = re.search(r">> Passed \(\d+\): (.*?)>> Failed", clean, re.DOTALL) or re.search(r">> Passed \(\d+\): (.*)$", clean, re.DOTALL)
    if match is None:
        return set()
    return {re.sub(r"\s+", "", value) for value in match.group(1).split(",") if value.strip()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_ebw_hard_residual_heldout_v1.json"))
    parser.add_argument("--preflight-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v39_hard_heldout_preflight"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v39_hard_heldout_generation"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v39 hard heldout generation")

    contract_path = resolve(args.contract)
    contract = load_json(contract_path)
    preflight_dir = resolve(args.preflight_dir)
    lock = load_json(preflight_dir / "execution_lock.json")
    lock_checks = {path: resolve(path).is_file() and file_hash(resolve(path)) == digest for path, digest in lock["files"].items()}
    source_root = resolve(contract["source_root"])
    base_root = resolve(contract["base_source_root"])
    audit_root = resolve(contract["audit_parent_root"])
    fresh_root = resolve(contract["fresh_generated_root"])
    generation_path = output_dir / "generation.json"
    checks_pre = {
        "lock_ready": lock["status"] == "LOCKED_BEFORE_HARD_HELDOUT_GENERATION_OUTCOMES" and all(lock_checks.values()),
        "fresh_root_absent": not fresh_root.exists(),
        "output_absent": not output_dir.exists(),
        "contract_hash": file_hash(contract_path) == lock["contract_sha256"],
    }
    if not all(checks_pre.values()):
        raise RuntimeError(checks_pre)

    output_dir.mkdir(parents=True)
    (fresh_root / "data").mkdir(parents=True)
    (fresh_root / "experiments").mkdir()
    for directory in ("base_dbs", "api_docs"):
        shutil.copytree(base_root / "data" / directory, fresh_root / "data" / directory)
    for filename in ("LICENSE", "README_BEFORE_SHARING.md", "version.txt"):
        shutil.copy2(base_root / "data" / filename, fresh_root / "data" / filename)
    (fresh_root / "data/tasks").mkdir()
    (fresh_root / "data/datasets").mkdir()

    command = [
        str(source_root / ".venv/bin/python"),
        "-B",
        "-m",
        "generate.tasks.generate_and_validate_tasks",
        ",".join(contract["generator_ids"]),
        "--generator_num_tasks",
        str(contract["generator_num_tasks"]),
        "--use_environment",
        "--use_compiled_solution",
        "--random_seed",
        str(contract["random_seed"]),
        "--suppress_errors",
        "--no_color",
    ]
    environment = os.environ.copy()
    environment.update({"APPWORLD_ROOT": str(fresh_root), "PYTHONHASHSEED": str(contract["python_hash_seed"]), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONWARNINGS": "ignore", "PATH": str(source_root / ".venv/bin") + os.pathsep + environment.get("PATH", "")})
    log_path = output_dir / "generation.log"
    started = time.time()
    with log_path.open("w") as log:
        process = subprocess.run(command, cwd=source_root, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False)
    seconds = time.time() - started

    metadata_path = contract["semantic_audit"]["ignored_metadata_path"]
    ignored_keys = set(contract["semantic_audit"]["ignored_metadata_keys"])
    audit_rows = []
    semantic_audit_ok = True
    for generator in contract["generator_ids"]:
        for variation in contract["audit_variations"]:
            task_id = f"{generator}_{variation}"
            parent_task = audit_root / "data/tasks" / task_id
            fresh_task = fresh_root / "data/tasks" / task_id
            parent_hash = semantic_tree_hash(parent_task, metadata_path, ignored_keys)
            fresh_hash = semantic_tree_hash(fresh_task, metadata_path, ignored_keys) if fresh_task.is_dir() else None
            match = parent_hash == fresh_hash
            semantic_audit_ok = semantic_audit_ok and match
            audit_rows.append({"task_id": task_id, "generator_id": generator, "variation": variation, "semantic_match": match, "parent_semantic_sha256": parent_hash, "fresh_semantic_sha256": fresh_hash})
    fresh_rows = []
    for generator in contract["generator_ids"]:
        for variation in contract["fresh_variations"]:
            task_id = f"{generator}_{variation}"
            task_path = fresh_root / "data/tasks" / task_id
            fresh_rows.append({"task_id": task_id, "generator_id": generator, "variation": variation, "split": "hard_residual_heldout", "exists": task_path.is_dir(), "tree_sha256": raw_tree_hash(task_path) if task_path.is_dir() else None})
    log_passed = passed_generators(log_path)
    checks = {
        **checks_pre,
        "command": process.returncode == 0,
        "upstream_passed_generators": set(contract["generator_ids"]) <= log_passed,
        "semantic_audit_1_2": semantic_audit_ok,
        "fresh_cardinality": len(fresh_rows) == contract["expected_fresh_tasks"],
        "fresh_tasks_exist": all(row["exists"] for row in fresh_rows),
        "scope": contract["model_gpu_docker_used"] is False and contract["external_process_actions"] is False and contract["guard_outcomes_observed"] is False,
    }
    status = contract["verdicts"]["generation_pass"] if all(checks.values()) else contract["verdicts"]["blocked"]
    if not checks["scope"]:
        status = contract["verdicts"]["protocol_fail"]

    manifest_path = output_dir / "fresh_manifest.json"
    write_json(manifest_path, {"schema": "ebw_track_a_v39_hard_heldout_manifest_v1", "status": status, "fresh_rows": fresh_rows, "audit_rows": audit_rows, "guard_outcomes_observed": False})
    payload = {"schema": "ebw_track_a_v39_hard_heldout_generation_v1", "status": status, "checks": checks, "fresh_tasks": len(fresh_rows), "audit_tasks": len(audit_rows), "eligible_generator_ids": contract["generator_ids"], "seconds": seconds, "returncode": process.returncode, "hashes": {"contract": file_hash(contract_path), "execution_lock": file_hash(preflight_dir / "execution_lock.json"), "generation_log": file_hash(log_path), "manifest": file_hash(manifest_path), "source": file_hash(Path(__file__))}, "guard_outcomes_observed": False, "model_gpu_docker_used": False, "external_process_actions": False, "headline_eligible": False}
    write_json(generation_path, payload)
    report = ["# EBW Track A v39 Hard Held-Out Generation", "", f"## Status: **`{status}`**", "", f"- Fresh tasks: {len(fresh_rows)}", f"- Audit tasks: {len(audit_rows)}", f"- Runtime: {seconds / 60:.1f} minutes", "- Guard/model outcomes observed: No", "- GPU/Docker/external process actions: No", "", "## Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "fresh_tasks": len(fresh_rows), "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))
    if status != contract["verdicts"]["generation_pass"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()