"""Create a value-free instance manifest for broad value-bound witness verification."""
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
    return hashlib.sha256(f"{task_id}|{call_index}|{field_name}".encode()).hexdigest()[:20]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_appworld_broad_value_bound_witness_preflight_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_broad_value_bound_witness_preflight_v1"))
    args = parser.parse_args()
    contract_path = resolve(args.contract)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite broad value-bound witness preflight")

    contract = load_json(contract_path)
    pool_manifest_path = resolve(contract["pool_manifest"])
    sketch_preflight_path = resolve(contract["witness_sketch_preflight"])
    sketch_manifest_path = resolve(contract["sketch_manifest"])
    template_baseline_path = resolve(contract["template_baseline"])
    fresh_path = resolve(contract["fresh_pool_certification"])
    root = resolve(contract["generated_root"])
    pool_manifest = load_json(pool_manifest_path)
    sketch_preflight = load_json(sketch_preflight_path)
    sketch_manifest = load_json(sketch_manifest_path)
    template_baseline = load_json(template_baseline_path)
    fresh = load_json(fresh_path)

    schema_rows = {
        (row["method"], row["app"], row["api_name"], row["field_name"]): row
        for row in sketch_manifest["rows"]
    }
    resolver = TraceResolver()
    rows: list[dict[str, Any]] = []
    family_counts: Counter[str] = Counter()
    no_pre_read_by_family: Counter[str] = Counter()
    no_same_app_pre_read_by_family: Counter[str] = Counter()
    tasks_with_target_instances: set[str] = set()
    write_ordinals: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
    max_pre_reads = 0
    max_same_app_pre_reads = 0

    for task in pool_manifest["rows"]:
        task_id = task["task_id"]
        calls = json.loads((root / "data/tasks" / task_id / "ground_truth/api_calls.json").read_text())
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
                tasks_with_target_instances.add(task_id)
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

    expected = contract["expected_counts"]
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
        "contract_frozen": contract["status"] == "FROZEN_BEFORE_BROAD_VALUE_BOUND_WITNESS_OUTCOMES",
        "pool_manifest": pool_manifest["status"] == contract["expected_statuses"]["pool_manifest"],
        "sketch_preflight_ready": sketch_preflight["status"] == contract["expected_statuses"]["witness_sketch_preflight"],
        "sketch_manifest_binding": file_hash(sketch_manifest_path) == sketch_preflight["sketch_manifest_sha256"],
        "template_baseline_pass": template_baseline["status"] == contract["expected_statuses"]["template_baseline"],
        "target_instance_count": len(rows) == expected["target_instances"],
        "tasks_with_target_instances": len(tasks_with_target_instances) == expected["tasks_with_target_instances"],
        "family_instance_counts": dict(sorted(family_counts.items())) == expected["family_instance_counts"],
        "pre_read_availability": dict(sorted(no_pre_read_by_family.items())) == expected["no_pre_read_by_family"],
        "same_app_pre_read_availability": dict(sorted(no_same_app_pre_read_by_family.items())) == expected["no_same_app_pre_read_by_family"],
        "max_pre_read_counts": max_pre_reads == expected["max_pre_reads_before_target"] and max_same_app_pre_reads == expected["max_same_app_pre_reads_before_target"],
        "row_value_free": all(set(row) == row_keys for row in rows),
        "unique_instance_ids": len({row["instance_id"] for row in rows}) == len(rows),
        "fresh_sealed": fresh["status"] == contract["expected_statuses"]["fresh_pool"] and fresh["fresh_confirmation_sealed"] is True,
        "scope": contract["protected_content_export"] is False and contract["model_gpu_docker_used"] is False and contract["external_process_actions"] is False and contract["headline_eligible"] is False,
    }
    status = contract["verdicts"]["ready"] if all(checks.values()) else contract["verdicts"]["blocked"]
    if not checks["contract_frozen"] or not checks["scope"]:
        status = contract["verdicts"]["protocol_fail"]

    output_dir.mkdir(parents=True)
    instance_manifest_path = output_dir / "instance_manifest.json"
    write_json(
        instance_manifest_path,
        {
            "schema": "appworld_broad_value_bound_witness_instance_manifest_v1",
            "status": status,
            "rows": rows,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
            "value_hashes_exported": False,
        },
    )
    payload = {
        "schema": "appworld_broad_value_bound_witness_preflight_v1",
        "status": status,
        "checks": checks,
        "target_instances": len(rows),
        "tasks_with_target_instances": len(tasks_with_target_instances),
        "family_instance_counts": dict(sorted(family_counts.items())),
        "no_pre_read_by_family": dict(sorted(no_pre_read_by_family.items())),
        "no_same_app_pre_read_by_family": dict(sorted(no_same_app_pre_read_by_family.items())),
        "max_pre_reads_before_target": max_pre_reads,
        "max_same_app_pre_reads_before_target": max_same_app_pre_reads,
        "instance_manifest_sha256": file_hash(instance_manifest_path),
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
    write_json(output_dir / "preflight.json", payload)
    report = [
        "# AppWorld Broad Value-Bound Witness Preflight",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Target field instances: {len(rows)}",
        f"- Tasks with target instances: {len(tasks_with_target_instances)}",
        f"- Instances with no pre-write reads: {sum(no_pre_read_by_family.values())}",
        "- Argument values exported: No",
        "- Response values exported: No",
        "- Value hashes exported: No",
        "- Fresh variations 10-12: sealed",
        "- Model/GPU/Docker/external process actions: No",
        "- Action correctness claim: No",
        "",
        "## Family Instance Counts",
        "",
        "| Proof family | Instances |",
        "|---|---:|",
    ]
    report += [f"| {family} | {count} |" for family, count in sorted(family_counts.items())]
    report += ["", "## Same-App Pre-Read Missing Counts", "", "| Proof family | Instances |", "|---|---:|"]
    if no_same_app_pre_read_by_family:
        report += [f"| {family} | {count} |" for family, count in sorted(no_same_app_pre_read_by_family.items())]
    else:
        report += ["| none | 0 |"]
    report += ["", "## Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "PREFLIGHT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "target_instances": len(rows), "report": str((output_dir / "PREFLIGHT.md").relative_to(REPO_ROOT))}))
    if status != contract["verdicts"]["ready"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()