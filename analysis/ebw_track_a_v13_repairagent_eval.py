"""Evaluate RepairAgent patch proposals with the v12 MetaVerifier."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v12_repairagent_metaverifier import contract_failure_modes, load_json, metaverify, resolve, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]

SCHEMA_KEYS: dict[str, set[str]] = {
    "frontier_grammar": {"proposal_id", "target_residual", "patch_type", "source_binding", "slug_transform", "destination_directory_rule_id", "extension", "parser_policy"},
    "response_contract": {"proposal_id", "target_residual", "patch_type", "required_key", "forbidden_keys", "parser_policy"},
    "parser_repair": {"proposal_id", "target_residual", "patch_type", "allow_key_alias", "parser_policy"},
    "prompt_only": {"proposal_id", "target_residual", "patch_type", "parser_policy"},
}


@dataclass(frozen=True)
class ProposalParse:
    ok: bool
    proposal: dict[str, Any] | None
    message: str | None


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_patch_proposal(raw: str | dict[str, Any]) -> ProposalParse:
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            return ProposalParse(False, None, f"json_decode: {error.msg}")
    else:
        value = dict(raw)
    if not isinstance(value, dict):
        return ProposalParse(False, None, "proposal must be object")
    patch_type = value.get("patch_type")
    if patch_type not in SCHEMA_KEYS:
        return ProposalParse(False, None, "unknown patch_type")
    if set(value) != SCHEMA_KEYS[patch_type]:
        return ProposalParse(False, None, "keys must exactly match patch_type schema")
    for key in ["proposal_id", "target_residual", "patch_type", "parser_policy"]:
        if not isinstance(value.get(key), str) or not value[key].strip():
            return ProposalParse(False, None, f"{key} must be nonempty string")
    if patch_type == "frontier_grammar":
        for key in ["source_binding", "slug_transform", "destination_directory_rule_id", "extension"]:
            if not isinstance(value.get(key), str) or not value[key].strip():
                return ProposalParse(False, None, f"{key} must be nonempty string")
    if patch_type == "response_contract":
        if not isinstance(value.get("required_key"), str) or not value["required_key"].strip():
            return ProposalParse(False, None, "required_key must be nonempty string")
        if not isinstance(value.get("forbidden_keys"), list) or not all(isinstance(item, str) and item for item in value["forbidden_keys"]):
            return ProposalParse(False, None, "forbidden_keys must be list of strings")
    if patch_type == "parser_repair" and not isinstance(value.get("allow_key_alias"), dict):
        return ProposalParse(False, None, "allow_key_alias must be object")
    return ProposalParse(True, value, None)


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v13_repairagent_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--raw-outputs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v13 RepairAgent eval output")

    manifest_path = resolve(args.prompt_manifest)
    raw_path = resolve(args.raw_outputs)
    manifest = load_json(manifest_path)
    raw = load_json(raw_path)
    rows_by_residual = {row["residual_id"]: row for row in manifest["rows"]}
    artifacts = load_artifacts()
    rows = []
    accepted = []
    parse_ok = 0
    for raw_row in raw["rows"]:
        row = rows_by_residual[raw_row["residual_id"]]
        parsed = parse_patch_proposal(raw_row["output"])
        if not parsed.ok or parsed.proposal is None:
            result = {"accepted": False, "reason": "parse_error", "checks": {"message": parsed.message}, "proposal_id": None}
        else:
            parse_ok += 1
            result = metaverify(parsed.proposal, artifacts)
        if result["accepted"]:
            accepted.append(result["proposal_id"])
        rows.append({"residual_id": row["residual_id"], "residual_class": row["residual_class"], "parse_ok": parsed.ok, "metaverifier_result": result})

    output_dir.mkdir(parents=True)
    rows_path = output_dir / "rows.json"
    write_json(rows_path, {"schema": "ebw_track_a_v13_repairagent_eval_rows_v1", "rows": rows})
    payload = {
        "schema": "ebw_track_a_v13_repairagent_eval_v1",
        "status": "RPD_EBW_TRACK_A_V13_REPAIRAGENT_EVAL_COMPLETE",
        "processed": len(rows),
        "parse_rate": parse_ok / max(1, len(rows)),
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
        "# EBW Track A v13 RepairAgent Eval",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Processed: {len(rows)}",
        f"- Parse rate: {payload['parse_rate']:.3f}",
        f"- Accepted proposals: {accepted}",
        "- Sealed variations 10-12 opened: No",
        "",
        "## Rows",
        "",
        "| Residual | Parse OK | Accepted | Reason |",
        "|---|---:|---:|---|",
    ]
    for row in rows:
        result = row["metaverifier_result"]
        report.append(f"| `{row['residual_id']}` | {row['parse_ok']} | {result['accepted']} | `{result['reason']}` |")
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "processed": len(rows), "accepted": accepted, "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()