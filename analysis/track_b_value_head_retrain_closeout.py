"""Summarize the one authorized Track B value-head retrain attempt."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = REPO_ROOT / "results/track_b_value_head_retrain_20260609"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_049_track_b_value_head_retrain.json"
ROOT_ACCEPTANCE_PATH = RUN_ROOT / "acceptance.json"

SEED_DIRS = [
    (102, "seed102_gpu0"),
    (137, "seed137_gpu1"),
    (256, "seed256_gpu6"),
]

BASE_CHECKPOINT = "results/track_b_trm_retry_seed102_ddp8_sharded_20260608T114308Z/seed102_ddp8/trm_operator_seed102.pt"
LAUNCH_CORRECTION_NOTE = (
    "The first seed137/seed256 launches used their older hidden_dim=768 checkpoints and failed before training at state_dict shape load. "
    "The completed reruns used the same 6.9M seed102 DDP Track B base checkpoint as seed102 so the parameter count and mask head stayed fixed; this completed the single authorized attempt rather than starting a second retrain."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"event": "write_json", "path": _rel(path), "status": payload.get("status")}), flush=True)


def _metric(payload: dict[str, Any], split: str, key: str) -> Any:
    value_fix = payload.get("value_head_fix", {})
    table = value_fix.get(f"{split}_mask_only_vs_full_commit", {})
    return table.get(key)


def _dominant(mapping: dict[str, Any] | None) -> str | None:
    if not mapping:
        return None
    return max(mapping, key=mapping.get)


def _seed_summary(seed: int, dirname: str) -> dict[str, Any]:
    path = RUN_ROOT / dirname / "acceptance.json"
    payload = _read(path)
    if not payload:
        return {"seed": seed, "dirname": dirname, "acceptance": _rel(path), "present": False}
    eval_table = payload.get("value_head_fix", {}).get("eval_mask_only_vs_full_commit", {})
    block_audit = eval_table.get("commit_block_audit", {}) if isinstance(eval_table.get("commit_block_audit"), dict) else {}
    stick_hist = eval_table.get("stick_reason_histogram", {}) if isinstance(eval_table.get("stick_reason_histogram"), dict) else {}
    acceptance = payload.get("acceptance", {}) if isinstance(payload.get("acceptance"), dict) else {}
    return {
        "seed": seed,
        "dirname": dirname,
        "acceptance": _rel(path),
        "present": True,
        "status": payload.get("status"),
        "completed_step": payload.get("training_curve_summary", {}).get("completed_step"),
        "parameter_count": payload.get("parameter_count"),
        "trainable_parameter_count": payload.get("trainable_parameter_count"),
        "calibrated_tau": payload.get("value_head_fix", {}).get("calibrated_tau"),
        "G1": payload.get("G1"),
        "G2": payload.get("G2"),
        "G1_pass": acceptance.get("G1_pass"),
        "leading_indicator_success": acceptance.get("leading_indicator_success"),
        "eval_mask_only_precision": _metric(payload, "eval", "mask_only_precision"),
        "eval_mask_only_recall": _metric(payload, "eval", "mask_only_recall"),
        "eval_full_commit_precision": _metric(payload, "eval", "full_commit_precision"),
        "eval_full_commit_recall": _metric(payload, "eval", "full_commit_recall"),
        "eval_full_proposed_commits": _metric(payload, "eval", "full_proposed_commits"),
        "eval_full_true_forced_states": _metric(payload, "eval", "full_true_forced_states"),
        "dominant_stick_reason": _dominant(stick_hist),
        "dominant_block_audit": _dominant(block_audit),
        "gate_or_appendix_decision": acceptance.get("gate_or_appendix_decision"),
    }


def build_acceptance() -> dict[str, Any]:
    rows = [_seed_summary(seed, dirname) for seed, dirname in SEED_DIRS]
    all_present = all(row.get("present") for row in rows)
    passing_rows = [row for row in rows if row.get("G1_pass") and row.get("G1") is not None and float(row.get("G1") or 0.0) >= 0.95]
    learned_cells_present = False
    passed = bool(passing_rows) and learned_cells_present
    status = "TRACK_B_VALUE_HEAD_RETRAIN_GATE_PASSED" if passed else "APPENDIX_VALUE_HEAD_LEARNABILITY_FINDING_NO_SECOND_RETRAIN_NO_DAGGER_RL"
    return {
        "module": "track_b_value_head_retrain_closeout",
        "generated_at": _now(),
        "status": status,
        "attempt_count": 1,
        "seeds": [seed for seed, _ in SEED_DIRS],
        "run_root": _rel(RUN_ROOT),
        "all_seed_acceptances_present": all_present,
        "no_second_retrain": True,
        "no_dagger_rl": True,
        "off_critical_path": True,
        "headline_locked_without_track_b": True,
        "launch_correction_note": LAUNCH_CORRECTION_NOTE,
        "base_checkpoint_for_completed_attempt": BASE_CHECKPOINT,
        "gate_requirements": {
            "G1_threshold": 0.95,
            "G2_requires_learned_recurrent_autonomous_stage_a_cells": True,
            "learned_recurrent_autonomous_stage_a_cells_present": learned_cells_present,
        },
        "decision": {
            "outcome": status,
            "next_step": "Close in appendix as mask-identification-works / value-selection-hard if no seed gates; no second retrain, no DAgger, no RL.",
            "passing_seed_count": len(passing_rows),
        },
        "result_tables": {
            "seed_acceptance_summary": {
                "columns": [
                    "seed",
                    "status",
                    "completed_step",
                    "parameter_count",
                    "trainable_parameter_count",
                    "calibrated_tau",
                    "G1",
                    "G2",
                    "G1_pass",
                    "leading_indicator_success",
                    "eval_mask_only_precision",
                    "eval_mask_only_recall",
                    "eval_full_commit_precision",
                    "eval_full_commit_recall",
                    "dominant_stick_reason",
                    "dominant_block_audit",
                    "gate_or_appendix_decision",
                ],
                "rows": rows,
            }
        },
        "seed_acceptance_paths": [_rel(RUN_ROOT / dirname / "acceptance.json") for _, dirname in SEED_DIRS],
        "launch_diagnostic_logs": [_rel(RUN_ROOT / dirname / "train.log") for seed, dirname in SEED_DIRS if seed in {137, 256}],
        "completed_attempt_logs": [_rel(RUN_ROOT / dirname / "train_rerun.log") for seed, dirname in SEED_DIRS if seed in {137, 256}],
        "fail_closed": not all_present,
    }


def build_item(acceptance: dict[str, Any]) -> dict[str, Any]:
    rows = acceptance.get("result_tables", {}).get("seed_acceptance_summary", {}).get("rows", [])
    artifacts = [
        _rel(ROOT_ACCEPTANCE_PATH),
        _rel(ITEM_PATH),
        *acceptance.get("seed_acceptance_paths", []),
        *acceptance.get("launch_diagnostic_logs", []),
        *acceptance.get("completed_attempt_logs", []),
    ]
    item_status = acceptance.get("status")
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": "049",
        "name": "Track B one-shot value-head retrain",
        "status": item_status,
        "purpose": "Execute exactly one off-critical-path Track B value-head/commit-conjunction retrain after the mask/full diagnostic showed high mask-only P/R but low full-commit P/R.",
        "code_added_used": [
            {"path": "experiments/train_trm_operator.py", "change": "Adds per-cell value-head mode, value-head-only checkpoint initialization, per-cell forced-value CE, tau-calibrated post-fix mask/full metrics, and one-attempt acceptance fields."},
            {"path": "experiments/train_recurrent_operator.py", "change": "Allows shared commit/eval helpers to consume per-cell value logits."},
            {"path": "analysis/track_b_value_head_retrain_closeout.py", "change": "Aggregates the three seed acceptances into this item and the root acceptance.json."},
        ],
        "commands": [
            {"command": f"CUDA_VISIBLE_DEVICES={{0,1,6}} .venv/bin/python -m experiments.train_trm_operator --value-head-mode per_cell --train-value-head-only --init-checkpoint {BASE_CHECKPOINT} --steps 3000 --batch-size 2048 --amp-bf16 --torch-compile", "purpose": "Run the completed single authorized value-head retrain attempt for seeds 102, 137, and 256 using the fixed 6.9M Track B base checkpoint."},
            {"command": ".venv/bin/python -m analysis.track_b_value_head_retrain_closeout", "purpose": "Write the root acceptance.json and item049 summary after all three seed acceptances exist."},
        ],
        "artifacts": artifacts,
        "provenance": {
            "repo": "/home/aiscuser/RECURRENT_NN",
            "generated_at": _now(),
            "track": "B_value_head_commit_conjunction_retrain",
            "run_root": _rel(RUN_ROOT),
            "attempt_count": 1,
            "base_checkpoint_for_completed_attempt": BASE_CHECKPOINT,
            "launch_correction_note": LAUNCH_CORRECTION_NOTE,
        },
        "result_tables": {
            "seed_acceptance_summary": acceptance.get("result_tables", {}).get("seed_acceptance_summary", {}),
            "attempt_policy": {
                "columns": ["policy", "value"],
                "rows": [
                    {"policy": "attempt_count", "value": acceptance.get("attempt_count")},
                    {"policy": "no_second_retrain", "value": acceptance.get("no_second_retrain")},
                    {"policy": "no_dagger_rl", "value": acceptance.get("no_dagger_rl")},
                    {"policy": "headline_locked_without_track_b", "value": acceptance.get("headline_locked_without_track_b")},
                    {"policy": "all_seed_acceptances_present", "value": acceptance.get("all_seed_acceptances_present")},
                    {"policy": "base_checkpoint_for_completed_attempt", "value": acceptance.get("base_checkpoint_for_completed_attempt")},
                    {"policy": "launch_correction", "value": acceptance.get("launch_correction_note")},
                ],
            },
        },
        "honesty": {
            "does_not_establish": "This one retrain does not affect the certified Track A headline. Track B is a passing learned operator only if the retrain gates and learned_recurrent autonomous Stage A cells are present; otherwise it closes as mask-identification-works / value-selection-hard appendix evidence.",
        },
        "decision": {
            "gate_outcomes": [
                {"gate": "single_authorized_retrain_attempt", "number": "attempt_count=1; no_second_retrain=true; no_dagger_rl=true", "outcome": "PASS"},
                {"gate": "track_b_learned_operator_gate", "number": f"passing_seed_count={acceptance.get('decision', {}).get('passing_seed_count')}; learned_cells_present={acceptance.get('gate_requirements', {}).get('learned_recurrent_autonomous_stage_a_cells_present')}", "outcome": "PASS" if item_status == "TRACK_B_VALUE_HEAD_RETRAIN_GATE_PASSED" else "FAIL"},
            ],
            "next_step_routing": acceptance.get("decision", {}).get("next_step"),
        },
    }


def main() -> None:
    acceptance = build_acceptance()
    _write(ROOT_ACCEPTANCE_PATH, acceptance)
    _write(ITEM_PATH, build_item(acceptance))


if __name__ == "__main__":
    main()