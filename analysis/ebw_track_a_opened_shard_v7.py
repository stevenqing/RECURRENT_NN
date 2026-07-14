"""Create a value-free stratified opened-pool shard for EBW Track A v7."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
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


def ordinal_for(row: dict[str, Any], ordinal_by_instance: dict[str, int]) -> int:
    if "write_ordinal_for_schema" in row:
        return int(row["write_ordinal_for_schema"])
    return ordinal_by_instance[row["instance_id"]]


def quoted_literal_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for pattern in [r'"([^"\n]+)"', r"'([^'\n]+)'", r"\u201c([^\u201d\n]+)\u201d", r"\u2018([^\u2019\n]+)\u2019"]:
        for match in re.finditer(pattern, text):
            spans.append((match.start(1), match.end(1)))
    return spans


def required_obligation(row: dict[str, Any]) -> str | None:
    if row["proof_family"] == "filesystem_path_derivation_proof":
        return "derived_path_binding"
    if row["proof_family"] == "literal_text_derivation_proof":
        return "literal_intent_binding"
    if row["proof_family"] == "state_transition_membership_proof":
        if row["api_name"] == "add_song_to_playlist" and row["field_name"] == "playlist_id":
            return "prior_effect_binding"
        return "ordered_role_binding"
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_execution_preflight_v1/evaluation_manifest.json"))
    parser.add_argument("--readiness", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v7_freeze_readiness/readiness.json"))
    parser.add_argument("--root", type=Path, default=Path("external_repos/appworld_generated_broad_schema_v1"))
    parser.add_argument("--ordinal-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_broad_value_bound_witness_preflight_v1/instance_manifest.json"))
    parser.add_argument("--per-obligation", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_opened_shard_v8_candidate_bound"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A v7 opened shard")

    manifest_path = resolve(args.execution_manifest)
    readiness_path = resolve(args.readiness)
    root = resolve(args.root)
    ordinal_manifest_path = resolve(args.ordinal_manifest)
    source = load_json(manifest_path)
    readiness = load_json(readiness_path)
    ordinal_manifest = load_json(ordinal_manifest_path)
    ordinal_by_instance = {row["instance_id"]: int(row["write_ordinal_for_schema"]) for row in ordinal_manifest["rows"]}
    task_instruction_cache: dict[str, str] = {}
    by_obligation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    excluded_counts: Counter[str] = Counter()
    for row in source["rows"]:
        obligation = required_obligation(row)
        if obligation is not None:
            if obligation == "literal_intent_binding":
                task_id = row["task_id"]
                if task_id not in task_instruction_cache:
                    task_instruction_cache[task_id] = load_json(root / "data/tasks" / task_id / "specs.json")["instruction"]
                spans = quoted_literal_spans(task_instruction_cache[task_id])
                if not spans:
                    excluded_counts["literal_intent_no_quoted_span"] += 1
                    continue
                if ordinal_for(row, ordinal_by_instance) >= len(spans):
                    excluded_counts["literal_intent_insufficient_quoted_spans_for_ordinal"] += 1
                    continue
            by_obligation[obligation].append(row)
    available_counts = {obligation: len(rows) for obligation, rows in sorted(by_obligation.items())}
    selected = []
    for obligation in ["derived_path_binding", "literal_intent_binding", "ordered_role_binding", "prior_effect_binding"]:
        rows = sorted(by_obligation[obligation], key=lambda item: (item["generator_id"], item["variation"], item["task_id"], int(item["call_index"]), item["field_name"], item["instance_id"]))
        chosen = rows[: min(args.per_obligation, len(rows))]
        for row in chosen:
            copy = dict(row)
            copy["required_obligation"] = obligation
            selected.append(copy)
    counts = Counter(row["required_obligation"] for row in selected)
    checks = {
        "readiness_ready": readiness["status"] == "RPD_EBW_TRACK_A_VERIFIER_POLICY_V7_READY_NOT_TAGGED",
        "source_status": source["status"] == "RPD_EBW_TRACK_A_EXECUTION_PREFLIGHT_READY",
        "per_obligation_counts": all(counts[obligation] == min(args.per_obligation, available_counts.get(obligation, 0)) for obligation in ["derived_path_binding", "literal_intent_binding", "ordered_role_binding", "prior_effect_binding"]),
        "all_obligations_represented": all(counts[obligation] > 0 for obligation in ["derived_path_binding", "literal_intent_binding", "ordered_role_binding", "prior_effect_binding"]),
        "unique_instance_ids": len({row["instance_id"] for row in selected}) == len(selected),
        "dev_slice_excluded": source["dev_slice_excluded"] is True,
        "scope": source["sealed_variations_opened"] is False and source["protected_content_exported"] is False and source["argument_values_exported"] is False and source["response_values_exported"] is False,
    }
    status = "RPD_EBW_TRACK_A_OPENED_SHARD_V7_READY" if all(checks.values()) else "RPD_EBW_TRACK_A_OPENED_SHARD_V7_BLOCKED"
    if not checks["scope"]:
        status = "RPD_EBW_TRACK_A_OPENED_SHARD_V7_PROTOCOL_FAIL"

    output_dir.mkdir(parents=True)
    shard_path = output_dir / "evaluation_manifest.json"
    write_json(
        shard_path,
        {
            "schema": "ebw_track_a_opened_shard_v7_manifest_v1",
            "status": status,
            "rows": selected,
            "per_obligation": args.per_obligation,
            "dev_slice_excluded": True,
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
            "value_hashes_exported": False,
            "sealed_variations_opened": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_opened_shard_v7_v1",
        "status": status,
        "checks": checks,
        "rows": len(selected),
        "per_obligation": args.per_obligation,
        "counts": dict(sorted(counts.items())),
        "available_counts": available_counts,
        "excluded_counts": dict(sorted(excluded_counts.items())),
        "source_manifest_sha256": file_hash(manifest_path),
        "readiness_sha256": file_hash(readiness_path),
        "ordinal_manifest_sha256": file_hash(ordinal_manifest_path),
        "evaluation_manifest_sha256": file_hash(shard_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "shard.json", payload)
    report = [
        "# EBW Track A v7 Opened-Pool Shard",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Rows: {len(selected)}",
        f"- Target per obligation: {args.per_obligation}",
        "- Rare obligations: include all available rows when fewer than target",
        "- Candidate-ready filter: literal rows require at least one quoted span in task text",
        "- Dev slice excluded: Yes",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Counts",
        "",
        "| Required obligation | Rows |",
        "|---|---:|",
    ]
    report += [f"| {obligation} | {count} |" for obligation, count in sorted(counts.items())]
    report += ["", "## Available Rows", "", "| Required obligation | Available rows |", "|---|---:|"]
    report += [f"| {obligation} | {count} |" for obligation, count in sorted(available_counts.items())]
    report += ["", "## Exclusions", "", "| Reason | Rows |", "|---|---:|"]
    report += [f"| {reason} | {count} |" for reason, count in sorted(excluded_counts.items())]
    report += ["", "## Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "SHARD.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "rows": len(selected), "report": str((output_dir / "SHARD.md").relative_to(REPO_ROOT))}))
    if status != "RPD_EBW_TRACK_A_OPENED_SHARD_V7_READY":
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()