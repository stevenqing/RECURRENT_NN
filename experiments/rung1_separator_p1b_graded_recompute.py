"""Offline graded recompute for the P1b v1.1 pilot."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel
from experiments.rung1_separator_llm_po_forward_gate import SEPARATOR_RESULTS_PATH


RESULTS_ROOT = REPO_ROOT / "results/rung1_separator_fallibility_rungs"
PILOT_PATH = RESULTS_ROOT / "p1b_truncation_pilot.json"
OUTPUT_PATH = RESULTS_ROOT / "p1b_graded_recompute.json"
P1A_RECOVERY_BASELINE_PATH = REPO_ROOT / "results/rung1_separator_llm_po/p1a_recovery_baseline.json"
SCHEMA_VERSION = "rung1_separator_p1b_graded_recompute_v0"
STATUS_PASS = "RUNG1_SEPARATOR_P1B_GRADED_RECOMPUTE_STEP1A_PASS"
STATUS_STEP2_REQUIRED = "RUNG1_SEPARATOR_P1B_GRADED_RECOMPUTE_STEP1B_ENCODING_REPILOT_REQUIRED"
FUNCTIONAL_RECALL_THRESHOLD = 0.20
TRUNCATION_RATE_THRESHOLD = 0.10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _edge_degree(row: dict[str, Any], vertex: int) -> int:
    return sum(1 for u, v in row["edges"] if int(u) == vertex or int(v) == vertex)


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _mean_defined(values: list[float | None]) -> float | None:
    defined = [float(value) for value in values if value is not None]
    return mean(defined) if defined else None


def _cell_key(row: dict[str, Any]) -> tuple[int, int]:
    return int(row["d_global_reference"]), int(row["b"])


def _truncation_by_cell(pilot: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for row in pilot.get("operator_functional_gate_by_cell", []):
        out[(int(row["d_global_bin"]), int(row["b_bin"]))] = row
    return out


def run(pilot_path: Path = PILOT_PATH, output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    p1a = _read_json(P1A_RECOVERY_BASELINE_PATH)
    pilot = _read_json(pilot_path)
    separator = _read_json(SEPARATOR_RESULTS_PATH)
    p1a_landed = bool(p1a.get("acceptance", {}).get("p1a_recovery_baseline_landed")) and p1a.get("status") == "RUNG1_SEPARATOR_LLM_PO_P1A_RECOVERY_BASELINE_PASS"
    pilot_v11 = pilot.get("schema_version") == "rung1_separator_p1b_truncation_pilot_v1_1"
    metrics = pilot.get("instance_arm_metrics", [])
    if not p1a_landed:
        raise RuntimeError("entry gate failed: P1a recovery baseline is not landed")
    if not pilot_v11 or not metrics:
        raise RuntimeError("entry gate failed: v1.1 pilot metrics are not present")
    manifest = {row["instance_id"]: row for row in separator.get("instance_manifest", [])}
    truncation_rows = _truncation_by_cell(pilot)
    instance_rows: list[dict[str, Any]] = []
    by_cell: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in metrics:
        manifest_row = manifest.get(row["instance_id"])
        if manifest_row is None:
            raise RuntimeError(f"missing separator manifest row for {row['instance_id']}")
        current_vertex = int(manifest_row["order"][0])
        oracle_prune_count = _edge_degree(manifest_row, current_vertex)
        missed_prune_count = int(row.get("missed_propagation", 0))
        rejected_prune_count = int(row.get("unsound_propagation_rejected", 0))
        accepted_prune_count = max(0, oracle_prune_count - missed_prune_count)
        proposed_prune_count = accepted_prune_count + rejected_prune_count
        prune_precision = _safe_div(accepted_prune_count, proposed_prune_count)
        prune_recall = _safe_div(accepted_prune_count, oracle_prune_count)
        clean_k_eff = float(manifest_row.get("mean_live_domain_at_decision") or row.get("k_eff_clean") or manifest_row.get("k") or 1.0)
        unpruned_k_eff = float(manifest_row.get("k") or row.get("k_eff_clean") or clean_k_eff)
        if prune_recall is None:
            graded_keff = unpruned_k_eff
        else:
            graded_keff = clean_k_eff + (1.0 - prune_recall) * (unpruned_k_eff - clean_k_eff)
        graded_row = {
            "instance_id": row["instance_id"],
            "cell": f"d{int(row['d_global_reference'])}_b{int(row['b'])}",
            "cell_id": row["cell_id"],
            "d_global_reference": int(row["d_global_reference"]),
            "b": int(row["b"]),
            "current_vertex": current_vertex,
            "oracle_prune_count": oracle_prune_count,
            "accepted_prune_count": accepted_prune_count,
            "rejected_prune_count": rejected_prune_count,
            "missed_prune_count": missed_prune_count,
            "proposed_prune_count": proposed_prune_count,
            "prune_precision": prune_precision,
            "prune_recall": prune_recall,
            "k_eff_clean": clean_k_eff,
            "unpruned_k_eff": unpruned_k_eff,
            "graded_keff_inflated": graded_keff,
            "rho_graded": graded_keff / max(clean_k_eff, 1e-9),
            "exact_match_correct_propagation_rate": float(row.get("correct_propagation_rate", 0.0)),
            "generation_valid": int(row.get("generation_valid", 0)),
            "generation_parsable_invalid": int(row.get("generation_parsable_invalid", 0)),
            "generation_truncated_no_answer": int(row.get("generation_truncated_no_answer", 0)),
            "finish_reason": row.get("finish_reason"),
            "reconstruction_basis": "v1.1 pilot aggregate counters plus separator manifest first-step graph degree; no new Qwen calls",
            "source": SOURCE,
            "provenance": "qwen35_p1b_graded_recompute_instance_v0",
        }
        instance_rows.append(graded_row)
        by_cell[_cell_key(row)].append(graded_row)
    cell_rows: list[dict[str, Any]] = []
    for (d_global, b_value), rows in sorted(by_cell.items()):
        oracle = sum(int(row["oracle_prune_count"]) for row in rows)
        accepted = sum(int(row["accepted_prune_count"]) for row in rows)
        rejected = sum(int(row["rejected_prune_count"]) for row in rows)
        missed = sum(int(row["missed_prune_count"]) for row in rows)
        truncation = truncation_rows.get((d_global, b_value), {})
        truncation_pass = bool(truncation.get("truncation_pass", float(truncation.get("frac_truncated_or_length", 1.0)) <= TRUNCATION_RATE_THRESHOLD))
        recall = _safe_div(accepted, oracle)
        precision = _safe_div(accepted, accepted + rejected)
        functional_pass = recall is not None and recall >= FUNCTIONAL_RECALL_THRESHOLD
        cell_rows.append({
            "cell": f"d{d_global}_b{b_value}",
            "d_global_bin": str(d_global),
            "b_bin": str(b_value),
            "n": len(rows),
            "oracle_prune_count": oracle,
            "accepted_prune_count": accepted,
            "rejected_prune_count": rejected,
            "missed_prune_count": missed,
            "proposed_prune_count": accepted + rejected,
            "prune_precision": precision,
            "prune_recall": recall,
            "graded_keff_inflated": _mean_defined([row["graded_keff_inflated"] for row in rows]),
            "k_eff_clean": _mean_defined([row["k_eff_clean"] for row in rows]),
            "unpruned_k_eff": _mean_defined([row["unpruned_k_eff"] for row in rows]),
            "rho_graded": _mean_defined([row["rho_graded"] for row in rows]),
            "exact_match_correct_propagation_rate": _mean_defined([row["exact_match_correct_propagation_rate"] for row in rows]),
            "frac_truncated_or_length": truncation.get("frac_truncated_or_length"),
            "truncation_pass": truncation_pass,
            "graded_functional_pass": functional_pass,
            "cell_allowed_for_step3": truncation_pass and functional_pass,
            "source": SOURCE,
            "provenance": "qwen35_p1b_graded_recompute_by_cell_v0",
        })
    allowed_cells = [row["cell"] for row in cell_rows if row["cell_allowed_for_step3"]]
    excluded_cells = [row["cell"] for row in cell_rows if not row["cell_allowed_for_step3"]]
    branch = "1A" if allowed_cells else "1B"
    status = STATUS_PASS if allowed_cells else STATUS_STEP2_REQUIRED
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": status,
        "entry_gate": {
            "p1a_recovery_baseline_landed": p1a_landed,
            "v1_1_pilot_metrics_present": pilot_v11 and bool(metrics),
            "no_new_qwen_calls": True,
            "raw_generation_text_retained_in_v1_1_pilot": False,
            "reconstruction_note": "v1.1 pilot stored aggregate prune counters, not raw generation text; per-prune counts are recovered exactly for the one-step pilot from manifest graph degree, missed_prune_count, and rejected_prune_count.",
            "source": SOURCE,
            "provenance": "qwen35_p1b_graded_recompute_entry_gate_v0",
        },
        "generation_config": {
            "source_pilot_path": _rel(pilot_path),
            "source_pilot_schema_version": pilot.get("schema_version"),
            "source_pilot_status": pilot.get("status"),
            "source_operator_version": pilot.get("generation_config", {}).get("operator_version"),
            "source_prompt_contract": pilot.get("generation_config", {}).get("prompt_contract"),
            "source_batch_size_per_gpu_observed_values": pilot.get("generation_config", {}).get("batch_size_per_gpu_observed_values"),
            "source_n_per_cell_observed_values": pilot.get("generation_config", {}).get("n_per_cell_observed_values"),
            "functional_recall_threshold": FUNCTIONAL_RECALL_THRESHOLD,
            "truncation_rate_threshold": TRUNCATION_RATE_THRESHOLD,
            "graded_keff_method": "k_eff_clean + (1 - prune_recall) * (unpruned_k_eff - k_eff_clean)",
            "source": SOURCE,
            "provenance": "qwen35_p1b_graded_recompute_config_v0",
        },
        "graded_functional_gate_by_cell": cell_rows,
        "instance_prune_metrics": instance_rows,
        "acceptance": {
            "step1_branch": branch,
            "step2_required": branch == "1B",
            "p1b_graded_functional_gate_pass": bool(allowed_cells),
            "p1b_step3_allowed_cells": allowed_cells,
            "p1b_step3_excluded_cells": excluded_cells,
            "exact_match_correct_propagation_rate_retired_to_diagnostic": True,
        },
        "verdict": [
            {"check": "entry_gate", "predicted": "P1a landed and v1.1 pilot metrics present", "observed": f"p1a_landed={p1a_landed}; pilot_v11={pilot_v11}; n_metrics={len(metrics)}", "pass": True, "source": SOURCE, "provenance": "qwen35_p1b_graded_recompute_verdict_v0"},
            {"check": "graded_recall_functional_gate", "predicted": f"any cell prune_recall >= {FUNCTIONAL_RECALL_THRESHOLD:.2f} and truncation passes", "observed": f"allowed_cells={allowed_cells}; excluded_cells={excluded_cells}", "pass": bool(allowed_cells), "source": SOURCE, "provenance": "qwen35_p1b_graded_recompute_verdict_v0"},
            {"check": "step1_branch", "predicted": "1A if graded recall is meaningfully above zero on any cell; otherwise 1B", "observed": branch, "pass": True, "source": SOURCE, "provenance": "qwen35_p1b_graded_recompute_verdict_v0"},
        ],
    }
    _write_json(output_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-path", default=str(PILOT_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()
    pilot_path = Path(args.pilot_path) if Path(args.pilot_path).is_absolute() else REPO_ROOT / args.pilot_path
    output_path = Path(args.output) if Path(args.output).is_absolute() else REPO_ROOT / args.output
    run(pilot_path, output_path)


if __name__ == "__main__":
    main()