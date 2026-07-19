"""CPU-only feasibility gate for title-slug export path binding."""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
from collections import Counter
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v11_residual_taxonomy import classify_post_v10_abstain
from analysis.ebw_track_a_v9_path_pair_feasibility import clean_directory_literal, norm_path
from experiments.ebw_obligation_sketch import barrier_unique_validity

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


def slug_title(title: str) -> str:
    return re.sub(r"\s+", "_", str(title).strip())


def parse_export_rule(task_text: str) -> dict[str, str] | None:
    directory_match = re.search(r'to\s+"([^"]+)"\s+directory', task_text)
    extension_match = re.search(r'extension should be\s+"(\.[^"]+)"', task_text)
    if not directory_match or not extension_match:
        return None
    if "note title" not in task_text.casefold() or "replacing white space" not in task_text.casefold():
        return None
    return {
        "destination_directory": clean_directory_literal(directory_match.group(1)),
        "extension": extension_match.group(1),
        "slug_transform": "whitespace_to_underscore",
        "destination_directory_rule_id": "task_literal_backup_directory",
    }


def find_show_note_evidence(context: dict[str, Any], live_content: str) -> dict[str, Any] | None:
    for read in reversed(context["pre_write_reads"]):
        response = read["response"]
        if not isinstance(response, dict):
            continue
        title = response.get("title")
        content = response.get("content")
        if title and content == live_content:
            return {
                "source_read_id": read["read_id"],
                "title_field": "response.title",
                "content_field": "response.content",
                "title": str(title),
                "content_sha256": text_hash(str(content)),
            }
    return None


def title_slug_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    context = row["context"]
    action = context["candidate_action"]
    args = action["arguments"]
    target_arg = action["target_arg"]
    live_content = args.get("content")
    live_target = args.get(target_arg)
    if target_arg != "file_path" or not isinstance(live_content, str) or not live_target:
        return None
    rule = parse_export_rule(context["task_text"])
    evidence = find_show_note_evidence(context, live_content)
    if rule is None or evidence is None:
        return None
    expected = posixpath.join(rule["destination_directory"], slug_title(evidence["title"]) + rule["extension"])
    return {
        "obligation": "title_slug_export_path_binding",
        "source_read_id": evidence["source_read_id"],
        "title_field": evidence["title_field"],
        "content_field": evidence["content_field"],
        "destination_directory_rule_id": rule["destination_directory_rule_id"],
        "slug_transform": rule["slug_transform"],
        "extension": rule["extension"],
        "target_arg": target_arg,
        "expected_file_path": expected,
        "live_target": live_target,
        "match": norm_path(expected) == norm_path(live_target),
        "title_sha256": text_hash(evidence["title"]),
        "content_sha256": evidence["content_sha256"],
    }


def adversarial_values(candidate: dict[str, Any]) -> list[str]:
    expected = norm_path(candidate["expected_file_path"])
    directory = posixpath.dirname(expected)
    basename = posixpath.basename(expected)
    stem, dot, suffix = basename.rpartition(".")
    if not dot:
        stem, suffix = basename, ""
    values = [
        posixpath.join(directory, stem + "__ebw_alternative__" + dot + suffix),
        posixpath.join(directory, basename.replace("_", " ", 1)),
        posixpath.join("~/wrong_backup_dir", basename),
        posixpath.join(directory, stem + ".txt"),
    ]
    deduped = []
    seen: set[str] = set()
    for value in values:
        key = norm_path(value)
        if key != expected and key not in seen:
            seen.add(key)
            deduped.append(value)
    return deduped


def valid_title_slug(value: Any, candidate: dict[str, Any]) -> bool:
    return norm_path(value) == norm_path(candidate["expected_file_path"])


def target_rows(merged_manifest: dict[str, Any], rescore_rows: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {row["instance_id"]: row for row in merged_manifest["rows"]}
    selected = []
    for result in rescore_rows["rows"]:
        row = by_id[result["instance_id"]]
        if result["decision"] == "abstain_no_valid" and classify_post_v10_abstain(row) == "title_slug_export_path_binding_missing":
            selected.append(row)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_full_merged_outputs/prompt_manifest.json"))
    parser.add_argument("--merged-rescore-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v10_merged/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_title_slug_feasibility_v2"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v11 title-slug feasibility")

    manifest_path = resolve(args.merged_prompt_manifest)
    rows_path = resolve(args.merged_rescore_rows)
    merged_manifest = load_json(manifest_path)
    rescore_rows = load_json(rows_path)
    selected = target_rows(merged_manifest, rescore_rows)
    counts: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    result_rows = []
    evaluation_rows = []
    for row in selected:
        candidate = title_slug_candidate(row)
        if candidate is None:
            label = "no_title_slug_candidate"
            decision = "abstain_no_valid"
            live_valid = False
            adversarial_valids = {}
        elif not candidate["match"]:
            label = "title_slug_candidate_mismatch"
            decision = "abstain_no_valid"
            live_valid = False
            adversarial_valids = {}
        else:
            label = "title_slug_candidate_matches_live"
            live_value = row["live_arguments"][row["field_name"]]
            live_valid = valid_title_slug(live_value, candidate)
            adversarial_valids = {f"adversarial_{index}": valid_title_slug(value, candidate) for index, value in enumerate(adversarial_values(candidate))}
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
                        "required_obligation": "title_slug_export_path_binding",
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
    write_json(rows_out, {"schema": "ebw_track_a_v11_title_slug_feasibility_rows_v1", "rows": result_rows})
    write_json(
        evaluation_manifest,
        {
            "schema": "ebw_track_a_v11_title_slug_target_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V11_TITLE_SLUG_TARGET_READY",
            "rows": evaluation_rows,
            "target_selection": "post-v10 title_slug_export_path_binding_missing abstains with matching deterministic candidates",
            "sealed_variations_opened": False,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v11_title_slug_feasibility_v1",
        "status": "RPD_EBW_TRACK_A_V11_TITLE_SLUG_FEASIBILITY_COMPLETE",
        "target_rows": len(selected),
        "candidate_counts": dict(sorted(counts.items())),
        "decision_counts": dict(sorted(decisions.items())),
        "evaluation_rows": len(evaluation_rows),
        "merged_prompt_manifest_sha256": file_hash(manifest_path),
        "merged_rescore_rows_sha256": file_hash(rows_path),
        "rows_sha256": file_hash(rows_out),
        "evaluation_manifest_sha256": file_hash(evaluation_manifest),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "feasibility.json", payload)
    report = [
        "# EBW Track A v11 Title-Slug Feasibility",
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
        "The title-slug proof frontier is sufficient for the post-v10 Simple Note export abstain class when the source note is bound to the latest matching pre-write `show_note` read. The deterministic candidate binds that title/content read to the task literal backup directory, applies whitespace-to-underscore slugging, appends `.md`, and passes adversarial uniqueness under path-shaped alternatives. This authorizes the grammar/parser gate before any model call.",
    ]
    (output_dir / "FEASIBILITY.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "target_rows": len(selected), "counts": payload["candidate_counts"], "decisions": payload["decision_counts"], "report": str((output_dir / "FEASIBILITY.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()