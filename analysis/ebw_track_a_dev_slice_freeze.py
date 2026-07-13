"""Freeze value-free EBW Track A dev slice IDs."""
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


def obligation_for(row: dict[str, Any]) -> str | None:
    if row["decision"] != "commit_live":
        return None
    if row["proof_family"] == "filesystem_path_derivation_proof":
        return "derived_path_binding"
    if row["proof_family"] == "literal_text_derivation_proof":
        return "literal_intent_binding"
    if row["ledger_source"] == "state_transition_created_playlist_verifier_v1":
        return "prior_effect_binding"
    if row["ledger_source"] == "state_transition_like_song_verifier_v1":
        return "ordered_role_binding"
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_dev_slice_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_dev_slice_v1"))
    args = parser.parse_args()
    contract_path = resolve(args.contract)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A dev slice")

    contract = load_json(contract_path)
    ledger_rows_path = resolve(contract["source_ledger"])
    ledger_result_path = resolve(contract["source_ledger_result"])
    ledger_rows = load_json(ledger_rows_path)["rows"]
    ledger_result = load_json(ledger_result_path)
    by_obligation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ledger_rows:
        obligation = obligation_for(row)
        if obligation is not None:
            by_obligation[obligation].append(row)

    selected = []
    example_ids = {}
    for obligation in sorted(contract["expected_counts"]):
        rows = sorted(by_obligation[obligation], key=lambda row: row["instance_id"])
        chosen = rows[: int(contract["per_obligation_instances"])]
        if chosen:
            example_ids[obligation] = chosen[0]["instance_id"]
        for row in chosen:
            selected.append(
                {
                    "instance_id": row["instance_id"],
                    "task_id": row["task_id"],
                    "generator_id": row["generator_id"],
                    "variation": row["variation"],
                    "call_index": row["call_index"],
                    "method": row["method"],
                    "app": row["app"],
                    "api_name": row["api_name"],
                    "field_name": row["field_name"],
                    "proof_family": row["proof_family"],
                    "obligation": obligation,
                    "ledger_source": row["ledger_source"],
                    "decision": row["decision"],
                }
            )

    counts = Counter(row["obligation"] for row in selected)
    row_keys = {"instance_id", "task_id", "generator_id", "variation", "call_index", "method", "app", "api_name", "field_name", "proof_family", "obligation", "ledger_source", "decision"}
    checks = {
        "contract_frozen": contract["status"] == "FROZEN_DEV_SLICE_IDS_BEFORE_TRACK_A_TAG",
        "source_ledger_pass": ledger_result["status"] == "RPD_APPWORLD_BROAD_SAFE_DERIVATION_LEDGER_V5_PASS",
        "counts": dict(sorted(counts.items())) == contract["expected_counts"],
        "max_instances": len(selected) <= int(contract["max_dev_instances"]),
        "unique_instance_ids": len({row["instance_id"] for row in selected}) == len(selected),
        "example_ids": set(example_ids) == set(contract["expected_counts"]),
        "row_value_free": all(set(row) == row_keys for row in selected),
        "scope": contract["protected_content_export"] is False and contract["argument_values_export"] is False and contract["response_values_export"] is False and contract["value_hashes_export"] is False and contract["sealed_variations_opened"] is False and contract["model_gpu_docker_used"] is False and contract["external_process_actions"] is False,
    }
    status = contract["verdicts"]["ready"] if all(checks.values()) else contract["verdicts"]["blocked"]
    if not checks["contract_frozen"] or not checks["scope"]:
        status = contract["verdicts"]["protocol_fail"]

    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "dev_slice_manifest.json"
    write_json(
        manifest_path,
        {
            "schema": "ebw_track_a_dev_slice_manifest_v1",
            "status": status,
            "rows": selected,
            "example_ids": example_ids,
            "main_report_exclusion": True,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
            "value_hashes_exported": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_dev_slice_freeze_v1",
        "status": status,
        "checks": checks,
        "counts": dict(sorted(counts.items())),
        "instances": len(selected),
        "example_ids": example_ids,
        "dev_slice_manifest_sha256": file_hash(manifest_path),
        "source_ledger_sha256": file_hash(ledger_rows_path),
        "source_ledger_result_sha256": file_hash(ledger_result_path),
        "contract_sha256": file_hash(contract_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
        "protected_content_exported": False,
    }
    write_json(output_dir / "freeze.json", payload)
    report = [
        "# EBW Track A Dev Slice v1",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Instances: {len(selected)}",
        "- Main report exclusion: Yes",
        "- Protected content exported: No",
        "- Argument/response values exported: No",
        "- Value hashes exported: No",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Counts",
        "",
        "| Obligation | Instances | Example ID |",
        "|---|---:|---|",
    ]
    report += [f"| {obligation} | {int(counts.get(obligation, 0))} | {example_ids.get(obligation, '')} |" for obligation in sorted(contract["expected_counts"])]
    report += ["", "## Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "DEV_SLICE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "instances": len(selected), "report": str((output_dir / "DEV_SLICE.md").relative_to(REPO_ROOT))}))
    if status != contract["verdicts"]["ready"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()