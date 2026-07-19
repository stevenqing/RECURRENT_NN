"""Build the full executable v10 manifest from the full-v8 executable prompt manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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


def manifest_row(row: dict[str, Any], required_obligation: str) -> dict[str, Any]:
    action = row["context"]["candidate_action"]
    return {
        "instance_id": row["instance_id"],
        "task_id": row["task_id"],
        "call_index": row["call_index"],
        "field_name": row["field_name"],
        "proof_family": row["proof_family"],
        "method": action["method"],
        "app": action["app"],
        "api_name": action["api_name"],
        "required_obligation": required_obligation,
        "write_ordinal_for_schema": row["write_ordinal_for_schema"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_full_opened_v8_executable/prompt_manifest.json"))
    parser.add_argument("--source-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_full_opened_v8_executable/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_full_executable_manifest"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v10 full executable manifest")

    prompt_manifest_path = resolve(args.source_prompt_manifest)
    source_rows_path = resolve(args.source_rows)
    source_rows = {row["instance_id"]: row for row in load_json(source_rows_path)["rows"]}
    rows = load_json(prompt_manifest_path)["rows"]
    selected = []
    overrides = []
    coverage: Counter[str] = Counter()
    by_previous_decision: Counter[str] = Counter()
    output_obligations: Counter[str] = Counter()
    for row in rows:
        required_obligation = str(row["required_obligation"])
        if required_obligation == "derived_path_binding":
            candidate = path_pair_candidate(row)
            if candidate is None:
                coverage["derived_no_path_pair_candidate"] += 1
            elif candidate["match"]:
                coverage["derived_path_pair_match_override"] += 1
                previous = source_rows.get(row["instance_id"], {}).get("decision", "missing_source_decision")
                by_previous_decision[previous] += 1
                required_obligation = "path_pair_transform_binding"
                overrides.append({"instance_id": row["instance_id"], "task_id": row["task_id"], "previous_decision": previous})
            else:
                coverage["derived_path_pair_mismatch_keep_v8"] += 1
        else:
            coverage[f"keep_{required_obligation}"] += 1
        output_obligations[required_obligation] += 1
        selected.append(manifest_row(row, required_obligation))

    output_dir.mkdir(parents=True)
    evaluation_manifest = output_dir / "evaluation_manifest.json"
    write_json(
        evaluation_manifest,
        {
            "schema": "ebw_track_a_v10_full_executable_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V10_FULL_EXECUTABLE_MANIFEST_READY",
            "rows": selected,
            "target_selection": "full-v8 executable rows with only live-matching normalized path-pair candidates overridden to path_pair_transform_binding",
            "sealed_variations_opened": False,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v10_full_executable_manifest_summary_v1",
        "status": "RPD_EBW_TRACK_A_V10_FULL_EXECUTABLE_MANIFEST_READY",
        "rows": len(selected),
        "coverage_counts": dict(sorted(coverage.items())),
        "output_required_obligations": dict(sorted(output_obligations.items())),
        "path_pair_overrides_by_previous_decision": dict(sorted(by_previous_decision.items())),
        "path_pair_overrides": len(overrides),
        "source_prompt_manifest_sha256": file_hash(prompt_manifest_path),
        "source_rows_sha256": file_hash(source_rows_path),
        "evaluation_manifest_sha256": file_hash(evaluation_manifest),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "manifest.json", payload)
    write_json(output_dir / "overrides.json", {"schema": "ebw_track_a_v10_path_pair_overrides_v1", "rows": overrides})
    report = [
        "# EBW Track A v10 Full Executable Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(selected)}",
        f"- Path-pair overrides: {len(overrides)}",
        "- Target selection: full-v8 executable rows, overriding only live-matching normalized path-pair candidates",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Output Obligations",
        "",
        "| Obligation | Rows |",
        "|---|---:|",
    ]
    report += [f"| `{key}` | {value} |" for key, value in sorted(output_obligations.items())]
    report += ["", "## Override Source Decisions", "", "| Previous v8 decision | Rows |", "|---|---:|"]
    report += [f"| `{key}` | {value} |" for key, value in sorted(by_previous_decision.items())]
    report += [
        "",
        "## Interpretation",
        "",
        "This manifest preserves the v8 candidate-bound executable scope and changes only the derived-path rows whose normalized path-pair candidate matches the live destination. The override set is exactly the previously unsafe derived-path class, so this is a targeted full-executable rerun rather than a broader coverage claim.",
    ]
    (output_dir / "MANIFEST.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(selected), "path_pair_overrides": len(overrides), "report": str((output_dir / "MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()