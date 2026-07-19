"""Evaluate held-out free-form RepairAgent patch proposals."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v33_heldout_ttc_eval import candidate_for, proposal_slots_ok, verify_candidate

REPO_ROOT = Path(__file__).resolve().parents[1]

SCHEMA_KEYS = {
    "frontier_candidate": {"proposal_id", "target_residual", "patch_type", "span_source", "target_arg", "parser_policy"},
    "parser_repair": {"proposal_id", "target_residual", "patch_type", "allow_key_alias", "parser_policy"},
    "prompt_only": {"proposal_id", "target_residual", "patch_type", "parser_policy"},
}


@dataclass(frozen=True)
class PatchParse:
    ok: bool
    proposal: dict[str, Any] | None
    message: str | None


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def parse_freeform_patch(raw: str | dict[str, Any]) -> PatchParse:
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            return PatchParse(False, None, f"json_decode: {error.msg}")
    else:
        value = dict(raw)
    if not isinstance(value, dict):
        return PatchParse(False, None, "proposal must be object")
    patch_type = value.get("patch_type")
    if patch_type not in SCHEMA_KEYS:
        return PatchParse(False, None, "unknown patch_type")
    if set(value) != SCHEMA_KEYS[patch_type]:
        return PatchParse(False, None, "keys must exactly match patch_type schema")
    for key in ["proposal_id", "target_residual", "patch_type", "parser_policy"]:
        if not isinstance(value.get(key), str) or not value[key].strip():
            return PatchParse(False, None, f"{key} must be nonempty string")
    if patch_type == "frontier_candidate":
        for key in ["span_source", "target_arg"]:
            if not isinstance(value.get(key), str) or not value[key].strip():
                return PatchParse(False, None, f"{key} must be nonempty string")
    if patch_type == "parser_repair" and not isinstance(value.get("allow_key_alias"), dict):
        return PatchParse(False, None, "allow_key_alias must be object")
    return PatchParse(True, value, None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v35_heldout_freeform_repair_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--raw-outputs", type=Path, required=True)
    parser.add_argument("--base-prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v32_heldout_prompt_manifest_no_repair/prompt_manifest.json"))
    parser.add_argument("--baseline-rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v32_heldout_no_repair/rows.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v35 held-out free-form repair eval")
    manifest_path = resolve(args.prompt_manifest)
    raw_path = resolve(args.raw_outputs)
    base_manifest_path = resolve(args.base_prompt_manifest)
    baseline_rows_path = resolve(args.baseline_rows)
    manifest = load_json(manifest_path)
    raw = load_json(raw_path)
    base_manifest = load_json(base_manifest_path)
    baseline_rows = load_json(baseline_rows_path)["rows"]
    prompt_by_id = {row["residual_id"]: row for row in manifest["rows"]}
    base_by_id = {row["instance_id"]: row for row in base_manifest["rows"]}
    noncommit_rows = [base_by_id[row["instance_id"]] for row in baseline_rows if row["decision"] != "commit_live"]
    rows = []
    accepted = []
    parse_ok = 0
    for raw_row in raw["rows"]:
        prompt_row = prompt_by_id[raw_row["residual_id"]]
        parsed = parse_freeform_patch(raw_row["output"])
        target_rows = []
        if not parsed.ok or parsed.proposal is None:
            result = {"accepted": False, "reason": "parse_error", "checks": {"message": parsed.message}, "proposal_id": None}
        else:
            parse_ok += 1
            proposal = parsed.proposal
            if proposal["target_residual"] != prompt_row["residual_class"]:
                result = {"accepted": False, "reason": "rejected_residual_family_mismatch", "checks": {}, "proposal_id": proposal["proposal_id"], "proposal": proposal}
            elif proposal["patch_type"] != "frontier_candidate":
                result = {"accepted": False, "reason": "rejected_wrong_patch_type", "checks": {"patch_type": proposal["patch_type"]}, "proposal_id": proposal["proposal_id"], "proposal": proposal}
            elif not proposal_slots_ok(proposal, prompt_row["residual_class"]):
                result = {"accepted": False, "reason": "rejected_wrong_or_relaxed_slots", "checks": {}, "proposal_id": proposal["proposal_id"], "proposal": proposal}
            else:
                decision_counts: dict[str, int] = {}
                for row in noncommit_rows:
                    candidate = candidate_for(row, prompt_row["residual_class"])
                    if candidate is None:
                        decision = "abstain_no_valid"
                    else:
                        decision, _verifier = verify_candidate(row, prompt_row["residual_class"], candidate)
                    decision_counts[decision] = decision_counts.get(decision, 0) + 1
                    target_rows.append({"instance_id": row["instance_id"], "task_id": row["task_id"], "decision": decision})
                accepted_result = decision_counts == {"commit_live": len(noncommit_rows)}
                result = {"accepted": accepted_result, "reason": "accepted_freeform_heldout_frontier" if accepted_result else "heldout_frontier_failed_gate", "checks": {"target_decision_counts": decision_counts, "target_rows": len(noncommit_rows)}, "proposal_id": proposal["proposal_id"], "proposal": proposal}
        if result["accepted"]:
            accepted.append(result["proposal_id"])
        rows.append({"residual_id": raw_row["residual_id"], "residual_class": prompt_row["residual_class"], "parse_ok": parsed.ok, "proposal": parsed.proposal, "target_rows": target_rows, "metaverifier_result": result})
    output_dir.mkdir(parents=True)
    rows_path = output_dir / "rows.json"
    write_json(rows_path, {"schema": "ebw_track_a_v35_freeform_repair_eval_rows_v1", "rows": rows})
    payload = {
        "schema": "ebw_track_a_v35_freeform_repair_eval_v1",
        "status": "RPD_EBW_TRACK_A_V35_HELDOUT_FREEFORM_REPAIR_EVAL_COMPLETE",
        "processed": len(rows),
        "parse_rate": parse_ok / max(1, len(rows)),
        "accepted_count": len(accepted),
        "accepted_proposals": accepted,
        "prompt_manifest_sha256": file_hash(manifest_path),
        "raw_outputs_sha256": file_hash(raw_path),
        "base_prompt_manifest_sha256": file_hash(base_manifest_path),
        "baseline_rows_sha256": file_hash(baseline_rows_path),
        "rows_sha256": file_hash(rows_path),
        "sealed_variations_opened": bool(manifest.get("sealed_variations_opened", False)),
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v35 Held-Out Free-Form Repair Eval",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Processed: {len(rows)}",
        f"- Parse rate: {payload['parse_rate']:.3f}",
        f"- Accepted proposals: {accepted}",
        "- Sealed variations 10-12 opened: Yes",
        "",
        "## Rows",
        "",
        "| Residual | Parse OK | Accepted | Reason |",
        "|---|---:|---:|---|",
    ]
    for row in rows:
        result = row["metaverifier_result"]
        report.append(f"| `{row['residual_class']}` | {row['parse_ok']} | {result['accepted']} | `{result['reason']}` |")
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "accepted_count": len(accepted), "accepted": accepted, "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()