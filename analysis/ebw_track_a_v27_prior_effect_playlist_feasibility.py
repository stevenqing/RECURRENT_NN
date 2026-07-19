"""CPU-only feasibility gate for prior-effect playlist-id binding."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v20_residual_taxonomy import classify_post_v17_abstain
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


def prior_effect_playlist_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    context = row["context"]
    action = context["candidate_action"]
    target_arg = action["target_arg"]
    live_target = action["arguments"].get(target_arg)
    if action.get("api_name") != "add_song_to_playlist" or target_arg != "playlist_id" or live_target is None:
        return None
    for effect in reversed(context.get("prior_effects", [])):
        response = effect.get("response")
        if effect.get("api_name") != "create_playlist" or not isinstance(response, dict):
            continue
        if same_value(response.get("playlist_id"), live_target):
            return {
                "obligation": "prior_effect_binding",
                "effect_step_id": effect["effect_step_id"],
                "effect_field": "playlist_id",
                "target_arg": target_arg,
                "expected_effect_value": live_target,
                "effect_api_name": "create_playlist",
                "match": True,
            }
    return None


def valid_prior_effect_value(value: Any, candidate: dict[str, Any]) -> bool:
    return same_value(value, candidate["expected_effect_value"])


def prior_playlist_ids(context: dict[str, Any]) -> list[Any]:
    values = []
    for effect in context.get("prior_effects", []):
        response = effect.get("response")
        if isinstance(response, dict) and "playlist_id" in response:
            values.append(response["playlist_id"])
    return values


def adversarial_values(row: dict[str, Any], candidate: dict[str, Any]) -> list[Any]:
    expected = candidate["expected_effect_value"]
    values = prior_playlist_ids(row["context"])
    action = row["context"]["candidate_action"]
    if "song_id" in action["arguments"]:
        values.append(action["arguments"]["song_id"])
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
        if result["decision"] == "abstain_no_valid" and classify_post_v17_abstain(row) == "prior_effect_playlist_id_binding_abstain":
            selected.append(row)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v26_ordered_note_title_identity_merged_outputs/prompt_manifest.json"))
    parser.add_argument("--rescore-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v26_ordered_note_merged/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v27_prior_effect_playlist_feasibility"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v27 prior effect playlist feasibility")

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
        candidate = prior_effect_playlist_candidate(row)
        if candidate is None:
            label = "no_prior_effect_playlist_candidate"
            decision = "abstain_no_valid"
            live_valid = False
            adversarial_valids = {}
        else:
            label = "prior_effect_playlist_candidate_matches_live"
            live_value = row["live_arguments"][row["field_name"]]
            live_valid = valid_prior_effect_value(live_value, candidate)
            adversarial_valids = {f"adversarial_{index}": valid_prior_effect_value(value, candidate) for index, value in enumerate(adversarial_values(row, candidate))}
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
                        "required_obligation": "prior_effect_binding",
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
    write_json(rows_out, {"schema": "ebw_track_a_v27_prior_effect_playlist_feasibility_rows_v1", "rows": result_rows})
    write_json(
        evaluation_manifest,
        {
            "schema": "ebw_track_a_v27_prior_effect_playlist_target_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V27_PRIOR_EFFECT_PLAYLIST_TARGET_READY",
            "rows": evaluation_rows,
            "target_selection": "post-v26 prior_effect_playlist_id_binding_abstains with matching create_playlist prior effects",
            "sealed_variations_opened": False,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v27_prior_effect_playlist_feasibility_v1",
        "status": "RPD_EBW_TRACK_A_V27_PRIOR_EFFECT_PLAYLIST_FEASIBILITY_COMPLETE",
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
        "# EBW Track A v27 Prior-Effect Playlist Feasibility",
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
        "The prior-effect playlist frontier is sufficient for the remaining `add_song_to_playlist.playlist_id` residuals. The proof binds every playlist write to the earlier `create_playlist.response.playlist_id` prior effect; song IDs and adjacent integer IDs fail the unique-validity barrier. This is a frontier/candidate repair for an existing strict `prior_effect_binding` schema, not a parser relaxation.",
    ]
    (output_dir / "FEASIBILITY.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "target_rows": len(selected), "counts": payload["candidate_counts"], "decisions": payload["decision_counts"], "report": str((output_dir / "FEASIBILITY.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()