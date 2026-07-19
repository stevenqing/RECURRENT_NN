"""Merge v29 frontier selection outputs with v29b targeted retry outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v29_frontier_closure_repair_policy import load_json, resolve, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_selection_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--base-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v29_frontier_selection/raw_model_outputs.json"))
    parser.add_argument("--retry-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v29b_frontier_selection_retry/raw_model_outputs.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29b_frontier_selection_merged_outputs"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v29b merged frontier selection outputs")

    base_prompt_path = resolve(args.base_prompt_manifest)
    base_raw_path = resolve(args.base_raw_outputs)
    retry_raw_path = resolve(args.retry_raw_outputs)
    base_prompt = load_json(base_prompt_path)
    base_raw = load_json(base_raw_path)
    retry_raw = load_json(retry_raw_path)
    retry_by_id = {row["residual_id"]: row for row in retry_raw["rows"]}
    base_by_id = {row["residual_id"]: row for row in base_raw["rows"]}
    merged_raw = []
    source_counts: Counter[str] = Counter()
    for row in base_prompt["rows"]:
        residual_id = row["residual_id"]
        if residual_id in retry_by_id:
            merged_raw.append(retry_by_id[residual_id])
            source_counts["v29b_retry"] += 1
        else:
            merged_raw.append(base_by_id[residual_id])
            source_counts["v29_base"] += 1

    output_dir.mkdir(parents=True)
    prompt_path = output_dir / "prompt_manifest.json"
    raw_path = output_dir / "raw_model_outputs.json"
    write_json(prompt_path, {**base_prompt, "status": "RPD_EBW_TRACK_A_V29B_FRONTIER_SELECTION_MERGED_PROMPT_MANIFEST_READY", "prompt_protocol": "mixed_v29_frontier_selection_v29b_retry"})
    write_json(
        raw_path,
        {
            "schema": "ebw_track_a_v29b_frontier_selection_merged_raw_outputs_v1",
            "status": "RPD_EBW_TRACK_A_V29B_FRONTIER_SELECTION_MERGED_RAW_OUTPUTS_READY",
            "rows": merged_raw,
            "source_counts": dict(sorted(source_counts.items())),
            "base_raw_outputs_sha256": file_hash(base_raw_path),
            "retry_raw_outputs_sha256": file_hash(retry_raw_path),
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v29b_frontier_selection_merged_outputs_summary_v1",
        "status": "RPD_EBW_TRACK_A_V29B_FRONTIER_SELECTION_MERGED_OUTPUTS_READY",
        "rows": len(merged_raw),
        "source_counts": dict(sorted(source_counts.items())),
        "prompt_manifest_sha256": file_hash(prompt_path),
        "raw_outputs_sha256": file_hash(raw_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "merge.json", payload)
    report = [
        "# EBW Track A v29b Frontier Selection Merged Outputs",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(merged_raw)}",
        "- Merge policy: v29 base frontier selections plus v29b targeted retry for failed residuals",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Source Counts",
        "",
        "| Source | Rows |",
        "|---|---:|",
    ]
    report += [f"| `{key}` | {value} |" for key, value in sorted(source_counts.items())]
    (output_dir / "MERGE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(merged_raw), "source_counts": payload["source_counts"], "report": str((output_dir / "MERGE.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()