"""Merge full-v8 row outputs with v10 path-pair override row outputs."""
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


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v8-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_full_opened_v8_executable/prompt_manifest.json"))
    parser.add_argument("--v8-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_full_opened_v8_executable/raw_model_outputs.json"))
    parser.add_argument("--v10-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v10_path_rule_normalized/prompt_manifest.json"))
    parser.add_argument("--v10-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v10_path_rule_normalized/raw_model_outputs.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_full_merged_outputs"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v10 full merged outputs")

    v8_prompt_path = resolve(args.v8_prompt_manifest)
    v8_raw_path = resolve(args.v8_raw_outputs)
    v10_prompt_path = resolve(args.v10_prompt_manifest)
    v10_raw_path = resolve(args.v10_raw_outputs)
    v8_prompt = load_json(v8_prompt_path)
    v8_raw = load_json(v8_raw_path)
    v10_prompt = load_json(v10_prompt_path)
    v10_raw = load_json(v10_raw_path)
    v10_rows_by_id = {row["instance_id"]: row for row in v10_prompt["rows"]}
    v10_raw_by_id = {row["instance_id"]: row for row in v10_raw["rows"]}
    if set(v10_rows_by_id) != set(v10_raw_by_id):
        raise RuntimeError("v10 prompt/raw ids differ")

    merged_rows = []
    merged_raw_rows = []
    source_counts: Counter[str] = Counter()
    raw_v8_by_id = {row["instance_id"]: row for row in v8_raw["rows"]}
    for row in v8_prompt["rows"]:
        instance_id = row["instance_id"]
        if instance_id in v10_rows_by_id:
            merged_rows.append(v10_rows_by_id[instance_id])
            merged_raw_rows.append(v10_raw_by_id[instance_id])
            source_counts["v10_path_pair_override"] += 1
        else:
            merged_rows.append(row)
            merged_raw_rows.append(raw_v8_by_id[instance_id])
            source_counts["v8_original"] += 1

    if len(merged_rows) != len(v8_prompt["rows"]):
        raise RuntimeError("merged prompt row count mismatch")
    if len(merged_raw_rows) != len(v8_raw["rows"]):
        raise RuntimeError("merged raw row count mismatch")
    if [row["instance_id"] for row in merged_rows] != [row["instance_id"] for row in merged_raw_rows]:
        raise RuntimeError("merged prompt/raw order mismatch")

    output_dir.mkdir(parents=True)
    prompt_manifest = {
        "schema": "ebw_track_a_prompt_manifest_v1",
        "status": "RPD_EBW_TRACK_A_V10_FULL_MERGED_PROMPT_MANIFEST_READY",
        "rows": merged_rows,
        "skipped_rows": [],
        "source_manifest_sha256": file_hash(v8_prompt_path),
        "override_prompt_manifest_sha256": file_hash(v10_prompt_path),
        "sealed_variations_opened": False,
        "prompt_protocol": "mixed_candidate_bound_v8_path_pair_v10",
        "merge_policy": "row_independent_greedy_outputs_v8_full_plus_v10_path_pair_overrides",
    }
    raw_outputs = {
        "schema": "ebw_track_a_raw_outputs_v1",
        "status": "RPD_EBW_TRACK_A_V10_FULL_MERGED_RAW_OUTPUTS_READY",
        "rows": merged_raw_rows,
        "source_counts": dict(sorted(source_counts.items())),
        "v8_raw_outputs_sha256": file_hash(v8_raw_path),
        "v10_raw_outputs_sha256": file_hash(v10_raw_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    prompt_path = output_dir / "prompt_manifest.json"
    raw_path = output_dir / "raw_model_outputs.json"
    write_json(prompt_path, prompt_manifest)
    write_json(raw_path, raw_outputs)
    payload = {
        "schema": "ebw_track_a_v10_full_merged_outputs_summary_v1",
        "status": "RPD_EBW_TRACK_A_V10_FULL_MERGED_OUTPUTS_READY",
        "rows": len(merged_rows),
        "source_counts": dict(sorted(source_counts.items())),
        "prompt_manifest_sha256": file_hash(prompt_path),
        "raw_outputs_sha256": file_hash(raw_path),
        "source_prompt_manifest_sha256": file_hash(v8_prompt_path),
        "override_prompt_manifest_sha256": file_hash(v10_prompt_path),
        "source_raw_outputs_sha256": file_hash(v8_raw_path),
        "override_raw_outputs_sha256": file_hash(v10_raw_path),
        "row_id_sequence_sha256": text_hash("\n".join(row["instance_id"] for row in merged_rows)),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "merge.json", payload)
    report = [
        "# EBW Track A v10 Full Merged Outputs",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(merged_rows)}",
        "- Merge policy: row-independent greedy outputs from full-v8 plus v10 path-pair overrides",
        "- Model/GPU/Docker/external process actions: No",
        "- Sealed variations 10-12 opened: No",
        "",
        "## Source Counts",
        "",
        "| Source | Rows |",
        "|---|---:|",
    ]
    report += [f"| `{key}` | {value} |" for key, value in sorted(source_counts.items())]
    report += [
        "",
        "## Interpretation",
        "",
        "Because each EBW row is generated independently with greedy decoding, this merge reuses already completed row-level model calls: unchanged rows come from the full-v8 executable run, and the diagnosed derived-path unsafe rows come from the v10 normalized path-pair target run. The follow-up CPU rescore is a compositional full-executable gate, not a new GPU full-run.",
    ]
    (output_dir / "MERGE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(merged_rows), "source_counts": payload["source_counts"], "report": str((output_dir / "MERGE.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()