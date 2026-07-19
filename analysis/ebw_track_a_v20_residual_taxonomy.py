"""CPU-only residual taxonomy after the v17 full executable gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

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


def classify_post_v17_abstain(row: dict[str, Any]) -> str:
    obligation = str(row.get("required_obligation"))
    task_text = row["context"]["task_text"].casefold()
    field_name = str(row.get("field_name"))
    action = row["context"]["candidate_action"]
    api_name = str(action.get("api_name"))
    target_arg = str(action.get("target_arg"))
    if obligation == "derived_path_binding":
        if api_name == "move_file" and field_name == "source_file_path" and target_arg == "source_file_path":
            return "source_path_identity_binding_missing"
        if api_name == "create_file" and "spotify" in task_text and "csv" in task_text and "export" in task_text:
            return "literal_export_path_binding_missing"
        return "derived_path_remaining_abstain"
    if obligation == "prior_effect_binding":
        if api_name == "add_song_to_playlist" and field_name == "playlist_id":
            return "prior_effect_playlist_id_binding_abstain"
        return "prior_effect_remaining_abstain"
    if obligation == "ordered_role_binding":
        if api_name == "update_note" and field_name == "note_id":
            return "ordered_note_title_identity_binding_abstain"
        return "ordered_role_remaining_abstain"
    return f"{obligation}_remaining_abstain"


def sample_row(row: dict[str, Any]) -> dict[str, Any]:
    action = row["context"]["candidate_action"]
    return {
        "instance_id": row["instance_id"],
        "task_id": row["task_id"],
        "required_obligation": row.get("required_obligation"),
        "field_name": row.get("field_name"),
        "api_name": action.get("api_name"),
        "method": action.get("method"),
        "target_arg": action.get("target_arg"),
        "task_text_snippet": row["context"]["task_text"][:240],
    }


def recommended_targets(counts: Counter[str]) -> list[dict[str, Any]]:
    return [
        {
            "rank": 1,
            "target": "source_path_identity_binding",
            "residual_class": "source_path_identity_binding_missing",
            "rows": counts.get("source_path_identity_binding_missing", 0),
            "why": "Small, clean complement to path-pair repair: move_file.source_file_path should be proven by immutable source path evidence, not by destination path grammar. It is likely CPU-feasible and keeps the proof-family progression coherent.",
            "gate": "Build deterministic source-path identity candidates over the 5 move_file source_file_path abstains; require exact source path evidence and path-shaped adversaries fail.",
        },
        {
            "rank": 2,
            "target": "literal_export_path_binding",
            "residual_class": "literal_export_path_binding_missing",
            "rows": counts.get("literal_export_path_binding_missing", 0),
            "why": "Very small but clean task-text literal path proof: backup CSV path is quoted in the user instruction. Good parser/control exercise after source identity.",
            "gate": "Bind quoted file path literal span to create_file.file_path with exact span evidence and adversarial path alternatives.",
        },
        {
            "rank": 3,
            "target": "ordered_note_title_identity_binding",
            "residual_class": "ordered_note_title_identity_binding_abstain",
            "rows": counts.get("ordered_note_title_identity_binding_abstain", 0),
            "why": "Tests relation between quoted task item and Simple Note identity. Small count but more semantically meaningful than literal path extraction.",
            "gate": "Bind quoted bucket-list item to a note whose content/title contains that item before patching note_id.",
        },
        {
            "rank": 4,
            "target": "prior_effect_playlist_id_binding",
            "residual_class": "prior_effect_playlist_id_binding_abstain",
            "rows": counts.get("prior_effect_playlist_id_binding_abstain", 0),
            "why": "Largest remaining post-v17 abstain class, but likely needs relation between newly created playlist effect and multiple subsequent add_song_to_playlist writes; tackle after simpler identity/literal proofs clarify the residual protocol.",
            "gate": "Audit prior_effect rows to distinguish missing effect binding from ambiguity under repeated playlist_id use before model calls.",
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v17_full_merged_outputs/prompt_manifest.json"))
    parser.add_argument("--rescore-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v17_merged/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v20_residual_taxonomy"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v20 residual taxonomy")

    manifest_path = resolve(args.prompt_manifest)
    rows_path = resolve(args.rescore_rows)
    manifest = load_json(manifest_path)
    rescore_rows = load_json(rows_path)
    by_id = {row["instance_id"]: row for row in manifest["rows"]}
    decision_counts: Counter[str] = Counter(row["decision"] for row in rescore_rows["rows"])
    decision_by_obligation: dict[str, Counter[str]] = defaultdict(Counter)
    residual_counts: Counter[str] = Counter()
    residual_by_task: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in rescore_rows["rows"]:
        row = by_id[result["instance_id"]]
        obligation = str(row.get("required_obligation"))
        decision_by_obligation[result["decision"]][obligation] += 1
        if result["decision"] != "abstain_no_valid":
            continue
        label = classify_post_v17_abstain(row)
        residual_counts[label] += 1
        residual_by_task[label][row["task_id"]] += 1
        if len(samples[label]) < 3:
            samples[label].append(sample_row(row))
    targets = recommended_targets(residual_counts)
    payload = {
        "schema": "ebw_track_a_v20_residual_taxonomy_v1",
        "status": "RPD_EBW_TRACK_A_V20_RESIDUAL_TAXONOMY_COMPLETE",
        "decision_counts": dict(sorted(decision_counts.items())),
        "decision_by_obligation": {key: dict(sorted(value.items())) for key, value in sorted(decision_by_obligation.items())},
        "post_v17_residual_counts": dict(sorted(residual_counts.items())),
        "post_v17_residual_by_task": {key: dict(counter.most_common()) for key, counter in sorted(residual_by_task.items())},
        "samples": dict(samples),
        "recommended_targets": targets,
        "prompt_manifest_sha256": file_hash(manifest_path),
        "rescore_rows_sha256": file_hash(rows_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    output_dir.mkdir(parents=True)
    write_json(output_dir / "taxonomy.json", payload)
    report = [
        "# EBW Track A v20 Residual Taxonomy",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        "- Scope: CPU-only taxonomy after v17 full executable compositional gate",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## v17 Full-Executable Decisions",
        "",
        "| Decision | Rows |",
        "|---|---:|",
    ]
    report += [f"| `{key}` | {value} |" for key, value in sorted(decision_counts.items())]
    report += ["", "## Remaining Abstain Residuals", "", "| Residual class | Rows |", "|---|---:|"]
    report += [f"| `{key}` | {value} |" for key, value in sorted(residual_counts.items(), key=lambda item: (-item[1], item[0]))]
    report += ["", "## Recommended Next Proof Families", ""]
    for target in targets:
        report += [
            f"### {target['rank']}. `{target['target']}`",
            "",
            f"- Residual class: `{target['residual_class']}`",
            f"- Rows: {target['rows']}",
            f"- Why: {target['why']}",
            f"- Gate: {target['gate']}",
            "",
        ]
    report += [
        "## Research Interpretation",
        "",
        "The remaining v17 abstentions are safe frontier gaps, not safety failures. The next best CPU-first proof family is source-path identity binding for move_file.source_file_path, because it is a direct complement to the destination path-pair grammar and should be decidable from immutable source path evidence. The largest remaining class is prior-effect playlist binding, but it likely needs relation/cursor reasoning over repeated writes and should be handled after simpler identity/literal frontiers are exhausted.",
    ]
    (output_dir / "TAXONOMY.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "residual_counts": payload["post_v17_residual_counts"], "report": str((output_dir / "TAXONOMY.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()