"""Build held-out free-form RepairAgent patch prompts for v33 residual packets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

PATCH_SCHEMAS = [
    {
        "patch_type": "frontier_candidate",
        "target_residual": "literal_export_path_binding_missing",
        "required_keys": ["proposal_id", "target_residual", "patch_type", "span_source", "target_arg", "parser_policy"],
        "allowed_parser_policy": "strict_json_no_regex_repair",
    },
    {
        "patch_type": "parser_repair",
        "required_keys": ["proposal_id", "target_residual", "patch_type", "allow_key_alias", "parser_policy"],
        "negative_control": True,
    },
    {
        "patch_type": "prompt_only",
        "required_keys": ["proposal_id", "target_residual", "patch_type", "parser_policy"],
        "negative_control": True,
    },
]


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


def blind_packet(packet: dict[str, Any]) -> dict[str, Any]:
    allowed = {"residual_id", "residual_class", "typed_reason", "target_rows", "counterexample_summary", "failed_frontier"}
    return {key: packet[key] for key in packet if key in allowed}


def build_messages(packet: dict[str, Any]) -> list[dict[str, str]]:
    user_payload = {
        "task": "Propose exactly one patch JSON object for this held-out typed residual. Do not select primitive IDs; write patch JSON directly.",
        "response_contract": [
            "Return exactly one JSON object and no markdown.",
            "The object must match one allowed_patch_schema exactly: no extra keys and no missing keys.",
            "target_residual must equal residual_packet.residual_class exactly.",
            "Preserve strict parser policy when a proof-frontier repair is possible.",
            "Do not propose prompt_only or parser relaxation for proof-frontier residuals.",
        ],
        "allowed_patch_schemas": PATCH_SCHEMAS,
        "residual_packet": blind_packet(packet),
    }
    return [
        {"role": "system", "content": "You are RepairAgent for proof-carrying AppWorld writes. Infer minimal verifier-safe patch JSON from held-out typed residuals."},
        {"role": "user", "content": json.dumps(user_payload, indent=2, sort_keys=True, ensure_ascii=False)},
    ]


def prompt_text_from_messages(messages: list[dict[str, str]], response_prefill: str) -> str:
    parts = [f"[{message['role'].upper()}]\n{message['content']}" for message in messages]
    parts.append(f"[ASSISTANT]\n{response_prefill}")
    return "\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ttc-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v33_heldout_ttc_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v35_heldout_freeform_repair_prompt_manifest"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v35 held-out free-form RepairAgent prompt manifest")

    source_path = resolve(args.ttc_prompt_manifest)
    source = load_json(source_path)
    response_prefill = "{"
    rows = []
    for packet in source["repair_packets"]:
        messages = build_messages(packet)
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
                "prompt_protocol": "chat_template_json_prefill_heldout_freeform_repair_v35",
            }
        )
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "prompt_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_v35_heldout_freeform_repair_prompt_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V35_HELDOUT_FREEFORM_REPAIR_PROMPT_MANIFEST_READY",
            "rows": rows,
            "repair_packets": source["repair_packets"],
            "prompt_protocol": "chat_template_json_prefill_heldout_freeform_repair_v35",
            "source_ttc_prompt_manifest_sha256": file_hash(source_path),
            "sealed_variations_opened": bool(source.get("sealed_variations_opened", False)),
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v35_heldout_freeform_repair_prompt_manifest_build_v1",
        "status": "RPD_EBW_TRACK_A_V35_HELDOUT_FREEFORM_REPAIR_PROMPT_MANIFEST_READY",
        "rows": len(rows),
        "prompt_manifest_sha256": file_hash(manifest_path),
        "sealed_variations_opened": bool(source.get("sealed_variations_opened", False)),
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "manifest_build.json", payload)
    report = [
        "# EBW Track A v35 Held-Out Free-Form Repair Prompt Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(rows)}",
        "- Prompt protocol: `chat_template_json_prefill_heldout_freeform_repair_v35`",
        "- Repair mode: free-form patch JSON",
        "- Sealed variations 10-12 opened: Yes",
        "- Model/GPU/Docker actions: No",
    ]
    (output_dir / "PROMPT_MANIFEST.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(rows), "report": str((output_dir / "PROMPT_MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()