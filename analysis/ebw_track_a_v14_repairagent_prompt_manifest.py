"""Build answer-blinded RepairAgent prompts from v12 residual packets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v13_repairagent_prompt_manifest import PATCH_SCHEMAS, prompt_text_from_messages

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


def blind_packet(packet: dict[str, Any]) -> dict[str, Any]:
    allowed = {"residual_id", "residual_class", "typed_reason", "target_rows", "counterexample_summary", "failed_frontier", "failure_modes", "failed_prompt_protocol", "strict_before"}
    return {key: packet[key] for key in packet if key in allowed}


def build_messages(packet: dict[str, Any]) -> list[dict[str, str]]:
    blinded = blind_packet(packet)
    user_payload = {
        "task": "Propose exactly one patch JSON object for this typed residual. The accepted repair is not provided.",
        "response_contract": [
            "Return exactly one JSON object and no markdown.",
            "The object must match one allowed_patch_schema exactly: no extra keys and no missing keys.",
            "target_residual must equal residual_packet.residual_class exactly, not residual_id and not a placeholder.",
            "Do not propose parser relaxation when the strict parser can be preserved.",
            "Do not propose prompt_only patches for proof-frontier residuals; propose a deterministic frontier_grammar patch.",
            "For output-contract residuals, preserve strict parsing and identify the required output key plus forbidden leaking key.",
        ],
        "allowed_patch_schemas": PATCH_SCHEMAS,
        "residual_packet": blinded,
    }
    return [
        {"role": "system", "content": "You are RepairAgent for proof-carrying AppWorld writes. Infer minimal verifier-safe patches from typed residuals without seeing the accepted repair."},
        {"role": "user", "content": json.dumps(user_payload, indent=2, sort_keys=True, ensure_ascii=False)},
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-packets", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v12_repairagent_metaverifier/repair_packets.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v14_repairagent_prompt_manifest"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v14 RepairAgent prompt manifest")

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
                "prompt_protocol": "chat_template_json_prefill_repairagent_blind_v14",
            }
        )
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "prompt_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_v14_repairagent_prompt_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V14_REPAIRAGENT_PROMPT_MANIFEST_READY",
            "rows": rows,
            "prompt_protocol": "chat_template_json_prefill_repairagent_blind_v14",
            "repair_packets_sha256": file_hash(packets_path),
            "answer_blinded": True,
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v14_repairagent_prompt_manifest_build_v1",
        "status": "RPD_EBW_TRACK_A_V14_REPAIRAGENT_PROMPT_MANIFEST_READY",
        "rows": len(rows),
        "prompt_manifest_sha256": file_hash(manifest_path),
        "repair_packets_sha256": file_hash(packets_path),
        "answer_blinded": True,
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "manifest_build.json", payload)
    report = [
        "# EBW Track A v14 Blind RepairAgent Prompt Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(rows)}",
        "- Prompt protocol: `chat_template_json_prefill_repairagent_blind_v14`",
        "- Answer-blinded: Yes",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
    ]
    (output_dir / "PROMPT_MANIFEST.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(rows), "report": str((output_dir / "PROMPT_MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()