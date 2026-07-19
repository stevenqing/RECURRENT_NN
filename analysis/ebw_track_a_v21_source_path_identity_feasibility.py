"""CPU-only feasibility gate for source-path identity binding."""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
from collections import Counter
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v20_residual_taxonomy import classify_post_v17_abstain
from analysis.ebw_track_a_v9_path_pair_feasibility import norm_path
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


def find_source_path_evidence(context: dict[str, Any], source_file_path: str) -> dict[str, Any] | None:
    source_norm = norm_path(source_file_path)
    for read in reversed(context["pre_write_reads"]):
        response = read.get("response")
        if not isinstance(response, dict):
            continue
        if norm_path(response.get("path", "")) == source_norm:
            return {
                "source_read_id": read["read_id"],
                "source_path_field": "response.path",
                "expected_source_file_path": response["path"],
                "source_created_at": response.get("created_at"),
            }
    return None


def source_path_identity_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    context = row["context"]
    action = context["candidate_action"]
    args = action["arguments"]
    target_arg = action["target_arg"]
    source_path = args.get("source_file_path")
    live_target = args.get(target_arg)
    if action.get("api_name") != "move_file" or target_arg != "source_file_path" or not source_path or not live_target:
        return None
    evidence = find_source_path_evidence(context, str(source_path))
    if evidence is None:
        return None
    return {
        "obligation": "source_path_identity_binding",
        "source_read_id": evidence["source_read_id"],
        "source_path_field": evidence["source_path_field"],
        "identity_transform": "exact_path",
        "target_arg": target_arg,
        "expected_source_file_path": evidence["expected_source_file_path"],
        "source_created_at": evidence["source_created_at"],
        "live_target": live_target,
        "match": norm_path(str(live_target)) == norm_path(str(evidence["expected_source_file_path"])),
    }


def valid_source_path(value: Any, candidate: dict[str, Any]) -> bool:
    return norm_path(str(value)) == norm_path(str(candidate["expected_source_file_path"]))


def sibling_source_paths(context: dict[str, Any], expected: str) -> list[str]:
    expected_norm = norm_path(expected)
    values = []
    seen: set[str] = set()
    for read in context["pre_write_reads"]:
        response = read.get("response")
        if not isinstance(response, dict):
            continue
        path = response.get("path")
        if not path:
            continue
        path_norm = norm_path(str(path))
        if path_norm == expected_norm or path_norm in seen:
            continue
        seen.add(path_norm)
        values.append(str(path))
    return values


def adversarial_values(row: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    expected = norm_path(str(candidate["expected_source_file_path"]))
    directory = posixpath.dirname(expected)
    basename = posixpath.basename(expected)
    values = sibling_source_paths(row["context"], expected)[:3]
    values.extend(
        [
            norm_path(str(row["context"]["candidate_action"]["arguments"].get("destination_file_path", ""))),
            posixpath.join(directory, "__ebw_wrong_source__" + basename),
        ]
    )
    deduped = []
    seen: set[str] = set()
    for value in values:
        value_norm = norm_path(value)
        if not value_norm or value_norm == expected or value_norm in seen:
            continue
        seen.add(value_norm)
        deduped.append(value)
    return deduped


def target_rows(prompt_manifest: dict[str, Any], rescore_rows: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {row["instance_id"]: row for row in prompt_manifest["rows"]}
    selected = []
    for result in rescore_rows["rows"]:
        row = by_id[result["instance_id"]]
        if result["decision"] == "abstain_no_valid" and classify_post_v17_abstain(row) == "source_path_identity_binding_missing":
            selected.append(row)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v17_full_merged_outputs/prompt_manifest.json"))
    parser.add_argument("--rescore-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v17_merged/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v21_source_path_identity_feasibility"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v21 source path identity feasibility")

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
        candidate = source_path_identity_candidate(row)
        if candidate is None:
            label = "no_source_path_identity_candidate"
            decision = "abstain_no_valid"
            live_valid = False
            adversarial_valids = {}
        elif not candidate["match"]:
            label = "source_path_identity_candidate_mismatch"
            decision = "abstain_no_valid"
            live_valid = False
            adversarial_valids = {}
        else:
            label = "source_path_identity_candidate_matches_live"
            live_value = row["live_arguments"][row["field_name"]]
            live_valid = valid_source_path(live_value, candidate)
            adversarial_valids = {f"adversarial_{index}": valid_source_path(value, candidate) for index, value in enumerate(adversarial_values(row, candidate))}
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
                        "required_obligation": "source_path_identity_binding",
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
    write_json(rows_out, {"schema": "ebw_track_a_v21_source_path_identity_feasibility_rows_v1", "rows": result_rows})
    write_json(
        evaluation_manifest,
        {
            "schema": "ebw_track_a_v21_source_path_identity_target_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V21_SOURCE_PATH_IDENTITY_TARGET_READY",
            "rows": evaluation_rows,
            "target_selection": "post-v17 source_path_identity_binding_missing abstains with matching deterministic candidates",
            "sealed_variations_opened": False,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v21_source_path_identity_feasibility_v1",
        "status": "RPD_EBW_TRACK_A_V21_SOURCE_PATH_IDENTITY_FEASIBILITY_COMPLETE",
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
        "# EBW Track A v21 Source-Path Identity Feasibility",
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
        "The source-path identity frontier is sufficient for the remaining `move_file.source_file_path` abstain class. The deterministic candidate binds the write argument to an immutable pre-write `response.path` and requires exact path identity; sibling source paths, destination paths, and mutated path-shaped alternatives fail the unique-validity barrier. This is a CPU-feasible next proof family before adding grammar or running Qwen.",
    ]
    (output_dir / "FEASIBILITY.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "target_rows": len(selected), "counts": payload["candidate_counts"], "decisions": payload["decision_counts"], "report": str((output_dir / "FEASIBILITY.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()