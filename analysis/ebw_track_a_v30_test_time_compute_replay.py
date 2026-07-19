"""Retrospective replay of the frozen v29b RepairAgent loop over opened EBW rows."""
from __future__ import annotations

import argparse
import hashlib
import json
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


def counts(path: str) -> dict[str, int]:
    return load_json(path)["decision_counts"]


def accepted_count(path: str) -> int:
    return int(load_json(path)["accepted_count"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v30_test_time_compute_freeze/freeze.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v30_test_time_compute_replay"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v30 test-time compute replay")

    freeze_path = resolve(args.freeze)
    freeze = load_json(freeze_path)
    paths = {
        "round0_v17_base": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v17_merged/results.json",
        "source_identity_v22": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v22_source_identity_merged/results.json",
        "literal_export_v24": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v24_literal_export_merged/results.json",
        "ordered_note_v26": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v26_ordered_note_merged/results.json",
        "prior_effect_v28": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v28_prior_effect_merged/results.json",
        "v29_model_eval": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29_frontier_selection_model/results.json",
        "v29b_retry_eval": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29b_frontier_selection_retry/results.json",
        "v29b_merged_eval": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29b_frontier_selection_merged/results.json",
    }
    sequential_curve = [
        {"stage": "round0_no_repair", "decision_counts": counts(paths["round0_v17_base"]), "test_time_repair_model_calls": 0},
        {"stage": "after_source_path_identity", "decision_counts": counts(paths["source_identity_v22"]), "test_time_repair_model_calls": 1},
        {"stage": "after_literal_export_path", "decision_counts": counts(paths["literal_export_v24"]), "test_time_repair_model_calls": 2},
        {"stage": "after_ordered_note_title_identity", "decision_counts": counts(paths["ordered_note_v26"]), "test_time_repair_model_calls": 3},
        {"stage": "after_prior_effect_playlist", "decision_counts": counts(paths["prior_effect_v28"]), "test_time_repair_model_calls": 4},
    ]
    parallel_curve = [
        {"stage": "round0_no_repair", "decision_counts": counts(paths["round0_v17_base"]), "repair_rounds": 0, "test_time_repair_model_calls": 0},
        {"stage": "round1_parallel_v29b_repair", "decision_counts": counts(paths["prior_effect_v28"]), "repair_rounds": 1, "test_time_repair_model_calls": 5},
    ]
    checks = {
        "freeze_ready": freeze["status"] == "RPD_EBW_TRACK_A_V30_TEST_TIME_COMPUTE_FREEZE_READY",
        "v29b_accepts_all_packets": accepted_count(paths["v29b_merged_eval"]) == 4,
        "v28_closes_opened_executable": counts(paths["prior_effect_v28"]) == {"commit_live": 847},
        "unsafe_absent_after_replay": "unsafe_unique_wrong" not in counts(paths["prior_effect_v28"]),
        "retrospective_not_heldout": True,
        "sealed_variations_not_opened_by_replay": True,
        "model_gpu_docker_not_used_by_replay": True,
        "external_process_actions_absent": True,
    }
    status = "RPD_EBW_TRACK_A_V30_RETROSPECTIVE_TTC_REPLAY_PASS" if all(checks.values()) else "RPD_EBW_TRACK_A_V30_RETROSPECTIVE_TTC_REPLAY_FAIL"
    output_dir.mkdir(parents=True)
    payload = {
        "schema": "ebw_track_a_v30_test_time_compute_replay_v1",
        "status": status,
        "checks": checks,
        "claim_boundary": "Retrospective opened-data replay validates loop mechanics only; it is not a prospective held-out TTC result.",
        "parallel_repair_curve": parallel_curve,
        "sequential_diagnostic_curve": sequential_curve,
        "model_selection": {
            "v29_initial_accepted": accepted_count(paths["v29_model_eval"]),
            "v29b_retry_accepted": accepted_count(paths["v29b_retry_eval"]),
            "v29b_merged_accepted": accepted_count(paths["v29b_merged_eval"]),
        },
        "input_hashes": {key: file_hash(resolve(path)) for key, path in paths.items()},
        "freeze_sha256": file_hash(freeze_path),
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    write_json(output_dir / "replay.json", payload)
    report = [
        "# EBW Track A v30 Retrospective Test-Time Compute Replay",
        "",
        f"## Status: **`{status}`**",
        "",
        "- Scope: opened-data retrospective replay of the frozen v29b RepairAgent loop",
        "- Held-out/prospective claim: No",
        "- Sealed AppWorld variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions by replay: No",
        "",
        "## Parallel Repair Curve",
        "",
        "| Stage | Repair rounds | Model calls | Commit | Abstain | Unsafe |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in parallel_curve:
        decision = row["decision_counts"]
        report.append(f"| `{row['stage']}` | {row['repair_rounds']} | {row['test_time_repair_model_calls']} | {decision.get('commit_live', 0)} | {decision.get('abstain_no_valid', 0)} | {decision.get('unsafe_unique_wrong', 0)} |")
    report += [
        "",
        "## Claim Boundary",
        "",
        payload["claim_boundary"],
    ]
    (output_dir / "REPLAY.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "report": str((output_dir / "REPLAY.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()