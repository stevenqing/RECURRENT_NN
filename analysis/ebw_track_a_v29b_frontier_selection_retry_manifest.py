"""Build a targeted retry manifest for failed v29 frontier primitive selections."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v29_frontier_closure_repair_policy import load_json, resolve, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def retry_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    updated = [dict(message) for message in messages]
    updated.append(
        {
            "role": "user",
            "content": "Retry the same residual. Use exact primitive IDs from primitive_library only. The valid strict parser primitive ID is parser_policy.strict, not parser_policy.strict_json_no_regex_repair. Return exactly one JSON object.",
        }
    )
    return updated


def prompt_text_from_messages(messages: list[dict[str, str]], response_prefill: str) -> str:
    parts = [f"[{message['role'].upper()}]\n{message['content']}" for message in messages]
    parts.append(f"[ASSISTANT]\n{response_prefill}")
    return "\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_selection_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--eval-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29_frontier_selection_model/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29b_frontier_selection_retry_manifest"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v29b retry manifest")

    base_manifest_path = resolve(args.base_prompt_manifest)
    eval_rows_path = resolve(args.eval_rows)
    manifest = load_json(base_manifest_path)
    eval_rows = load_json(eval_rows_path)["rows"]
    failed_ids = {row["residual_id"] for row in eval_rows if not row["metaverifier_result"]["accepted"]}
    rows = []
    for row in manifest["rows"]:
        if row["residual_id"] not in failed_ids:
            continue
        messages = retry_messages(row["messages"])
        response_prefill = row.get("response_prefill", "{")
        prompt = prompt_text_from_messages(messages, response_prefill)
        retry_row = dict(row)
        retry_row["messages"] = messages
        retry_row["messages_sha256"] = text_hash(json.dumps(messages, sort_keys=True, ensure_ascii=False))
        retry_row["prompt"] = prompt
        retry_row["prompt_sha256"] = text_hash(prompt)
        retry_row["prompt_protocol"] = "chat_template_json_prefill_frontier_selection_v29b_retry"
        rows.append(retry_row)

    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "prompt_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_v29b_frontier_selection_retry_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V29B_FRONTIER_SELECTION_RETRY_MANIFEST_READY",
            "rows": rows,
            "prompt_protocol": "chat_template_json_prefill_frontier_selection_v29b_retry",
            "retry_selection": "failed v29 model frontier primitive selections only",
            "base_prompt_manifest_sha256": file_hash(base_manifest_path),
            "eval_rows_sha256": file_hash(eval_rows_path),
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v29b_frontier_selection_retry_manifest_build_v1",
        "status": "RPD_EBW_TRACK_A_V29B_FRONTIER_SELECTION_RETRY_MANIFEST_READY",
        "rows": len(rows),
        "failed_ids": sorted(failed_ids),
        "prompt_manifest_sha256": file_hash(manifest_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "manifest_build.json", payload)
    report = [
        "# EBW Track A v29b Frontier Selection Retry Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(rows)}",
        f"- Failed IDs: `{', '.join(sorted(failed_ids))}`",
        "- Prompt protocol: `chat_template_json_prefill_frontier_selection_v29b_retry`",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
    ]
    (output_dir / "PROMPT_MANIFEST.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(rows), "failed_ids": payload["failed_ids"], "report": str((output_dir / "PROMPT_MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()