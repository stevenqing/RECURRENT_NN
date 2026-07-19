"""Merge v11b full executable outputs with v17 archive-path repaired outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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
    parser.add_argument("--base-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11b_full_merged_outputs/prompt_manifest.json"))
    parser.add_argument("--base-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11b_full_merged_outputs/raw_model_outputs.json"))
    parser.add_argument("--archive-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v17_archive_path_target/prompt_manifest.json"))
    parser.add_argument("--archive-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v17_archive_path_target/raw_model_outputs.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v17_full_merged_outputs"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v17 full merged outputs")

    base_prompt_path = resolve(args.base_prompt_manifest)
    base_raw_path = resolve(args.base_raw_outputs)
    archive_prompt_path = resolve(args.archive_prompt_manifest)
    archive_raw_path = resolve(args.archive_raw_outputs)
    base_prompt = load_json(base_prompt_path)
    base_raw = load_json(base_raw_path)
    archive_prompt = load_json(archive_prompt_path)
    archive_raw = load_json(archive_raw_path)
    archive_rows_by_id = {row["instance_id"]: row for row in archive_prompt["rows"]}
    archive_raw_by_id = {row["instance_id"]: row for row in archive_raw["rows"]}
    base_raw_by_id = {row["instance_id"]: row for row in base_raw["rows"]}
    merged_rows = []
    merged_raw = []
    source_counts: Counter[str] = Counter()
    for row in base_prompt["rows"]:
        instance_id = row["instance_id"]
        if instance_id in archive_rows_by_id:
            merged_rows.append(archive_rows_by_id[instance_id])
            merged_raw.append(archive_raw_by_id[instance_id])
            source_counts["v17_archive_path_repair"] += 1
        else:
            merged_rows.append(row)
            merged_raw.append(base_raw_by_id[instance_id])
            source_counts["v11b_full_base"] += 1
    if [row["instance_id"] for row in merged_rows] != [row["instance_id"] for row in merged_raw]:
        raise RuntimeError("merged prompt/raw order mismatch")

    output_dir.mkdir(parents=True)
    prompt_path = output_dir / "prompt_manifest.json"
    raw_path = output_dir / "raw_model_outputs.json"
    write_json(
        prompt_path,
        {
            "schema": "ebw_track_a_prompt_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V17_FULL_MERGED_PROMPT_MANIFEST_READY",
            "rows": merged_rows,
            "skipped_rows": [],
            "prompt_protocol": "mixed_v11b_full_archive_path_v17",
            "merge_policy": "v11b_full_compositional_outputs_plus_v17_archive_path_repair",
            "sealed_variations_opened": False,
        },
    )
    write_json(
        raw_path,
        {
            "schema": "ebw_track_a_raw_outputs_v1",
            "status": "RPD_EBW_TRACK_A_V17_FULL_MERGED_RAW_OUTPUTS_READY",
            "rows": merged_raw,
            "source_counts": dict(sorted(source_counts.items())),
            "base_raw_outputs_sha256": file_hash(base_raw_path),
            "archive_raw_outputs_sha256": file_hash(archive_raw_path),
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v17_full_merged_outputs_summary_v1",
        "status": "RPD_EBW_TRACK_A_V17_FULL_MERGED_OUTPUTS_READY",
        "rows": len(merged_rows),
        "source_counts": dict(sorted(source_counts.items())),
        "prompt_manifest_sha256": file_hash(prompt_path),
        "raw_outputs_sha256": file_hash(raw_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "merge.json", payload)
    report = [
        "# EBW Track A v17 Full Merged Outputs",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(merged_rows)}",
        "- Merge policy: v11b full compositional outputs plus v17 archive-path repair",
        "- Sealed variations 10-12 opened: No",
        "",
        "## Source Counts",
        "",
        "| Source | Rows |",
        "|---|---:|",
    ]
    report += [f"| `{key}` | {value} |" for key, value in sorted(source_counts.items())]
    (output_dir / "MERGE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(merged_rows), "source_counts": payload["source_counts"], "report": str((output_dir / "MERGE.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()