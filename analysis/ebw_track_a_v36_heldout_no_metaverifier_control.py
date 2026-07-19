"""Held-out structured RepairAgent control without MetaVerifier checks."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v29_frontier_closure_repair_policy import compile_selection, primitive_library
from analysis.ebw_track_a_v29_frontier_selection_eval import parse_selection
from analysis.ebw_track_a_v33_heldout_ttc_eval import proposal_slots_ok

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


def negative_control_selections(residual_id: str) -> list[dict[str, Any]]:
    return [
        {
            "control_id": "negative_wrong_span_source",
            "selection": {
                "residual_id": residual_id,
                "template_id": "template.frontier_candidate.literal_export_path_binding",
                "selected_primitives": ["span_source.any_quoted_task_string", "target_arg.file_path", "parser_policy.strict"],
            },
        },
        {
            "control_id": "negative_parser_relaxation",
            "selection": {
                "residual_id": residual_id,
                "template_id": "template.frontier_candidate.literal_export_path_binding",
                "selected_primitives": ["span_source.quoted_task_path_exact", "target_arg.file_path", "parser_policy.tolerant_alias"],
            },
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v33_heldout_ttc_prompt_manifest/prompt_manifest.json"))
    parser.add_argument("--structured-raw-outputs", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v33_heldout_ttc_selection/raw_model_outputs.json"))
    parser.add_argument("--metaverifier-eval", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v33_heldout_ttc/results.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v36_heldout_no_metaverifier_control"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v36 no-MetaVerifier control")

    manifest_path = resolve(args.prompt_manifest)
    raw_path = resolve(args.structured_raw_outputs)
    metaverifier_path = resolve(args.metaverifier_eval)
    manifest = load_json(manifest_path)
    raw = load_json(raw_path)
    metaverifier = load_json(metaverifier_path)
    library = primitive_library()
    residual_by_id = {row["residual_id"]: row["residual_class"] for row in manifest["rows"]}
    rows = []
    for raw_row in raw["rows"]:
        parsed = parse_selection(raw_row["output"], library)
        selection = parsed.selection if parsed.ok else None
        proposal, compile_error = compile_selection(selection, raw_row["residual_class"], library) if selection is not None else (None, "parse_error")
        rows.append(
            {
                "case_id": "model_selection",
                "residual_id": raw_row["residual_id"],
                "residual_class": raw_row["residual_class"],
                "selection": selection,
                "compiled_proposal": proposal,
                "compile_error": compile_error,
                "accepted_without_metaverifier": proposal is not None,
                "would_pass_metaverifier_slot_check": proposal is not None and proposal_slots_ok(proposal, raw_row["residual_class"]),
            }
        )
        for control in negative_control_selections(raw_row["residual_id"]):
            residual_class = residual_by_id[raw_row["residual_id"]]
            proposal, compile_error = compile_selection(control["selection"], residual_class, library)
            rows.append(
                {
                    "case_id": control["control_id"],
                    "residual_id": raw_row["residual_id"],
                    "residual_class": residual_class,
                    "selection": control["selection"],
                    "compiled_proposal": proposal,
                    "compile_error": compile_error,
                    "accepted_without_metaverifier": proposal is not None,
                    "would_pass_metaverifier_slot_check": proposal is not None and proposal_slots_ok(proposal, residual_class),
                }
            )

    compiler_accepts = [row for row in rows if row["accepted_without_metaverifier"]]
    bad_compiler_accepts = [row for row in compiler_accepts if not row["would_pass_metaverifier_slot_check"]]
    status = "RPD_EBW_TRACK_A_V36_HELDOUT_NO_METAVERIFIER_CONTROL_COMPLETE"
    output_dir.mkdir(parents=True)
    rows_path = output_dir / "rows.json"
    write_json(rows_path, {"schema": "ebw_track_a_v36_no_metaverifier_control_rows_v1", "rows": rows})
    payload = {
        "schema": "ebw_track_a_v36_no_metaverifier_control_v1",
        "status": status,
        "processed": len(rows),
        "accepted_without_metaverifier": len(compiler_accepts),
        "bad_controls_accepted_without_metaverifier": len(bad_compiler_accepts),
        "metaverifier_accepted_count": metaverifier["accepted_count"],
        "prompt_manifest_sha256": file_hash(manifest_path),
        "structured_raw_outputs_sha256": file_hash(raw_path),
        "metaverifier_eval_sha256": file_hash(metaverifier_path),
        "rows_sha256": file_hash(rows_path),
        "sealed_variations_opened": bool(manifest.get("sealed_variations_opened", False)),
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v36 Held-Out No-MetaVerifier Control",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Cases: {len(rows)}",
        f"- Accepted without MetaVerifier: {len(compiler_accepts)}",
        f"- Bad controls accepted without MetaVerifier: {len(bad_compiler_accepts)}",
        f"- v33 MetaVerifier accepted count: {metaverifier['accepted_count']}",
        "- Sealed variations 10-12 opened: Yes",
        "",
        "## Rows",
        "",
        "| Case | Compiler accepted | Would pass MetaVerifier slot check |",
        "|---|---:|---:|",
    ]
    for row in rows:
        report.append(f"| `{row['case_id']}` | {row['accepted_without_metaverifier']} | {row['would_pass_metaverifier_slot_check']} |")
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "accepted_without_metaverifier": len(compiler_accepts), "bad_controls_accepted_without_metaverifier": len(bad_compiler_accepts), "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()