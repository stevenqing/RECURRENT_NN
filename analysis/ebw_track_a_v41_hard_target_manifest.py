"""Build a small exploratory hard target manifest from v40 pass-subset rows."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

TARGETS = {
    ("move_file", "source_file_path"): "source_path_identity_binding_missing",
    ("update_note", "note_id"): "ordered_note_title_identity_binding_abstain",
    ("add_song_to_playlist", "playlist_id"): "prior_effect_playlist_id_binding_abstain",
}


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
    parser.add_argument("--instance-manifest", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v40_hard_pass_subset_instance_preflight/instance_manifest.json"))
    parser.add_argument("--max-per-class", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v41_hard_target_manifest"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v41 hard target manifest")

    manifest_path = resolve(args.instance_manifest)
    manifest = load_json(manifest_path)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in manifest["rows"]:
        target_class = TARGETS.get((row["api_name"], row["field_name"]))
        if target_class is not None:
            grouped[target_class].append(row)
    selected = []
    for target_class, rows in sorted(grouped.items()):
        selected.extend(sorted(rows, key=lambda row: (row["task_id"], row["call_index"], row["field_name"]))[: args.max_per_class])
    selected_counts = Counter(TARGETS[(row["api_name"], row["field_name"])] for row in selected)

    output_dir.mkdir(parents=True)
    target_path = output_dir / "evaluation_manifest.json"
    write_json(
        target_path,
        {
            "schema": "ebw_track_a_v41_hard_target_evaluation_manifest_v1",
            "status": "RPD_EBW_TRACK_A_V41_HARD_TARGET_MANIFEST_READY",
            "rows": selected,
            "target_classes": dict(sorted(selected_counts.items())),
            "selection_policy": "exploratory_pass_subset_first_rows_by_task_call_max_per_class",
            "claim_boundary": "Exploratory hard pass-subset only; v39 four-generator hard held-out protocol was blocked.",
            "protected_content_exported": False,
            "argument_values_exported": False,
            "response_values_exported": False,
            "value_hashes_exported": False,
            "sealed_variations_opened": True,
        },
    )
    payload = {
        "schema": "ebw_track_a_v41_hard_target_manifest_build_v1",
        "status": "RPD_EBW_TRACK_A_V41_HARD_TARGET_MANIFEST_READY",
        "rows": len(selected),
        "target_classes": dict(sorted(selected_counts.items())),
        "max_per_class": args.max_per_class,
        "source_instance_manifest_sha256": file_hash(manifest_path),
        "evaluation_manifest_sha256": file_hash(target_path),
        "sealed_variations_opened": True,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
        "headline_eligible": False,
    }
    write_json(output_dir / "manifest_build.json", payload)
    report = [
        "# EBW Track A v41 Hard Target Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Rows: {len(selected)}",
        f"- Max per class: {args.max_per_class}",
        "- Claim boundary: exploratory pass-subset only; v39 hard held-out protocol was blocked.",
        "- Model/GPU/Docker actions: No",
        "",
        "## Target Classes",
        "",
        "| Target class | Rows |",
        "|---|---:|",
    ]
    report += [f"| `{key}` | {value} |" for key, value in sorted(selected_counts.items())]
    (output_dir / "TARGET_MANIFEST.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "rows": len(selected), "target_classes": payload["target_classes"], "report": str((output_dir / "TARGET_MANIFEST.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()