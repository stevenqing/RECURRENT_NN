"""Audit EBW Track A freeze-readiness artifacts without running a model."""
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


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config/ebw_track_a_runner_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_freeze_readiness_v1"))
    args = parser.parse_args()
    config_path = resolve(args.config)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A freeze-readiness audit")

    config = load_json(config_path)
    paths = {name: resolve(path) for name, path in config["paths"].items()}
    freeze_spec = load_json(paths["freeze_spec"])
    budget = load_json(paths["budget"])
    prompt_freeze = load_json(paths["prompt_freeze"])
    dev_freeze = load_json(paths["dev_slice_freeze"])
    dev_manifest = load_json(paths["dev_slice_manifest"])
    opened_manifest = load_json(paths["opened_instance_manifest"])
    safe_ledger = load_json(paths["safe_ledger_v5"])

    spec_ga = freeze_spec["tracks"]["A"]
    checks = {
        "config_frozen": config["status"] == "FROZEN_RUNNER_ASSERTS_BEFORE_TRACK_A_TAG",
        "freeze_spec_status": freeze_spec["status"] == "FREEZE_DOCUMENT_BEFORE_TRACK_A_TAG",
        "budget_frozen": budget["status"] == "FROZEN_BUDGET_VALUES_BEFORE_TRACK_A_TAG",
        "parser_exists": paths["parser"].is_file(),
        "parser_tests_exist": paths["parser_tests"].is_file(),
        "prompt_freeze_ready": prompt_freeze["status"] == "RPD_EBW_TRACK_A_PROMPT_EXAMPLES_READY_NOT_TAGGED",
        "prompt_hash": prompt_freeze["prompt_template_sha256"] == config["expected_prompt_sha256"] == file_hash(paths["prompt_template_filled"]),
        "dev_slice_ready": dev_freeze["status"] == "RPD_EBW_TRACK_A_DEV_SLICE_READY",
        "dev_slice_manifest_binding": file_hash(paths["dev_slice_manifest"]) == dev_freeze["dev_slice_manifest_sha256"],
        "dev_slice_exclusion": dev_manifest["main_report_exclusion"] is True and config["reporting"]["exclude_dev_slice_ids"] is True,
        "dev_slice_size": len(dev_manifest["rows"]) == 40,
        "opened_manifest_count": len(opened_manifest["rows"]) == freeze_spec["data"]["opened_pool_instances"],
        "safe_ledger_denominator": safe_ledger["decision_counts"]["commit_live"] == spec_ga["main_gate"]["denominator"] == config["gates"]["GA_main"]["denominator"],
        "ga_dev_asserts": config["gates"]["GA_dev"] == spec_ga["dev_gate"],
        "ga_main_asserts": config["gates"]["GA_main"] == spec_ga["main_gate"],
        "budget_caps": budget["max_model_calls_per_candidate"] == 2 and budget["max_output_tokens_per_call"] == 512 and budget["max_repair_rounds"] == 1,
        "baseline_arms_present": set(config["baseline_arms"]) == {"direct_action_no_gate", "self_consistency_n8_vote", "occurrence_verifier", "api_aware_mapper_to_template", "hand_coded_ledger_v5_templates", "sequential_matched_budget_synthesis", "parallel_role_synthesis", "agent_sentry_l1_l2_taint"},
        "sealed_closed": config["sealed_variations_opened"] is False and prompt_freeze["sealed_variations_opened"] is False and dev_freeze["sealed_variations_opened"] is False,
        "no_model_or_external": config["model_gpu_docker_used"] is False and config["external_process_actions"] is False and config["git_tag_created"] is False,
    }
    status = config["verdicts"]["ready"] if all(checks.values()) else config["verdicts"]["blocked"]
    if not checks["config_frozen"] or not checks["sealed_closed"] or not checks["no_model_or_external"]:
        status = config["verdicts"]["protocol_fail"]

    output_dir.mkdir(parents=True)
    lock_files = {
        "config": str(config_path.relative_to(REPO_ROOT)),
        **{name: str(path.relative_to(REPO_ROOT)) for name, path in paths.items()},
    }
    lock = {
        "schema": "ebw_track_a_freeze_readiness_execution_lock_v1",
        "status": "LOCKED_BEFORE_EBW_FREEZE_A_TAG",
        "files": {name: file_hash(resolve(path)) for name, path in lock_files.items()},
        "prompt_sha256": prompt_freeze["prompt_template_sha256"],
        "dev_slice_manifest_sha256": dev_freeze["dev_slice_manifest_sha256"],
        "sealed_variations_opened": False,
        "git_tag_created": False,
    }
    lock_path = output_dir / "execution_lock.json"
    write_json(lock_path, lock)
    payload = {
        "schema": "ebw_track_a_freeze_readiness_v1",
        "status": status,
        "checks": checks,
        "execution_lock_sha256": file_hash(lock_path),
        "prompt_sha256": prompt_freeze["prompt_template_sha256"],
        "dev_slice_instances": len(dev_manifest["rows"]),
        "baseline_arms": sorted(config["baseline_arms"]),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
        "git_tag_created": False,
    }
    write_json(output_dir / "readiness.json", payload)
    report = [
        "# EBW Track A Freeze Readiness",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Prompt SHA256: `{payload['prompt_sha256']}`",
        f"- Dev slice instances: {payload['dev_slice_instances']}",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "- Git tag created: No",
        "",
        "## Checks",
        "",
    ]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    report += ["", "## Still Required For `ebw-freeze-A`", "", "- commit all freeze artifacts", "- create git tag `ebw-freeze-A`", "- only then open sealed variations 10-12 for Track A confirmation if GA-main passes"]
    (output_dir / "FREEZE_READINESS.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "report": str((output_dir / "FREEZE_READINESS.md").relative_to(REPO_ROOT))}))
    if status != config["verdicts"]["ready"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()