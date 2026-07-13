"""Filesystem path derivation verifier baseline for broad AppWorld witnesses."""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analysis.appworld_broad_value_bound_template_verifier import (
    adversarial_candidate,
    candidate_valid,
    decision,
    normalize_string,
    run_task_trace,
    scalar_pool,
)
from analysis.recurrent_appworld_generated_typed_provenance_development_v6 import install_v6_compatibility
from experiments.appworld_trace_replay import canonical

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


def norm_path(value: Any) -> str:
    text = str(value).strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    return text.rstrip("/") or text


def basename(value: Any) -> str:
    return posixpath.basename(norm_path(value)).casefold()


def path_like_pool(pre_reads: list[Any]) -> list[Any]:
    output = []
    seen = set()
    for value in scalar_pool(pre_reads, include_arguments=True):
        if not isinstance(value, str):
            continue
        if "/" not in value and "\\" not in value:
            continue
        key = canonical(norm_path(value))
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def path_occurs(candidate: Any, pre_reads: list[Any]) -> bool:
    target = normalize_string(norm_path(candidate))
    return any(normalize_string(norm_path(value)) == target for value in path_like_pool(pre_reads))


def adversarial_path_candidate(live_value: Any, pre_reads: list[Any]) -> tuple[Any, str]:
    for value in path_like_pool(pre_reads):
        if canonical(norm_path(value)) != canonical(norm_path(live_value)):
            return value, "pre_read_path_scalar"
    return str(live_value) + "_alternative", "string_mutation"


