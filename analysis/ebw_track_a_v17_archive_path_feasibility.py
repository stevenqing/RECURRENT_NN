"""CPU-only feasibility gate for directory-basename archive path binding."""
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


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def tilde_to_home_pattern(path: str) -> str:
    normalized = norm_path(path)
    if normalized.startswith("~/"):
        return "/home/*/" + normalized[2:]
    return normalized


def same_user_path(value: Any, target_path: str) -> bool:
    value_norm = norm_path(str(value)).rstrip("/")
    target_norm = norm_path(str(target_path)).rstrip("/")
    if value_norm == target_norm:
        return True
    pattern = tilde_to_home_pattern(target_norm)
    if "*" in pattern:
        prefix, suffix = pattern.split("*", 1)
        return value_norm.startswith(prefix) and value_norm.endswith(suffix)
    return False


def parse_archive_rule(task_text: str) -> dict[str, str] | None:
    match = re.search(r'save them in\s+"([^"]*<vacation_spot>(\.[^"]+))"', task_text)
    if not match:
        return None
    template = clean_directory_literal(match.group(1))
    extension = match.group(2)
    if "<vacation_spot>" not in template:
        return None
    return {
        "template": template,
        "destination_directory": clean_directory_literal(template.split("<vacation_spot>", 1)[0]),
        "extension": extension,
        "template_rule_id": "task_literal_vacation_spot_archive_template",
        "basename_transform": "directory_basename",
    }


def field_for_list_index(index: int) -> str:
    return f"response.{index}"


def archive_path_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    context = row["context"]
    action = context["candidate_action"]
    args = action["arguments"]
    source_dir = args.get("directory_path")
    target_arg = action["target_arg"]
    live_target = args.get(target_arg)
    if target_arg != "compressed_file_path" or not source_dir or not live_target:
        return None
    rule = parse_archive_rule(context["task_text"])
    if rule is None:
        return None
    for read in context["pre_write_reads"]:
        response = read["response"]
        if not isinstance(response, list):
            continue
        for index, value in enumerate(response):
            if same_user_path(value, str(source_dir)):
                basename = posixpath.basename(norm_path(str(source_dir)))
                expected = rule["template"].replace("<vacation_spot>", basename)
                return {
                    "obligation": "directory_basename_archive_path_binding",
                    "source_read_id": read["read_id"],
                    "source_directory_field": field_for_list_index(index),
                    "destination_template_rule_id": rule["template_rule_id"],
                    "basename_transform": rule["basename_transform"],
                    "extension": rule["extension"],
                    "target_arg": target_arg,
                    "expected_archive_path": expected,
                    "live_target": live_target,
                    "match": norm_path(expected) == norm_path(str(live_target)),
                    "source_directory_basename": basename,
                }
    return None


def valid_archive_path(value: Any, candidate: dict[str, Any]) -> bool:
    return norm_path(str(value)) == norm_path(candidate["expected_archive_path"])


def adversarial_values(candidate: dict[str, Any]) -> list[str]:
    expected = norm_path(candidate["expected_archive_path"])
    directory = posixpath.dirname(expected)
    basename = posixpath.basename(expected)
    stem, dot, suffix = basename.rpartition(".")
    values = [
        posixpath.join(directory, stem + "__ebw_alternative__" + dot + suffix),
        posixpath.join(directory, stem + ".zip" if suffix != "zip" else stem + ".tar"),
        posixpath.join("~/wrong_archive_dir", basename),
        posixpath.join(directory, basename.replace("_", "-", 1)),
    ]
    deduped = []
    seen: set[str] = set()
    for value in values:
        key = norm_path(value)
        if key != expected and key not in seen:
            seen.add(key)
            deduped.append(value)
    return deduped


def target_rows(prompt_manifest: dict[str, Any], rescore_rows: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {row["instance_id"]: row for row in prompt_manifest["rows"]}
    selected = []
    for result in rescore_rows["rows"]:
        row = by_id[result["instance_id"]]
        if result["decision"] == "abstain_no_valid" and classify_post_v10_abstain(row) == "directory_basename_archive_path_binding_missing":
            selected.append(row)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11b_full_merged_outputs/prompt_manifest.json"))
    parser.add_argument("--rescore-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v11b_merged/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v17_archive_path_feasibility"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v17 archive path feasibility")

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
        candidate = archive_path_candidate(row)
        if candidate is None:
            label = "no_archive_path_candidate"
            decision = "abstain_no_valid"
            live_valid = False
            adversarial_valids = {}
        elif not candidate["match"]:
            label = "archive_path_candidate_mismatch"
            decision = "abstain_no_valid"
            live_valid = False
            adversarial_valids = {}
        else:
            label = "archive_path_candidate_matches_live"
            live_value = row["live_arguments"][row["field_name"]]
            live_valid = valid_archive_path(live_value, candidate)
            adversarial_valids = {f"adversarial_{index}": valid_archive_path(value, candidate) for index, value in enumerate(adversarial_values(candidate))}
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
                        "required_obligation": "directory_basename_archive_path_binding",
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
    write_json(rows_out, {"schema": "ebw_track_a_v17_archive_path_feasibility_rows_v1", "rows": result_rows})
    write_json(
        evaluation_manifest,
        {
            "schema": "ebw_track_a_v17_archive_path_target_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V17_ARCHIVE_PATH_TARGET_READY",
            "rows": evaluation_rows,
            "target_selection": "post-v11b directory_basename_archive_path_binding_missing abstains with matching deterministic candidates",
            "sealed_variations_opened": False,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v17_archive_path_feasibility_v1",
        "status": "RPD_EBW_TRACK_A_V17_ARCHIVE_PATH_FEASIBILITY_COMPLETE",
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
        "# EBW Track A v17 Archive Path Feasibility",
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
        "The archive-path frontier is sufficient for the post-v11b vacation-directory compression abstain class. The deterministic candidate binds a source directory listed in immutable `show_directory` evidence, extracts its basename as `<vacation_spot>`, and fills the task literal archive template and extension. This is a clean next proof family for structured RepairAgent expansion before touching the larger ordered-role gap.",
    ]
    (output_dir / "FEASIBILITY.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "target_rows": len(selected), "counts": payload["candidate_counts"], "decisions": payload["decision_counts"], "report": str((output_dir / "FEASIBILITY.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()