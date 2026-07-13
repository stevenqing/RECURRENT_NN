"""Created-playlist state-transition verifier for broad AppWorld witnesses."""
from __future__ import annotations

import argparse
import hashlib
import json
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analysis.appworld_broad_value_bound_template_verifier import decision, run_task_trace, same_value, scalar_pool, type_mutation
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


def find_values_for_key(value: Any, key_name: str) -> list[Any]:
    output: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == key_name:
                output.append(child)
            output.extend(find_values_for_key(child, key_name))
    elif isinstance(value, list):
        for child in value:
            output.extend(find_values_for_key(child, key_name))
    return output


def latest_created_playlist_id(history: list[Any]) -> Any | None:
    for call in reversed(history):
        if call.method != "post" or call.app_name != "spotify" or call.api_name != "create_playlist":
            continue
        values = find_values_for_key(call.response, "playlist_id")
        if values:
            return values[-1]
    return None


def valid_created_playlist_candidate(candidate: Any, history: list[Any]) -> bool:
    playlist_id = latest_created_playlist_id(history)
    return playlist_id is not None and same_value(candidate, playlist_id)


def adversarial_candidate(live_value: Any, history: list[Any]) -> tuple[Any, str]:
    pools = []
    prior_reads = [call for call in history if call.method == "get" and call.app_name == "spotify"]
    prior_writes = [call for call in history if call.method != "get" and call.app_name == "spotify"]
    pools.extend(scalar_pool(prior_reads, include_arguments=False))
    pools.extend(scalar_pool(prior_writes, include_arguments=False))
    seen = set()
    for value in pools:
        key = canonical(value)
        if key in seen:
            continue
        seen.add(key)
        if not same_value(value, live_value):
            return value, "prior_spotify_scalar"
    return type_mutation(live_value), "type_mutation"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_appworld_broad_state_transition_created_playlist_verifier_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_broad_state_transition_created_playlist_verifier_v1"))
    args = parser.parse_args()
    contract_path = resolve(args.contract)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite state-transition created-playlist verifier")

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
    target_rows = [
        row for row in manifest["rows"]
        if row["proof_family"] == contract["target_proof_family"]
        and f"{row['method']}.{row['app']}.{row['api_name']}.{row['field_name']}" == contract["target_schema"]
    ]
    rows_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in target_rows:
        rows_by_task[row["task_id"]].append(row)

    result_rows = []
    decision_counts: Counter[str] = Counter()
    adversarial_sources: Counter[str] = Counter()
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
            live_value = target_call.arguments[row["field_name"]]
            history = live_calls[:call_index]
            adversarial_value, adversarial_source = adversarial_candidate(live_value, history)
            live_valid = valid_created_playlist_candidate(live_value, history)
            adversarial_valid = valid_created_playlist_candidate(adversarial_value, history)
            verdict = decision(live_valid, adversarial_valid)
            decision_counts[verdict] += 1
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
        "contract_frozen": contract["status"] == "FROZEN_BEFORE_STATE_TRANSITION_CREATED_PLAYLIST_VERIFIER_OUTCOMES",
        "preflight_ready": preflight["status"] == contract["expected_statuses"]["value_bound_preflight"],
        "parent_negative_preserved": parent["status"] == contract["expected_statuses"]["parent_negative_baseline"],
        "instance_manifest_binding": file_hash(manifest_path) == preflight["instance_manifest_sha256"],
        "target_instance_count": len(target_rows) == contract["expected_instances"],
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
    write_json(rows_path, {"schema": "appworld_broad_state_transition_created_playlist_verifier_rows_v1", "status": status, "rows": result_rows, "protected_content_exported": False, "argument_values_exported": False, "response_values_exported": False, "value_hashes_exported": False})
    payload = {
        "schema": "appworld_broad_state_transition_created_playlist_verifier_v1",
        "status": status,
        "protocol_checks": protocol_checks,
        "safety_checks": safety_checks,
        "decision_counts": dict(sorted(decision_counts.items())),
        "adversarial_sources": dict(sorted(adversarial_sources.items())),
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
        "# AppWorld Broad State-Transition Created-Playlist Verifier",
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
    report += ["", "## Protocol Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in protocol_checks.items()]
    report += ["", "## Safety Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in safety_checks.items()]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "unsafe_unique_wrong": unsafe, "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))
    if status == contract["verdicts"]["protocol_fail"]:
        raise RuntimeError(protocol_checks)


if __name__ == "__main__":
    main()