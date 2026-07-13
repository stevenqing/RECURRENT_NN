"""Literal text derivation verifier baseline for broad AppWorld witnesses."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analysis.appworld_broad_value_bound_template_verifier import decision, run_task_trace, scalar_pool
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


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def quoted_literals(instruction: str) -> set[str]:
    spans = []
    patterns = [r'"([^"\n]+)"', r"'([^'\n]+)'", r"“([^”\n]+)”", r"‘([^’\n]+)’"]
    for pattern in patterns:
        spans.extend(match.group(1) for match in re.finditer(pattern, instruction))
    return {normalize_text(span) for span in spans if normalize_text(span)}


def text_like_pool(pre_reads: list[Any]) -> list[Any]:
    output = []
    seen = set()
    for value in scalar_pool(pre_reads, include_arguments=True):
        if not isinstance(value, str):
            continue
        text = normalize_text(value)
        if not text:
            continue
        key = canonical(text)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def adversarial_text_candidate(live_value: Any, pre_reads: list[Any]) -> tuple[Any, str]:
    for value in text_like_pool(pre_reads):
        if canonical(normalize_text(value)) != canonical(normalize_text(live_value)):
            return value, "pre_read_text_scalar"
    return str(live_value) + " [alternative]", "string_mutation"


def literal_text_valid(candidate: Any, instruction_literals: set[str]) -> bool:
    return normalize_text(candidate) in instruction_literals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_appworld_broad_literal_text_derivation_verifier_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_broad_literal_text_derivation_verifier_v1"))
    args = parser.parse_args()
    contract_path = resolve(args.contract)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite literal text derivation verifier")

    contract = load_json(contract_path)
    warnings.filterwarnings("ignore")
    install_v6_compatibility()
    from appworld import update_root

    root = resolve(contract["generated_root"])
    update_root(str(root))
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
    adversarial_sources: Counter[str] = Counter()
    trace_failures = 0
    task_summaries = []
    for task_id, task_rows in sorted(rows_by_task.items()):
        baseline_pass, live_calls, error_type = run_task_trace(task_id)
        instruction = json.loads((root / "data/tasks" / task_id / "specs.json").read_text())["instruction"]
        literals = quoted_literals(instruction)
        task_summaries.append({"task_id": task_id, "baseline_pass": baseline_pass, "live_calls": len(live_calls), "target_instances": len(task_rows), "quoted_literal_count": len(literals), "error_type": error_type})
        if not baseline_pass:
            trace_failures += 1
            continue
        for row in sorted(task_rows, key=lambda item: (item["call_index"], item["field_name"])):
            call_index = int(row["call_index"])
            target_call = live_calls[call_index]
            live_value = target_call.arguments[row["field_name"]]
            pre_reads = [call for call in live_calls[:call_index] if call.method == "get" and call.app_name != "supervisor"]
            adversarial_value, adversarial_source = adversarial_text_candidate(live_value, pre_reads)
            live_valid = literal_text_valid(live_value, literals)
            adversarial_valid = literal_text_valid(adversarial_value, literals)
            verdict = decision(live_valid, adversarial_valid)
            schema_key = f"{row['method']}.{row['app']}.{row['api_name']}.{row['field_name']}"
            decision_counts[verdict] += 1
            schema_counts[schema_key] += 1
            schema_decisions[schema_key][verdict] += 1
            adversarial_sources[adversarial_source] += 1
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
        "contract_frozen": contract["status"] == "FROZEN_BEFORE_LITERAL_TEXT_DERIVATION_VERIFIER_OUTCOMES",
        "preflight_ready": preflight["status"] == contract["expected_statuses"]["value_bound_preflight"],
        "parent_negative_preserved": parent["status"] == contract["expected_statuses"]["parent_negative_baseline"],
        "instance_manifest_binding": file_hash(manifest_path) == preflight["instance_manifest_sha256"],
        "target_instance_count": len(target_rows) == contract["expected_instances"],
        "schema_counts": dict(sorted(schema_counts.items())) == contract["expected_schema_counts"],
        "row_count": len(result_rows) == len(target_rows),
        "trace_execution": trace_failures == 0 and all(summary["baseline_pass"] for summary in task_summaries),
        "decision_labels": set(decision_counts).issubset(set(contract["decision_labels"])),
        "scope": contract["protected_content_export"] is False and contract["instruction_text_export"] is False and contract["argument_values_export"] is False and contract["response_values_export"] is False and contract["value_hashes_export"] is False and contract["model_gpu_docker_used"] is False and contract["external_process_actions"] is False and contract["headline_eligible"] is False,
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
    write_json(rows_path, {"schema": "appworld_broad_literal_text_derivation_verifier_rows_v1", "status": status, "rows": result_rows, "protected_content_exported": False, "instruction_text_exported": False, "argument_values_exported": False, "response_values_exported": False, "value_hashes_exported": False})
    payload = {
        "schema": "appworld_broad_literal_text_derivation_verifier_v1",
        "status": status,
        "protocol_checks": protocol_checks,
        "safety_checks": safety_checks,
        "decision_counts": dict(sorted(decision_counts.items())),
        "schema_decision_counts": {key: dict(sorted(counter.items())) for key, counter in sorted(schema_decisions.items())},
        "adversarial_sources": dict(sorted(adversarial_sources.items())),
        "target_instances": len(target_rows),
        "trace_failures": trace_failures,
        "task_summaries": task_summaries,
        "rows_sha256": file_hash(rows_path),
        "contract_sha256": file_hash(contract_path),
        "fresh_confirmation_sealed": True,
        "protected_content_exported": False,
        "instruction_text_exported": False,
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
        "# AppWorld Broad Literal Text Derivation Verifier",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Target instances: {len(target_rows)}",
        f"- Evaluated instances: {len(result_rows)}",
        f"- Unsafe unique-wrong: {unsafe}",
        "- Action correctness claim: No",
        "- Instruction text exported: No",
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