"""Build v16b primitive-selection retry prompts for v16 compile failures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v16_primitive_selection_prompt_manifest import compact_library, prompt_text_from_messages
from analysis.ebw_track_a_v15_structured_repair_policy import blind_packet, primitive_library

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


def build_messages(packet: dict[str, Any], library: dict[str, Any], compile_error: str) -> list[dict[str, str]]:
    user_payload = {
        "task": "Retry primitive selection for a prior compile failure. Select primitive IDs only; do not write patch JSON.",
        "prior_compile_error": compile_error,
        "response_contract": [
            "Return exactly one JSON object and no markdown.",
            "Required keys exactly: residual_id, template_id, selected_primitives.",
            "residual_id must equal residual_packet.residual_id exactly.",
            "template_id must be one patch_templates[].id.",
            "selected_primitives must include one primitive for every required slot of the selected template.",
            "For response_contract templates, include both a response_contract primitive and parser_policy.strict.",
            "Do not omit parser_policy.strict when strict parsing should be preserved.",
        ],
        "selection_schema": {
            "required_keys": ["residual_id", "template_id", "selected_primitives"],
            "selected_primitives_type": "list[string]",
        },
        "primitive_library": compact_library(library),
        "residual_packet": packet,
    }
    return [
        {"role": "system", "content": "You are RepairAgent selecting verifier-safe repair primitives. Retry by covering every required slot."},
        {"role": "user", "content": json.dumps(user_payload, indent=2, sort_keys=True, ensure_ascii=False)},
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-packets", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v12_repairagent_metaverifier/repair_packets.json"))
    parser.add_argument("--v16-eval-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16_primitive_selection_model/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v16b_primitive_selection_retry_manifest"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v16b primitive-selection retry manifest")

    packets_by_id = {packet["residual_id"]: blind_packet(packet) for packet in load_json(args.repair_packets)["packets"]}
    failures = [row for row in load_json(args.v16_eval_rows)["rows"] if row.get("compile_error") or not row["metaverifier_result"].get("accepted")]
    library = primitive_library()
    response_prefill = "{"
    rows = []
    for failure in failures:
        packet = packets_by_id[failure["residual_id"]]
        messages = build_messages(packet, library, str(failure.get("compile_error") or failure["metaverifier_result"].get("reason")))
        prompt = prompt_text_from_messages(messages, response_prefill)
        rows.append(
            {
                "residual_id": packet["residual_id"],
                "residual_class": packet["residual_class"],
                "messages": messages,
                "messages_sha256": text_hash(json.dumps(messages, sort_keys=True, ensure_ascii=False)),
                "prompt": prompt,
                "prompt_sha256": text_hash(prompt),
                "response_prefill": response_prefill,
                "prompt_protocol": "chat_template_json_prefill_primitive_selection_retry_v16b",
                "source_failure_reason": str(failure.get("compile_error") or failure["metaverifier_result"].get("reason")),
            }
        )
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "prompt_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_v16b_primitive_selection_retry_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V16B_PRIMITIVE_SELECTION_RETRY_MANIFEST_READY",
            "rows": rows,
            "prompt_protocol": "chat_template_json_prefill_primitive_selection_retry_v16b",
            "source_eval_rows_sha256": file_hash(resolve(args.v16_eval_rows)),
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v16b_primitive_selection_retry_manifest_build_v1",
        "status": "RPD_EBW_TRACK_A_V16B_PRIMITIVE_SELECTION_RETRY_MANIFEST_READY",
        "rows": len(rows),
        "prompt_manifest_sha256": file_hash(manifest_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "manifest_build.json", payload)
    report = [
        "# EBW Track A v16b Primitive Selection Retry Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(rows)}",
        "- Prompt protocol: `chat_template_json_prefill_primitive_selection_retry_v16b`",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
    ]
    (output_dir / "PROMPT_MANIFEST.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(rows), "report": str((output_dir / "PROMPT_MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()