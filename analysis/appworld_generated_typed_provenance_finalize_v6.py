"""Certify the frozen AppWorld generated typed-provenance v6 result."""
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
    result_path = output_dir / "results.json"
    result_binding_path = output_dir / "result_binding.json"
    execution_lock_path = output_dir / "execution_lock.json"
    command_lock_path = output_dir / "command_lock.json"
    certification_path = output_dir / "certification.json"
    if certification_path.exists():
        raise RuntimeError(f"Refusing to overwrite certification: {certification_path}")

    result = load_json(result_path)
    result_binding = load_json(result_binding_path)
    execution_lock = load_json(execution_lock_path)
    command_lock = load_json(command_lock_path)
    contract = load_json(
        resolve("specs/recurrent_parallel_appworld_generated_typed_provenance_development_v6.json")
    )
    appworld_root = resolve(contract["appworld_root"])
    shard_dir = output_dir / "task_shards"
    shard_hashes = {
        path.stem: file_hash(path) for path in sorted(shard_dir.glob("*.json"))
    }
    selected_raw_hashes_match = all(
        tree_hash(appworld_root / "data/tasks" / row["task_id"])
        == row["tree_sha256"]
        for row in execution_lock["selected_tasks"]
    )
    selected_cache_files = [
        str(item.relative_to(appworld_root / "data/tasks"))
        for row in execution_lock["selected_tasks"]
        for item in (appworld_root / "data/tasks" / row["task_id"]).rglob("*.pyc")
    ]
    command_source_path = resolve("analysis/appworld_generated_typed_provenance_command_lock_v6.py")
    runner_path = resolve(
        "analysis/recurrent_appworld_generated_typed_provenance_development_v6.py"
    )
    checks = {
        "result_binding": (
            file_hash(result_path) == result_binding["results_sha256"]
            and file_hash(execution_lock_path) == result_binding["execution_lock_sha256"]
            and shard_hashes == result_binding["task_shard_sha256"]
        ),
        "command_lock_binding": (
            file_hash(execution_lock_path) == command_lock["execution_lock_sha256"]
            and file_hash(command_source_path) == command_lock["source_sha256"]
            and file_hash(runner_path) == command_lock["runner_sha256"]
        ),
        "no_bytecode_command": (
            "-B" in command_lock["command"]
            and command_lock["environment"]["PYTHONDONTWRITEBYTECODE"] == "1"
        ),
        "selected_raw_hashes": selected_raw_hashes_match,
        "selected_cache_absent": not selected_cache_files,
        "all_baselines": (
            len(result["task_summaries"]) == contract["expected_open_tasks"]
            and all(summary["baseline_pass"] for summary in result["task_summaries"])
            and all(summary["error_type"] is None for summary in result["task_summaries"])
        ),
        "verdict_consistent": (
            result["status"] == contract["verdicts"]["no_go"]
            and result["gates"]["T3_typed_safety"] is False
            and all(
                passed
                for gate, passed in result["gates"].items()
                if gate != "T3_typed_safety"
            )
        ),
        "metric_consistency": (
            result["old_guard"]["wrong"] == 3
            and result["typed_guard"]["wrong"] == 1
            and result["strict_pairs"] == len(result["rows"]) == 36
        ),
        "confirmation_sealed": (
            result["confirmation_outcomes_sealed"] is True
            and execution_lock["confirmation_outcomes_sealed"] is True
        ),
        "scope": (
            result["protected_content_exported"] is False
            and result["external_process_actions"] is False
            and result["model_gpu_docker_used"] is False
            and result["headline_eligible"] is False
        ),
    }
    certification_status = (
        "RPD_APPWORLD_GENERATED_TYPED_PROVENANCE_V6_RESULT_CERTIFIED"
        if all(checks.values())
        else "RPD_APPWORLD_GENERATED_TYPED_PROVENANCE_V6_CERTIFICATION_FAIL"
    )
    certification = {
        "schema": "recurrent_appworld_generated_typed_provenance_certification_v6",
        "status": certification_status,
        "method_verdict": result["status"],
        "checks": checks,
        "results_sha256": file_hash(result_path),
        "execution_lock_sha256": file_hash(execution_lock_path),
        "command_lock_sha256": file_hash(command_lock_path),
        "strict_pairs": result["strict_pairs"],
        "old_guard": result["old_guard"],
        "typed_guard": result["typed_guard"],
        "confirmation_outcomes_sealed": True,
        "external_process_actions": False,
    }
    write_json(certification_path, certification)
    report = [
        "# AppWorld 0.2 Generated Typed-Provenance v6 — Certified Result",
        "",
        f"## Certification: **`{certification_status}`**",
        "",
        f"## Method verdict: **`{result['status']}`**",
        "",
        "- Baseline tasks: 24/24 PASS",
        f"- Strict pairs: {result['strict_pairs']}",
        f"- Source tasks: {result['source_tasks']}",
        f"- Source generators: {result['source_generators']}",
        f"- Old guard: coverage {result['old_guard']['coverage']:.3f}, accuracy {result['old_guard']['accuracy']:.3f}, wrong {result['old_guard']['wrong']}",
        f"- Typed guard: coverage {result['typed_guard']['coverage']:.3f}, accuracy {result['typed_guard']['accuracy']:.3f}, wrong {result['typed_guard']['wrong']}",
        "- Confirmation outcomes: Sealed",
        "- External process actions: No",
        "",
        "## Gate result",
        "",
    ]
    report.extend(
        f"- `{gate}`: **{'PASS' if passed else 'FAIL'}**"
        for gate, passed in result["gates"].items()
    )
    report.extend(
        [
            "",
            "Typed provenance improved safety but retained one wrong covered choice, so the",
            "pre-registered zero-wrong gate blocks confirmation. This is a development NO_GO,",
            "not a protocol failure and not a headline result.",
            "",
            "## Certification checks",
            "",
        ]
    )
    report.extend(
        f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()
    )
    (output_dir / "FINAL_REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": certification_status, "method_verdict": result["status"]}))
    if not all(checks.values()):
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()
