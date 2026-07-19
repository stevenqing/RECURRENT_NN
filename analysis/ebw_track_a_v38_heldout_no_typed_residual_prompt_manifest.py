"""Build held-out RepairAgent prompts without typed residual fields."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v16_primitive_selection_prompt_manifest import compact_library, prompt_text_from_messages

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


def build_untyped_packet(baseline_rows: list[dict[str, Any]], prompt_rows_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    failed = [row for row in baseline_rows if row["decision"] != "commit_live"]
    api_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    obligation_counts: Counter[str] = Counter()
    parse_counts: Counter[str] = Counter()
    task_ids: set[str] = set()
    for result in failed:
        row = prompt_rows_by_id[result["instance_id"]]
        action = row["context"]["candidate_action"]
        api_counts[str(action.get("api_name"))] += 1
        field_counts[str(row.get("field_name"))] += 1
        obligation_counts[str(row.get("required_obligation"))] += 1
        parse_counts["parse_ok" if result.get("parse_ok") else "parse_error"] += 1
        task_ids.add(str(row.get("task_id")))
    return {
        "residual_id": "R_HELDOUT_UNTYPED_FAILURE_V38",
        "target_rows": len(failed),
        "baseline_decision_counts": dict(Counter(row["decision"] for row in failed)),
        "baseline_parse_counts": dict(sorted(parse_counts.items())),
        "api_name_counts": dict(sorted(api_counts.items())),
        "field_name_counts": dict(sorted(field_counts.items())),
        "previous_required_obligation_counts": dict(sorted(obligation_counts.items())),
        "task_count": len(task_ids),
        "visible_failure_summary": "The proof-agent pass produced safe abstentions for these held-out write fields. Select repair primitives from the frozen library without typed residual labels.",
    }


def build_messages(untyped_packet: dict[str, Any], library: dict[str, Any]) -> list[dict[str, str]]:
    user_payload = {
        "task": "Select primitive IDs for a deterministic RepairAgent compiler. Do not write patch JSON.",
        "response_contract": [
            "Return exactly one JSON object and no markdown.",
            "Required keys exactly: residual_id, template_id, selected_primitives.",
            "residual_id must equal untyped_failure_packet.residual_id exactly.",
            "template_id must be one patch_templates[].id.",
            "selected_primitives must include one primitive for every required slot of the selected template.",
            "Use only information in the untyped failure packet and frozen primitive library.",
        ],
        "selection_schema": {"required_keys": ["residual_id", "template_id", "selected_primitives"], "selected_primitives_type": "list[string]"},
        "primitive_library": compact_library(library),
        "untyped_failure_packet": untyped_packet,
    }
    return [
        {"role": "system", "content": "You are RepairAgent selecting verifier-safe repair primitives. Typed residual labels are withheld; select IDs only."},
        {"role": "user", "content": json.dumps(user_payload, indent=2, sort_keys=True, ensure_ascii=False)},
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v32_heldout_prompt_manifest_no_repair/prompt_manifest.json"))
    parser.add_argument("--baseline-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v32_heldout_no_repair/rows.json"))
    parser.add_argument("--typed-ttc-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v33_heldout_ttc_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--primitive-library", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_closure_repair_policy/primitive_library.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v38_heldout_no_typed_residual_prompt_manifest"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v38 no-typed-residual prompt manifest")

    base_manifest_path = resolve(args.base_prompt_manifest)
    baseline_rows_path = resolve(args.baseline_rows)
    typed_manifest_path = resolve(args.typed_ttc_manifest)
    library_path = resolve(args.primitive_library)
    base_manifest = load_json(base_manifest_path)
    baseline_rows = load_json(baseline_rows_path)["rows"]
    typed_manifest = load_json(typed_manifest_path)
    library = load_json(library_path)
    prompt_rows_by_id = {row["instance_id"]: row for row in base_manifest["rows"]}
    untyped_packet = build_untyped_packet(baseline_rows, prompt_rows_by_id)
    response_prefill = "{"
    messages = build_messages(untyped_packet, library)
    prompt = prompt_text_from_messages(messages, response_prefill)
    typed_packet = typed_manifest["repair_packets"][0]
    rows = [
        {
            "residual_id": untyped_packet["residual_id"],
            "residual_class": typed_packet["residual_class"],
            "messages": messages,
            "messages_sha256": text_hash(json.dumps(messages, sort_keys=True, ensure_ascii=False)),
            "prompt": prompt,
            "prompt_sha256": text_hash(prompt),
            "response_prefill": response_prefill,
            "prompt_protocol": "chat_template_json_prefill_no_typed_residual_v38",
        }
    ]

    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "prompt_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_v38_no_typed_residual_prompt_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V38_NO_TYPED_RESIDUAL_PROMPT_MANIFEST_READY",
            "rows": rows,
            "repair_packets": [{**typed_packet, "residual_id": untyped_packet["residual_id"]}],
            "untyped_failure_packet": untyped_packet,
            "withheld_fields": ["residual_class", "typed_reason", "failed_frontier", "counterexample_summary"],
            "prompt_protocol": "chat_template_json_prefill_no_typed_residual_v38",
            "base_prompt_manifest_sha256": file_hash(base_manifest_path),
            "baseline_rows_sha256": file_hash(baseline_rows_path),
            "typed_ttc_manifest_sha256": file_hash(typed_manifest_path),
            "primitive_library_sha256": file_hash(library_path),
            "sealed_variations_opened": bool(base_manifest.get("sealed_variations_opened", False)),
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v38_no_typed_residual_prompt_manifest_build_v1",
        "status": "RPD_EBW_TRACK_A_V38_NO_TYPED_RESIDUAL_PROMPT_MANIFEST_READY",
        "rows": len(rows),
        "target_rows": untyped_packet["target_rows"],
        "prompt_manifest_sha256": file_hash(manifest_path),
        "sealed_variations_opened": bool(base_manifest.get("sealed_variations_opened", False)),
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "manifest_build.json", payload)
    report = [
        "# EBW Track A v38 No-Typed-Residual Prompt Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(rows)}",
        f"- Target held-out failures: {untyped_packet['target_rows']}",
        "- Withheld fields: `residual_class`, `typed_reason`, `failed_frontier`, `counterexample_summary`",
        "- Sealed variations 10-12 opened: Yes",
        "- Model/GPU/Docker actions: No",
    ]
    (output_dir / "PROMPT_MANIFEST.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(rows), "target_rows": untyped_packet["target_rows"], "report": str((output_dir / "PROMPT_MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()