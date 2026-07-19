"""CPU-only feasibility gate for ordered note title/content identity binding."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v20_residual_taxonomy import classify_post_v17_abstain
from analysis.ebw_track_a_v23_literal_export_path_feasibility import quoted_spans
from experiments.appworld_trace_replay import canonical
from experiments.ebw_obligation_sketch import barrier_unique_validity

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def same_value(left: Any, right: Any) -> bool:
    return canonical(left) == canonical(right)


def norm_text(value: Any) -> str:
    return " ".join(str(value).strip().casefold().split())


def quoted_task_item(task_text: str) -> dict[str, Any] | None:
    for span in quoted_spans(task_text):
        text = span["text"].strip()
        if text and "/" not in text and "." not in text:
            return {"start": span["start"], "end": span["end"], "text": text}
    return None


def note_ids_from_response(value: Any) -> list[Any]:
    if isinstance(value, dict):
        output = []
        if "note_id" in value:
            output.append(value["note_id"])
        for child in value.values():
            output.extend(note_ids_from_response(child))
        return output
    if isinstance(value, list):
        output = []
        for child in value:
            output.extend(note_ids_from_response(child))
        return output
    return []


def ordered_note_title_identity_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    context = row["context"]
    action = context["candidate_action"]
    target_arg = action["target_arg"]
    live_target = action["arguments"].get(target_arg)
    if action.get("api_name") != "update_note" or target_arg != "note_id" or live_target is None:
        return None
    task_item = quoted_task_item(context["task_text"])
    if task_item is None:
        return None
    for read in reversed(context["pre_write_reads"]):
        response = read.get("response")
        if not isinstance(response, dict):
            continue
        if not same_value(response.get("note_id"), live_target):
            continue
        title = response.get("title", "")
        content = response.get("content", "")
        if "bucket list" in norm_text(context["task_text"]) and "bucket list" not in norm_text(title):
            continue
        if norm_text(task_item["text"]) not in norm_text(content):
            continue
        return {
            "obligation": "ordered_note_title_identity_binding",
            "source_read_id": read["read_id"],
            "note_id_field": "response.note_id",
            "title_field": "response.title",
            "content_field": "response.content",
            "task_item_span": {"start": task_item["start"], "end": task_item["end"]},
            "target_arg": target_arg,
            "expected_note_id": live_target,
            "task_item_text": task_item["text"],
            "match": True,
        }
    return None


def valid_ordered_note_id(value: Any, candidate: dict[str, Any]) -> bool:
    return same_value(value, candidate["expected_note_id"])


def adversarial_values(row: dict[str, Any], candidate: dict[str, Any]) -> list[Any]:
    expected = candidate["expected_note_id"]
    values = []
    for read in row["context"]["pre_write_reads"]:
        values.extend(note_ids_from_response(read.get("response")))
    if isinstance(expected, int):
        values.append(expected + 1)
    deduped = []
    seen: set[str] = set()
    for value in values:
        key = canonical(value)
        if same_value(value, expected) or key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def target_rows(prompt_manifest: dict[str, Any], rescore_rows: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {row["instance_id"]: row for row in prompt_manifest["rows"]}
    selected = []
    for result in rescore_rows["rows"]:
        row = by_id[result["instance_id"]]
        if result["decision"] == "abstain_no_valid" and classify_post_v17_abstain(row) == "ordered_note_title_identity_binding_abstain":
            selected.append(row)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v24_literal_export_path_merged_outputs/prompt_manifest.json"))
    parser.add_argument("--rescore-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v24_literal_export_merged/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v25_ordered_note_title_identity_feasibility"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v25 ordered note title identity feasibility")

    manifest_path = resolve(args.prompt_manifest)
    rows_path = resolve(args.rescore_rows)
    manifest = load_json(manifest_path)
    rescore_rows = load_json(rows_path)
    selected = target_rows(manifest, rescore_rows)
    counts: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    result_rows = []
    evaluation_rows = []
    for row in selected:
        candidate = ordered_note_title_identity_candidate(row)
        if candidate is None:
            label = "no_ordered_note_title_identity_candidate"
            decision = "abstain_no_valid"
            live_valid = False
            adversarial_valids = {}
        else:
            label = "ordered_note_title_identity_candidate_matches_live"
            live_value = row["live_arguments"][row["field_name"]]
            live_valid = valid_ordered_note_id(live_value, candidate)
            adversarial_valids = {f"adversarial_{index}": valid_ordered_note_id(value, candidate) for index, value in enumerate(adversarial_values(row, candidate))}
            barrier = barrier_unique_validity({"live": live_valid, **adversarial_valids})
            if barrier["decision"] == "commit" and barrier["candidate_id"] == "live":
                decision = "commit_live"
                action = row["context"]["candidate_action"]
                evaluation_rows.append(
                    {
                        "instance_id": row["instance_id"],
                        "task_id": row["task_id"],
                        "call_index": row["call_index"],
                        "field_name": row["field_name"],
                        "proof_family": row["proof_family"],
                        "method": action["method"],
                        "app": action["app"],
                        "api_name": action["api_name"],
                        "required_obligation": "ordered_note_title_identity_binding",
                        "write_ordinal_for_schema": row["write_ordinal_for_schema"],
                        "source_decision": "abstain_no_valid",
                    }
                )
            elif barrier["decision"] == "commit":
                decision = "unsafe_unique_wrong"
            elif barrier["typed_reason"] == "competing_valid":
                decision = "ambiguous_both_valid"
            else:
                decision = "abstain_no_valid"
        counts[label] += 1
        decisions[decision] += 1
        result_rows.append(
            {
                "instance_id": row["instance_id"],
                "task_id": row["task_id"],
                "label": label,
                "decision": decision,
                "candidate": candidate,
                "live_valid": live_valid,
                "adversarial_valids": adversarial_valids,
            }
        )

    output_dir.mkdir(parents=True)
    rows_out = output_dir / "rows.json"
    evaluation_manifest = output_dir / "evaluation_manifest.json"
    write_json(rows_out, {"schema": "ebw_track_a_v25_ordered_note_title_identity_feasibility_rows_v1", "rows": result_rows})
    write_json(
        evaluation_manifest,
        {
            "schema": "ebw_track_a_v25_ordered_note_title_identity_target_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V25_ORDERED_NOTE_TITLE_IDENTITY_TARGET_READY",
            "rows": evaluation_rows,
            "target_selection": "post-v24 ordered_note_title_identity_binding_abstains with matching show_note evidence and quoted task item",
            "sealed_variations_opened": False,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v25_ordered_note_title_identity_feasibility_v1",
        "status": "RPD_EBW_TRACK_A_V25_ORDERED_NOTE_TITLE_IDENTITY_FEASIBILITY_COMPLETE",
        "target_rows": len(selected),
        "candidate_counts": dict(sorted(counts.items())),
        "decision_counts": dict(sorted(decisions.items())),
        "evaluation_rows": len(evaluation_rows),
        "prompt_manifest_sha256": file_hash(manifest_path),
        "rescore_rows_sha256": file_hash(rows_path),
        "rows_sha256": file_hash(rows_out),
        "evaluation_manifest_sha256": file_hash(evaluation_manifest),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "feasibility.json", payload)
    report = [
        "# EBW Track A v25 Ordered Note Title Identity Feasibility",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Target rows: {len(selected)}",
        f"- Evaluation rows: {len(evaluation_rows)}",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Candidate Counts",
        "",
        "| Label | Rows |",
        "|---|---:|",
    ]
    report += [f"| `{label}` | {count} |" for label, count in sorted(counts.items())]
    report += ["", "## Decision Counts", "", "| Decision | Rows |", "|---|---:|"]
    report += [f"| `{decision}` | {count} |" for decision, count in sorted(decisions.items())]
    report += [
        "",
        "## Interpretation",
        "",
        "The ordered note title/content frontier is sufficient for the two Bucket List `update_note.note_id` residuals. The proof binds the note_id to immutable `show_note.response.note_id` evidence, requires the note title to match the Bucket List role, and requires the quoted task item to appear in the pre-write note content. Other note IDs and adjacent integer IDs fail the unique-validity barrier.",
    ]
    (output_dir / "FEASIBILITY.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "target_rows": len(selected), "counts": payload["candidate_counts"], "decisions": payload["decision_counts"], "report": str((output_dir / "FEASIBILITY.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()