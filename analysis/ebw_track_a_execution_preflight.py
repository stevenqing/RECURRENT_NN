"""Create EBW Track A opened-pool execution preflight after freeze tag."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def git_rev_parse(rev: str) -> str:
    return subprocess.check_output(["git", "rev-parse", rev], cwd=REPO_ROOT, text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_execution_preflight_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_execution_preflight_v1"))
    args = parser.parse_args()
    contract_path = resolve(args.contract)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A execution preflight")

    contract = load_json(contract_path)
    runner_config_path = resolve(contract["runner_config"])
    readiness_path = resolve(contract["freeze_readiness"])
    readiness_lock_path = resolve(contract["freeze_readiness_lock"])
    opened_path = resolve(contract["opened_instance_manifest"])
    dev_path = resolve(contract["dev_slice_manifest"])
    prompt_freeze_path = resolve(contract["prompt_freeze"])
    prompt_template_path = resolve(contract["prompt_template_filled"])
    budget_path = resolve(contract["budget"])
    parser_path = resolve(contract["parser"])
    parser_tests_path = resolve(contract["parser_tests"])
    safe_ledger_path = resolve(contract["safe_ledger_v5"])

    runner_config = load_json(runner_config_path)
    readiness = load_json(readiness_path)
    readiness_lock = load_json(readiness_lock_path)
    opened = load_json(opened_path)
    dev = load_json(dev_path)
    prompt_freeze = load_json(prompt_freeze_path)
    budget = load_json(budget_path)
    safe_ledger = load_json(safe_ledger_path)

    tag_commit = git_rev_parse(f"{contract['freeze_tag']}^{{commit}}")
    head_commit = git_rev_parse("HEAD")
    dev_ids = {row["instance_id"] for row in dev["rows"]}
    reportable_rows = []
    for row in opened["rows"]:
        if row["instance_id"] in dev_ids:
            continue
        reportable_rows.append(
            {
                "instance_id": row["instance_id"],
                "task_id": row["task_id"],
                "generator_id": row["generator_id"],
                "variation": row["variation"],
                "call_index": row["call_index"],
                "method": row["method"],
                "app": row["app"],
                "api_name": row["api_name"],
                "field_name": row["field_name"],
                "field_type": row["field_type"],
                "field_kind": row["field_kind"],
                "proof_family": row["proof_family"],
                "pre_write_read_count": row["pre_write_read_count"],
                "same_app_pre_write_read_count": row["same_app_pre_write_read_count"],
            }
        )

    proof_family_counts = Counter(row["proof_family"] for row in reportable_rows)
    expected = contract["expected_counts"]
    checks = {
        "contract_frozen": contract["status"] == "FROZEN_AFTER_EBW_FREEZE_A_TAG_BEFORE_MODEL_OUTCOMES",
        "tag_commit": tag_commit == contract["expected_tag_commit"],
        "head_at_tag": head_commit == tag_commit,
        "readiness_status": readiness["status"] == contract["expected_statuses"]["freeze_readiness"],
        "readiness_lock_binding": file_hash(readiness_lock_path) == readiness["execution_lock_sha256"],
        "runner_config_tag": runner_config["freeze_tag"] == contract["freeze_tag"],
        "prompt_status": prompt_freeze["status"] == contract["expected_statuses"]["prompt_freeze"],
        "prompt_hash": prompt_freeze["prompt_template_sha256"] == file_hash(prompt_template_path) == runner_config["expected_prompt_sha256"],
        "budget_caps": budget["max_model_calls_per_candidate"] == 2 and budget["max_repair_rounds"] == 1 and budget["max_output_tokens_per_call"] == 512,
        "parser_exists": parser_path.is_file() and parser_tests_path.is_file(),
        "dev_status": dev["main_report_exclusion"] is True and len(dev_ids) == expected["dev_slice_instances"],
        "opened_count": len(opened["rows"]) == expected["opened_instances"],
        "reportable_count": len(reportable_rows) == expected["reportable_instances"],
        "no_dev_overlap": not (dev_ids & {row["instance_id"] for row in reportable_rows}),
        "unique_reportable_ids": len({row["instance_id"] for row in reportable_rows}) == len(reportable_rows),
        "safe_ledger": safe_ledger["status"] == contract["expected_statuses"]["safe_ledger_v5"] and safe_ledger["decision_counts"]["commit_live"] == expected["safe_ledger_denominator"],
        "ga_asserts": runner_config["gates"] == contract["gates"],
        "baseline_arms": set(runner_config["baseline_arms"]) == {"direct_action_no_gate", "self_consistency_n8_vote", "occurrence_verifier", "api_aware_mapper_to_template", "hand_coded_ledger_v5_templates", "sequential_matched_budget_synthesis", "parallel_role_synthesis", "agent_sentry_l1_l2_taint"},
        "sealed_closed": contract["execution_policy"]["sealed_variations_opened"] is False and runner_config["sealed_variations_opened"] is False,
        "no_model_or_external": contract["execution_policy"]["model_run"] is False and runner_config["model_gpu_docker_used"] is False and runner_config["external_process_actions"] is False,
    }
    status = contract["verdicts"]["ready"] if all(checks.values()) else contract["verdicts"]["blocked"]
    if not checks["contract_frozen"] or not checks["sealed_closed"] or not checks["no_model_or_external"]:
        status = contract["verdicts"]["protocol_fail"]

    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "evaluation_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_opened_evaluation_manifest_v1",
            "status": status,
            "rows": reportable_rows,
            "dev_slice_excluded": True,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
            "value_hashes_exported": False,
            "sealed_variations_opened": False,
        },
    )
    lock_files = {
        "contract": contract_path,
        "runner_config": runner_config_path,
        "freeze_readiness": readiness_path,
        "freeze_readiness_lock": readiness_lock_path,
        "opened_instance_manifest": opened_path,
        "dev_slice_manifest": dev_path,
        "prompt_freeze": prompt_freeze_path,
        "prompt_template_filled": prompt_template_path,
        "budget": budget_path,
        "parser": parser_path,
        "parser_tests": parser_tests_path,
        "safe_ledger_v5": safe_ledger_path,
        "evaluation_manifest": manifest_path,
    }
    execution_lock = {
        "schema": "ebw_track_a_execution_lock_v1",
        "status": "LOCKED_BEFORE_TRACK_A_MODEL_OUTCOMES",
        "freeze_tag": contract["freeze_tag"],
        "tag_commit": tag_commit,
        "files": {name: file_hash(path) for name, path in lock_files.items()},
        "prompt_sha256": prompt_freeze["prompt_template_sha256"],
        "reportable_instances": len(reportable_rows),
        "dev_slice_instances": len(dev_ids),
        "safe_ledger_denominator": expected["safe_ledger_denominator"],
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    lock_path = output_dir / "execution_lock.json"
    write_json(lock_path, execution_lock)
    payload = {
        "schema": "ebw_track_a_execution_preflight_v1",
        "status": status,
        "checks": checks,
        "freeze_tag": contract["freeze_tag"],
        "tag_commit": tag_commit,
        "prompt_sha256": prompt_freeze["prompt_template_sha256"],
        "opened_instances": len(opened["rows"]),
        "dev_slice_instances": len(dev_ids),
        "reportable_instances": len(reportable_rows),
        "proof_family_counts": dict(sorted(proof_family_counts.items())),
        "execution_lock_sha256": file_hash(lock_path),
        "evaluation_manifest_sha256": file_hash(manifest_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "preflight.json", payload)
    report = [
        "# EBW Track A Execution Preflight",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Freeze tag: `{contract['freeze_tag']}`",
        f"- Tag commit: `{tag_commit}`",
        f"- Prompt SHA256: `{prompt_freeze['prompt_template_sha256']}`",
        f"- Opened instances: {len(opened['rows'])}",
        f"- Dev slice excluded: {len(dev_ids)}",
        f"- Reportable opened instances: {len(reportable_rows)}",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Proof Family Counts",
        "",
        "| Proof family | Reportable instances |",
        "|---|---:|",
    ]
    report += [f"| {family} | {count} |" for family, count in sorted(proof_family_counts.items())]
    report += ["", "## Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "PREFLIGHT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "reportable_instances": len(reportable_rows), "report": str((output_dir / "PREFLIGHT.md").relative_to(REPO_ROOT))}))
    if status != contract["verdicts"]["ready"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()