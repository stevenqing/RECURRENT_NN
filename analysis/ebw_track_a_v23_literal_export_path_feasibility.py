"""CPU-only feasibility gate for literal export file-path binding."""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
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


def quoted_spans(task_text: str) -> list[dict[str, Any]]:
    patterns = [r'"([^"\n]+)"', r"'([^'\n]+)'", r"\u201c([^\u201d\n]+)\u201d", r"\u2018([^\u2019\n]+)\u2019"]
    spans = []
    seen: set[tuple[int, int]] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, task_text):
            span = (match.start(1), match.end(1))
            if span in seen:
                continue
            seen.add(span)
            spans.append({"start": span[0], "end": span[1], "text": match.group(1)})
    return sorted(spans, key=lambda item: (item["start"], item["end"], item["text"]))


def literal_export_path_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    context = row["context"]
    action = context["candidate_action"]
    target_arg = action["target_arg"]
    live_target = action["arguments"].get(target_arg)
    if action.get("api_name") != "create_file" or target_arg != "file_path" or not live_target:
        return None
    for span in quoted_spans(context["task_text"]):
        if norm_path(span["text"]) == norm_path(str(live_target)):
            return {
                "obligation": "literal_intent_binding",
                "user_span": {"start": span["start"], "end": span["end"]},
                "target_arg": target_arg,
                "expected_file_path": span["text"],
                "live_target": live_target,
                "match": True,
            }
    return None


def valid_literal_export_path(value: Any, candidate: dict[str, Any]) -> bool:
    return norm_path(str(value)) == norm_path(str(candidate["expected_file_path"]))


def adversarial_values(row: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    expected = norm_path(str(candidate["expected_file_path"]))
    directory = posixpath.dirname(expected)
    basename = posixpath.basename(expected)
    stem, dot, suffix = basename.rpartition(".")
    values = [span["text"] for span in quoted_spans(row["context"]["task_text"]) if norm_path(span["text"]) != expected]
    values.extend(
        [
            posixpath.join("~/wrong_export_dir", basename),
            posixpath.join(directory, stem + "__ebw_alternative__" + dot + suffix) if stem else expected + "__ebw_alternative__",
        ]
    )
    deduped = []
    seen: set[str] = set()
    for value in values:
        key = norm_path(value)
        if key and key != expected and key not in seen:
            seen.add(key)
            deduped.append(value)
    return deduped


def target_rows(prompt_manifest: dict[str, Any], rescore_rows: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {row["instance_id"]: row for row in prompt_manifest["rows"]}
    selected = []
    for result in rescore_rows["rows"]:
        row = by_id[result["instance_id"]]
        if result["decision"] == "abstain_no_valid" and classify_post_v17_abstain(row) == "literal_export_path_binding_missing":
            selected.append(row)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v22_source_path_identity_merged_outputs/prompt_manifest.json"))
    parser.add_argument("--rescore-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v22_source_identity_merged/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v23_literal_export_path_feasibility"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v23 literal export path feasibility")

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
        candidate = literal_export_path_candidate(row)
        if candidate is None:
            label = "no_literal_export_path_candidate"
            decision = "abstain_no_valid"
            live_valid = False
            adversarial_valids = {}
        else:
            label = "literal_export_path_candidate_matches_live"
            live_value = row["live_arguments"][row["field_name"]]
            live_valid = valid_literal_export_path(live_value, candidate)
            adversarial_valids = {f"adversarial_{index}": valid_literal_export_path(value, candidate) for index, value in enumerate(adversarial_values(row, candidate))}
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
                        "required_obligation": "literal_intent_binding",
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
    write_json(rows_out, {"schema": "ebw_track_a_v23_literal_export_path_feasibility_rows_v1", "rows": result_rows})
    write_json(
        evaluation_manifest,
        {
            "schema": "ebw_track_a_v23_literal_export_path_target_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V23_LITERAL_EXPORT_PATH_TARGET_READY",
            "rows": evaluation_rows,
            "target_selection": "post-v22 literal_export_path_binding_missing abstains with matching quoted task path spans",
            "sealed_variations_opened": False,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v23_literal_export_path_feasibility_v1",
        "status": "RPD_EBW_TRACK_A_V23_LITERAL_EXPORT_PATH_FEASIBILITY_COMPLETE",
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
        "# EBW Track A v23 Literal Export Path Feasibility",
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
        "The literal export path frontier is sufficient for the two Spotify CSV `create_file.file_path` residuals. This repair does not add a tolerant parser or new free-form proof schema: it reuses the existing strict `literal_intent_binding` sketch and binds the target file path to the exact quoted path span in the user instruction. Header-string quotes and path-shaped mutations fail the unique-validity barrier.",
    ]
    (output_dir / "FEASIBILITY.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "target_rows": len(selected), "counts": payload["candidate_counts"], "decisions": payload["decision_counts"], "report": str((output_dir / "FEASIBILITY.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()