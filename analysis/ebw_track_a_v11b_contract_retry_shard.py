"""Build a v11b retry shard for v11 title-slug strict parse/contract failures."""
from __future__ import annotations

import argparse
import hashlib
import json
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
    parser.add_argument("--source-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v11_title_slug_target/prompt_manifest.json"))
    parser.add_argument("--source-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11_title_slug_target/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11b_contract_retry_shard"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v11b contract retry shard")

    manifest_path = resolve(args.source_manifest)
    rows_path = resolve(args.source_rows)
    manifest = {row["instance_id"]: row for row in load_json(manifest_path)["rows"]}
    source_rows = load_json(rows_path)["rows"]
    selected = []
    for result in source_rows:
        if result["decision"] == "commit_live":
            continue
        row = manifest[result["instance_id"]]
        action = row["context"]["candidate_action"]
        selected.append(
            {
                "instance_id": row["instance_id"],
                "task_id": row["task_id"],
                "call_index": row["call_index"],
                "field_name": row["field_name"],
                "proof_family": row["proof_family"],
                "method": action["method"],
                "app": action["app"],
                "api_name": action["api_name"],
                "required_obligation": "title_slug_export_path_binding",
                "write_ordinal_for_schema": row["write_ordinal_for_schema"],
                "source_decision": result["decision"],
            }
        )

    output_dir.mkdir(parents=True)
    evaluation_manifest = output_dir / "evaluation_manifest.json"
    write_json(
        evaluation_manifest,
        {
            "schema": "ebw_track_a_v11b_contract_retry_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V11B_CONTRACT_RETRY_SHARD_READY",
            "rows": selected,
            "target_selection": "v11 title-slug strict parse/contract failures only",
            "sealed_variations_opened": False,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v11b_contract_retry_shard_v1",
        "status": "RPD_EBW_TRACK_A_V11B_CONTRACT_RETRY_SHARD_READY",
        "rows": len(selected),
        "source_manifest_sha256": file_hash(manifest_path),
        "source_rows_sha256": file_hash(rows_path),
        "evaluation_manifest_sha256": file_hash(evaluation_manifest),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "shard.json", payload)
    report = [
        "# EBW Track A v11b Contract Retry Shard",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(selected)}",
        "- Target: v11 title-slug strict parse/contract failures only",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
    ]
    (output_dir / "SHARD.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(selected), "report": str((output_dir / "SHARD.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()