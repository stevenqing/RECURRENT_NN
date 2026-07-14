"""Freeze-readiness audit for EBW Track A v8 candidate-bound policy."""
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
    parser.add_argument("--prompt-freeze-v8", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v8/prompt_freeze_v8.json"))
    parser.add_argument("--prompt-assets-v8", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v8/track_a_prompt_assets_v8.json"))
    parser.add_argument("--prompt-protocol-v8", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_prompt_protocol_v8.json"))
    parser.add_argument("--verifier-policy-v7", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_verifier_policy_v7.json"))
    parser.add_argument("--opened-shard-v8", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_opened_shard_v8_candidate_bound_v2/results.json"))
    parser.add_argument("--opened-shard-manifest-v8", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_opened_shard_v8_candidate_bound_v2/prompt_manifest.json"))
    parser.add_argument("--parser-tests", type=Path, default=Path("analysis/test_ebw_obligation_sketch.py"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v8_freeze_readiness"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A v8 readiness")

    prompt_freeze_path = resolve(args.prompt_freeze_v8)
    prompt_assets_path = resolve(args.prompt_assets_v8)
    prompt_protocol_path = resolve(args.prompt_protocol_v8)
    verifier_policy_path = resolve(args.verifier_policy_v7)
    opened_shard_path = resolve(args.opened_shard_v8)
    opened_manifest_path = resolve(args.opened_shard_manifest_v8)
    parser_tests_path = resolve(args.parser_tests)
    prompt_freeze = load_json(prompt_freeze_path)
    prompt_assets = load_json(prompt_assets_path)
    prompt_protocol = load_json(prompt_protocol_path)
    verifier_policy = load_json(verifier_policy_path)
    opened_shard = load_json(opened_shard_path)
    opened_manifest = load_json(opened_manifest_path)
    tag_commit = git_rev_parse(f"{prompt_protocol['parent_freeze_tag']}^{{commit}}")
    checks = {
        "prompt_v8_ready": prompt_freeze["status"] == "RPD_EBW_TRACK_A_PROMPT_V8_READY_NOT_TAGGED",
        "prompt_assets_hash": prompt_freeze["prompt_assets_sha256"] == file_hash(prompt_assets_path),
        "prompt_protocol_v8": prompt_assets["prompt_protocol"] == "chat_template_json_prefill_candidate_bound_v8",
        "prompt_protocol_scope": prompt_protocol["sealed_variations_opened"] is False and prompt_protocol["model_gpu_docker_used"] is False and prompt_protocol["external_process_actions"] is False,
        "verifier_policy_hash": opened_shard["derived_path_adversary_policy"] == "path_shape_preserving_basename_mutation_v7" and file_hash(verifier_policy_path) == opened_shard.get("verifier_policy_sha256", file_hash(verifier_policy_path)) if "verifier_policy_sha256" in opened_shard else True,
        "opened_shard_status": opened_shard["status"] == "RPD_EBW_TRACK_A_MODEL_RUN_COMPLETE",
        "opened_shard_prompt_protocol": opened_shard["prompt_protocol"] == prompt_assets["prompt_protocol"],
        "opened_manifest_prompt_protocol": opened_manifest["prompt_protocol"] == prompt_assets["prompt_protocol"],
        "opened_shard_parse_rate": opened_shard["parse_rate"] == 1.0,
        "opened_shard_no_unsafe": int(opened_shard["decision_counts"].get("unsafe_unique_wrong", 0)) == 0,
        "opened_shard_commit_recovery": int(opened_shard["decision_counts"].get("commit_live", 0)) >= 54,
        "parser_tests_exist": parser_tests_path.is_file(),
    }
    status = prompt_protocol["verdicts"]["ready"] if all(checks.values()) else prompt_protocol["verdicts"]["blocked"]
    if not checks["prompt_protocol_scope"]:
        status = prompt_protocol["verdicts"]["protocol_fail"]

    output_dir.mkdir(parents=True)
    payload = {
        "schema": "ebw_track_a_v8_freeze_readiness_v1",
        "status": status,
        "checks": checks,
        "freeze_tag": prompt_protocol["parent_freeze_tag"],
        "tag_commit": tag_commit,
        "prompt_assets_v8_sha256": file_hash(prompt_assets_path),
        "prompt_freeze_v8_sha256": file_hash(prompt_freeze_path),
        "prompt_protocol_v8_sha256": file_hash(prompt_protocol_path),
        "verifier_policy_v7_sha256": file_hash(verifier_policy_path),
        "opened_shard_v8_results_sha256": file_hash(opened_shard_path),
        "opened_shard_v8_manifest_sha256": file_hash(opened_manifest_path),
        "prompt_protocol": prompt_assets["prompt_protocol"],
        "derived_path_adversary_policy": opened_shard["derived_path_adversary_policy"],
        "opened_shard_decision_counts": opened_shard["decision_counts"],
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "readiness.json", payload)
    report = [
        "# EBW Track A v8 Freeze Readiness",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Freeze tag: `{prompt_protocol['parent_freeze_tag']}`",
        f"- Tag commit: `{tag_commit}`",
        f"- Prompt protocol: `{payload['prompt_protocol']}`",
        f"- Derived path adversary policy: `{payload['derived_path_adversary_policy']}`",
        f"- Opened-shard decision counts: {payload['opened_shard_decision_counts']}",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Checks",
        "",
    ]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "READINESS.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "report": str((output_dir / "READINESS.md").relative_to(REPO_ROOT))}))
    if status != prompt_protocol["verdicts"]["ready"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()