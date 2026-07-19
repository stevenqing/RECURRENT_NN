"""Build a CPU-only residual taxonomy after the v10 full executable gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v9_path_pair_feasibility import path_pair_candidate

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


def normalize_reason(reason: str) -> str:
    if "missing_ordered_role_candidate" in reason:
        return "coverage_ordered_role_candidate_missing"
    if "missing_required_literal_span" in reason:
        return "coverage_literal_span_missing"
    if "required_literal_span_not_live_value" in reason:
        return "coverage_literal_span_ordinal_not_live"
    return "coverage_other"


def classify_post_v10_abstain(row: dict[str, Any]) -> str:
    obligation = str(row.get("required_obligation"))
    task_text = row["context"]["task_text"].casefold()
    field_name = str(row.get("field_name"))
    candidate = path_pair_candidate(row) if obligation == "derived_path_binding" else None
    if obligation == "derived_path_binding":
        if field_name == "source_file_path":
            return "source_path_identity_binding_missing"
        if "note title" in task_text and "replacing white space" in task_text:
            return "title_slug_export_path_binding_missing"
        if "compress" in task_text and "<vacation_spot>" in task_text:
            return "directory_basename_archive_path_binding_missing"
        if "spotify" in task_text and "csv" in task_text and "export" in task_text:
            return "literal_export_path_binding_missing"
        if candidate is None:
            return "derived_path_no_path_pair_candidate"
        if not candidate["match"]:
            return "derived_path_path_pair_mismatch_safe_abstain"
        return "derived_path_other_abstain"
    if obligation == "prior_effect_binding":
        return "prior_effect_playlist_membership_binding_abstain"
    if obligation == "ordered_role_binding":
        return "ordered_note_identity_binding_abstain"
    return f"{obligation}_abstain"


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_full_merged_outputs/prompt_manifest.json"))
    parser.add_argument("--merged-rescore-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v10_merged/rows.json"))
    parser.add_argument("--full-v8-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_full_opened_v8_executable/prompt_manifest.json"))
    parser.add_argument("--full-v10-rebuilt-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_full_opened_v10_executable/prompt_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_residual_taxonomy"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v11 residual taxonomy")

    merged_manifest_path = resolve(args.merged_prompt_manifest)
    rescore_rows_path = resolve(args.merged_rescore_rows)
    full_v8_manifest_path = resolve(args.full_v8_prompt_manifest)
    full_v10_rebuilt_path = resolve(args.full_v10_rebuilt_prompt_manifest)
    merged_rows = load_json(merged_manifest_path)["rows"]
    rescore_rows = load_json(rescore_rows_path)["rows"]
    full_v8_manifest = load_json(full_v8_manifest_path)
    full_v10_rebuilt = load_json(full_v10_rebuilt_path)
    merged_by_id = {row["instance_id"]: row for row in merged_rows}

    decision_counts: Counter[str] = Counter(row["decision"] for row in rescore_rows)
    decision_by_obligation: dict[str, Counter[str]] = defaultdict(Counter)
    post_v10_residual_counts: Counter[str] = Counter()
    post_v10_residual_by_task: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in rescore_rows:
        row = merged_by_id[result["instance_id"]]
        obligation = str(row.get("required_obligation"))
        decision_by_obligation[result["decision"]][obligation] += 1
        if result["decision"] == "abstain_no_valid":
            label = classify_post_v10_abstain(row)
            post_v10_residual_counts[label] += 1
            post_v10_residual_by_task[label][row["task_id"]] += 1
            if len(samples[label]) < 3:
                samples[label].append(sample_row(row))

    coverage_skip_counts: Counter[str] = Counter()
    coverage_skip_by_task: dict[str, Counter[str]] = defaultdict(Counter)
    for skipped in full_v8_manifest.get("skipped_rows", []):
        label = normalize_reason(skipped.get("reason", ""))
        coverage_skip_counts[label] += 1
        coverage_skip_by_task[label][skipped.get("task_id", "unknown")] += 1

    rebuild_skip_counts: Counter[str] = Counter(normalize_reason(skipped.get("reason", "")) for skipped in full_v10_rebuilt.get("skipped_rows", []))

    recommended_targets = [
        {
            "rank": 1,
            "target": "title_slug_export_path_binding",
            "residual_source": "post_v10_abstain",
            "covered_rows_now": post_v10_residual_counts.get("title_slug_export_path_binding_missing", 0),
            "why": "A deterministic transform from immutable note title to backup file path: replace whitespace with underscores, choose task-specified directory, append .md. This is a clean text-gradient target and less likely to be dismissed as path punctuation normalization.",
            "gate": "CPU feasibility over Simple Note export abstains, then model-facing proof synthesis, then merged full-executable rescore.",
        },
        {
            "rank": 2,
            "target": "ordered_role_candidate_repair",
            "residual_source": "coverage_skip",
            "covered_rows_now": coverage_skip_counts.get("coverage_ordered_role_candidate_missing", 0),
            "why": "Largest remaining coverage gap. Needs relation/cursor candidate construction rather than another prompt rule, so it tests whether RepairAgent can ask for a new frontier primitive.",
            "gate": "Development-only candidate frontier feasibility before any model run; residual_shuffled control should fail.",
        },
        {
            "rank": 3,
            "target": "literal_span_sequence_binding",
            "residual_source": "coverage_skip",
            "covered_rows_now": coverage_skip_counts.get("coverage_literal_span_missing", 0) + coverage_skip_counts.get("coverage_literal_span_ordinal_not_live", 0),
            "why": "Directly tests typed residuals for task-text evidence binding across multi-write instructions. Good control against prompt-only repair because the barrier can require exact span/ordinal evidence.",
            "gate": "Build deterministic span-sequence candidates, then compare RepairAgent patch against prompt-only and residual-shuffled controls.",
        },
        {
            "rank": 4,
            "target": "directory_basename_archive_path_binding",
            "residual_source": "post_v10_abstain",
            "covered_rows_now": post_v10_residual_counts.get("directory_basename_archive_path_binding_missing", 0),
            "why": "Small but clean filesystem proof family: directory basename determines archive basename and task-specified extension/destination directory.",
            "gate": "CPU feasibility only unless bundled with title_slug_export_path_binding.",
        },
    ]

    payload = {
        "schema": "ebw_track_a_v11_residual_taxonomy_v1",
        "status": "RPD_EBW_TRACK_A_V11_RESIDUAL_TAXONOMY_COMPLETE",
        "decision_counts": dict(sorted(decision_counts.items())),
        "decision_by_obligation": {key: dict(sorted(counter.items())) for key, counter in sorted(decision_by_obligation.items())},
        "post_v10_residual_counts": dict(sorted(post_v10_residual_counts.items())),
        "post_v10_residual_by_task": {key: dict(counter.most_common()) for key, counter in sorted(post_v10_residual_by_task.items())},
        "coverage_skip_counts": dict(sorted(coverage_skip_counts.items())),
        "coverage_skip_by_task_top10": {key: dict(counter.most_common(10)) for key, counter in sorted(coverage_skip_by_task.items())},
        "rebuilt_v10_prompt_skip_counts": dict(sorted(rebuild_skip_counts.items())),
        "samples": dict(samples),
        "recommended_targets": recommended_targets,
        "merged_prompt_manifest_sha256": file_hash(merged_manifest_path),
        "merged_rescore_rows_sha256": file_hash(rescore_rows_path),
        "full_v8_prompt_manifest_sha256": file_hash(full_v8_manifest_path),
        "full_v10_rebuilt_prompt_manifest_sha256": file_hash(full_v10_rebuilt_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    output_dir.mkdir(parents=True)
    write_json(output_dir / "taxonomy.json", payload)

    report = [
        "# EBW Track A v11 Residual Taxonomy",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        "- Scope: CPU-only taxonomy after v10 full executable compositional gate",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## v10 Full-Executable Decisions",
        "",
        "| Decision | Rows |",
        "|---|---:|",
    ]
    report += [f"| `{key}` | {value} |" for key, value in sorted(decision_counts.items())]
    report += ["", "## Post-v10 Abstain Residuals", "", "| Residual class | Rows |", "|---|---:|"]
    report += [f"| `{key}` | {value} |" for key, value in sorted(post_v10_residual_counts.items(), key=lambda item: (-item[1], item[0]))]
    report += ["", "## Coverage Skips From Full-v8 Executable Scope", "", "| Residual class | Rows |", "|---|---:|"]
    report += [f"| `{key}` | {value} |" for key, value in sorted(coverage_skip_counts.items(), key=lambda item: (-item[1], item[0]))]
    report += ["", "## Recommended RepairAgent Benchmark Targets", ""]
    for target in recommended_targets:
        report += [
            f"### {target['rank']}. `{target['target']}`",
            "",
            f"- Residual source: `{target['residual_source']}`",
            f"- Rows currently exposed: {target['covered_rows_now']}",
            f"- Why: {target['why']}",
            f"- Gate: {target['gate']}",
            "",
        ]
    report += [
        "## Research Interpretation",
        "",
        "The next research step should not be another v10 score chase. The v10 gate already solved the diagnosed unsafe class. The useful contribution is a repair benchmark where typed residuals propose new frontier primitives, a MetaVerifier rejects prompt-only shortcuts, and controls show that shuffled or family-mismatched residuals do not repair the gate.",
    ]
    (output_dir / "TAXONOMY.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "report": str((output_dir / "TAXONOMY.md").relative_to(REPO_ROOT)), "post_v10_residual_counts": payload["post_v10_residual_counts"], "coverage_skip_counts": payload["coverage_skip_counts"]}))


if __name__ == "__main__":
    main()