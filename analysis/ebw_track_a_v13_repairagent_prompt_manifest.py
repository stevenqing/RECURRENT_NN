"""Build CPU-only RepairAgent proposal prompts from v12 residual packets."""
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


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


PATCH_SCHEMAS = [
    {
        "patch_type": "frontier_grammar",
        "required_keys": ["proposal_id", "target_residual", "patch_type", "source_binding", "slug_transform", "destination_directory_rule_id", "extension", "parser_policy"],
        "allowed_parser_policy": "strict_json_no_regex_repair",
    },
    {
        "patch_type": "response_contract",
        "required_keys": ["proposal_id", "target_residual", "patch_type", "required_key", "forbidden_keys", "parser_policy"],
        "allowed_parser_policy": "strict_json_no_regex_repair",
    },
    {
        "patch_type": "parser_repair",
        "required_keys": ["proposal_id", "target_residual", "patch_type", "allow_key_alias", "parser_policy"],
    },
    {
        "patch_type": "prompt_only",
        "required_keys": ["proposal_id", "target_residual", "patch_type", "parser_policy"],
    },
]


def expected_patch(packet: dict[str, Any]) -> dict[str, Any]:
    if packet["residual_class"] == "title_slug_export_path_binding_missing":
        return {
            "proposal_id": "agent_title_slug_latest_show_note",
            "target_residual": packet["residual_class"],
            "patch_type": "frontier_grammar",
            "source_binding": "latest_matching_pre_write_show_note",
            "slug_transform": "whitespace_to_underscore",
            "destination_directory_rule_id": "task_literal_backup_directory",
            "extension": ".md",
            "parser_policy": "strict_json_no_regex_repair",
        }
    if packet["residual_class"] == "output_contract_obligation_key_leakage":
        return {
            "proposal_id": "agent_output_contract_obligation_key",
            "target_residual": packet["residual_class"],
            "patch_type": "response_contract",
            "required_key": "obligation",
            "forbidden_keys": ["required_obligation"],
            "parser_policy": "strict_json_no_regex_repair",
        }
    raise ValueError(packet["residual_class"])


def build_messages(packet: dict[str, Any]) -> list[dict[str, str]]:
    user_payload = {
        "task": "Propose exactly one patch JSON object for the residual packet.",
        "response_contract": [
            "Return exactly one JSON object and no markdown.",
            "The object must match one allowed_patch_schema exactly: no extra keys and no missing keys.",
            "Prefer proof-frontier or response-contract repairs. Do not propose parser relaxation unless the residual explicitly requires it.",
            "Use parser_policy=strict_json_no_regex_repair when preserving strict parsing.",
        ],
        "allowed_patch_schemas": PATCH_SCHEMAS,
        "residual_packet": packet,
    }
    return [
        {"role": "system", "content": "You are RepairAgent for proof-carrying AppWorld writes. Propose minimal verifier-safe patches from typed residuals."},
        {"role": "user", "content": json.dumps(user_payload, indent=2, sort_keys=True, ensure_ascii=False)},
    ]


def prompt_text_from_messages(messages: list[dict[str, str]], response_prefill: str) -> str:
    parts = [f"[{message['role'].upper()}]\n{message['content']}" for message in messages]
    parts.append(f"[ASSISTANT]\n{response_prefill}")
    return "\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-packets", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v12_repairagent_metaverifier/repair_packets.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v13_repairagent_prompt_manifest"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v13 RepairAgent prompt manifest")

    packets_path = resolve(args.repair_packets)
    packets = load_json(packets_path)["packets"]
    rows = []
    response_prefill = "{"
    for packet in packets:
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
                "prompt_protocol": "chat_template_json_prefill_repairagent_v13",
                "expected_patch": expected_patch(packet),
            }
        )

    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "prompt_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_v13_repairagent_prompt_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V13_REPAIRAGENT_PROMPT_MANIFEST_READY",
            "rows": rows,
            "prompt_protocol": "chat_template_json_prefill_repairagent_v13",
            "repair_packets_sha256": file_hash(packets_path),
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v13_repairagent_prompt_manifest_build_v1",
        "status": "RPD_EBW_TRACK_A_V13_REPAIRAGENT_PROMPT_MANIFEST_READY",
        "rows": len(rows),
        "prompt_manifest_sha256": file_hash(manifest_path),
        "repair_packets_sha256": file_hash(packets_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "manifest_build.json", payload)
    report = [
        "# EBW Track A v13 RepairAgent Prompt Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(rows)}",
        "- Prompt protocol: `chat_template_json_prefill_repairagent_v13`",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
    ]
    (output_dir / "PROMPT_MANIFEST.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(rows), "report": str((output_dir / "PROMPT_MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()