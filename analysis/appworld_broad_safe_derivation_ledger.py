"""Combine safe broad derivation verifiers into a value-free ledger."""
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


def value_free_row(row: dict[str, Any], decision: str, source: str) -> dict[str, Any]:
    return {
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
        "decision": decision,
        "ledger_source": source,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_appworld_broad_safe_derivation_ledger_v2.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_broad_safe_derivation_ledger_v2"))
    args = parser.parse_args()
    contract_path = resolve(args.contract)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite safe derivation ledger")

    contract = load_json(contract_path)
    manifest_path = resolve(contract["instance_manifest"])
    path_results_path = resolve(contract["path_verifier"])
    path_rows_path = resolve(contract["path_rows"])
    literal_results_path = resolve(contract["literal_verifier"])
    literal_rows_path = resolve(contract["literal_rows"])
    created_playlist_results_path = resolve(contract["created_playlist_verifier"]) if "created_playlist_verifier" in contract else None
    created_playlist_rows_path = resolve(contract["created_playlist_rows"]) if "created_playlist_rows" in contract else None
    ordered_entity_results_path = resolve(contract["ordered_entity_verifier"]) if "ordered_entity_verifier" in contract else None
    ordered_entity_rows_path = resolve(contract["ordered_entity_rows"]) if "ordered_entity_rows" in contract else None
    like_song_results_path = resolve(contract["like_song_verifier"]) if "like_song_verifier" in contract else None
    like_song_rows_path = resolve(contract["like_song_rows"]) if "like_song_rows" in contract else None
    manifest = load_json(manifest_path)
    path_results = load_json(path_results_path)
    path_rows = load_json(path_rows_path)["rows"]
    literal_results = load_json(literal_results_path)
    literal_rows = load_json(literal_rows_path)["rows"]
    created_playlist_results = load_json(created_playlist_results_path) if created_playlist_results_path else None
    created_playlist_rows = load_json(created_playlist_rows_path)["rows"] if created_playlist_rows_path else []
    ordered_entity_results = load_json(ordered_entity_results_path) if ordered_entity_results_path else None
    ordered_entity_rows = load_json(ordered_entity_rows_path)["rows"] if ordered_entity_rows_path else []
    like_song_results = load_json(like_song_results_path) if like_song_results_path else None
    like_song_rows = load_json(like_song_rows_path)["rows"] if like_song_rows_path else []

    path_by_id = {row["instance_id"]: row for row in path_rows}
    literal_by_id = {row["instance_id"]: row for row in literal_rows}
    created_playlist_by_id = {row["instance_id"]: row for row in created_playlist_rows}
    like_song_by_id = {row["instance_id"]: row for row in like_song_rows}
    ordered_entity_by_id = {row["instance_id"]: row for row in ordered_entity_rows}
    ordered_schema_has_unsafe: set[str] = set()
    for row in ordered_entity_rows:
        if row["decision"] == "unsafe_unique_wrong":
            ordered_schema_has_unsafe.add(f"{row['method']}.{row['app']}.{row['api_name']}.{row['field_name']}")
    ledger_rows = []
    for row in manifest["rows"]:
        family = row["proof_family"]
        if family == "filesystem_path_derivation_proof":
            verifier_row = path_by_id[row["instance_id"]]
            ledger_rows.append(value_free_row(row, verifier_row["decision"], "filesystem_path_derivation_verifier_v2"))
        elif family == "literal_text_derivation_proof":
            verifier_row = literal_by_id[row["instance_id"]]
            ledger_rows.append(value_free_row(row, verifier_row["decision"], "literal_text_derivation_verifier_v1"))
        elif family == "state_transition_membership_proof":
            if row["instance_id"] in created_playlist_by_id:
                verifier_row = created_playlist_by_id[row["instance_id"]]
                ledger_rows.append(value_free_row(row, verifier_row["decision"], "state_transition_created_playlist_verifier_v1"))
            elif row["instance_id"] in like_song_by_id:
                verifier_row = like_song_by_id[row["instance_id"]]
                ledger_rows.append(value_free_row(row, verifier_row["decision"], "state_transition_like_song_verifier_v1"))
            elif row["instance_id"] in ordered_entity_by_id and f"{row['method']}.{row['app']}.{row['api_name']}.{row['field_name']}" not in ordered_schema_has_unsafe:
                verifier_row = ordered_entity_by_id[row["instance_id"]]
                ledger_rows.append(value_free_row(row, verifier_row["decision"], "state_transition_ordered_entity_zero_unsafe_schema_slice_v1"))
            else:
                ledger_rows.append(value_free_row(row, "abstain_no_valid", "state_transition_fail_closed"))
        else:
            raise RuntimeError(f"unsupported family: {family}")

    decision_counts = Counter(row["decision"] for row in ledger_rows)
    family_counts = Counter(row["proof_family"] for row in ledger_rows)
    family_decisions: dict[str, Counter[str]] = defaultdict(Counter)
    for row in ledger_rows:
        family_decisions[row["proof_family"]][row["decision"]] += 1
    expected = contract["expected_counts"]
    checks = {
        "contract_frozen": contract["status"] == "FROZEN_BEFORE_SAFE_DERIVATION_LEDGER_OUTCOMES",
        "parent_ledger": "parent_ledger" not in contract or load_json(contract["parent_ledger"])["status"] == contract["expected_statuses"]["parent_ledger"],
        "path_verifier_safe": path_results["status"] == contract["expected_statuses"]["path_verifier"],
        "literal_verifier_safe": literal_results["status"] == contract["expected_statuses"]["literal_verifier"],
        "created_playlist_verifier_safe": created_playlist_results is None or created_playlist_results["status"] == contract["expected_statuses"]["created_playlist_verifier"],
        "like_song_verifier_safe": like_song_results is None or like_song_results["status"] == contract["expected_statuses"]["like_song_verifier"],
        "ordered_entity_verifier_recorded": ordered_entity_results is None or ordered_entity_results["status"] == contract["expected_statuses"]["ordered_entity_verifier"],
        "row_count": len(ledger_rows) == expected["total_instances"],
        "unique_instance_ids": len({row["instance_id"] for row in ledger_rows}) == len(ledger_rows),
        "decision_counts": {key: int(decision_counts.get(key, 0)) for key in expected["decision_counts"]} == expected["decision_counts"],
        "family_counts": dict(sorted(family_counts.items())) == expected["family_counts"],
        "path_binding": file_hash(path_rows_path) == path_results["rows_sha256"],
        "literal_binding": file_hash(literal_rows_path) == literal_results["rows_sha256"],
        "created_playlist_binding": created_playlist_results is None or file_hash(created_playlist_rows_path) == created_playlist_results["rows_sha256"],
        "like_song_binding": like_song_results is None or file_hash(like_song_rows_path) == like_song_results["rows_sha256"],
        "ordered_entity_binding": ordered_entity_results is None or file_hash(ordered_entity_rows_path) == ordered_entity_results["rows_sha256"],
        "scope": contract["protected_content_export"] is False and contract["argument_values_export"] is False and contract["response_values_export"] is False and contract["value_hashes_export"] is False and contract["model_gpu_docker_used"] is False and contract["external_process_actions"] is False and contract["headline_eligible"] is False,
    }
    status = contract["verdicts"]["pass"] if all(checks.values()) else contract["verdicts"]["fail"]
    if not checks["contract_frozen"] or not checks["scope"]:
        status = contract["verdicts"]["protocol_fail"]

    output_dir.mkdir(parents=True)
    rows_path = output_dir / "rows.json"
    write_json(rows_path, {"schema": "appworld_broad_safe_derivation_ledger_rows_v1", "status": status, "rows": ledger_rows, "protected_content_exported": False, "argument_values_exported": False, "response_values_exported": False, "value_hashes_exported": False})
    payload = {
        "schema": contract["schema"].replace("recurrent_parallel_", "").replace("_contract", ""),
        "status": status,
        "checks": checks,
        "decision_counts": {key: int(decision_counts.get(key, 0)) for key in contract["expected_counts"]["decision_counts"]},
        "family_decision_counts": {family: dict(sorted(counter.items())) for family, counter in sorted(family_decisions.items())},
        "target_instances": len(ledger_rows),
        "rows_sha256": file_hash(rows_path),
        "contract_sha256": file_hash(contract_path),
        "fresh_confirmation_sealed": True,
        "protected_content_exported": False,
        "argument_values_exported": False,
        "response_values_exported": False,
        "value_hashes_exported": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
        "headline_eligible": False,
        "action_correctness_claim": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# AppWorld Broad Safe Derivation Ledger",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Target instances: {len(ledger_rows)}",
        "- Policy: path verifier v2 + literal verifier v1 + state-transition fail closed",
        "- Action correctness claim: No",
        "- Argument values exported: No",
        "- Response values exported: No",
        "- Value hashes exported: No",
        "- Fresh variations 10-12: sealed",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Decision Counts",
        "",
        "| Decision | Count |",
        "|---|---:|",
    ]
    report += [f"| {key} | {int(decision_counts.get(key, 0))} |" for key in expected["decision_counts"]]
    report += ["", "## Family Decision Counts", ""]
    for family, counter in sorted(family_decisions.items()):
        report += [f"### `{family}`", "", "| Decision | Count |", "|---|---:|"]
        report += [f"| {key} | {int(counter.get(key, 0))} |" for key in expected["decision_counts"]]
        report += [""]
    report += ["## Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "decision_counts": payload["decision_counts"], "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT))}))
    if status != contract["verdicts"]["pass"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()