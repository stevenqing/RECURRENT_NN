"""Freeze-readiness audit for EBW Track A v7 verifier policy."""
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


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def git_rev_parse(rev: str) -> str:
    return subprocess.check_output(["git", "rev-parse", rev], cwd=REPO_ROOT, text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-freeze-v6", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v6/prompt_freeze_v6.json"))
    parser.add_argument("--prompt-assets-v6", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v6/track_a_prompt_assets_v6.json"))
    parser.add_argument("--verifier-policy-v7", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_verifier_policy_v7.json"))
    parser.add_argument("--dev40-v7", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_dev40_v7_rescore/results.json"))
    parser.add_argument("--parser-tests", type=Path, default=Path("analysis/test_ebw_obligation_sketch.py"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v7_freeze_readiness"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A v7 readiness")

    prompt_freeze_path = resolve(args.prompt_freeze_v6)
    prompt_assets_path = resolve(args.prompt_assets_v6)
    verifier_policy_path = resolve(args.verifier_policy_v7)
    dev40_path = resolve(args.dev40_v7)
    parser_tests_path = resolve(args.parser_tests)
    prompt_freeze = load_json(prompt_freeze_path)
    prompt_assets = load_json(prompt_assets_path)
    verifier_policy = load_json(verifier_policy_path)
    dev40 = load_json(dev40_path)
    tag_commit = git_rev_parse(f"{verifier_policy['parent_freeze_tag']}^{{commit}}")
    checks = {
        "parent_prompt_v6_ready": prompt_freeze["status"] == "RPD_EBW_TRACK_A_PROMPT_V6_READY_NOT_TAGGED",
        "prompt_assets_hash": prompt_freeze["prompt_assets_sha256"] == file_hash(prompt_assets_path),
        "prompt_protocol_v6": prompt_assets["prompt_protocol"] == "chat_template_json_prefill_role_literal_derived_v6",
        "verifier_policy_status": verifier_policy["status"] == "DEV_DERIVED_PATH_ADVERSARY_REPAIR_AFTER_V6_DEV40_BEFORE_NEW_TAG",
        "verifier_policy_scope": verifier_policy["sealed_variations_opened"] is False and verifier_policy["model_gpu_docker_used"] is False and verifier_policy["external_process_actions"] is False,
        "dev40_status": dev40["status"] == "RPD_EBW_TRACK_A_RESCORE_COMPLETE",
        "dev40_prompt_protocol": dev40["prompt_protocol"] == prompt_assets["prompt_protocol"],
        "dev40_verifier_policy_hash": dev40["verifier_policy_sha256"] == file_hash(verifier_policy_path),
        "dev40_parse_rate": dev40["parse_rate"] == 1.0,
        "dev40_no_unsafe": int(dev40["decision_counts"].get("unsafe_unique_wrong", 0)) == 0,
        "dev40_commit_recovery": int(dev40["decision_counts"].get("commit_live", 0)) >= 30,
        "parser_tests_exist": parser_tests_path.is_file(),
    }
    status = verifier_policy["verdicts"]["ready"] if all(checks.values()) else verifier_policy["verdicts"]["blocked"]
    if not checks["verifier_policy_scope"]:
        status = verifier_policy["verdicts"]["protocol_fail"]

    output_dir.mkdir(parents=True)
    payload = {
        "schema": "ebw_track_a_v7_freeze_readiness_v1",
        "status": status,
        "checks": checks,
        "freeze_tag": verifier_policy["parent_freeze_tag"],
        "tag_commit": tag_commit,
        "prompt_assets_v6_sha256": file_hash(prompt_assets_path),
        "prompt_freeze_v6_sha256": file_hash(prompt_freeze_path),
        "verifier_policy_v7_sha256": file_hash(verifier_policy_path),
        "dev40_v7_results_sha256": file_hash(dev40_path),
        "prompt_protocol": prompt_assets["prompt_protocol"],
        "derived_path_adversary_policy": dev40["derived_path_adversary_policy"],
        "dev40_decision_counts": dev40["decision_counts"],
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "readiness.json", payload)
    report = [
        "# EBW Track A v7 Freeze Readiness",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Freeze tag: `{verifier_policy['parent_freeze_tag']}`",
        f"- Tag commit: `{tag_commit}`",
        f"- Prompt protocol: `{payload['prompt_protocol']}`",
        f"- Derived path adversary policy: `{payload['derived_path_adversary_policy']}`",
        f"- Dev40 decision counts: {payload['dev40_decision_counts']}",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Checks",
        "",
    ]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "READINESS.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "report": str((output_dir / "READINESS.md").relative_to(REPO_ROOT))}))
    if status != verifier_policy["verdicts"]["ready"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()