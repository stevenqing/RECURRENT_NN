"""Write item047 closeout status labels and item048 ledger entry."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "results/closeout_047/status_corrections.json"
ITEM_PATH = REPO_ROOT / "results/experiment_items/item_048_item047_headline_closeout.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    target = REPO_ROOT / path
    if not target.exists():
        return None
    with target.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"event": "write_json", "path": str(path.relative_to(REPO_ROOT)), "status": payload.get("status")}), flush=True)


def _result_at_depth(cell: dict[str, Any], depth: int, metric: str = "joint_accuracy") -> Any:
    for row in cell.get("curve", []):
        if int(row.get("depth", -1)) == depth:
            return row.get(metric)
    return None


def _headline_certification_summary(figure: dict[str, Any]) -> dict[str, Any]:
    tables = figure.get("result_tables", {}) if isinstance(figure.get("result_tables"), dict) else {}
    source = tables.get("module1_overlay_certification", {})
    rows = source.get("rows", []) if isinstance(source, dict) else []
    summary_rows = [
        {
            "arm": row.get("arm"),
            "D": row.get("D"),
            "band": row.get("band"),
            "n": row.get("n"),
            "predicted_d_star_floor": row.get("predicted_d_star_floor"),
            "observed_spill_off_solve_rate": row.get("observed_spill_off_solve_rate"),
            "depth_le_dstar_fraction": row.get("depth_le_dstar_fraction"),
            "solve_matches_depth_le_dstar": row.get("solve_matches_depth_le_dstar"),
        }
        for row in rows
        if row.get("band") in {"R3-5", "R6+"}
    ]
    return {
        "columns": ["arm", "D", "band", "n", "predicted_d_star_floor", "observed_spill_off_solve_rate", "depth_le_dstar_fraction", "solve_matches_depth_le_dstar"],
        "rows": summary_rows,
    }


def _spill_accounting_summary(figure: dict[str, Any]) -> dict[str, Any]:
    tables = figure.get("result_tables", {}) if isinstance(figure.get("result_tables"), dict) else {}
    source = tables.get("spill_accounting", {})
    rows = source.get("rows", []) if isinstance(source, dict) else []
    summary_rows = [
        {
            "arm": row.get("arm"),
            "D": row.get("D"),
            "seed": row.get("seed"),
            "band": row.get("band"),
            "predicted_d_star_floor": row.get("predicted_d_star_floor"),
            "positive_overflow_entries": row.get("positive_overflow_entries"),
            "observed_table_overflow_entries": row.get("observed_table_overflow_entries"),
            "observed_peak_register_bytes": row.get("observed_peak_register_bytes"),
            "spill_on_solve_rate": row.get("spill_on_solve_rate"),
            "overflow_matches_table": row.get("overflow_matches_table"),
        }
        for row in rows
        if row.get("band") in {"R3-5", "R6+"}
    ]
    return {
        "columns": ["arm", "D", "seed", "band", "predicted_d_star_floor", "positive_overflow_entries", "observed_table_overflow_entries", "observed_peak_register_bytes", "spill_on_solve_rate", "overflow_matches_table"],
        "rows": summary_rows,
    }


def _track_b_pr_summary(track_b: dict[str, Any]) -> dict[str, Any]:
    tables = track_b.get("result_tables", {}) if isinstance(track_b.get("result_tables"), dict) else {}
    source = tables.get("mask_only_vs_full_commit_pr", {})
    rows = source.get("rows", []) if isinstance(source, dict) else []
    summary_rows = []
    for row in rows:
        histogram = row.get("stick_reason_histogram", {}) if isinstance(row.get("stick_reason_histogram"), dict) else {}
        dominant_reason = max(histogram, key=histogram.get) if histogram else None
        summary_rows.append({
            "split": row.get("split"),
            "n_examples": row.get("n_examples"),
            "mask_only_precision": row.get("mask_only_precision"),
            "mask_only_recall": row.get("mask_only_recall"),
            "full_commit_precision": row.get("full_commit_precision"),
            "full_commit_recall": row.get("full_commit_recall"),
            "mask_proposed_cells": row.get("mask_proposed_cells"),
            "mask_true_cells": row.get("mask_true_cells"),
            "full_proposed_commits": row.get("full_proposed_commits"),
            "full_true_forced_states": row.get("full_true_forced_states"),
            "dominant_stick_reason": dominant_reason,
            "dominant_stick_count": histogram.get(dominant_reason) if dominant_reason else None,
        })
    return {
        "columns": ["split", "n_examples", "mask_only_precision", "mask_only_recall", "full_commit_precision", "full_commit_recall", "mask_proposed_cells", "mask_true_cells", "full_proposed_commits", "full_true_forced_states", "dominant_stick_reason", "dominant_stick_count"],
        "rows": summary_rows,
    }


def _gru_cell_summary(grid: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for cell in grid.get("cells", []):
        best = cell.get("best_config", {}) if isinstance(cell.get("best_config"), dict) else {}
        rows.append({
            "D": cell.get("D"),
            "seed": cell.get("seed"),
            "frontier_joint_095": cell.get("frontier_joint_095"),
            "joint_depth_8": _result_at_depth(cell, 8),
            "joint_depth_12": _result_at_depth(cell, 12),
            "joint_depth_16": _result_at_depth(cell, 16),
            "joint_depth_21": _result_at_depth(cell, 21),
            "joint_depth_24": _result_at_depth(cell, 24),
            "best_val_loss": best.get("best_val_loss"),
            "decoder_type": best.get("decoder_type"),
            "converged": cell.get("converged"),
            "result_path": cell.get("result_path"),
        })
    rows.sort(key=lambda row: (int(row.get("D") or 0), int(row.get("seed") or 0)))
    return {
        "columns": ["D", "seed", "frontier_joint_095", "joint_depth_8", "joint_depth_12", "joint_depth_16", "joint_depth_21", "joint_depth_24", "best_val_loss", "decoder_type", "converged", "result_path"],
        "rows": rows,
    }


def _gru_rerun_summary(gru: dict[str, Any]) -> dict[str, Any]:
    tables = gru.get("result_tables", {}) if isinstance(gru.get("result_tables"), dict) else {}
    source = tables.get("gru_r3plus_rerun", {})
    rows = source.get("rows", []) if isinstance(source, dict) else []
    by_cell: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        key = (int(row.get("D", 0)), int(row.get("seed", 0)))
        cell = by_cell.setdefault(key, {
            "D": row.get("D"),
            "seed": row.get("seed"),
            "frontier_joint_095": row.get("frontier_joint_095"),
            "peak_register_bytes": row.get("peak_register_bytes"),
            "gru_audit_pass": row.get("gru_audit_pass"),
            "gru_converged": row.get("gru_converged"),
            "training_curve_ref": row.get("gru_training_curve_ref"),
        })
        if row.get("band") == "R3-5":
            cell["r3_5_solve_rate"] = row.get("solve_rate")
            cell["r3_5_n"] = row.get("n")
        if row.get("band") == "R6+":
            cell["r6plus_solve_rate"] = row.get("solve_rate")
            cell["r6plus_n"] = row.get("n")
    summary_rows = [by_cell[key] for key in sorted(by_cell)]
    return {
        "columns": ["D", "seed", "frontier_joint_095", "r3_5_n", "r3_5_solve_rate", "r6plus_n", "r6plus_solve_rate", "peak_register_bytes", "gru_audit_pass", "gru_converged", "training_curve_ref"],
        "rows": summary_rows,
    }


def _closeout_decision_summary(labels: dict[str, Any], figure: dict[str, Any], track_b: dict[str, Any], gru: dict[str, Any]) -> dict[str, Any]:
    track_b_decision = track_b.get("decision", {}) if isinstance(track_b.get("decision"), dict) else {}
    eval_row = None
    track_b_rows = _track_b_pr_summary(track_b).get("rows", []) if track_b else []
    for row in track_b_rows:
        if row.get("split") == "eval":
            eval_row = row
            break
    gru_rows = _gru_rerun_summary(gru).get("rows", []) if gru else []
    max_gru_solve = max([float(row.get("r3_5_solve_rate") or 0.0) for row in gru_rows] + [float(row.get("r6plus_solve_rate") or 0.0) for row in gru_rows] + [0.0])
    checks = figure.get("checks", {}) if isinstance(figure.get("checks"), dict) else {}
    return {
        "columns": ["metric", "value"],
        "rows": [
            {"metric": "headline_figure", "value": labels.get("headline_figure")},
            {"metric": "spill_off_matches_depth_le_dstar", "value": checks.get("spill_off_solve_matches_depth_le_dstar")},
            {"metric": "spill_on_overflow_matches_table", "value": checks.get("spill_on_overflow_entries_match_depth_minus_dstar")},
            {"metric": "track_b_outcome", "value": track_b_decision.get("outcome")},
            {"metric": "track_b_eval_mask_only_precision", "value": eval_row.get("mask_only_precision") if eval_row else None},
            {"metric": "track_b_eval_mask_only_recall", "value": eval_row.get("mask_only_recall") if eval_row else None},
            {"metric": "track_b_eval_full_commit_precision", "value": eval_row.get("full_commit_precision") if eval_row else None},
            {"metric": "track_b_eval_full_commit_recall", "value": eval_row.get("full_commit_recall") if eval_row else None},
            {"metric": "track_b_threshold", "value": track_b_decision.get("threshold")},
            {"metric": "gru_in_loop_arm", "value": labels.get("gru_in_loop_arm")},
            {"metric": "gru_max_r3plus_solve_rate", "value": max_gru_solve},
            {"metric": "gru_all_audit_pass", "value": all(bool(row.get("gru_audit_pass")) for row in gru_rows) if gru_rows else None},
            {"metric": "gru_all_converged", "value": all(bool(row.get("gru_converged")) for row in gru_rows) if gru_rows else None},
        ],
    }


def build_status() -> dict[str, Any]:
    line1 = _read("results/overnight_047_headline_preregistered/line1_headline/line1_headline.json") or {}
    figure = _read("results/closeout_047/headline_figure/headline_figure_certification.json") or {}
    track_b = _read("results/closeout_047/track_b_mask_commit/track_b_mask_commit_split_diagnostic.json")
    gru = _read("results/closeout_047/gru_in_loop/gru_in_loop_r3plus_rerun.json")

    figure_status = "HEADLINE_FIGURE_CERTIFIED" if str(figure.get("status", "")).startswith("HEADLINE_FIGURE_CERTIFIED") else "CANDIDATE_PENDING_OVERLAY"
    track_b_status = track_b.get("status") if track_b else "DIAGNOSIS_PENDING"
    gru_status = gru.get("status") if gru else "INCOMPLETE_AUDIT_RED"
    gru_quotable = bool(gru) and str(gru_status).endswith("AUDIT_PASS")
    payload = {
        "module": "closeout_047_status",
        "generated_at": _now(),
        "status": "ITEM047_CLOSEOUT_STATUS_RECORDED",
        "supersedes_labels_from": [
            "results/overnight_047_headline_preregistered/line1_headline/line1_headline.json",
            "results/overnight_047_headline_preregistered/line2_track_b_diagnostic/track_b_forced_diagnostic.json",
        ],
        "labels": {
            "rot_vs_no_revert_causal_result": "SOLID",
            "gru_in_loop_arm": gru_status,
            "gru_rows_quotable": gru_quotable,
            "track_b": track_b_status,
            "headline_figure": figure_status,
            "capacity_law_transfer": "CERTIFIED" if figure_status == "HEADLINE_FIGURE_CERTIFIED" else "CANDIDATE_PENDING_OVERLAY",
        },
        "checks": {
            "line1_equivalence_green": bool(line1.get("checks", {}).get("equivalence_logged_before_grid")),
            "line1_gru_audit_red_not_quoted": not bool(line1.get("checks", {}).get("gru_audit_nonzero_bytes_and_curve")) and not gru_quotable,
            "track_b_not_closed_until_split_diagnostic": track_b is not None or track_b_status == "DIAGNOSIS_PENDING",
            "headline_overlay_certified_or_pending_label": figure_status in {"HEADLINE_FIGURE_CERTIFIED", "CANDIDATE_PENDING_OVERLAY"},
        },
        "inputs": {
            "line1": "results/overnight_047_headline_preregistered/line1_headline/line1_headline.json",
            "headline_figure": "results/closeout_047/headline_figure/headline_figure_certification.json" if figure else None,
            "track_b_split": "results/closeout_047/track_b_mask_commit/track_b_mask_commit_split_diagnostic.json" if track_b else None,
            "gru_rerun": "results/closeout_047/gru_in_loop/gru_in_loop_r3plus_rerun.json" if gru else None,
        },
        "fail_closed": False,
    }
    return payload


def build_item(status_payload: dict[str, Any]) -> dict[str, Any]:
    labels = status_payload["labels"]
    figure = _read(status_payload["inputs"].get("headline_figure") or "") or {}
    track_b = _read(status_payload["inputs"].get("track_b_split") or "") or {}
    gru = _read(status_payload["inputs"].get("gru_rerun") or "") or {}
    grid = _read("results/closeout_047/gru_in_loop/gru_in_loop_grid.json") or {}
    track_b_resolved = labels["track_b"] != "DIAGNOSIS_PENDING"
    gru_resolved = bool(labels["gru_rows_quotable"])
    artifacts = [
        "results/closeout_047/status_corrections.json",
        "results/closeout_047/headline_figure/headline_figure_certification.json",
        "results/closeout_047/headline_figure/headline_overlay_spilloff.png",
        "results/experiment_items/item_048_item047_headline_closeout.json",
    ]
    if track_b_resolved:
        artifacts.append("results/closeout_047/track_b_mask_commit/track_b_mask_commit_split_diagnostic.json")
    if status_payload["inputs"].get("gru_rerun"):
        artifacts.append("results/closeout_047/gru_in_loop/gru_in_loop_grid.json")
        artifacts.append("results/closeout_047/gru_in_loop/gru_in_loop_r3plus_rerun.json")
        artifacts.extend([
            f"results/closeout_047/gru_in_loop/cells/D{D}_Kv81_Ku9_with_replacement_seed{seed}/results.json"
            for D in (128, 256, 512)
            for seed in (42, 137)
        ])
    if gru_resolved and track_b_resolved:
        item_status = "ITEM047_CLOSEOUT_COMPLETE"
        honesty_text = "The closeout locks the causal structured-register headline with certified figure/spill accounting, resolves Track B as an off-critical-path mask-head learnability finding, and only quotes GRU rows after nonzero bytes, training curve refs, and converged=true are present."
        next_step_routing = "Closeout acceptance gates are resolved; keep Track B out of the critical path and quote GRU only through the real in-loop rerun artifact."
    else:
        item_status = "ITEM047_CLOSEOUT_IN_PROGRESS"
        missing = []
        if not gru_resolved:
            missing.append("GRU in-loop audit pass")
        if not track_b_resolved:
            missing.append("Track B split diagnostic")
        missing_text = ", ".join(missing)
        honesty_text = f"Until {missing_text} resolves, this item does not quote GRU collapse or close Track B beyond the evidence already written."
        next_step_routing = "Finish the unresolved closeout gates; do not quote GRU collapse or overstate Track B until the corresponding artifacts resolve."
    return {
        "schema_version": "log_item_contract_v1",
        "item_number": "048",
        "name": "Item047 headline closeout status and diagnostics",
        "status": item_status,
        "purpose": "Correct item047 done-but-not-done labels, certify the headline overlay/spill accounting, split Track B mask-only versus full-commit metrics, and keep the GRU in-loop arm red until real bytes/training curves/convergence exist.",
        "code_added_used": [
            {"path": "analysis/headline_figure_certification.py", "change": "Certifies observed spill-off solve against d*(D), spill-on overflow accounting, and the factored codebook mapping footnote."},
            {"path": "analysis/track_b_mask_commit_split_diagnostic.py", "change": "Separates mask-only P/R from full-commit P/R on the existing seed102 checkpoint with tau=0."},
            {"path": "analysis/gru_in_loop_arm.py", "change": "Defines the real in-loop GRU arm train/rerun audit path with nonzero bytes and curve references required before quotation."},
            {"path": "analysis/closeout_047_status.py", "change": "Writes corrected status labels and this ledger item."},
        ],
        "commands": [
            {"command": ".venv/bin/python -m analysis.headline_figure_certification", "purpose": "Certify Task 2 overlay and spill accounting."},
            {"command": ".venv/bin/python -m analysis.track_b_mask_commit_split_diagnostic --device cuda:0", "purpose": "Run Task 3 split diagnostic on the existing checkpoint; no retraining and no DAgger/RL."},
            {"command": ".venv/bin/python -m analysis.gru_in_loop_arm train && .venv/bin/python -m analysis.gru_in_loop_arm rerun", "purpose": "Task 1 real GRU in-loop arm path; rows remain audit-red until this completes."},
            {"command": ".venv/bin/python -m analysis.closeout_047_status", "purpose": "Regenerate corrected labels and item048."},
        ],
        "artifacts": artifacts,
        "provenance": {
            "repo": "/home/aiscuser/RECURRENT_NN",
            "generated_at": _now(),
            "track": "item047_closeout",
            "source_item": "047",
        },
        "result_tables": {
            "closeout_decision_metrics": _closeout_decision_summary(labels, figure, track_b, gru),
            "headline_certification_r3plus": _headline_certification_summary(figure),
            "spill_accounting_r3plus": _spill_accounting_summary(figure),
            "track_b_mask_only_vs_full_commit": _track_b_pr_summary(track_b),
            "gru_cell_frontiers_and_curves": _gru_cell_summary(grid),
            "gru_r3plus_rerun_summary": _gru_rerun_summary(gru),
            "corrected_status_labels": {
                "columns": ["label", "status"],
                "rows": [{"label": key, "status": value} for key, value in labels.items()],
            },
            "acceptance_state": {
                "columns": ["task", "status", "artifact"],
                "rows": [
                    {"task": "Task 1 GRU arm", "status": labels["gru_in_loop_arm"], "artifact": status_payload["inputs"].get("gru_rerun")},
                    {"task": "Task 2 headline figure", "status": labels["headline_figure"], "artifact": status_payload["inputs"].get("headline_figure")},
                    {"task": "Task 3 Track B split", "status": labels["track_b"], "artifact": status_payload["inputs"].get("track_b_split")},
                ],
            },
        },
        "honesty": {
            "does_not_establish": honesty_text,
        },
        "decision": {
            "gate_outcomes": [
                {"gate": "rot_vs_no_revert_causal_spine", "number": labels["rot_vs_no_revert_causal_result"], "outcome": "PASS"},
                {"gate": "headline_overlay", "number": labels["headline_figure"], "outcome": "PASS" if labels["headline_figure"] == "HEADLINE_FIGURE_CERTIFIED" else "PENDING"},
                {"gate": "gru_in_loop_audit", "number": labels["gru_in_loop_arm"], "outcome": "PASS" if labels["gru_rows_quotable"] else "PENDING"},
                {"gate": "track_b_split_diagnostic", "number": labels["track_b"], "outcome": "PENDING" if labels["track_b"] == "DIAGNOSIS_PENDING" else "PASS"},
            ],
            "next_step_routing": next_step_routing,
        },
    }


def main() -> None:
    status_payload = build_status()
    _write(STATUS_PATH, status_payload)
    _write(ITEM_PATH, build_item(status_payload))


if __name__ == "__main__":
    main()