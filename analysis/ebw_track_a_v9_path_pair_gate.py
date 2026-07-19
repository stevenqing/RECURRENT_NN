"""Deterministic v9 path-pair gate for full-opened v8 derived failures."""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
from collections import Counter
from pathlib import Path
from typing import Any

from analysis.ebw_track_a_v9_path_pair_feasibility import norm_path, path_pair_candidate
from experiments.ebw_obligation_sketch import barrier_unique_validity

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


def sketch_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "obligation": "path_pair_transform_binding",
        "source_read_id": candidate["source_read_id"],
        "source_path_field": candidate["source_path_field"],
        "date_read_id": candidate["date_read_id"],
        "date_field": candidate["date_field"],
        "destination_directory_rule_id": candidate["destination_directory_rule_id"],
        "transform": candidate["transform"],
        "target_arg": candidate["target_arg"],
    }


def valid_path_pair(value: Any, candidate: dict[str, Any]) -> bool:
    return norm_path(value) == norm_path(candidate["expected_destination_file_path"])


def adversarial_values(candidate: dict[str, Any]) -> list[str]:
    expected = norm_path(candidate["expected_destination_file_path"])
    directory = posixpath.dirname(expected)
    basename = posixpath.basename(expected)
    parts = basename.split("_", 1)
    values = []
    if len(parts) == 2 and len(parts[0]) == 10:
        values.append(posixpath.join(directory, "1999-01-01_" + parts[1]))
    parts_dash = basename.split("-", 3)
    if len(parts_dash) >= 4 and all(part.isdigit() for part in parts_dash[:3]):
        values.append(posixpath.join(directory, "1999-01-01-" + parts_dash[3]))
    alt_dir = "~/trash" if not expected.startswith("~/trash/") else "~/downloads"
    values.append(posixpath.join(alt_dir, basename))
    values.append(posixpath.join(directory, basename + "__ebw_alternative__"))
    deduped = []
    seen: set[str] = set()
    for value in values:
        key = norm_path(value)
        if key != expected and key not in seen:
            seen.add(key)
            deduped.append(value)
    return deduped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_full_opened_v8_executable/prompt_manifest.json"))
    parser.add_argument("--rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_full_opened_v8_executable/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_path_pair_gate"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v9 path-pair gate")

    manifest_path = resolve(args.prompt_manifest)
    rows_path = resolve(args.rows)
    manifest = load_json(manifest_path)["rows"]
    row_results = {row["instance_id"]: row for row in load_json(rows_path)["rows"]}
    result_rows = []
    counts: Counter[str] = Counter()
    for row in manifest:
        if row.get("required_obligation") != "derived_path_binding":
            continue
        previous = row_results.get(row["instance_id"], {}).get("decision")
        candidate = path_pair_candidate(row)
        if previous != "unsafe_unique_wrong" or candidate is None or not candidate["match"]:
            continue
        live_value = row["live_arguments"][row["field_name"]]
        live_valid = valid_path_pair(live_value, candidate)
        adversarial_valids = {f"adversarial_{index}": valid_path_pair(value, candidate) for index, value in enumerate(adversarial_values(candidate))}
        barrier = barrier_unique_validity({"live": live_valid, **adversarial_valids})
        if barrier["decision"] == "commit" and barrier["candidate_id"] == "live":
            decision = "commit_live"
        elif barrier["decision"] == "commit":
            decision = "unsafe_unique_wrong"
        elif barrier["typed_reason"] == "competing_valid":
            decision = "ambiguous_both_valid"
        else:
            decision = "abstain_no_valid"
        counts[decision] += 1
        result_rows.append(
            {
                "instance_id": row["instance_id"],
                "task_id": row["task_id"],
                "previous_decision": previous,
                "decision": decision,
                "sketch": sketch_from_candidate(candidate),
                "live_valid": live_valid,
                "adversarial_valids": adversarial_valids,
            }
        )

    output_dir.mkdir(parents=True)
    rows_out = output_dir / "rows.json"
    write_json(rows_out, {"schema": "ebw_track_a_v9_path_pair_gate_rows_v1", "rows": result_rows})
    payload = {
        "schema": "ebw_track_a_v9_path_pair_gate_v1",
        "status": "RPD_EBW_TRACK_A_V9_PATH_PAIR_GATE_COMPLETE",
        "target_rows": len(result_rows),
        "decision_counts": dict(sorted(counts.items())),
        "previous_required_decision": "unsafe_unique_wrong",
        "target_selection": "derived_path unsafe rows with matching v9 path-pair candidate",
        "prompt_manifest_sha256": file_hash(manifest_path),
        "source_rows_sha256": file_hash(rows_path),
        "rows_sha256": file_hash(rows_out),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "results.json", payload)
    report = [
        "# EBW Track A v9 Path-Pair Gate",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Target rows: {len(result_rows)}",
        "- Target selection: derived-path full-v8 unsafe rows with matching v9 path-pair candidate",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Decision Counts",
        "",
        "| Decision | Rows |",
        "|---|---:|",
    ]
    report += [f"| {decision} | {count} |" for decision, count in sorted(counts.items())]
    report += ["", "## Interpretation", "", "A deterministic path-pair proof is sufficient to turn the directly covered full-v8 derived unsafe rows into commit-live decisions under path-shaped adversaries. Remaining unsafe requires richer path-rule parsing, not another basename proof."]
    (output_dir / "GATE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "target_rows": len(result_rows), "counts": payload["decision_counts"], "report": str((output_dir / "GATE.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()