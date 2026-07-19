"""Build a value-free held-out instance manifest for EBW TTC evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from experiments.appworld_trace_replay import TraceResolver

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


def instance_id(task_id: str, call_index: int, field_name: str) -> str:
    return hashlib.sha256(f"heldout|{task_id}|{call_index}|{field_name}".encode()).hexdigest()[:20]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_ebw_test_time_compute_heldout_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v31_heldout_instance_preflight"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v31 held-out instance preflight")

    contract_path = resolve(args.contract)
    contract = load_json(contract_path)
    ttc_freeze_path = resolve(contract["ttc_freeze"])
    fresh_cert_path = resolve(contract["fresh_semantic_certification"])
    fresh_manifest_path = resolve(contract["fresh_manifest"])
    sketch_manifest_path = resolve(contract["sketch_manifest"])
    root = resolve(contract["fresh_generated_root"])
    ttc_freeze = load_json(ttc_freeze_path)
    fresh_cert = load_json(fresh_cert_path)
    fresh_manifest = load_json(fresh_manifest_path)
    sketch_manifest = load_json(sketch_manifest_path)
    schema_rows = {
        (row["method"], row["app"], row["api_name"], row["field_name"]): row
        for row in sketch_manifest["rows"]
        if row["proof_family"] in contract["included_proof_families"]
    }

    resolver = TraceResolver()
    rows: list[dict[str, Any]] = []
    family_counts: Counter[str] = Counter()
    task_counts: Counter[str] = Counter()
    write_ordinals: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
    no_pre_read_by_family: Counter[str] = Counter()
    no_same_app_pre_read_by_family: Counter[str] = Counter()
    max_pre_reads = 0
    max_same_app_pre_reads = 0
    for task in fresh_manifest["fresh_rows"]:
        task_id = task["task_id"]
        calls_path = root / "data/tasks" / task_id / "ground_truth/api_calls.json"
        calls = json.loads(calls_path.read_text())
        resolved = [resolver.resolve(index, call) for index, call in enumerate(calls)]
        for call_index, resolved_call in enumerate(resolved):
            if resolved_call.method == "get":
                continue
            arguments = resolved_call.arguments()
            for field_name in sorted(arguments):
                key = (resolved_call.method, resolved_call.app_name, resolved_call.api_name, field_name)
                if key not in schema_rows:
                    continue
                schema_row = schema_rows[key]
                pre_reads = [call for call in resolved[:call_index] if call.method == "get" and call.app_name != "supervisor"]
                same_app_pre_reads = [call for call in pre_reads if call.app_name == resolved_call.app_name]
                ordinal_key = (task_id, resolved_call.method, resolved_call.app_name, resolved_call.api_name, field_name)
                write_ordinal = write_ordinals[ordinal_key]
                write_ordinals[ordinal_key] += 1
                family = schema_row["proof_family"]
                family_counts[family] += 1
                task_counts[task_id] += 1
                max_pre_reads = max(max_pre_reads, len(pre_reads))
                max_same_app_pre_reads = max(max_same_app_pre_reads, len(same_app_pre_reads))
                if not pre_reads:
                    no_pre_read_by_family[family] += 1
                if not same_app_pre_reads:
                    no_same_app_pre_read_by_family[family] += 1
                rows.append(
                    {
                        "instance_id": instance_id(task_id, call_index, field_name),
                        "task_id": task_id,
                        "generator_id": task["generator_id"],
                        "variation": task["variation"],
                        "call_index": call_index,
                        "method": resolved_call.method,
                        "app": resolved_call.app_name,
                        "api_name": resolved_call.api_name,
                        "field_name": field_name,
                        "field_type": schema_row["field_type"],
                        "field_kind": schema_row["field_kind"],
                        "proof_family": family,
                        "write_ordinal_for_schema": write_ordinal,
                        "pre_write_read_count": len(pre_reads),
                        "same_app_pre_write_read_count": len(same_app_pre_reads),
                        "has_pre_write_reads": bool(pre_reads),
                        "has_same_app_pre_write_reads": bool(same_app_pre_reads),
                    }
                )

    row_keys = {
        "instance_id",
        "task_id",
        "generator_id",
        "variation",
        "call_index",
        "method",
        "app",
        "api_name",
        "field_name",
        "field_type",
        "field_kind",
        "proof_family",
        "write_ordinal_for_schema",
        "pre_write_read_count",
        "same_app_pre_write_read_count",
        "has_pre_write_reads",
        "has_same_app_pre_write_reads",
    }
    checks = {
        "contract_frozen": contract["status"] == "FROZEN_AFTER_V30_BEFORE_HELDOUT_VALUE_OUTCOMES",
        "ttc_freeze_ready": ttc_freeze["status"] == contract["expected_statuses"]["ttc_freeze"],
        "fresh_certification_pass": fresh_cert["status"] == contract["expected_statuses"]["fresh_semantic_certification"],
        "fresh_manifest_pass": fresh_manifest["status"] == contract["expected_statuses"]["fresh_manifest"],
        "sketch_manifest_ready": sketch_manifest["status"] == contract["expected_statuses"]["sketch_manifest"],
        "fresh_task_count": len(fresh_manifest["fresh_rows"]) == contract["expected_fresh_tasks"],
        "fresh_variations": sorted({row["variation"] for row in fresh_manifest["fresh_rows"]}) == contract["fresh_variations"],
        "fresh_root_exists": root.is_dir(),
        "target_instances_nonzero": len(rows) > 0,
        "all_tasks_have_targets": set(task_counts) == {row["task_id"] for row in fresh_manifest["fresh_rows"]},
        "unique_instance_ids": len({row["instance_id"] for row in rows}) == len(rows),
        "row_value_free": all(set(row) == row_keys for row in rows),
        "scope": contract["protected_content_export"] is False and contract["argument_values_export"] is False and contract["response_values_export"] is False and contract["value_hashes_export"] is False and contract["model_gpu_docker_used"] is False and contract["external_process_actions"] is False,
    }
    status = contract["verdicts"]["ready"] if all(checks.values()) else contract["verdicts"]["blocked"]
    if not checks["contract_frozen"] or not checks["scope"]:
        status = contract["verdicts"]["protocol_fail"]

    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "instance_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_v31_heldout_instance_manifest_v1",
            "status": status,
            "rows": rows,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
            "value_hashes_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v31_heldout_instance_preflight_v1",
        "status": status,
        "checks": checks,
        "fresh_tasks": len(fresh_manifest["fresh_rows"]),
        "target_instances": len(rows),
        "tasks_with_target_instances": len(task_counts),
        "family_instance_counts": dict(sorted(family_counts.items())),
        "no_pre_read_by_family": dict(sorted(no_pre_read_by_family.items())),
        "no_same_app_pre_read_by_family": dict(sorted(no_same_app_pre_read_by_family.items())),
        "max_pre_reads_before_target": max_pre_reads,
        "max_same_app_pre_reads_before_target": max_same_app_pre_reads,
        "instance_manifest_sha256": file_hash(manifest_path),
        "contract_sha256": file_hash(contract_path),
        "input_hashes": {
            "ttc_freeze": file_hash(ttc_freeze_path),
            "fresh_certification": file_hash(fresh_cert_path),
            "fresh_manifest": file_hash(fresh_manifest_path),
            "sketch_manifest": file_hash(sketch_manifest_path),
        },
        "claim_boundary": contract["claim_boundary"],
        "protected_content_exported": False,
        "argument_values_exported": False,
        "response_values_exported": False,
        "value_hashes_exported": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
        "headline_eligible": False,
    }
    write_json(output_dir / "preflight.json", payload)
    report = [
        "# EBW Track A v31 Held-Out Instance Preflight",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Fresh held-out tasks: {len(fresh_manifest['fresh_rows'])}",
        f"- Target field instances: {len(rows)}",
        f"- Tasks with target instances: {len(task_counts)}",
        "- Argument values exported: No",
        "- Response values exported: No",
        "- Value hashes exported: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Family Instance Counts",
        "",
        "| Proof family | Instances |",
        "|---|---:|",
    ]
    report += [f"| `{family}` | {count} |" for family, count in sorted(family_counts.items())]
    report += ["", "## Claim Boundary", "", contract["claim_boundary"], "", "## Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "PREFLIGHT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "fresh_tasks": len(fresh_manifest["fresh_rows"]), "target_instances": len(rows), "report": str((output_dir / "PREFLIGHT.md").relative_to(REPO_ROOT))}))
    if status != contract["verdicts"]["ready"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()