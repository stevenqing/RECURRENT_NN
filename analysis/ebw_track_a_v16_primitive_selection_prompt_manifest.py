"""Build v16 primitive-selection prompts for RepairAgent."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v15_structured_repair_policy import blind_packet, primitive_library, select_structured_patch

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


def prompt_text_from_messages(messages: list[dict[str, str]], response_prefill: str) -> str:
    parts = [f"[{message['role'].upper()}]\n{message['content']}" for message in messages]
    parts.append(f"[ASSISTANT]\n{response_prefill}")
    return "\n\n".join(parts)


def compact_library(library: dict[str, Any]) -> dict[str, Any]:
    return {
        "patch_templates": library["patch_templates"],
        "primitive_groups": {
            key: values
            for key, values in library.items()
            if key not in {"schema", "patch_templates"}
        },
    }


def expected_selection(packet: dict[str, Any]) -> dict[str, Any]:
    selected = select_structured_patch(packet)
    return {
        "residual_id": selected["residual_id"],
        "template_id": selected["template_id"],
        "selected_primitives": selected["selected_primitives"],
    }


def build_messages(packet: dict[str, Any], library: dict[str, Any]) -> list[dict[str, str]]:
    user_payload = {
        "task": "Select primitive IDs for a deterministic RepairAgent compiler. Do not write patch JSON.",
        "response_contract": [
            "Return exactly one JSON object and no markdown.",
            "Required keys exactly: residual_id, template_id, selected_primitives.",
            "residual_id must equal residual_packet.residual_id exactly.",
            "template_id must be one patch_templates[].id.",
            "selected_primitives must be a list of primitive ids from primitive_groups.",
            "Choose primitives that address the residual counterexample while preserving strict parser policy.",
        ],
        "selection_schema": {
            "required_keys": ["residual_id", "template_id", "selected_primitives"],
            "selected_primitives_type": "list[string]",
        },
        "primitive_library": compact_library(library),
        "residual_packet": packet,
    }
    return [
        {"role": "system", "content": "You are RepairAgent selecting verifier-safe repair primitives. Select IDs only; a deterministic compiler will build patch JSON."},
        {"role": "user", "content": json.dumps(user_payload, indent=2, sort_keys=True, ensure_ascii=False)},
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-packets", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v12_repairagent_metaverifier/repair_packets.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v16_primitive_selection_prompt_manifest"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v16 primitive-selection prompt manifest")

    packets_path = resolve(args.repair_packets)
    packets = [blind_packet(packet) for packet in load_json(packets_path)["packets"]]
    library = primitive_library()
    rows = []
    response_prefill = "{"
    for packet in packets:
        messages = build_messages(packet, library)
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
                "prompt_protocol": "chat_template_json_prefill_primitive_selection_v16",
                "expected_selection": expected_selection(packet),
            }
        )
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "prompt_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_v16_primitive_selection_prompt_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V16_PRIMITIVE_SELECTION_PROMPT_MANIFEST_READY",
            "rows": rows,
            "prompt_protocol": "chat_template_json_prefill_primitive_selection_v16",
            "repair_packets_sha256": file_hash(packets_path),
            "answer_blinded": True,
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    write_json(output_dir / "primitive_library.json", library)
    payload = {
        "schema": "ebw_track_a_v16_primitive_selection_prompt_manifest_build_v1",
        "status": "RPD_EBW_TRACK_A_V16_PRIMITIVE_SELECTION_PROMPT_MANIFEST_READY",
        "rows": len(rows),
        "prompt_manifest_sha256": file_hash(manifest_path),
        "repair_packets_sha256": file_hash(packets_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "manifest_build.json", payload)
    report = [
        "# EBW Track A v16 Primitive Selection Prompt Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(rows)}",
        "- Prompt protocol: `chat_template_json_prefill_primitive_selection_v16`",
        "- Answer-blinded: Yes",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
    ]
    (output_dir / "PROMPT_MANIFEST.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(rows), "report": str((output_dir / "PROMPT_MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()