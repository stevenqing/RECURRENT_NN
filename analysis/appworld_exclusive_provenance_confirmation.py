"""Held-out AppWorld 0.2 confirmation of exclusive causal provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Any

from analysis import recurrent_appworld_generated_typed_provenance_development as frozen_runner
from analysis.recurrent_appworld_generated_typed_provenance_development_v6 import (
    install_v6_compatibility,
)
from experiments.appworld_exclusive_provenance import exclusive_choice_from_tiers

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARD_SCHEMA = "recurrent_appworld_exclusive_provenance_confirmation_task_shard_v1"
RESULT_SCHEMA = "recurrent_appworld_exclusive_provenance_confirmation_v1"


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
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def forbidden_keys(value: Any, forbidden: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in forbidden:
                found.add(str(key).lower())
            found.update(forbidden_keys(child, forbidden))
    elif isinstance(value, list):
        for child in value:
            found.update(forbidden_keys(child, forbidden))
    return found


def metric(rows: list[dict[str, Any]], choice_key: str) -> dict[str, float | int]:
    covered = [row for row in rows if row[choice_key] is not None]
    correct = sum(row[choice_key] == row["preferred"] for row in covered)
    return {
        "coverage": len(covered) / len(rows) if rows else 0.0,
        "covered": len(covered),
        "correct": correct,
        "wrong": len(covered) - correct,
        "accuracy": correct / len(covered) if covered else 0.0,
    }


def write_progress(
    output_dir: Path,
    completed: int,
    total: int,
    pairs: int,
    baseline_passes: int,
    state: str,
) -> None:
    write_json(
        output_dir / "progress.json",
        {
            "schema": "recurrent_appworld_exclusive_provenance_confirmation_progress_v1",
            "state": state,
            "completed_tasks": completed,
            "total_tasks": total,
            "strict_pairs_so_far": pairs,
            "baseline_passes_so_far": baseline_passes,
            "external_process_actions": False,
        },
    )
    (output_dir / "PROGRESS.md").write_text(
        "\n".join(
            [
                "# AppWorld Exclusive-Provenance Confirmation Progress",
                "",
                f"- State: **{state}**",
                f"- Completed tasks: {completed}/{total}",
                f"- Baseline passes: {baseline_passes}/{completed}",
                f"- Strict pairs so far: {pairs}",
                "- External process actions: No",
            ]
        )
        + "\n"
    )


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
    warnings.filterwarnings("ignore")
    contract_path = resolve(args.contract)
    contract = load_json(contract_path)
    output_dir = resolve(args.output_dir)
    lock_path = output_dir / "execution_lock.json"
    result_path = output_dir / "results.json"
    if result_path.exists():
        raise RuntimeError(f"Refusing to overwrite confirmation results: {result_path}")
    execution_lock = load_json(lock_path)
    execution_lock_sha256 = file_hash(lock_path)

    immutable_checks = {
        path: resolve(path).is_file() and file_hash(resolve(path)) == expected_hash
        for path, expected_hash in execution_lock["immutable_inputs"].items()
    }
    source_root = resolve(contract["source_root"])
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    appworld_root = resolve(contract["appworld_root"])
    runtime_checks = {
        "execution_lock": execution_lock["status"]
        == "LOCKED_BEFORE_EXCLUSIVE_PROVENANCE_CONFIRMATION_OUTCOMES",
        "immutable_inputs": all(immutable_checks.values()),
        "source_commit": source_commit == contract["source_commit"],
        "confirmation_tasks": len(execution_lock["selected_tasks"])
        == contract["expected_open_tasks"],
        "confirmation_variations": all(
            row["split"] == contract["open_split"]
            and row["variation"] in contract["open_variations"]
            for row in execution_lock["selected_tasks"]
        ),
        "no_bytecode": (
            sys.dont_write_bytecode
            and os.environ.get("PYTHONDONTWRITEBYTECODE") == "1"
            and "-B" in execution_lock["execution_command"]
        ),
        "python_hash_seed": os.environ.get("PYTHONHASHSEED") == "0",
        "appworld_root": os.environ.get("APPWORLD_ROOT") == str(appworld_root),
        "results_absent": not result_path.exists(),
    }
    if not all(runtime_checks.values()):
        raise RuntimeError(runtime_checks)

    install_v6_compatibility()
    frozen_runner.SHARD_SCHEMA = SHARD_SCHEMA
    from appworld import update_root

    update_root(str(appworld_root))
    shard_dir = output_dir / "task_shards"
    shard_dir.mkdir(exist_ok=True)
    selected_tasks = sorted(execution_lock["selected_tasks"], key=lambda row: row["task_id"])
    shards: list[dict[str, Any]] = []
    started = time.time()
    for task_index, task_row in enumerate(selected_tasks, start=1):
        shard_path = shard_dir / f"{task_row['task_id']}.json"
        if shard_path.exists():
            shard = load_json(shard_path)
            valid_existing = (
                shard.get("schema") == SHARD_SCHEMA
                and shard.get("execution_lock_sha256") == execution_lock_sha256
                and shard.get("task_tree_sha256") == task_row["tree_sha256"]
                and shard.get("summary", {}).get("task_id") == task_row["task_id"]
            )
            if not valid_existing:
                raise RuntimeError(f"Invalid existing confirmation shard: {shard_path}")
        else:
            shard = frozen_runner.process_task(
                task_row, appworld_root, contract, execution_lock_sha256
            )
            write_json(shard_path, shard)
        shards.append(shard)
        rows_so_far = [row for current in shards for row in current["rows"]]
        baseline_passes = sum(bool(current["summary"]["baseline_pass"]) for current in shards)
        write_progress(
            output_dir,
            task_index,
            len(selected_tasks),
            len(rows_so_far),
            baseline_passes,
            "RUNNING" if task_index < len(selected_tasks) else "AGGREGATING",
        )
        print(
            json.dumps(
                {
                    "completed": task_index,
                    "total": len(selected_tasks),
                    "task_id": task_row["task_id"],
                    "baseline_pass": shard["summary"]["baseline_pass"],
                    "selected_pairs": len(shard["rows"]),
                }
            ),
            flush=True,
        )

    task_summaries = [shard["summary"] for shard in shards]
    rows = sorted(
        [dict(row) for shard in shards for row in shard["rows"]],
        key=lambda row: row["pair_id"],
    )
    for row in rows:
        choice = exclusive_choice_from_tiers(row["typed_tier_A"], row["typed_tier_B"])
        row.update(
            {
                "exclusive_choice": choice,
                "exclusive_covered": choice is not None,
                "exclusive_correct": choice == row["preferred"] if choice else None,
            }
        )
    old_metrics = metric(rows, "old_choice")
    typed_metrics = metric(rows, "typed_choice")
    exclusive_metrics = metric(rows, "exclusive_choice")
    source_tasks = {row["task_id"] for row in rows}
    source_generators = {row["generator_id"] for row in rows}

    selected_hashes_match = all(
        tree_hash(appworld_root / "data/tasks" / row["task_id"])
        == row["tree_sha256"]
        for row in selected_tasks
    )
    immutable_still_match = all(
        resolve(path).is_file() and file_hash(resolve(path)) == expected_hash
        for path, expected_hash in execution_lock["immutable_inputs"].items()
    )
    forbidden = {key.lower() for key in contract["output_forbidden_keys"]}
    scope_payload = {"task_summaries": task_summaries, "rows": rows}
    gates = {
        "C0_live_baselines": (
            len(task_summaries) == contract["expected_open_tasks"]
            and all(summary["baseline_pass"] for summary in task_summaries)
            and all(summary["error_type"] is None for summary in task_summaries)
        ),
        "C1_strict_yield": (
            len(rows) >= 20 and len(source_tasks) >= 12 and len(source_generators) >= 6
        ),
        "C2_exclusive_coverage": exclusive_metrics["coverage"] >= 0.50,
        "C3_exclusive_safety": exclusive_metrics["wrong"] == 0,
        "C4_vs_typed_safety": exclusive_metrics["wrong"] <= typed_metrics["wrong"],
        "C5_hash_and_execution_integrity": (
            selected_hashes_match
            and immutable_still_match
            and runtime_checks["no_bytecode"]
            and runtime_checks["python_hash_seed"]
            and runtime_checks["appworld_root"]
        ),
        "C6_scope": (
            all(
                row["variation"] in contract["open_variations"]
                and row["generator_id"] in execution_lock["selected_generator_ids"]
                for row in rows
            )
            and not forbidden_keys(scope_payload, forbidden)
            and contract["model_gpu_docker_used"] is False
            and contract["external_process_actions"] is False
        ),
    }
    if not gates["C0_live_baselines"] or not gates["C5_hash_and_execution_integrity"] or not gates["C6_scope"]:
        status = contract["verdicts"]["protocol_fail"]
    elif all(gates.values()):
        status = contract["verdicts"]["pass"]
    else:
        status = contract["verdicts"]["fail"]

    payload = {
        "schema": RESULT_SCHEMA,
        "status": status,
        "gates": gates,
        "source_tasks": len(source_tasks),
        "source_generators": len(source_generators),
        "strict_pairs": len(rows),
        "old_guard": old_metrics,
        "typed_max_tier_guard": typed_metrics,
        "exclusive_guard": exclusive_metrics,
        "task_summaries": task_summaries,
        "rows": rows,
        "runtime_checks": runtime_checks,
        "execution_lock_sha256": execution_lock_sha256,
        "task_shard_sha256": {
            path.stem: file_hash(path) for path in sorted(shard_dir.glob("*.json"))
        },
        "seconds": time.time() - started,
        "confirmation_variations": contract["open_variations"],
        "confirmation_outcomes_opened": True,
        "independent_instance_confirmation": True,
        "independent_task_type_confirmation": False,
        "protected_content_exported": False,
        "external_process_actions": False,
        "model_gpu_docker_used": False,
        "headline_eligible": False,
    }
    if forbidden_keys(payload, forbidden):
        raise RuntimeError("Forbidden protected keys reached confirmation payload")
    write_json(result_path, payload)
    write_json(
        output_dir / "result_binding.json",
        {
            "execution_lock_sha256": execution_lock_sha256,
            "results_sha256": file_hash(result_path),
            "task_shard_sha256": payload["task_shard_sha256"],
        },
    )
    report = [
        "# AppWorld Exclusive Causal Provenance — Held-Out Confirmation",
        "",
        f"## Verdict: **`{status}`**",
        "",
        f"- Confirmation tasks executed: {len(task_summaries)}/{contract['expected_open_tasks']}",
        f"- Strict pairs: {len(rows)}",
        f"- Source tasks: {len(source_tasks)}",
        f"- Source generators: {len(source_generators)}",
        "- Protected content exported: No",
        "- External process actions: No",
        "- Model/GPU/Docker used: No",
        "",
        "| Guard | Coverage | Correct commits | Wrong commits | Accuracy |",
        "|---|---:|---:|---:|---:|",
        f"| Old citation count | {old_metrics['coverage']:.3f} | {old_metrics['correct']} | {old_metrics['wrong']} | {old_metrics['accuracy']:.3f} |",
        f"| Typed max-tier | {typed_metrics['coverage']:.3f} | {typed_metrics['correct']} | {typed_metrics['wrong']} | {typed_metrics['accuracy']:.3f} |",
        f"| Exclusive provenance | {exclusive_metrics['coverage']:.3f} | {exclusive_metrics['correct']} | {exclusive_metrics['wrong']} | {exclusive_metrics['accuracy']:.3f} |",
        "",
        "## Gates",
        "",
    ]
    report.extend(
        f"- `{gate}`: **{'PASS' if passed else 'FAIL'}**" for gate, passed in gates.items()
    )
    report.extend(
        [
            "",
            "This is held-out instance confirmation within the same generator families,",
            "not independent task-type confirmation and not an end-to-end headline result.",
        ]
    )
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    write_progress(
        output_dir,
        len(selected_tasks),
        len(selected_tasks),
        len(rows),
        sum(bool(summary["baseline_pass"]) for summary in task_summaries),
        "COMPLETE",
    )
    print(
        json.dumps(
            {
                "status": status,
                "pairs": len(rows),
                "typed": typed_metrics,
                "exclusive": exclusive_metrics,
                "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT)),
            }
        )
    )


if __name__ == "__main__":
    main()
