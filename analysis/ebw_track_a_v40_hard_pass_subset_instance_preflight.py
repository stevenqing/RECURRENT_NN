"""Build value-free EBW instances for the v39 hard held-out pass subset.

This is explicitly exploratory because v39's preregistered four-generator hard
held-out generation was blocked. We only use generated fresh tasks that exist.
"""
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
    return hashlib.sha256(f"hard-pass-subset|{task_id}|{call_index}|{field_name}".encode()).hexdigest()[:20]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hard-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v39_hard_heldout_generation/fresh_manifest.json"))
    parser.add_argument("--sketch-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_broad_witness_sketch_v1/sketch_manifest.json"))
    parser.add_argument("--root", type=Path, default=Path("external_repos/appworld_generated_hard_v10_12"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v40_hard_pass_subset_instance_preflight"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v40 hard pass-subset preflight")

    hard_manifest_path = resolve(args.hard_manifest)
    sketch_manifest_path = resolve(args.sketch_manifest)
    root = resolve(args.root)
    hard_manifest = load_json(hard_manifest_path)
    sketch_manifest = load_json(sketch_manifest_path)
    fresh_rows = [row for row in hard_manifest["fresh_rows"] if row.get("exists")]
    schema_rows = {
        (row["method"], row["app"], row["api_name"], row["field_name"]): row
        for row in sketch_manifest["rows"]
    }
    resolver = TraceResolver()
    rows: list[dict[str, Any]] = []
    family_counts: Counter[str] = Counter()
    api_field_counts: Counter[tuple[str, str]] = Counter()
    task_counts: Counter[str] = Counter()
    write_ordinals: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
    for task in fresh_rows:
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
                api_field_counts[(resolved_call.api_name, field_name)] += 1
                task_counts[task_id] += 1
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

    status = "RPD_EBW_TRACK_A_V40_HARD_PASS_SUBSET_PREFLIGHT_READY"
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "instance_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_v40_hard_pass_subset_instance_manifest_v1",
            "status": status,
            "rows": rows,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
            "value_hashes_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v40_hard_pass_subset_instance_preflight_v1",
        "status": status,
        "claim_boundary": "Exploratory pass-subset only: v39 four-generator hard held-out protocol was blocked.",
        "source_v39_status": hard_manifest["status"],
        "fresh_tasks_used": len(fresh_rows),
        "target_instances": len(rows),
        "generators_used": sorted({row["generator_id"] for row in fresh_rows}),
        "family_instance_counts": dict(sorted(family_counts.items())),
        "api_field_counts": {f"{api}.{field}": count for (api, field), count in sorted(api_field_counts.items())},
        "instance_manifest_sha256": file_hash(manifest_path),
        "hard_manifest_sha256": file_hash(hard_manifest_path),
        "sketch_manifest_sha256": file_hash(sketch_manifest_path),
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
        "# EBW Track A v40 Hard Pass-Subset Instance Preflight",
        "",
        f"## Status: **`{status}`**",
        "",
        "- Claim boundary: exploratory pass-subset only; v39 hard held-out protocol was blocked.",
        f"- Fresh tasks used: {len(fresh_rows)}",
        f"- Target instances: {len(rows)}",
        f"- Generators used: {', '.join(payload['generators_used'])}",
        "- Argument/response/value hashes exported: No",
        "",
        "## Family Counts",
        "",
        "| Proof family | Instances |",
        "|---|---:|",
    ]
    report += [f"| `{family}` | {count} |" for family, count in sorted(family_counts.items())]
    report += ["", "## Hard API/Field Counts", "", "| API.field | Instances |", "|---|---:|"]
    for key, count in payload["api_field_counts"].items():
        if any(token in key for token in ["move_file", "update_note", "add_song_to_playlist", "create_playlist", "source_file_path", "note_id", "playlist_id"]):
            report.append(f"| `{key}` | {count} |")
    (output_dir / "PREFLIGHT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "fresh_tasks_used": len(fresh_rows), "target_instances": len(rows), "report": str((output_dir / "PREFLIGHT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()