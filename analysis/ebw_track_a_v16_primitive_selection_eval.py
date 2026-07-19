"""Evaluate primitive-selection outputs by deterministic compilation and MetaVerifier."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v12_repairagent_metaverifier import contract_failure_modes, load_json, metaverify, resolve, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]

TEMPLATE_TARGETS = {
    "template.frontier_grammar.title_slug_export_path_binding": "title_slug_export_path_binding_missing",
    "template.response_contract.output_obligation_key": "output_contract_obligation_key_leakage",
}

PRIMITIVE_VALUES = {
    "source_binding.latest_matching_pre_write_show_note": ("source_binding", "latest_matching_pre_write_show_note"),
    "source_binding.any_matching_show_note_content": ("source_binding", "any_matching_show_note_content"),
    "source_binding.read_group_same_rank": ("source_binding", "read_group_same_rank"),
    "slug_transform.whitespace_to_underscore": ("slug_transform", "whitespace_to_underscore"),
    "slug_transform.lowercase_first_letter": ("slug_transform", "lowercase_first_letter"),
    "destination_directory.task_literal_backup_directory": ("destination_directory_rule_id", "task_literal_backup_directory"),
    "destination_directory.dir_rule_001": ("destination_directory_rule_id", "DIR_RULE_001"),
    "extension.md_dot": ("extension", ".md"),
    "extension.md_no_dot": ("extension", "md"),
    "response_contract.require_obligation_forbid_required_obligation": ("response_contract", {"required_key": "obligation", "forbidden_keys": ["required_obligation"]}),
    "response_contract.require_required_obligation": ("response_contract", {"required_key": "required_obligation", "forbidden_keys": ["omitted_obligation"]}),
    "parser_policy.strict": ("parser_policy", "strict_json_no_regex_repair"),
    "parser_policy.tolerant_alias": ("parser_policy", "tolerant_alias_repair"),
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
    if value["template_id"] not in TEMPLATE_TARGETS:
        return SelectionParse(False, None, "unknown template_id")
    if not isinstance(value["selected_primitives"], list) or not all(isinstance(item, str) and item in PRIMITIVE_VALUES for item in value["selected_primitives"]):
        return SelectionParse(False, None, "selected_primitives must be known primitive id list")
    return SelectionParse(True, value, None)


def load_artifacts() -> dict[str, Any]:
    root = Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1")
    paths = {
        "title_slug_feasibility_v1": resolve(root / "track_a_v11_title_slug_feasibility/feasibility.json"),
        "title_slug_feasibility_v2": resolve(root / "track_a_v11_title_slug_feasibility_v2/feasibility.json"),
        "v11_model_results": resolve(root / "track_a_model_run_v11_title_slug_target/results.json"),
        "v11_model_rows": resolve(root / "track_a_model_run_v11_title_slug_target/rows.json"),
        "v11_model_raw": resolve(root / "track_a_model_run_v11_title_slug_target/raw_model_outputs.json"),
        "v11b_retry_results": resolve(root / "track_a_model_run_v11b_contract_retry/results.json"),
        "v11b_full_results": resolve(root / "track_a_rescore_full_opened_v11b_merged/results.json"),
    }
    return {
        "title_slug_feasibility_v1": load_json(paths["title_slug_feasibility_v1"]),
        "title_slug_feasibility_v2": load_json(paths["title_slug_feasibility_v2"]),
        "v11_title_slug_model": load_json(paths["v11_model_results"]),
        "v11b_contract_retry": load_json(paths["v11b_retry_results"]),
        "v11b_full_gate": load_json(paths["v11b_full_results"]),
        "contract_failure_modes": contract_failure_modes(paths["v11_model_raw"], paths["v11_model_rows"]),
    }


def compile_selection(selection: dict[str, Any], residual_class: str) -> tuple[dict[str, Any] | None, str | None]:
    template_id = selection["template_id"]
    if TEMPLATE_TARGETS[template_id] != residual_class:
        return None, "template_residual_mismatch"
    slots: dict[str, Any] = {}
    for primitive_id in selection["selected_primitives"]:
        key, value = PRIMITIVE_VALUES[primitive_id]
        if key == "response_contract":
            slots.update(value)
        else:
            slots[key] = value
    if template_id == "template.frontier_grammar.title_slug_export_path_binding":
        required = ["source_binding", "slug_transform", "destination_directory_rule_id", "extension", "parser_policy"]
        missing = [key for key in required if key not in slots]
        if missing:
            return None, "missing_slots:" + ",".join(missing)
        return {
            "proposal_id": "compiled_" + selection["residual_id"],
            "target_residual": residual_class,
            "patch_type": "frontier_grammar",
            "source_binding": slots["source_binding"],
            "slug_transform": slots["slug_transform"],
            "destination_directory_rule_id": slots["destination_directory_rule_id"],
            "extension": slots["extension"],
            "parser_policy": slots["parser_policy"],
        }, None
    if template_id == "template.response_contract.output_obligation_key":
        required = ["required_key", "forbidden_keys", "parser_policy"]
        missing = [key for key in required if key not in slots]
        if missing:
            return None, "missing_slots:" + ",".join(missing)
        return {
            "proposal_id": "compiled_" + selection["residual_id"],
            "target_residual": residual_class,
            "patch_type": "response_contract",
            "required_key": slots["required_key"],
            "forbidden_keys": slots["forbidden_keys"],
            "parser_policy": slots["parser_policy"],
        }, None
    return None, "unsupported_template"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v16_primitive_selection_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--raw-outputs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v16 primitive-selection eval output")
    manifest_path = resolve(args.prompt_manifest)
    raw_path = resolve(args.raw_outputs)
    manifest = load_json(manifest_path)
    raw = load_json(raw_path)
    rows_by_id = {row["residual_id"]: row for row in manifest["rows"]}
    artifacts = load_artifacts()
    rows = []
    accepted = []
    parse_ok = 0
    compile_ok = 0
    for raw_row in raw["rows"]:
        row = rows_by_id[raw_row["residual_id"]]
        parsed = parse_selection(raw_row["output"])
        if not parsed.ok or parsed.selection is None:
            result = {"accepted": False, "reason": "parse_error", "checks": {"message": parsed.message}, "proposal_id": None}
            proposal = None
            compile_error = None
        else:
            parse_ok += 1
            proposal, compile_error = compile_selection(parsed.selection, row["residual_class"])
            if proposal is None:
                result = {"accepted": False, "reason": "compile_error", "checks": {"message": compile_error}, "proposal_id": None}
            else:
                compile_ok += 1
                result = metaverify(proposal, artifacts)
        if result["accepted"]:
            accepted.append(result["proposal_id"])
        rows.append({"residual_id": row["residual_id"], "residual_class": row["residual_class"], "parse_ok": parsed.ok, "selection": parsed.selection, "compiled_proposal": proposal, "compile_error": compile_error, "metaverifier_result": result})
    output_dir.mkdir(parents=True)
    rows_path = output_dir / "rows.json"
    write_json(rows_path, {"schema": "ebw_track_a_v16_primitive_selection_eval_rows_v1", "rows": rows})
    payload = {
        "schema": "ebw_track_a_v16_primitive_selection_eval_v1",
        "status": "RPD_EBW_TRACK_A_V16_PRIMITIVE_SELECTION_EVAL_COMPLETE",
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
        "# EBW Track A v16 Primitive Selection Eval",
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