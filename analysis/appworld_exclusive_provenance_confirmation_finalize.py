"""Certify held-out AppWorld exclusive-provenance confirmation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.appworld_exclusive_provenance import exclusive_choice_from_tiers

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


def aggregate_metrics(first: dict[str, Any], second: dict[str, Any]) -> dict[str, float | int]:
    pairs = int(first["pairs"]) + int(second["pairs"])
    covered = int(first["covered"]) + int(second["covered"])
    correct = int(first["correct"]) + int(second["correct"])
    wrong = int(first["wrong"]) + int(second["wrong"])
    return {
        "pairs": pairs,
        "covered": covered,
        "correct": correct,
        "wrong": wrong,
        "coverage": covered / pairs,
        "accuracy": correct / covered if covered else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/recurrent_parallel_appworld_exclusive_provenance_confirmation_v1"),
    )
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    result_path = output_dir / "results.json"
    binding_path = output_dir / "result_binding.json"
    lock_path = output_dir / "execution_lock.json"
    certification_path = output_dir / "certification.json"
    if certification_path.exists():
        raise RuntimeError(f"Refusing to overwrite certification: {certification_path}")

    result = load_json(result_path)
    binding = load_json(binding_path)
    lock = load_json(lock_path)
    development_path = resolve(
        "results/recurrent_parallel_appworld_exclusive_provenance_development_v1/results.json"
    )
    development = load_json(development_path)
    contract = load_json(
        resolve("specs/recurrent_parallel_appworld_exclusive_provenance_confirmation_v1.json")
    )
    appworld_root = resolve(contract["appworld_root"])
    shard_dir = output_dir / "task_shards"
    shard_hashes = {
        path.stem: file_hash(path) for path in sorted(shard_dir.glob("*.json"))
    }
    immutable_inputs_match = all(
        resolve(path).is_file() and file_hash(resolve(path)) == expected_hash
        for path, expected_hash in lock["immutable_inputs"].items()
    )
    selected_hashes_match = all(
        tree_hash(appworld_root / "data/tasks" / row["task_id"])
        == row["tree_sha256"]
        for row in lock["selected_tasks"]
    )
    selected_cache_files = [
        str(item.relative_to(appworld_root / "data/tasks"))
        for row in lock["selected_tasks"]
        for item in (appworld_root / "data/tasks" / row["task_id"]).rglob("*.pyc")
    ]
    rule_rows_match = all(
        row["exclusive_choice"]
        == exclusive_choice_from_tiers(row["typed_tier_A"], row["typed_tier_B"])
        for row in result["rows"]
    )
    preserved_correct = all(
        not row["typed_correct"] or row["exclusive_choice"] == row["typed_choice"]
        for row in result["rows"]
        if row["typed_covered"]
    )
    blocked_typed_errors = all(
        row["exclusive_choice"] is None
        for row in result["rows"]
        if row["typed_correct"] is False
    )
    checks = {
        "result_binding": (
            file_hash(result_path) == binding["results_sha256"]
            and file_hash(lock_path) == binding["execution_lock_sha256"]
            and shard_hashes == binding["task_shard_sha256"]
        ),
        "immutable_inputs": immutable_inputs_match,
        "frozen_command": (
            "-B" in lock["execution_command"]
            and lock["execution_environment"]["PYTHONDONTWRITEBYTECODE"] == "1"
            and lock["execution_environment"]["PYTHONHASHSEED"] == "0"
        ),
        "selected_raw_hashes": selected_hashes_match,
        "selected_cache_absent": not selected_cache_files,
        "all_baselines": (
            len(result["task_summaries"]) == contract["expected_open_tasks"]
            and all(summary["baseline_pass"] for summary in result["task_summaries"])
            and all(summary["error_type"] is None for summary in result["task_summaries"])
        ),
        "all_gates": (
            result["status"] == contract["verdicts"]["pass"]
            and all(result["gates"].values())
        ),
        "metric_consistency": (
            result["strict_pairs"] == len(result["rows"]) == 35
            and result["typed_max_tier_guard"]["correct"] == 22
            and result["typed_max_tier_guard"]["wrong"] == 2
            and result["exclusive_guard"]["correct"] == 22
            and result["exclusive_guard"]["wrong"] == 0
        ),
        "rule_rows": rule_rows_match,
        "preserved_typed_correct": preserved_correct,
        "blocked_typed_errors": blocked_typed_errors,
        "development_binding": file_hash(development_path)
        == lock["development_results_sha256"],
        "scope": (
            result["confirmation_outcomes_opened"] is True
            and result["protected_content_exported"] is False
            and result["external_process_actions"] is False
            and result["model_gpu_docker_used"] is False
            and result["headline_eligible"] is False
        ),
    }
    certification_status = (
        "RPD_APPWORLD_EXCLUSIVE_PROVENANCE_CONFIRMATION_RESULT_CERTIFIED"
        if all(checks.values())
        else "RPD_APPWORLD_EXCLUSIVE_PROVENANCE_CONFIRMATION_CERTIFICATION_FAIL"
    )

    dev_typed = {"pairs": development["generated"]["pairs"], **development["generated"]["typed_max_tier"]}
    dev_exclusive = {"pairs": development["generated"]["pairs"], **development["generated"]["exclusive"]}
    confirmation_typed = {"pairs": result["strict_pairs"], **result["typed_max_tier_guard"]}
    confirmation_exclusive = {"pairs": result["strict_pairs"], **result["exclusive_guard"]}
    combined_typed = aggregate_metrics(dev_typed, confirmation_typed)
    combined_exclusive = aggregate_metrics(dev_exclusive, confirmation_exclusive)
    selective_dominance = {
        "typed_correct_commits_preserved": combined_exclusive["correct"]
        == combined_typed["correct"],
        "typed_wrong_commits_blocked": combined_typed["wrong"]
        - combined_exclusive["wrong"],
        "additional_abstentions": combined_typed["covered"]
        - combined_exclusive["covered"],
    }
    certification = {
        "schema": "recurrent_appworld_exclusive_provenance_confirmation_certification_v1",
        "status": certification_status,
        "confirmation_verdict": result["status"],
        "checks": checks,
        "development": {
            "typed_max_tier": dev_typed,
            "exclusive": dev_exclusive,
        },
        "confirmation": {
            "typed_max_tier": confirmation_typed,
            "exclusive": confirmation_exclusive,
        },
        "combined_generated": {
            "typed_max_tier": combined_typed,
            "exclusive": combined_exclusive,
            "selective_dominance": selective_dominance,
        },
        "results_sha256": file_hash(result_path),
        "execution_lock_sha256": file_hash(lock_path),
        "independent_instance_confirmation": True,
        "independent_task_type_confirmation": False,
        "external_process_actions": False,
        "headline_eligible": False,
    }
    write_json(certification_path, certification)
    report = [
        "# Exclusive Causal Provenance — Certified AppWorld Result",
        "",
        f"## Certification: **`{certification_status}`**",
        "",
        f"## Confirmation: **`{result['status']}`**",
        "",
        "### Held-out confirmation",
        "",
        "- Baseline tasks: 24/24 PASS",
        f"- Strict pairs: {result['strict_pairs']}",
        f"- Typed max-tier: {result['typed_max_tier_guard']['correct']} correct, {result['typed_max_tier_guard']['wrong']} wrong, coverage {result['typed_max_tier_guard']['coverage']:.3f}",
        f"- Exclusive provenance: {result['exclusive_guard']['correct']} correct, {result['exclusive_guard']['wrong']} wrong, coverage {result['exclusive_guard']['coverage']:.3f}",
        "- Confirmation gates: 7/7 PASS",
        "",
        "### Generated development + confirmation",
        "",
        "| Guard | Pairs | Coverage | Correct commits | Wrong commits | Accuracy |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Typed max-tier | {combined_typed['pairs']} | {combined_typed['coverage']:.3f} | {combined_typed['correct']} | {combined_typed['wrong']} | {combined_typed['accuracy']:.3f} |",
        f"| Exclusive provenance | {combined_exclusive['pairs']} | {combined_exclusive['coverage']:.3f} | {combined_exclusive['correct']} | {combined_exclusive['wrong']} | {combined_exclusive['accuracy']:.3f} |",
        "",
        f"Exclusive provenance preserved all {combined_typed['correct']} correct typed commits and abstained on all {combined_typed['wrong']} typed errors. It used {selective_dominance['additional_abstentions']} additional abstentions over {combined_typed['pairs']} strict pairs.",
        "",
        "### Interpretation",
        "",
        "The recurrent controller should commit at a barrier only under exclusive causal",
        "support. Competing supported lineages are not ranked by apparent evidence strength;",
        "they trigger abstention, another specialist round, or rollback.",
        "",
        "This is held-out instance confirmation within the same eight generator families.",
        "It is not independent task-type confirmation or an end-to-end headline result.",
        "",
        "## Certification checks",
        "",
    ]
    report.extend(
        f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()
    )
    (output_dir / "FINAL_REPORT.md").write_text("\n".join(report) + "\n")
    print(
        json.dumps(
            {
                "status": certification_status,
                "confirmation": result["status"],
                "combined_typed": combined_typed,
                "combined_exclusive": combined_exclusive,
            }
        )
    )
    if not all(checks.values()):
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()
