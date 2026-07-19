"""Merge v16 primitive-selection outputs with v16b retry outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-raw", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v16_primitive_selection/raw_model_outputs.json"))
    parser.add_argument("--retry-raw", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v16b_primitive_selection_retry/raw_model_outputs.json"))
    parser.add_argument("--base-eval", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16_primitive_selection_model/rows.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v16b_primitive_selection_merged_outputs"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v16b primitive-selection merged outputs")

    base_raw_path = resolve(args.base_raw)
    retry_raw_path = resolve(args.retry_raw)
    base_eval_path = resolve(args.base_eval)
    base_raw = load_json(base_raw_path)["rows"]
    retry_raw = load_json(retry_raw_path)["rows"]
    base_eval = load_json(base_eval_path)["rows"]
    retry_by_id = {row["residual_id"]: row for row in retry_raw}
    eval_by_id = {row["residual_id"]: row for row in base_eval}
    rows = []
    source_counts: Counter[str] = Counter()
    for row in base_raw:
        residual_id = row["residual_id"]
        if residual_id in retry_by_id and not eval_by_id[residual_id]["metaverifier_result"]["accepted"]:
            rows.append(retry_by_id[residual_id])
            source_counts["v16b_retry"] += 1
        else:
            rows.append(row)
            source_counts["v16_original"] += 1

    output_dir.mkdir(parents=True)
    raw_path = output_dir / "raw_model_outputs.json"
    write_json(
        raw_path,
        {
            "schema": "ebw_track_a_v16b_primitive_selection_merged_raw_outputs_v1",
            "status": "RPD_EBW_TRACK_A_V16B_PRIMITIVE_SELECTION_MERGED_OUTPUTS_READY",
            "rows": rows,
            "source_counts": dict(sorted(source_counts.items())),
            "base_raw_sha256": file_hash(base_raw_path),
            "retry_raw_sha256": file_hash(retry_raw_path),
            "base_eval_sha256": file_hash(base_eval_path),
            "sealed_variations_opened": False,
            "model_gpu_docker_used": False,
            "external_process_actions": False,
        },
    )
    payload = {
        "schema": "ebw_track_a_v16b_primitive_selection_merged_outputs_summary_v1",
        "status": "RPD_EBW_TRACK_A_V16B_PRIMITIVE_SELECTION_MERGED_OUTPUTS_READY",
        "rows": len(rows),
        "source_counts": dict(sorted(source_counts.items())),
        "raw_outputs_sha256": file_hash(raw_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "merge.json", payload)
    report = [
        "# EBW Track A v16b Primitive Selection Merged Outputs",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(rows)}",
        "- Merge policy: v16 original accepted rows plus v16b retry rows for failed selections",
        "- Sealed variations 10-12 opened: No",
        "",
        "## Source Counts",
        "",
        "| Source | Rows |",
        "|---|---:|",
    ]
    report += [f"| `{key}` | {value} |" for key, value in sorted(source_counts.items())]
    (output_dir / "MERGE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(rows), "source_counts": payload["source_counts"], "report": str((output_dir / "MERGE.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()