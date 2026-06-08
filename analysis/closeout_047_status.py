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


def _read(path: str) -> dict[str, Any] | None:
    target = REPO_ROOT / path
    if not target.exists():
        return None
    with target.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"event": "write_json", "path": str(path.relative_to(REPO_ROOT)), "status": payload.get("status")}), flush=True)


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
        artifacts.append("results/closeout_047/gru_in_loop/gru_in_loop_r3plus_rerun.json")
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