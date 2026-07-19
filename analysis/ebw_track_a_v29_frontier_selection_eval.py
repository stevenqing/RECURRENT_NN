"""Evaluate v29 frontier-selection outputs by deterministic compilation and MetaVerifier."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v29_frontier_closure_repair_policy import compile_selection, load_artifacts, load_json, metaverify_frontier_closure, primitive_library, resolve, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SelectionParse:
    ok: bool
    selection: dict[str, Any] | None
    message: str | None


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def known_template_ids(library: dict[str, Any]) -> set[str]:
    return {template["id"] for template in library["patch_templates"]}


def known_primitive_ids(library: dict[str, Any]) -> set[str]:
    ids = set()
    for key, values in library.items():
        if key in {"schema", "patch_templates"}:
            continue
        ids.update(item["id"] for item in values)
    return ids


def parse_selection(raw: str | dict[str, Any], library: dict[str, Any] | None = None) -> SelectionParse:
    library = library or primitive_library()
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
    if value["template_id"] not in known_template_ids(library):
        return SelectionParse(False, None, "unknown template_id")
    if not isinstance(value["selected_primitives"], list) or not all(isinstance(item, str) and item in known_primitive_ids(library) for item in value["selected_primitives"]):
        return SelectionParse(False, None, "selected_primitives must be known primitive id list")
    return SelectionParse(True, value, None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_selection_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--raw-outputs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v29 frontier selection eval")
    manifest_path = resolve(args.prompt_manifest)
    raw_path = resolve(args.raw_outputs)
    manifest = load_json(manifest_path)
    raw = load_json(raw_path)
    library = primitive_library()
    artifacts, input_hashes = load_artifacts(Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1"))
    rows_by_id = {row["residual_id"]: row for row in manifest["rows"]}
    rows = []
    accepted = []
    parse_ok = 0
    compile_ok = 0
    for raw_row in raw["rows"]:
        row = rows_by_id[raw_row["residual_id"]]
        parsed = parse_selection(raw_row["output"], library)
        if not parsed.ok or parsed.selection is None:
            proposal = None
            compile_error = None
            result = {"accepted": False, "reason": "parse_error", "checks": {"message": parsed.message}, "proposal_id": None}
        else:
            parse_ok += 1
            proposal, compile_error = compile_selection(parsed.selection, row["residual_class"], library)
            if proposal is None:
                result = {"accepted": False, "reason": "compile_error", "checks": {"message": compile_error}, "proposal_id": None}
            else:
                compile_ok += 1
                result = metaverify_frontier_closure(proposal, artifacts)
        if result["accepted"]:
            accepted.append(result["proposal_id"])
        rows.append({"residual_id": row["residual_id"], "residual_class": row["residual_class"], "parse_ok": parsed.ok, "selection": parsed.selection, "compiled_proposal": proposal, "compile_error": compile_error, "metaverifier_result": result})
    output_dir.mkdir(parents=True)
    rows_path = output_dir / "rows.json"
    write_json(rows_path, {"schema": "ebw_track_a_v29_frontier_selection_eval_rows_v1", "rows": rows})
    payload = {
        "schema": "ebw_track_a_v29_frontier_selection_eval_v1",
        "status": "RPD_EBW_TRACK_A_V29_FRONTIER_SELECTION_EVAL_COMPLETE",
        "processed": len(rows),
        "parse_rate": parse_ok / max(1, len(rows)),
        "compile_rate": compile_ok / max(1, len(rows)),
        "accepted_proposals": accepted,
        "accepted_count": len(accepted),
        "input_hashes": input_hashes,
        "prompt_manifest_sha256": file_hash(manifest_path),
        "raw_outputs_sha256": file_hash(raw_path),
        "rows_sha256": file_hash(rows_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v29 Frontier Selection Eval",
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
    print(json.dumps({"status": payload["status"], "processed": len(rows), "accepted_count": len(accepted), "accepted": accepted, "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()