def filesystem_path_valid(field_name: str, api_name: str, candidate: Any, target_arguments: dict[str, Any], pre_reads: list[Any]) -> bool:
    if api_name == "move_file" and field_name == "source_file_path":
        return path_occurs(candidate, pre_reads)
    if api_name == "move_file" and field_name == "destination_file_path":
        source_path = target_arguments.get("source_file_path")
        if source_path is None or not path_occurs(source_path, pre_reads):
            return False
        if canonical(norm_path(candidate)) == canonical(norm_path(source_path)):
            return False
        return basename(candidate) == basename(source_path)
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_appworld_broad_filesystem_path_derivation_verifier_v2.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_broad_filesystem_path_derivation_verifier_v2"))
    args = parser.parse_args()
    contract_path = resolve(args.contract)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite filesystem path derivation verifier")

    contract = load_json(contract_path)
    warnings.filterwarnings("ignore")
    install_v6_compatibility()
    from appworld import update_root

    update_root(str(resolve(contract["generated_root"])))
    preflight_path = resolve(contract["value_bound_preflight"])
    manifest_path = resolve(contract["instance_manifest"])
    parent_path = resolve(contract["parent_negative_baseline"])
    preflight = load_json(preflight_path)
    manifest = load_json(manifest_path)
    parent = load_json(parent_path)
    target_rows = [row for row in manifest["rows"] if row["proof_family"] == contract["target_proof_family"]]
    rows_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in target_rows:
        rows_by_task[row["task_id"]].append(row)

    result_rows = []
    decision_counts: Counter[str] = Counter()
    schema_counts: Counter[str] = Counter()
    schema_decisions: dict[str, Counter[str]] = defaultdict(Counter)
    trace_failures = 0
    task_summaries = []
    for task_id, task_rows in sorted(rows_by_task.items()):
        baseline_pass, live_calls, error_type = run_task_trace(task_id)
        task_summaries.append({"task_id": task_id, "baseline_pass": baseline_pass, "live_calls": len(live_calls), "target_instances": len(task_rows), "error_type": error_type})
        if not baseline_pass:
            trace_failures += 1
            continue
        for row in sorted(task_rows, key=lambda item: (item["call_index"], item["field_name"])):
            call_index = int(row["call_index"])
            target_call = live_calls[call_index]
            target_arguments = target_call.arguments
            live_value = target_arguments[row["field_name"]]
            pre_reads = [call for call in live_calls[:call_index] if call.method == "get" and call.app_name != "supervisor"]
            adversarial_value, adversarial_source = adversarial_path_candidate(live_value, pre_reads)
            live_valid = filesystem_path_valid(row["field_name"], row["api_name"], live_value, target_arguments, pre_reads)
            adversarial_valid = filesystem_path_valid(row["field_name"], row["api_name"], adversarial_value, target_arguments, pre_reads)
            verdict = decision(live_valid, adversarial_valid)
            schema_key = f"{row['method']}.{row['app']}.{row['api_name']}.{row['field_name']}"
            decision_counts[verdict] += 1
            schema_counts[schema_key] += 1
            schema_decisions[schema_key][verdict] += 1
            result_rows.append(
                {
                    "instance_id": row["instance_id"],
                    "task_id": task_id,
                    "generator_id": row["generator_id"],
                    "variation": row["variation"],
                    "call_index": call_index,
                    "method": row["method"],
                    "app": row["app"],
                    "api_name": row["api_name"],
                    "field_name": row["field_name"],
                    "proof_family": row["proof_family"],
                    "live_valid": live_valid,
                    "adversarial_valid": adversarial_valid,
                    "decision": verdict,
                    "adversarial_source": adversarial_source,
                }
            )

    unsafe = int(decision_counts.get("unsafe_unique_wrong", 0))
    protocol_checks = {
        "contract_frozen": contract["status"] == "FROZEN_BEFORE_FILESYSTEM_PATH_DERIVATION_VERIFIER_OUTCOMES",
        "preflight_ready": preflight["status"] == contract["expected_statuses"]["value_bound_preflight"],
        "parent_negative_preserved": parent["status"] == contract["expected_statuses"]["parent_negative_baseline"],
        "instance_manifest_binding": file_hash(manifest_path) == preflight["instance_manifest_sha256"],
        "target_instance_count": len(target_rows) == contract["expected_instances"],
        "schema_counts": dict(sorted(schema_counts.items())) == contract["expected_schema_counts"],
        "row_count": len(result_rows) == len(target_rows),
        "trace_execution": trace_failures == 0 and all(summary["baseline_pass"] for summary in task_summaries),
        "decision_labels": set(decision_counts).issubset(set(contract["decision_labels"])),
        "scope": contract["protected_content_export"] is False and contract["argument_values_export"] is False and contract["response_values_export"] is False and contract["value_hashes_export"] is False and contract["model_gpu_docker_used"] is False and contract["external_process_actions"] is False and contract["headline_eligible"] is False,
    }
    safety_checks = {"no_unsafe_unique_wrong": unsafe == contract["safety_gate"]["unsafe_unique_wrong_required"]}
    if not all(protocol_checks.values()):
        status = contract["verdicts"]["protocol_fail"]
    elif all(safety_checks.values()):
        status = contract["verdicts"]["safe"]
    else:
        status = contract["verdicts"]["unsafe"]

    output_dir.mkdir(parents=True)
    rows_path = output_dir / "rows.json"
    write_json(rows_path, {"schema": "appworld_broad_filesystem_path_derivation_verifier_rows_v1", "status": status, "rows": result_rows, "protected_content_exported": False, "argument_values_exported": False, "response_values_exported": False, "value_hashes_exported": False})
    payload = {
        "schema": "appworld_broad_filesystem_path_derivation_verifier_v1",
        "status": status,
        "protocol_checks": protocol_checks,
        "safety_checks": safety_checks,
        "decision_counts": dict(sorted(decision_counts.items())),
        "schema_decision_counts": {key: dict(sorted(counter.items())) for key, counter in sorted(schema_decisions.items())},
        "target_instances": len(target_rows),
        "trace_failures": trace_failures,
        "task_summaries": task_summaries,
        "rows_sha256": file_hash(rows_path),
        "contract_sha256": file_hash(contract_path),
        "fresh_confirmation_sealed": True,
        "protected_content_exported": False,
        "argument_values_exported": False,
        "response_values_exported": False,
        "value_hashes_exported": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
        "headline_eligible": False,
        "action_correctness_claim": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# AppWorld Broad Filesystem Path Derivation Verifier",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Target instances: {len(target_rows)}",
        f"- Evaluated instances: {len(result_rows)}",
        f"- Unsafe unique-wrong: {unsafe}",
        "- Action correctness claim: No",
        "- Argument values exported: No",
        "- Response values exported: No",
        "- Value hashes exported: No",
        "- Fresh variations 10-12: sealed",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Decision Counts",
        "",
        "| Decision | Count |",
        "|---|---:|",
    ]
    report += [f"| {label} | {int(decision_counts.get(label, 0))} |" for label in contract["decision_labels"]]
    report += ["", "## Schema Decisions", ""]
    for schema_key, counter in sorted(schema_decisions.items()):
        report += [f"### `{schema_key}`", "", "| Decision | Count |", "|---|---:|"]
        report += [f"| {label} | {int(counter.get(label, 0))} |" for label in contract["decision_labels"]]
        report += [""]
    report += ["## Protocol Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in protocol_checks.items()]
    report += ["", "## Safety Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in safety_checks.items()]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "unsafe_unique_wrong": unsafe, "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))
    if status == contract["verdicts"]["protocol_fail"]:
        raise RuntimeError(protocol_checks)


if __name__ == "__main__":
    main()