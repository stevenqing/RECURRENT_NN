"""Evaluate archive primitive-selection outputs by deterministic compilation and v18 MetaVerifier."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v18_archive_structured_repair_policy import compile_archive_proposal, load_json, metaverify_archive, resolve, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]

TEMPLATE_ID = "template.frontier_grammar.directory_basename_archive_path_binding"
TARGET_RESIDUAL = "directory_basename_archive_path_binding_missing"
KNOWN_PRIMITIVES = {
    "source_binding.immutable_directory_list_entry",
    "source_binding.latest_matching_pre_write_show_note",
    "source_binding.generic_basename_projection",
    "basename_transform.directory_basename",
    "basename_transform.file_basename",
    "destination_template.task_literal_vacation_spot_archive_template",
    "destination_template.task_literal_backup_directory",
    "extension_policy.task_template_extension",
    "extension_policy.always_md",
    "parser_policy.strict",
    "parser_policy.tolerant_alias",
}


@dataclass(frozen=True)
class SelectionParse:
    ok: bool
    selection: dict[str, Any] | None
    message: str | None


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_selection(raw: str | dict[str, Any]) -> SelectionParse:
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            return SelectionParse(False, None, f"json_decode: {error.msg}")
    else:
        value = dict(raw)
    if not isinstance(value, dict):
        return SelectionParse(False, None, "selection must be object")
    if set(value) != {"residual_id", "template_id", "selected_primitives"}:
        return SelectionParse(False, None, "keys must exactly be residual_id, template_id, selected_primitives")
    if not isinstance(value["residual_id"], str) or not value["residual_id"].strip():
        return SelectionParse(False, None, "residual_id must be nonempty string")
    if value["template_id"] != TEMPLATE_ID:
        return SelectionParse(False, None, "unknown template_id")
    if not isinstance(value["selected_primitives"], list) or not all(isinstance(item, str) and item in KNOWN_PRIMITIVES for item in value["selected_primitives"]):
        return SelectionParse(False, None, "selected_primitives must be known primitive id list")
    return SelectionParse(True, value, None)


def compile_selection(selection: dict[str, Any], residual_class: str) -> tuple[dict[str, Any] | None, str | None]:
    if selection["template_id"] != TEMPLATE_ID or residual_class != TARGET_RESIDUAL:
        return None, "template_residual_mismatch"
    required = {
        "source_binding.immutable_directory_list_entry",
        "basename_transform.directory_basename",
        "destination_template.task_literal_vacation_spot_archive_template",
        "extension_policy.task_template_extension",
        "parser_policy.strict",
    }
    selected = set(selection["selected_primitives"])
    missing = sorted(required - selected)
    if missing:
        return None, "missing_primitives:" + ",".join(missing)
    proposal = compile_archive_proposal(
        {
            "residual_id": selection["residual_id"],
            "target_residual": residual_class,
            "template_id": selection["template_id"],
            "selected_primitives": selection["selected_primitives"],
        }
    )
    proposal["proposal_id"] = "compiled_" + selection["residual_id"]
    return proposal, None


def load_artifacts() -> dict[str, Any]:
    root = Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1")
    return {
        "feasibility": load_json(resolve(root / "track_a_v17_archive_path_feasibility/feasibility.json")),
        "model": load_json(resolve(root / "track_a_model_run_v17_archive_path_target/results.json")),
        "full": load_json(resolve(root / "track_a_rescore_full_opened_v17_merged/results.json")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v19_archive_selection_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--raw-outputs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v19 archive selection eval")
    manifest_path = resolve(args.prompt_manifest)
    raw_path = resolve(args.raw_outputs)
    manifest = load_json(manifest_path)
    raw = load_json(raw_path)
    row_by_id = {row["residual_id"]: row for row in manifest["rows"]}
    artifacts = load_artifacts()
    rows = []
    accepted = []
    parse_ok = compile_ok = 0
    for raw_row in raw["rows"]:
        row = row_by_id[raw_row["residual_id"]]
        parsed = parse_selection(raw_row["output"])
        if not parsed.ok or parsed.selection is None:
            proposal = None
            compile_error = None
            result = {"accepted": False, "reason": "parse_error", "checks": {"message": parsed.message}, "proposal_id": None}
        else:
            parse_ok += 1
            proposal, compile_error = compile_selection(parsed.selection, row["residual_class"])
            if proposal is None:
                result = {"accepted": False, "reason": "compile_error", "checks": {"message": compile_error}, "proposal_id": None}
            else:
                compile_ok += 1
                result = metaverify_archive(proposal, artifacts)
        if result["accepted"]:
            accepted.append(result["proposal_id"])
        rows.append({"residual_id": row["residual_id"], "residual_class": row["residual_class"], "parse_ok": parsed.ok, "selection": parsed.selection, "compiled_proposal": proposal, "compile_error": compile_error, "metaverifier_result": result})
    output_dir.mkdir(parents=True)
    rows_path = output_dir / "rows.json"
    write_json(rows_path, {"schema": "ebw_track_a_v19_archive_selection_eval_rows_v1", "rows": rows})
    payload = {
        "schema": "ebw_track_a_v19_archive_selection_eval_v1",
        "status": "RPD_EBW_TRACK_A_V19_ARCHIVE_SELECTION_EVAL_COMPLETE",
        "processed": len(rows),
        "parse_rate": parse_ok / max(1, len(rows)),
        "compile_rate": compile_ok / max(1, len(rows)),
        "accepted_proposals": accepted,
        "accepted_count": len(accepted),
        "prompt_manifest_sha256": file_hash(manifest_path),
        "raw_outputs_sha256": file_hash(raw_path),
        "rows_sha256": file_hash(rows_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v19 Archive Selection Eval",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Processed: {len(rows)}",
        f"- Parse rate: {payload['parse_rate']:.3f}",
        f"- Compile rate: {payload['compile_rate']:.3f}",
        f"- Accepted proposals: {accepted}",
        "- Sealed variations 10-12 opened: No",
        "",
        "## Rows",
        "",
        "| Residual | Parse OK | Compiled | Accepted | Reason |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows:
        result = row["metaverifier_result"]
        report.append(f"| `{row['residual_id']}` | {row['parse_ok']} | {row['compiled_proposal'] is not None} | {result['accepted']} | `{result['reason']}` |")
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "processed": len(rows), "accepted": accepted, "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()