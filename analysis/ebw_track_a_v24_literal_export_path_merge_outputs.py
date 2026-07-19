"""Merge v22 outputs with deterministic literal export path proofs."""
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
        "obligation": "literal_intent_binding",
        "user_span": candidate["user_span"],
        "target_arg": candidate["target_arg"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v22_source_path_identity_merged_outputs/prompt_manifest.json"))
    parser.add_argument("--base-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v22_source_path_identity_merged_outputs/raw_model_outputs.json"))
    parser.add_argument("--literal-export-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v23_literal_export_path_feasibility/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v24_literal_export_path_merged_outputs"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v24 literal export path merged outputs")

    base_prompt_path = resolve(args.base_prompt_manifest)
    base_raw_path = resolve(args.base_raw_outputs)
    literal_rows_path = resolve(args.literal_export_rows)
    base_prompt = load_json(base_prompt_path)
    base_raw = load_json(base_raw_path)
    literal_rows = load_json(literal_rows_path)
    repairs_by_id = {
        row["instance_id"]: row["candidate"]
        for row in literal_rows["rows"]
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
            merged_row["required_obligation"] = "literal_intent_binding"
            merged_row["required_literal_span"] = candidate["user_span"]
            merged_prompt_rows.append(merged_row)
            merged_raw_rows.append(
                {
                    "instance_id": instance_id,
                    "output": json.dumps(sketch, indent=2, sort_keys=True),
                    "parse_ok": True,
                    "prompt_mode": "deterministic_literal_export_path_v24",
                }
            )
            source_counts["v24_literal_export_path_deterministic"] += 1
        else:
            merged_prompt_rows.append(row)
            merged_raw_rows.append(base_raw_by_id[instance_id])
            source_counts["v22_source_identity_base"] += 1
    if [row["instance_id"] for row in merged_prompt_rows] != [row["instance_id"] for row in merged_raw_rows]:
        raise RuntimeError("merged prompt/raw order mismatch")

    output_dir.mkdir(parents=True)
    prompt_path = output_dir / "prompt_manifest.json"
    raw_path = output_dir / "raw_model_outputs.json"
    write_json(
        prompt_path,
        {
            "schema": "ebw_track_a_prompt_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V24_LITERAL_EXPORT_PATH_MERGED_PROMPT_MANIFEST_READY",
            "rows": merged_prompt_rows,
            "skipped_rows": [],
            "prompt_protocol": "mixed_v22_source_identity_literal_export_path_deterministic_v24",
            "merge_policy": "v22_source_identity_compositional_outputs_plus_v24_deterministic_literal_export_path_proofs",
            "sealed_variations_opened": False,
        },
    )
    write_json(
        raw_path,
        {
            "schema": "ebw_track_a_raw_outputs_v1",
            "status": "RPD_EBW_TRACK_A_V24_LITERAL_EXPORT_PATH_MERGED_RAW_OUTPUTS_READY",
            "rows": merged_raw_rows,
            "source_counts": dict(sorted(source_counts.items())),
            "base_raw_outputs_sha256": file_hash(base_raw_path),
            "literal_export_rows_sha256": file_hash(literal_rows_path),
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v24_literal_export_path_merged_outputs_summary_v1",
        "status": "RPD_EBW_TRACK_A_V24_LITERAL_EXPORT_PATH_MERGED_OUTPUTS_READY",
        "rows": len(merged_prompt_rows),
        "source_counts": dict(sorted(source_counts.items())),
        "prompt_manifest_sha256": file_hash(prompt_path),
        "raw_outputs_sha256": file_hash(raw_path),
        "base_prompt_manifest_sha256": file_hash(base_prompt_path),
        "base_raw_outputs_sha256": file_hash(base_raw_path),
        "literal_export_rows_sha256": file_hash(literal_rows_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "merge.json", payload)
    report = [
        "# EBW Track A v24 Literal Export Path Merged Outputs",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(merged_prompt_rows)}",
        "- Merge policy: v22 source-path identity compositional outputs plus deterministic v24 literal export path proofs",
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
        "This merge is deterministic, not a Qwen synthesis result. It replaces only the two literal export path residual rows that passed the v23 CPU proof gate, allowing the existing strict literal-intent parser and verifier path to be tested by a full executable compositional rescore.",
    ]
    (output_dir / "MERGE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(merged_prompt_rows), "source_counts": payload["source_counts"], "report": str((output_dir / "MERGE.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()