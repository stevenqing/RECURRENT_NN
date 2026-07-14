"""Synthetic EBW Track A runner smoke test."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from experiments.ebw_obligation_sketch import barrier_unique_validity, parse_track_a_sketch

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


VALID_LITERAL = json.dumps({"obligation": "literal_intent_binding", "user_span": {"start": 1, "end": 4}, "target_arg": "message"})
VALID_PATH = json.dumps({"obligation": "derived_path_binding", "source_read_id": "read_1", "source_path_field": "response.path", "derivation": "basename", "target_arg": "destination_file_path"})
VALID_EFFECT = json.dumps({"obligation": "prior_effect_binding", "effect_step_id": "effect_2", "effect_field": "playlist_id", "target_arg": "playlist_id"})
VALID_ORDER = json.dumps({"obligation": "ordered_role_binding", "order_source_read_id": "read_3", "order_field": "song_id", "index_expr": "same_rank", "target_arg": "song_id"})


def synthetic_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "unique_live_first_pass",
            "live_candidate_id": "A",
            "candidates": {
                "A": {"outputs": [VALID_LITERAL], "verifier_valid": True},
                "B": {"outputs": [VALID_PATH], "verifier_valid": False},
            },
        },
        {
            "case_id": "parse_error_fail_closed",
            "live_candidate_id": "A",
            "candidates": {
                "A": {"outputs": ["not json"], "verifier_valid": True},
                "B": {"outputs": [VALID_PATH], "verifier_valid": False},
            },
        },
        {
            "case_id": "retry_success_commit_after_repair",
            "live_candidate_id": "A",
            "candidates": {
                "A": {"outputs": ["not json", VALID_EFFECT], "verifier_valid": True},
                "B": {"outputs": [VALID_PATH], "verifier_valid": False},
            },
        },
        {
            "case_id": "competing_valid_no_commit",
            "live_candidate_id": "A",
            "candidates": {
                "A": {"outputs": [VALID_LITERAL], "verifier_valid": True},
                "B": {"outputs": [VALID_ORDER], "verifier_valid": True},
            },
        },
        {
            "case_id": "no_valid_no_commit",
            "live_candidate_id": "A",
            "candidates": {
                "A": {"outputs": [VALID_LITERAL], "verifier_valid": False},
                "B": {"outputs": [VALID_ORDER], "verifier_valid": False},
            },
        },
        {
            "case_id": "wrong_unique_commit_counted_unsafe",
            "live_candidate_id": "A",
            "candidates": {
                "A": {"outputs": [VALID_LITERAL], "verifier_valid": False},
                "B": {"outputs": [VALID_ORDER], "verifier_valid": True},
            },
        },
    ]


def parse_with_one_retry(outputs: list[str]) -> tuple[bool, bool, str | None]:
    first = parse_track_a_sketch(outputs[0])
    if first.ok:
        return True, False, None
    if len(outputs) > 1:
        retry = parse_track_a_sketch(outputs[1])
        if retry.ok:
            return True, True, None
    return False, False, "parse_error"


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    verifier_results: dict[str, bool] = {}
    parse_errors = 0
    used_repair = False
    for candidate_id, payload in case["candidates"].items():
        parsed, repaired, error = parse_with_one_retry(payload["outputs"])
        used_repair = used_repair or repaired
        if not parsed:
            parse_errors += 1
            verifier_results[candidate_id] = False
        else:
            verifier_results[candidate_id] = bool(payload["verifier_valid"])
    barrier = barrier_unique_validity(verifier_results)
    if barrier["decision"] != "commit":
        outcome = "abstain_competing_valid" if barrier["typed_reason"] == "competing_valid" else "abstain_no_valid"
    elif barrier["candidate_id"] == case["live_candidate_id"]:
        outcome = "commit_live"
    else:
        outcome = "unsafe_unique_wrong"
    return {
        "case_id": case["case_id"],
        "outcome": outcome,
        "barrier": barrier,
        "parse_errors": parse_errors,
        "used_repair": used_repair,
        "commit_after_repair": outcome == "commit_live" and used_repair,
    }


def ga_main_summary(counter: Counter[str], denominator: int, absolute_min: int) -> dict[str, Any]:
    safe = int(counter.get("commit_live", 0))
    unsafe = int(counter.get("unsafe_unique_wrong", 0))
    return {
        "safe_commits": safe,
        "unsafe_unique_wrong": unsafe,
        "safe_commit_recovery": safe / denominator,
        "pass": unsafe == 0 and safe >= absolute_min,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_runner_smoke_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_runner_smoke_v1"))
    args = parser.parse_args()
    contract_path = resolve(args.contract)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A runner smoke")

    contract = load_json(contract_path)
    preflight_path = resolve(contract["execution_preflight"])
    lock_path = resolve(contract["execution_lock"])
    manifest_path = resolve(contract["evaluation_manifest"])
    budget_path = resolve(contract["budget"])
    preflight = load_json(preflight_path)
    lock = load_json(lock_path)
    manifest = load_json(manifest_path)
    budget = load_json(budget_path)

    rows = [evaluate_case(case) for case in synthetic_cases()]
    counter = Counter(row["outcome"] for row in rows)
    commit_after_repair = sum(1 for row in rows if row["commit_after_repair"])
    parse_error_cases = sum(1 for row in rows if row["parse_errors"])
    ga = ga_main_summary(counter, contract["ga_main_expected"]["safe_commit_recovery_denominator"], 167)
    expected = contract["synthetic_cases"]
    checks = {
        "contract_frozen": contract["status"] == "FROZEN_SYNTHETIC_RUNNER_SMOKE_BEFORE_MODEL_OUTCOMES",
        "preflight_ready": preflight["status"] == contract["expected_statuses"]["execution_preflight"],
        "lock_binding": file_hash(lock_path) == preflight["execution_lock_sha256"],
        "manifest_binding": file_hash(manifest_path) == preflight["evaluation_manifest_sha256"],
        "manifest_dev_excluded": manifest["dev_slice_excluded"] is True,
        "budget_retry": budget["max_repair_rounds"] == 1 and budget["retry_policy"] == "one_retry_on_non_json_only",
        "total_cases": len(rows) == expected["total"],
        "commit_live": int(counter.get("commit_live", 0)) == expected["commit_live"],
        "unsafe_unique_wrong": int(counter.get("unsafe_unique_wrong", 0)) == expected["unsafe_unique_wrong"],
        "abstain_no_valid": int(counter.get("abstain_no_valid", 0)) == expected["abstain_no_valid"],
        "abstain_competing_valid": int(counter.get("abstain_competing_valid", 0)) == expected["abstain_competing_valid"],
        "commit_after_repair": commit_after_repair == expected["commit_after_repair"],
        "parse_error_cases": parse_error_cases == expected["parse_error_cases"],
        "ga_main_unsafe_fails": ga["pass"] is contract["ga_main_expected"]["pass"] and ga["unsafe_unique_wrong"] == contract["ga_main_expected"]["unsafe_unique_wrong"],
        "sealed_closed": contract["sealed_variations_opened"] is False and lock["sealed_variations_opened"] is False,
        "no_model_or_external": contract["model_gpu_docker_used"] is False and contract["external_process_actions"] is False,
    }
    status = contract["verdicts"]["pass"] if all(checks.values()) else contract["verdicts"]["fail"]
    if not checks["contract_frozen"] or not checks["sealed_closed"] or not checks["no_model_or_external"]:
        status = contract["verdicts"]["protocol_fail"]

    output_dir.mkdir(parents=True)
    rows_path = output_dir / "synthetic_rows.json"
    write_json(rows_path, {"schema": "ebw_track_a_runner_smoke_rows_v1", "status": status, "rows": rows})
    payload = {
        "schema": "ebw_track_a_runner_smoke_v1",
        "status": status,
        "checks": checks,
        "outcome_counts": dict(sorted(counter.items())),
        "commit_after_repair": commit_after_repair,
        "parse_error_cases": parse_error_cases,
        "synthetic_ga_main": ga,
        "rows_sha256": file_hash(rows_path),
        "contract_sha256": file_hash(contract_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "smoke.json", payload)
    report = [
        "# EBW Track A Runner Smoke",
        "",
        f"## Status: **`{status}`**",
        "",
        "- Synthetic cases: 6",
        f"- Commit-live: {int(counter.get('commit_live', 0))}",
        f"- Unsafe unique-wrong: {int(counter.get('unsafe_unique_wrong', 0))}",
        f"- Commit after repair: {commit_after_repair}",
        f"- Parse-error cases: {parse_error_cases}",
        f"- Synthetic GA-main pass: {ga['pass']}",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Outcome Counts",
        "",
        "| Outcome | Count |",
        "|---|---:|",
    ]
    report += [f"| {key} | {value} |" for key, value in sorted(counter.items())]
    report += ["", "## Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "SMOKE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "report": str((output_dir / "SMOKE.md").relative_to(REPO_ROOT))}))
    if status != contract["verdicts"]["pass"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()