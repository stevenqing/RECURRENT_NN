"""Audit whether v9 path-pair proof can explain full-opened v8 derived failures."""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
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


def norm_path(value: Any) -> str:
    text = str(value).replace("\\", "/").strip()
    while "//" in text:
        text = text.replace("//", "/")
    if not text:
        return text
    return posixpath.normpath(text)


def clean_directory_literal(value: str) -> str:
    text = str(value).strip().strip('"\'`')
    text = re.sub(r"[),.;:]+$", "", text)
    return norm_path(text)


def tilde_dir_from_source(source_file_path: str) -> str:
    parts = norm_path(source_file_path).split("/")
    if len(parts) >= 4 and parts[1] == "home":
        return "~/" + "/".join(parts[3:-1])
    return posixpath.dirname(norm_path(source_file_path))


def parse_path_rule(task_text: str) -> dict[str, str] | None:
    prefix_match = re.search(r'prefix\s+"(Y{4}[-_]M{2}[-_]D{2}[-_]?)"', task_text)
    trash_match = re.search(r"files not from this year to\s+(~/?[\w./-]+)", task_text)
    source_match = re.search(r"file names in the\s+(~/?[\w./-]+)\s+directory", task_text)
    if not prefix_match or not trash_match:
        return None
    return {
        "prefix_pattern": prefix_match.group(1),
        "trash_directory": clean_directory_literal(trash_match.group(1)),
        "source_directory_hint": clean_directory_literal(source_match.group(1)) if source_match else "",
        "current_year": "2023",
    }


def format_prefix(pattern: str, created_at: str) -> str:
    year, month, day = created_at[:10].split("-")
    return pattern.replace("YYYY", year).replace("MM", month).replace("DD", day)


def find_source_metadata(context: dict[str, Any], source_file_path: str) -> dict[str, Any] | None:
    source_norm = norm_path(source_file_path)
    for read in context["pre_write_reads"]:
        response = read["response"]
        if not isinstance(response, dict):
            continue
        if norm_path(response.get("path", "")) == source_norm and response.get("created_at"):
            return {"read_id": read["read_id"], "path_field": "response.path", "date_field": "response.created_at", "created_at": response["created_at"]}
    return None


def path_pair_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    context = row["context"]
    args = context["candidate_action"]["arguments"]
    target_arg = context["candidate_action"]["target_arg"]
    source_path = args.get("source_file_path")
    live_target = args.get(target_arg)
    if not source_path or not live_target:
        return None
    rule = parse_path_rule(context["task_text"])
    metadata = find_source_metadata(context, source_path)
    if not rule or not metadata:
        return None
    prefix = format_prefix(rule["prefix_pattern"], metadata["created_at"])
    source_basename = posixpath.basename(norm_path(source_path))
    source_directory = rule["source_directory_hint"] or tilde_dir_from_source(source_path)
    destination_directory = source_directory if metadata["created_at"][:4] == rule["current_year"] else rule["trash_directory"]
    expected = f"{destination_directory}/{prefix}{source_basename}"
    return {
        "source_read_id": metadata["read_id"],
        "source_path_field": metadata["path_field"],
        "date_read_id": metadata["read_id"],
        "date_field": metadata["date_field"],
        "destination_directory_rule_id": f"current_year_{rule['current_year']}_else_trash",
        "transform": "date_prefix_basename_into_directory",
        "target_arg": target_arg,
        "expected_destination_file_path": expected,
        "match": norm_path(expected) == norm_path(live_target),
        "created_at": metadata["created_at"],
        "prefix_pattern": rule["prefix_pattern"],
        "source_directory": source_directory,
        "trash_directory": rule["trash_directory"],
        "live_target": live_target,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_full_opened_v8_executable/prompt_manifest.json"))
    parser.add_argument("--rows", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_full_opened_v8_executable/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_path_pair_feasibility"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v9 path-pair feasibility")

    manifest_path = resolve(args.prompt_manifest)
    rows_path = resolve(args.rows)
    manifest = load_json(manifest_path)["rows"]
    row_results = {row["instance_id"]: row for row in load_json(rows_path)["rows"]}
    counts: Counter[str] = Counter()
    by_decision: dict[str, Counter[str]] = defaultdict(Counter)
    by_task: Counter[str] = Counter()
    examples = []
    total_derived = 0
    for row in manifest:
        if row.get("required_obligation") != "derived_path_binding":
            continue
        total_derived += 1
        decision = row_results.get(row["instance_id"], {}).get("decision", "missing_result")
        candidate = path_pair_candidate(row)
        if candidate is None:
            label = "no_path_pair_candidate"
        elif candidate["match"]:
            label = "path_pair_candidate_matches_live"
        else:
            label = "path_pair_candidate_mismatch"
        counts[label] += 1
        by_decision[decision][label] += 1
        if decision == "unsafe_unique_wrong":
            by_task[row["task_id"]] += 1
        if (decision == "unsafe_unique_wrong" or label != "path_pair_candidate_matches_live") and len(examples) < 20:
            examples.append({"instance_id": row["instance_id"], "task_id": row["task_id"], "decision": decision, "label": label, "candidate": candidate, "live_arguments": row["live_arguments"], "task_text": row["context"]["task_text"][:240]})

    output_dir.mkdir(parents=True)
    payload = {
        "schema": "ebw_track_a_v9_path_pair_feasibility_v1",
        "status": "RPD_EBW_TRACK_A_V9_PATH_PAIR_FEASIBILITY_COMPLETE",
        "total_derived_rows": total_derived,
        "counts": dict(sorted(counts.items())),
        "by_decision": {decision: dict(sorted(counter.items())) for decision, counter in sorted(by_decision.items())},
        "unsafe_by_task": dict(by_task.most_common()),
        "examples": examples,
        "prompt_manifest_sha256": file_hash(manifest_path),
        "rows_sha256": file_hash(rows_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "feasibility.json", payload)
    report = [
        "# EBW Track A v9 Path-Pair Feasibility",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Total derived rows: {total_derived}",
        "- Sealed variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Candidate Labels",
        "",
        "| Label | Rows |",
        "|---|---:|",
    ]
    report += [f"| {label} | {count} |" for label, count in sorted(counts.items())]
    report += ["", "## By Decision", ""]
    for decision, counter in sorted(by_decision.items()):
        report += [f"### `{decision}`", "", "| Label | Rows |", "|---|---:|"]
        report += [f"| {label} | {count} |" for label, count in sorted(counter.items())]
        report += [""]
    report += ["## Interpretation", "", "The v9 path-pair transform can directly explain the date-prefix/directory-rule failures when the task text exposes a parseable prefix pattern and trash/current-year rule. Rows without a candidate or with mismatched expected path should fail closed or require another proof family."]
    (output_dir / "FEASIBILITY.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "report": str((output_dir / "FEASIBILITY.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()