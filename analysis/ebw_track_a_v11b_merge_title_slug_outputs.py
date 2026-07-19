"""Merge v11 title-slug outputs with v11b contract retry outputs."""
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
    parser.add_argument("--v11-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v11_title_slug_target/prompt_manifest.json"))
    parser.add_argument("--v11-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11_title_slug_target/raw_model_outputs.json"))
    parser.add_argument("--v11b-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v11b_contract_retry/prompt_manifest.json"))
    parser.add_argument("--v11b-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11b_contract_retry/raw_model_outputs.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11b_title_slug_merged_outputs"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v11b title-slug merged outputs")

    v11_prompt_path = resolve(args.v11_prompt_manifest)
    v11_raw_path = resolve(args.v11_raw_outputs)
    v11b_prompt_path = resolve(args.v11b_prompt_manifest)
    v11b_raw_path = resolve(args.v11b_raw_outputs)
    v11_prompt = load_json(v11_prompt_path)
    v11_raw = load_json(v11_raw_path)
    v11b_prompt = load_json(v11b_prompt_path)
    v11b_raw = load_json(v11b_raw_path)
    retry_rows_by_id = {row["instance_id"]: row for row in v11b_prompt["rows"]}
    retry_raw_by_id = {row["instance_id"]: row for row in v11b_raw["rows"]}
    merged_rows = []
    merged_raw = []
    source_counts: Counter[str] = Counter()
    v11_raw_by_id = {row["instance_id"]: row for row in v11_raw["rows"]}
    for row in v11_prompt["rows"]:
        instance_id = row["instance_id"]
        if instance_id in retry_rows_by_id:
            merged_rows.append(retry_rows_by_id[instance_id])
            merged_raw.append(retry_raw_by_id[instance_id])
            source_counts["v11b_contract_retry"] += 1
        else:
            merged_rows.append(row)
            merged_raw.append(v11_raw_by_id[instance_id])
            source_counts["v11_original"] += 1
    if [row["instance_id"] for row in merged_rows] != [row["instance_id"] for row in merged_raw]:
        raise RuntimeError("merged prompt/raw order mismatch")

    output_dir.mkdir(parents=True)
    prompt_path = output_dir / "prompt_manifest.json"
    raw_path = output_dir / "raw_model_outputs.json"
    write_json(
        prompt_path,
        {
            "schema": "ebw_track_a_prompt_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V11B_TITLE_SLUG_MERGED_PROMPT_MANIFEST_READY",
            "rows": merged_rows,
            "skipped_rows": [],
            "source_manifest_sha256": file_hash(v11_prompt_path),
            "retry_manifest_sha256": file_hash(v11b_prompt_path),
            "prompt_protocol": "mixed_title_slug_v11_v11b_contract_retry",
            "merge_policy": "v11_original_plus_v11b_contract_retry_failures",
            "sealed_variations_opened": False,
        },
    )
    write_json(
        raw_path,
        {
            "schema": "ebw_track_a_raw_outputs_v1",
            "status": "RPD_EBW_TRACK_A_V11B_TITLE_SLUG_MERGED_RAW_OUTPUTS_READY",
            "rows": merged_raw,
            "source_counts": dict(sorted(source_counts.items())),
            "v11_raw_outputs_sha256": file_hash(v11_raw_path),
            "v11b_raw_outputs_sha256": file_hash(v11b_raw_path),
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v11b_title_slug_merged_outputs_summary_v1",
        "status": "RPD_EBW_TRACK_A_V11B_TITLE_SLUG_MERGED_OUTPUTS_READY",
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
        "# EBW Track A v11b Title-Slug Merged Outputs",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(merged_rows)}",
        "- Merge policy: v11 original outputs plus v11b contract retry failures",
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