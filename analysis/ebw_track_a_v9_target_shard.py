"""Build the v9 target shard: full-v8 derived unsafe rows covered by path-pair candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v9_path_pair_feasibility import path_pair_candidate

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
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_full_opened_v8_executable/prompt_manifest.json"))
    parser.add_argument("--rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_full_opened_v8_executable/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_target_shard"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v9 target shard")

    manifest_path = resolve(args.prompt_manifest)
    rows_path = resolve(args.rows)
    manifest = load_json(manifest_path)["rows"]
    row_results = {row["instance_id"]: row for row in load_json(rows_path)["rows"]}
    selected = []
    for row in manifest:
        if row.get("required_obligation") != "derived_path_binding":
            continue
        result = row_results.get(row["instance_id"], {})
        candidate = path_pair_candidate(row)
        if result.get("decision") == "unsafe_unique_wrong" and candidate is not None and candidate["match"]:
            selected.append(
                {
                    "instance_id": row["instance_id"],
                    "task_id": row["task_id"],
                    "call_index": row["call_index"],
                    "field_name": row["field_name"],
                    "proof_family": row["proof_family"],
                    "method": row["context"]["candidate_action"]["method"],
                    "app": row["context"]["candidate_action"]["app"],
                    "api_name": row["context"]["candidate_action"]["api_name"],
                    "required_obligation": "path_pair_transform_binding",
                    "write_ordinal_for_schema": row["write_ordinal_for_schema"],
                    "source_decision": result.get("decision"),
                }
            )
    output_dir.mkdir(parents=True)
    shard_path = output_dir / "evaluation_manifest.json"
    write_json(
        shard_path,
        {
            "schema": "ebw_track_a_v9_target_shard_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V9_TARGET_SHARD_READY",
            "rows": selected,
            "target_selection": "full-v8 derived unsafe rows with matching v9 path-pair candidate",
            "sealed_variations_opened": False,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v9_target_shard_v1",
        "status": "RPD_EBW_TRACK_A_V9_TARGET_SHARD_READY",
        "rows": len(selected),
        "source_prompt_manifest_sha256": file_hash(manifest_path),
        "source_rows_sha256": file_hash(rows_path),
        "evaluation_manifest_sha256": file_hash(shard_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "shard.json", payload)
    report = [
        "# EBW Track A v9 Target Shard",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(selected)}",
        "- Target: full-v8 derived unsafe rows with matching v9 path-pair candidate",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
    ]
    (output_dir / "SHARD.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(selected), "report": str((output_dir / "SHARD.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()