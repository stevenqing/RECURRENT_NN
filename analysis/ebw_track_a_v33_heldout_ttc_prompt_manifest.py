"""Build held-out TTC RepairAgent primitive-selection prompts from v32 residuals."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from analysis.ebw_track_a_v21_source_path_identity_feasibility import source_path_identity_candidate
from analysis.ebw_track_a_v23_literal_export_path_feasibility import literal_export_path_candidate
from analysis.ebw_track_a_v25_ordered_note_title_identity_feasibility import ordered_note_title_identity_candidate
from analysis.ebw_track_a_v27_prior_effect_playlist_feasibility import prior_effect_playlist_candidate
from analysis.ebw_track_a_v29_frontier_selection_prompt_manifest import build_messages

REPO_ROOT = Path(__file__).resolve().parents[1]

CandidateFn = Callable[[dict[str, Any]], dict[str, Any] | None]

FROZEN_CANDIDATES: dict[str, CandidateFn] = {
    "source_path_identity_binding_missing": source_path_identity_candidate,
    "literal_export_path_binding_missing": literal_export_path_candidate,
    "ordered_note_title_identity_binding_abstain": ordered_note_title_identity_candidate,
    "prior_effect_playlist_id_binding_abstain": prior_effect_playlist_candidate,
}

PACKET_SUMMARIES = {
    "source_path_identity_binding_missing": ("source_path_identity_frontier_missing", "source_file_path must bind to immutable pre-write response.path evidence"),
    "literal_export_path_binding_missing": ("literal_task_path_span_frontier_missing", "file_path must bind to an exact quoted task path span; other quoted strings must fail"),
    "ordered_note_title_identity_binding_abstain": ("ordered_note_title_content_identity_frontier_missing", "note_id must bind to a show_note result with the target role title and quoted task item in content"),
    "prior_effect_playlist_id_binding_abstain": ("prior_effect_playlist_frontier_missing", "playlist_id must bind to an earlier create_playlist.response.playlist_id prior effect"),
}


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


def matched_residual_classes(row: dict[str, Any]) -> list[str]:
    matches = []
    for residual_class, candidate_fn in FROZEN_CANDIDATES.items():
        candidate = candidate_fn(row)
        if candidate is not None and candidate.get("match") is True:
            matches.append(residual_class)
    return matches


def packet_id(residual_class: str) -> str:
    return "R_HELDOUT_" + residual_class.upper().replace("_", "-").replace("-", "_") + "_V33"


def build_packet(residual_class: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    typed_reason, summary = PACKET_SUMMARIES[residual_class]
    failed_obligations = sorted({str(row.get("required_obligation")) for row in rows})
    return {
        "residual_id": packet_id(residual_class),
        "residual_class": residual_class,
        "typed_reason": typed_reason,
        "target_rows": len(rows),
        "counterexample_summary": summary,
        "failed_frontier": {"required_obligations": failed_obligations, "source": "v32_heldout_no_repair_noncommit"},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v32_heldout_prompt_manifest_no_repair/prompt_manifest.json"))
    parser.add_argument("--baseline-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v32_heldout_no_repair/rows.json"))
    parser.add_argument("--primitive-library", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_closure_repair_policy/primitive_library.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v33_heldout_ttc_prompt_manifest"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v33 held-out TTC prompt manifest")

    manifest_path = resolve(args.prompt_manifest)
    baseline_rows_path = resolve(args.baseline_rows)
    library_path = resolve(args.primitive_library)
    manifest = load_json(manifest_path)
    baseline_rows = load_json(baseline_rows_path)["rows"]
    library = load_json(library_path)
    rows_by_id = {row["instance_id"]: row for row in manifest["rows"]}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmatched = []
    ambiguous = []
    for result in baseline_rows:
        if result["decision"] == "commit_live":
            continue
        row = rows_by_id[result["instance_id"]]
        matches = matched_residual_classes(row)
        if len(matches) == 1:
            grouped[matches[0]].append(row)
        elif len(matches) > 1:
            ambiguous.append({"instance_id": result["instance_id"], "matches": matches})
        else:
            unmatched.append({"instance_id": result["instance_id"], "task_id": result["task_id"], "decision": result["decision"]})
    packets = [build_packet(residual_class, rows) for residual_class, rows in sorted(grouped.items())]
    response_prefill = "{"
    prompt_rows = []
    for packet in packets:
        messages = build_messages(packet, library)
        prompt = prompt_text_from_messages(messages, response_prefill)
        prompt_rows.append(
            {
                "residual_id": packet["residual_id"],
                "residual_class": packet["residual_class"],
                "messages": messages,
                "messages_sha256": text_hash(json.dumps(messages, sort_keys=True, ensure_ascii=False)),
                "prompt": prompt,
                "prompt_sha256": text_hash(prompt),
                "response_prefill": response_prefill,
                "prompt_protocol": "chat_template_json_prefill_heldout_ttc_v33",
            }
        )
    output_dir.mkdir(parents=True)
    prompt_path = output_dir / "prompt_manifest.json"
    write_json(
        prompt_path,
        {
            "schema": "ebw_track_a_v33_heldout_ttc_prompt_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V33_HELDOUT_TTC_PROMPT_MANIFEST_READY",
            "rows": prompt_rows,
            "repair_packets": packets,
            "unmatched_rows": unmatched,
            "ambiguous_rows": ambiguous,
            "prompt_protocol": "chat_template_json_prefill_heldout_ttc_v33",
            "baseline_rows_sha256": file_hash(baseline_rows_path),
            "source_prompt_manifest_sha256": file_hash(manifest_path),
            "primitive_library_sha256": file_hash(library_path),
            "sealed_variations_opened": bool(manifest.get("sealed_variations_opened", False)),
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v33_heldout_ttc_prompt_manifest_build_v1",
        "status": "RPD_EBW_TRACK_A_V33_HELDOUT_TTC_PROMPT_MANIFEST_READY",
        "residual_packets": len(packets),
        "target_rows": sum(packet["target_rows"] for packet in packets),
        "unmatched_rows": len(unmatched),
        "ambiguous_rows": len(ambiguous),
        "prompt_manifest_sha256": file_hash(prompt_path),
        "sealed_variations_opened": bool(manifest.get("sealed_variations_opened", False)),
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "manifest_build.json", payload)
    report = [
        "# EBW Track A v33 Held-Out TTC Prompt Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Residual packets: {len(packets)}",
        f"- Target rows: {payload['target_rows']}",
        f"- Unmatched rows: {len(unmatched)}",
        f"- Ambiguous rows: {len(ambiguous)}",
        "- Primitive library: frozen v29",
        "- Sealed variations 10-12 opened: Yes",
        "- Model/GPU/Docker actions: No",
        "",
        "## Packets",
        "",
        "| Residual | Rows | Typed reason |",
        "|---|---:|---|",
    ]
    report += [f"| `{packet['residual_class']}` | {packet['target_rows']} | `{packet['typed_reason']}` |" for packet in packets]
    (output_dir / "PROMPT_MANIFEST.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "residual_packets": len(packets), "target_rows": payload["target_rows"], "unmatched_rows": len(unmatched), "report": str((output_dir / "PROMPT_MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()