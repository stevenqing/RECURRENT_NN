"""Build v29 primitive-selection prompts for frontier closure residuals."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v16_primitive_selection_prompt_manifest import compact_library, prompt_text_from_messages
from analysis.ebw_track_a_v29_frontier_closure_repair_policy import load_json, resolve, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def blind_packet(packet: dict[str, Any]) -> dict[str, Any]:
    allowed = {"residual_id", "residual_class", "typed_reason", "target_rows", "counterexample_summary", "failed_frontier"}
    return {key: packet[key] for key in packet if key in allowed}


def build_messages(packet: dict[str, Any], library: dict[str, Any]) -> list[dict[str, str]]:
    user_payload = {
        "task": "Select primitive IDs for a deterministic RepairAgent compiler. Do not write patch JSON.",
        "response_contract": [
            "Return exactly one JSON object and no markdown.",
            "Required keys exactly: residual_id, template_id, selected_primitives.",
            "residual_id must equal residual_packet.residual_id exactly.",
            "template_id must be one patch_templates[].id.",
            "selected_primitives must include one primitive for every required slot of the selected template.",
            "Choose primitives that address the residual counterexample while preserving strict parser policy.",
        ],
        "selection_schema": {"required_keys": ["residual_id", "template_id", "selected_primitives"], "selected_primitives_type": "list[string]"},
        "primitive_library": compact_library(library),
        "residual_packet": blind_packet(packet),
    }
    return [
        {"role": "system", "content": "You are RepairAgent selecting verifier-safe proof-frontier repair primitives. Select IDs only; a deterministic compiler will build patch JSON."},
        {"role": "user", "content": json.dumps(user_payload, indent=2, sort_keys=True, ensure_ascii=False)},
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-packets", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_closure_repair_policy/repair_packets.json"))
    parser.add_argument("--primitive-library", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_closure_repair_policy/primitive_library.json"))
    parser.add_argument("--structured-selections", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_closure_repair_policy/structured_selections.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_selection_prompt_manifest"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v29 frontier selection prompt manifest")

    packets_path = resolve(args.repair_packets)
    library_path = resolve(args.primitive_library)
    selections_path = resolve(args.structured_selections)
    packets = load_json(packets_path)["packets"]
    library = load_json(library_path)
    selections_by_id = {row["residual_id"]: row for row in load_json(selections_path)["rows"]}
    response_prefill = "{"
    rows = []
    for packet in packets:
        messages = build_messages(packet, library)
        prompt = prompt_text_from_messages(messages, response_prefill)
        selection = selections_by_id[packet["residual_id"]]
        rows.append(
            {
                "residual_id": packet["residual_id"],
                "residual_class": packet["residual_class"],
                "messages": messages,
                "messages_sha256": text_hash(json.dumps(messages, sort_keys=True, ensure_ascii=False)),
                "prompt": prompt,
                "prompt_sha256": text_hash(prompt),
                "response_prefill": response_prefill,
                "prompt_protocol": "chat_template_json_prefill_frontier_selection_v29",
                "expected_selection": {"residual_id": selection["residual_id"], "template_id": selection["template_id"], "selected_primitives": selection["selected_primitives"]},
            }
        )
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "prompt_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_v29_frontier_selection_prompt_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V29_FRONTIER_SELECTION_PROMPT_MANIFEST_READY",
            "rows": rows,
            "prompt_protocol": "chat_template_json_prefill_frontier_selection_v29",
            "repair_packets_sha256": file_hash(packets_path),
            "primitive_library_sha256": file_hash(library_path),
            "answer_blinded": True,
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v29_frontier_selection_prompt_manifest_build_v1",
        "status": "RPD_EBW_TRACK_A_V29_FRONTIER_SELECTION_PROMPT_MANIFEST_READY",
        "rows": len(rows),
        "prompt_manifest_sha256": file_hash(manifest_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "manifest_build.json", payload)
    report = [
        "# EBW Track A v29 Frontier Selection Prompt Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(rows)}",
        "- Prompt protocol: `chat_template_json_prefill_frontier_selection_v29`",
        "- Answer-blinded: Yes",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
    ]
    (output_dir / "PROMPT_MANIFEST.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(rows), "report": str((output_dir / "PROMPT_MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()