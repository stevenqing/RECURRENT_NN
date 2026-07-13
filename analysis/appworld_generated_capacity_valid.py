"""Freeze the pre-outcome, capacity-valid subset of AppWorld 0.2 tasks."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


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


def passed_generators_from_log(path: Path) -> set[str]:
    clean_log = ANSI_RE.sub("", path.read_text(errors="replace"))
    match = re.search(r">> Passed \(\d+\): (.*?)>> Failed", clean_log, re.DOTALL)
    if match is None:
        return set()
    return {
        re.sub(r"\s+", "", generator)
        for generator in match.group(1).split(",")
        if generator.strip()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("specs/recurrent_parallel_appworld_generated_capacity_valid_v1.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/recurrent_parallel_appworld_generated_capacity_valid_v1"),
    )
    args = parser.parse_args()

    contract_path = resolve(args.contract)
    contract_md_path = contract_path.with_suffix(".md")
    output_dir = resolve(args.output_dir)
    output_was_absent = not output_dir.exists()
    if not output_was_absent:
        raise RuntimeError(f"Refusing to overwrite frozen output: {output_dir}")
    output_dir.mkdir(parents=True)

    contract = load_json(contract_path)
    parent_contract_path = resolve(contract["parent_spec"])
    parent_contract = load_json(parent_contract_path)
    parent_manifest_path = resolve(contract["parent_manifest"])
    parent_manifest = load_json(parent_manifest_path)
    parent_dir = parent_manifest_path.parent
    parent_generation_path = parent_dir / "generation.json"
    parent_binding_path = parent_dir / "result_binding.json"
    parent_log_path = parent_dir / "generation.log"
    parent_generation = load_json(parent_generation_path)
    parent_binding = load_json(parent_binding_path)

    required_variations = set(contract["eligibility_rule"]["required_variations"])
    rows_by_generator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in parent_manifest["rows"]:
        rows_by_generator[row["generator_id"]].append(row)

    complete_generators = {
        generator_id
        for generator_id, rows in rows_by_generator.items()
        if {row["variation"] for row in rows} == required_variations
        and all(row["exists"] and row["tree_sha256"] for row in rows)
    }
    passed_generators = passed_generators_from_log(parent_log_path)
    selected_generators = sorted(complete_generators & passed_generators)
    excluded_generators = sorted(set(rows_by_generator) - set(selected_generators))
    selected_rows = [
        row
        for row in parent_manifest["rows"]
        if row["generator_id"] in selected_generators
    ]

    expected = contract["expected"]
    split_counts = {
        split: sum(row["split"] == split for row in selected_rows)
        for split in contract["split_rule"]
    }
    split_variations_match = all(
        set(contract["split_rule"][row["split"]]) == {
            candidate["variation"]
            for candidate in selected_rows
            if candidate["generator_id"] == row["generator_id"]
            and candidate["split"] == row["split"]
        }
        for row in selected_rows
    )

    generated_root = resolve(parent_contract["generated_root"])
    task_root = generated_root / "data/tasks"
    actual_task_hashes_match = all(
        (task_root / row["task_id"]).is_dir()
        and tree_hash(task_root / row["task_id"]) == row["tree_sha256"]
        for row in selected_rows
    )

    source_root = resolve(parent_contract["source_root"])
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    checks = {
        "contract_frozen_before_guard_outcomes": contract["frozen_before_guard_outcomes"] is True,
        "output_absent_before_lock": output_was_absent,
        "parent_v2_fail_preserved": (
            parent_generation["status"] == contract["parent_status_required"]
            and parent_manifest["status"] == contract["parent_status_required"]
        ),
        "parent_binding_intact": (
            file_hash(parent_generation_path) == parent_binding["generation_sha256"]
            and file_hash(parent_manifest_path) == parent_binding["manifest_sha256"]
        ),
        "parent_generation_source_intact": (
            file_hash(resolve("analysis/appworld_generate_tasks_safe_v2.py"))
            == parent_generation["hashes"]["source"]
        ),
        "parent_capacity_boundary_preregistered": (
            parent_contract["minimum_valid_generators"] == expected["complete_generators"]
        ),
        "parent_operational_counts": (
            parent_generation["tasks"] == 84
            and parent_generation["valid_generators"] == expected["complete_generators"]
            and len(parent_manifest["rows"]) == 90
        ),
        "source_commit": source_commit == parent_contract["source_commit"],
        "complete_equals_passed_generators": complete_generators == passed_generators,
        "complete_generator_count": len(selected_generators) == expected["complete_generators"],
        "excluded_generators_are_partial": all(
            any(not row["exists"] for row in rows_by_generator[generator_id])
            for generator_id in excluded_generators
        ),
        "selected_tasks_exist": all(row["exists"] for row in selected_rows),
        "selected_task_hashes_bound": actual_task_hashes_match,
        "selected_task_count": len(selected_rows) == expected["tasks"],
        "split_counts": (
            split_counts["calibration"] == expected["calibration_tasks"]
            and split_counts["development"] == expected["development_tasks"]
            and split_counts["confirmation"] == expected["confirmation_tasks"]
        ),
        "split_variations_unchanged": split_variations_match,
        "protected_content_absent": all(
            set(row)
            == {"task_id", "generator_id", "variation", "split", "exists", "tree_sha256"}
            for row in selected_rows
        ),
    }
    status = contract["pass_status"] if all(checks.values()) else contract["fail_status"]

    holes = {}
    for generator_id in excluded_generators:
        rows = rows_by_generator[generator_id]
        holes[generator_id] = {
            "generated_variations": sorted(row["variation"] for row in rows if row["exists"]),
            "missing_variations": sorted(row["variation"] for row in rows if not row["exists"]),
        }

    manifest_path = output_dir / "task_manifest.json"
    manifest = {
        "schema": "recurrent_appworld_generated_capacity_valid_manifest_v1",
        "status": status,
        "selection_basis": contract["selection_basis"],
        "parent_manifest_sha256": file_hash(parent_manifest_path),
        "source_commit": source_commit,
        "complete_generator_ids": selected_generators,
        "excluded_partial_generators": holes,
        "split_rule": contract["split_rule"],
        "rows": selected_rows,
    }
    write_json(manifest_path, manifest)

    lock_path = output_dir / "execution_lock.json"
    lock = {
        "schema": "recurrent_appworld_generated_capacity_valid_execution_lock_v1",
        "status": "LOCKED_BEFORE_GENERATED_TASK_GUARD_OUTCOMES",
        "immutable_inputs": {
            str(contract_path.relative_to(REPO_ROOT)): file_hash(contract_path),
            str(contract_md_path.relative_to(REPO_ROOT)): file_hash(contract_md_path),
            str(parent_contract_path.relative_to(REPO_ROOT)): file_hash(parent_contract_path),
            str(parent_manifest_path.relative_to(REPO_ROOT)): file_hash(parent_manifest_path),
            str(parent_generation_path.relative_to(REPO_ROOT)): file_hash(parent_generation_path),
            str(parent_binding_path.relative_to(REPO_ROOT)): file_hash(parent_binding_path),
            str(parent_log_path.relative_to(REPO_ROOT)): file_hash(parent_log_path),
            str(Path(__file__).relative_to(REPO_ROOT)): file_hash(Path(__file__)),
        },
        "task_manifest_sha256": file_hash(manifest_path),
        "task_tree_sha256": {
            row["task_id"]: row["tree_sha256"] for row in selected_rows
        },
        "guard_outcomes_observed": False,
    }
    write_json(lock_path, lock)

    status_path = output_dir / "status.json"
    result = {
        "schema": "recurrent_appworld_generated_capacity_valid_v1",
        "status": status,
        "checks": checks,
        "selection_basis": contract["selection_basis"],
        "complete_generator_ids": selected_generators,
        "excluded_partial_generators": holes,
        "tasks": len(selected_rows),
        "split_counts": split_counts,
        "task_manifest_sha256": file_hash(manifest_path),
        "execution_lock_sha256": file_hash(lock_path),
        "guard_outcomes_observed": False,
        "development_authorized": status == contract["pass_status"],
        "confirmation_outcomes_sealed": True,
        "external_process_actions": False,
        "model_gpu_docker_used": False,
        "headline_eligible": False,
    }
    write_json(status_path, result)

    binding_path = output_dir / "result_binding.json"
    write_json(
        binding_path,
        {
            "execution_lock_sha256": file_hash(lock_path),
            "status_sha256": file_hash(status_path),
            "task_manifest_sha256": file_hash(manifest_path),
        },
    )

    report_lines = [
        "# AppWorld 0.2 Capacity-Valid Generated Pool",
        "",
        f"## Status: **`{status}`**",
        "",
        "The original v2 90-task result remains **FAIL**. This artifact applies the",
        "pre-outcome, operational-completeness rule to the preregistered minimum of",
        "eight valid generators; it does not reinterpret v2 as a pass.",
        "",
        f"- Complete generators: {len(selected_generators)}",
        f"- Capacity-valid tasks: {len(selected_rows)}",
        f"- Split counts: {split_counts}",
        f"- Included: {', '.join(selected_generators)}",
        f"- Excluded partial generators: {', '.join(excluded_generators)}",
        "- Guard outcomes observed: No",
        "- Confirmation outcomes: Sealed",
        "- External process actions: No",
        "- Model/GPU/Docker used: No",
        "",
        "## Capacity holes",
        "",
    ]
    report_lines.extend(
        f"- `{generator_id}`: generated {data['generated_variations']}; missing {data['missing_variations']}"
        for generator_id, data in holes.items()
    )
    report_lines.extend(["", "## Checks", ""])
    report_lines.extend(
        f"- `{name}`: **{'PASS' if value else 'FAIL'}**"
        for name, value in checks.items()
    )
    (output_dir / "REPORT.md").write_text("\n".join(report_lines) + "\n")

    print(json.dumps({"status": status, "tasks": len(selected_rows), "splits": split_counts}))
    if status != contract["pass_status"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()
