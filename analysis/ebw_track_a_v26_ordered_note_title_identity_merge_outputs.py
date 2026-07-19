"""Merge v24 outputs with deterministic ordered note title identity proofs."""
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


def sketch_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "obligation": "ordered_note_title_identity_binding",
        "source_read_id": candidate["source_read_id"],
        "note_id_field": candidate["note_id_field"],
        "title_field": candidate["title_field"],
        "content_field": candidate["content_field"],
        "task_item_span": candidate["task_item_span"],
        "target_arg": candidate["target_arg"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v24_literal_export_path_merged_outputs/prompt_manifest.json"))
    parser.add_argument("--base-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v24_literal_export_path_merged_outputs/raw_model_outputs.json"))
    parser.add_argument("--ordered-note-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v25_ordered_note_title_identity_feasibility/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v26_ordered_note_title_identity_merged_outputs"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v26 ordered note title identity merged outputs")

    base_prompt_path = resolve(args.base_prompt_manifest)
    base_raw_path = resolve(args.base_raw_outputs)
    ordered_rows_path = resolve(args.ordered_note_rows)
    base_prompt = load_json(base_prompt_path)
    base_raw = load_json(base_raw_path)
    ordered_rows = load_json(ordered_rows_path)
    repairs_by_id = {
        row["instance_id"]: row["candidate"]
        for row in ordered_rows["rows"]
        if row["decision"] == "commit_live" and row.get("candidate") is not None
    }
    base_raw_by_id = {row["instance_id"]: row for row in base_raw["rows"]}
    merged_prompt_rows = []
    merged_raw_rows = []
    source_counts: Counter[str] = Counter()
    for row in base_prompt["rows"]:
        instance_id = row["instance_id"]
        if instance_id in repairs_by_id:
            candidate = repairs_by_id[instance_id]
            sketch = sketch_from_candidate(candidate)
            merged_row = dict(row)
            merged_row["required_obligation"] = "ordered_note_title_identity_binding"
            merged_row["ordered_note_title_identity_candidates"] = [candidate]
            merged_prompt_rows.append(merged_row)
            merged_raw_rows.append(
                {
                    "instance_id": instance_id,
                    "output": json.dumps(sketch, indent=2, sort_keys=True),
                    "parse_ok": True,
                    "prompt_mode": "deterministic_ordered_note_title_identity_v26",
                }
            )
            source_counts["v26_ordered_note_title_identity_deterministic"] += 1
        else:
            merged_prompt_rows.append(row)
            merged_raw_rows.append(base_raw_by_id[instance_id])
            source_counts["v24_literal_export_base"] += 1
    if [row["instance_id"] for row in merged_prompt_rows] != [row["instance_id"] for row in merged_raw_rows]:
        raise RuntimeError("merged prompt/raw order mismatch")

    output_dir.mkdir(parents=True)
    prompt_path = output_dir / "prompt_manifest.json"
    raw_path = output_dir / "raw_model_outputs.json"
    write_json(
        prompt_path,
        {
            "schema": "ebw_track_a_prompt_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V26_ORDERED_NOTE_TITLE_IDENTITY_MERGED_PROMPT_MANIFEST_READY",
            "rows": merged_prompt_rows,
            "skipped_rows": [],
            "prompt_protocol": "mixed_v24_literal_export_ordered_note_title_identity_deterministic_v26",
            "merge_policy": "v24_literal_export_compositional_outputs_plus_v26_deterministic_ordered_note_title_identity_proofs",
            "sealed_variations_opened": False,
        },
    )
    write_json(
        raw_path,
        {
            "schema": "ebw_track_a_raw_outputs_v1",
            "status": "RPD_EBW_TRACK_A_V26_ORDERED_NOTE_TITLE_IDENTITY_MERGED_RAW_OUTPUTS_READY",
            "rows": merged_raw_rows,
            "source_counts": dict(sorted(source_counts.items())),
            "base_raw_outputs_sha256": file_hash(base_raw_path),
            "ordered_note_rows_sha256": file_hash(ordered_rows_path),
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v26_ordered_note_title_identity_merged_outputs_summary_v1",
        "status": "RPD_EBW_TRACK_A_V26_ORDERED_NOTE_TITLE_IDENTITY_MERGED_OUTPUTS_READY",
        "rows": len(merged_prompt_rows),
        "source_counts": dict(sorted(source_counts.items())),
        "prompt_manifest_sha256": file_hash(prompt_path),
        "raw_outputs_sha256": file_hash(raw_path),
        "base_prompt_manifest_sha256": file_hash(base_prompt_path),
        "base_raw_outputs_sha256": file_hash(base_raw_path),
        "ordered_note_rows_sha256": file_hash(ordered_rows_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "merge.json", payload)
    report = [
        "# EBW Track A v26 Ordered Note Title Identity Merged Outputs",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(merged_prompt_rows)}",
        "- Merge policy: v24 literal export compositional outputs plus deterministic v26 ordered note title identity proofs",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
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
        "This merge is deterministic, not a Qwen synthesis result. It replaces only the two ordered-note residual rows that passed the v25 CPU proof gate, allowing the new strict ordered-note schema and verifier path to be tested by a full executable compositional rescore.",
    ]
    (output_dir / "MERGE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(merged_prompt_rows), "source_counts": payload["source_counts"], "report": str((output_dir / "MERGE.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()