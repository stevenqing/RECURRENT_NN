"""Build paired typed and untyped RepairAgent prompts for hard ordered-note residuals."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v16_primitive_selection_prompt_manifest import compact_library, prompt_text_from_messages
from analysis.ebw_track_a_v29_frontier_closure_repair_policy import primitive_library

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


def response_contract() -> list[str]:
    return [
        "Return exactly one JSON object and no markdown.",
        "Required keys exactly: residual_id, template_id, selected_primitives.",
        "residual_id must match the packet residual_id exactly.",
        "template_id must be one patch_templates[].id.",
        "selected_primitives must include one primitive for every required slot of the selected template.",
        "Select primitive IDs only; do not write patch JSON.",
    ]


def build_messages(packet_key: str, packet: dict[str, Any], library: dict[str, Any], typed: bool) -> list[dict[str, str]]:
    payload = {
        "task": "Select primitive IDs for a deterministic RepairAgent compiler.",
        "response_contract": response_contract(),
        "selection_schema": {"required_keys": ["residual_id", "template_id", "selected_primitives"], "selected_primitives_type": "list[string]"},
        "primitive_library": compact_library(library),
        packet_key: packet,
    }
    system = "You are RepairAgent selecting verifier-safe repair primitives."
    if not typed:
        system += " Typed residual labels are withheld; infer from untyped failure metadata only."
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)}]


def typed_packet(noncommit_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "residual_id": "R_HARD_ORDERED_NOTE_TYPED_V42",
        "residual_class": "ordered_note_title_identity_binding_abstain",
        "typed_reason": "ordered_note_title_content_identity_frontier_missing",
        "target_rows": len(noncommit_rows),
        "counterexample_summary": "update_note.note_id cannot be recovered by same-rank ordered-role binding; it must bind to show_note.response.note_id with Bucket List title and quoted task item in pre-write content",
        "failed_frontier": {"required_obligation": "ordered_role_binding", "source": "v41_hard_target_no_repair_noncommit"},
    }


def untyped_packet(noncommit_rows: list[dict[str, Any]], prompt_rows_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    api_counts = Counter()
    field_counts = Counter()
    obligation_counts = Counter()
    parse_counts = Counter()
    task_ids = set()
    for result in noncommit_rows:
        row = prompt_rows_by_id[result["instance_id"]]
        action = row["context"]["candidate_action"]
        api_counts[str(action.get("api_name"))] += 1
        field_counts[str(row.get("field_name"))] += 1
        obligation_counts[str(row.get("required_obligation"))] += 1
        parse_counts["parse_ok" if result.get("parse_ok") else "parse_error"] += 1
        task_ids.add(row["task_id"])
    return {
        "residual_id": "R_HARD_ORDERED_NOTE_UNTYPED_V42",
        "target_rows": len(noncommit_rows),
        "baseline_decision_counts": dict(Counter(row["decision"] for row in noncommit_rows)),
        "baseline_parse_counts": dict(sorted(parse_counts.items())),
        "api_name_counts": dict(sorted(api_counts.items())),
        "field_name_counts": dict(sorted(field_counts.items())),
        "previous_required_obligation_counts": dict(sorted(obligation_counts.items())),
        "task_count": len(task_ids),
        "visible_failure_summary": "The proof-agent pass produced safe abstentions for these held-out write fields. Select repair primitives from the frozen library without typed residual labels.",
    }


def row_for(packet: dict[str, Any], packet_key: str, library: dict[str, Any], typed: bool, residual_class: str) -> dict[str, Any]:
    response_prefill = "{"
    messages = build_messages(packet_key, packet, library, typed)
    prompt = prompt_text_from_messages(messages, response_prefill)
    return {
        "residual_id": packet["residual_id"],
        "residual_class": residual_class,
        "messages": messages,
        "messages_sha256": text_hash(json.dumps(messages, sort_keys=True, ensure_ascii=False)),
        "prompt": prompt,
        "prompt_sha256": text_hash(prompt),
        "response_prefill": response_prefill,
        "prompt_protocol": "chat_template_json_prefill_hard_typed_v42" if typed else "chat_template_json_prefill_hard_untyped_v42",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v41_hard_target_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--baseline-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v41_hard_target_no_repair/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v42_hard_typed_vs_untyped_prompt_manifests"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v42 hard typed/untyped manifests")

    prompt_manifest_path = resolve(args.prompt_manifest)
    baseline_rows_path = resolve(args.baseline_rows)
    prompt_manifest = load_json(prompt_manifest_path)
    baseline_rows = load_json(baseline_rows_path)["rows"]
    prompt_rows_by_id = {row["instance_id"]: row for row in prompt_manifest["rows"]}
    noncommit_rows = [row for row in baseline_rows if row["decision"] != "commit_live"]
    library = primitive_library()
    typed = typed_packet(noncommit_rows)
    untyped = untyped_packet(noncommit_rows, prompt_rows_by_id)
    residual_class = typed["residual_class"]
    typed_row = row_for(typed, "residual_packet", library, True, residual_class)
    untyped_row = row_for(untyped, "untyped_failure_packet", library, False, residual_class)

    output_dir.mkdir(parents=True)
    typed_path = output_dir / "typed_prompt_manifest.json"
    untyped_path = output_dir / "untyped_prompt_manifest.json"
    common = {"schema": "ebw_track_a_v42_hard_repair_prompt_manifest_v1", "repair_target_rows": len(noncommit_rows), "sealed_variations_opened": True, "model_gpu_docker_used": False, "external_process_actions": False}
    write_json(typed_path, {**common, "status": "RPD_EBW_TRACK_A_V42_HARD_TYPED_PROMPT_MANIFEST_READY", "rows": [typed_row], "repair_packets": [typed], "prompt_protocol": typed_row["prompt_protocol"]})
    write_json(untyped_path, {**common, "status": "RPD_EBW_TRACK_A_V42_HARD_UNTYPED_PROMPT_MANIFEST_READY", "rows": [untyped_row], "repair_packets": [{**typed, "residual_id": untyped["residual_id"]}], "untyped_failure_packet": untyped, "withheld_fields": ["residual_class", "typed_reason", "failed_frontier", "counterexample_summary"], "prompt_protocol": untyped_row["prompt_protocol"]})
    payload = {
        "schema": "ebw_track_a_v42_hard_typed_vs_untyped_manifest_build_v1",
        "status": "RPD_EBW_TRACK_A_V42_HARD_TYPED_VS_UNTYPED_MANIFESTS_READY",
        "repair_target_rows": len(noncommit_rows),
        "typed_prompt_manifest_sha256": file_hash(typed_path),
        "untyped_prompt_manifest_sha256": file_hash(untyped_path),
        "source_prompt_manifest_sha256": file_hash(prompt_manifest_path),
        "baseline_rows_sha256": file_hash(baseline_rows_path),
        "sealed_variations_opened": True,
    }
    write_json(output_dir / "manifest_build.json", payload)
    report = [
        "# EBW Track A v42 Hard Typed vs Untyped Prompt Manifests",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Repair target rows: {len(noncommit_rows)}",
        f"- Residual class: `{residual_class}`",
        "- Typed prompt: includes residual_class, typed_reason, failed_frontier, counterexample_summary",
        "- Untyped prompt: withholds typed residual labels and frontier summary",
        "- Claim boundary: exploratory hard pass-subset only; v39 hard held-out protocol was blocked.",
    ]
    (output_dir / "PROMPT_MANIFESTS.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "repair_target_rows": len(noncommit_rows), "report": str((output_dir / "PROMPT_MANIFESTS.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()