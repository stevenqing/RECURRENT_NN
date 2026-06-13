"""Derived metrics dashboard for Reasoning Gym baseline artifacts."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import comb
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel


SCHEMA_VERSION = "reasoning_gym_baseline_metrics_v1"
STATUS_COMPLETE = "REASONING_GYM_BASELINE_METRICS_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path if path.is_absolute() else REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": _rel(path), "status": payload.get("status")}), flush=True)


def _load_artifact(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = path if path.is_absolute() else REPO_ROOT / path
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"schema_version": "checkpoint_rows", "status": "CHECKPOINT_ROWS"}, payload
    return payload, list(payload.get("rows", []))


def _pass_at_k(num_samples: int, num_correct: int, k_value: int) -> float | None:
    if num_samples < k_value or k_value <= 0:
        return None
    if num_correct <= 0:
        return 0.0
    if num_samples - num_correct < k_value:
        return 1.0
    return 1.0 - comb(num_samples - num_correct, k_value) / comb(num_samples, k_value)


def _score_bucket(score: float) -> str:
    if score >= 1.0:
        return "score_1"
    if score > 0.0:
        return "score_0_1"
    return "score_0"


def _artifact_metrics(path: Path, rows: list[dict[str, Any]], k_values: list[int]) -> list[dict[str, Any]]:
    out = []
    for benchmark, arm in sorted({(str(row.get("benchmark")), str(row.get("arm"))) for row in rows if row.get("benchmark") and row.get("arm")}):
        subset = [row for row in rows if str(row.get("benchmark")) == benchmark and str(row.get("arm")) == arm]
        by_source: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in subset:
            by_source[int(row.get("source_index", -1))].append(row)
        pass_at = {}
        oracle_best_at = {}
        eligible_by_k = {}
        for k_value in k_values:
            eligible = [source_rows for source_rows in by_source.values() if len(source_rows) >= k_value]
            eligible_by_k[str(k_value)] = len(eligible)
            if not eligible:
                pass_at[str(k_value)] = None
                oracle_best_at[str(k_value)] = None
                continue
            pass_at[str(k_value)] = mean(_pass_at_k(len(source_rows), sum(bool(row.get("solved")) for row in source_rows), k_value) for source_rows in eligible)
            oracle_best_at[str(k_value)] = mean(max(float(row.get("official_score", 0.0)) for row in source_rows[:k_value]) for source_rows in eligible)
        parseable_values = [bool(row.get("parseable_answer")) for row in subset if "parseable_answer" in row]
        truncated_values = [bool(row.get("truncated") or row.get("finish_reason") == "length") for row in subset if "finish_reason" in row or "truncated" in row]
        out.append(
            {
                "artifact": str(path),
                "benchmark": benchmark,
                "arm": arm,
                "n_rows": len(subset),
                "n_instances": len(by_source),
                "samples_per_instance_counts": dict(Counter(len(source_rows) for source_rows in by_source.values())),
                "solve_rate": mean(float(row.get("solved", False)) for row in subset),
                "mean_official_score": mean(float(row.get("official_score", 0.0)) for row in subset),
                "nonzero_score_rate": mean(float(float(row.get("official_score", 0.0)) > 0.0) for row in subset),
                "score_bucket_counts": dict(Counter(_score_bucket(float(row.get("official_score", 0.0))) for row in subset)),
                "mean_total_tokens": mean(int(row.get("total_tokens", 0)) for row in subset),
                "status_counts": dict(Counter(str(row.get("status")) for row in subset)),
                "finish_reason_counts": dict(Counter(str(row.get("finish_reason")) for row in subset if row.get("finish_reason") is not None)),
                "truncated_rate": mean(truncated_values) if truncated_values else None,
                "parseable_answer_rate": mean(parseable_values) if parseable_values else None,
                "pass_at_k": pass_at,
                "oracle_best_at_k": oracle_best_at,
                "eligible_instances_by_k": eligible_by_k,
                "source": SOURCE,
                "provenance": "rg_baseline_artifact_metrics_v1",
            }
        )
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    k_values = [int(item) for item in args.k_values.split(",") if item.strip()]
    input_paths = [Path(item) for item in args.inputs.split(",") if item.strip()]
    artifact_rows = []
    artifact_summaries = []
    for path in input_paths:
        metadata, rows = _load_artifact(path)
        artifact_summaries.append({"artifact": str(path), "status": metadata.get("status"), "schema_version": metadata.get("schema_version"), "n_rows": len(rows)})
        artifact_rows.extend(_artifact_metrics(path, rows, k_values))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "metric_policy": {
            "why": "Exact solve_rate is often binary on Reasoning Gym; derived metrics expose partial credit, truncation, parseability, and future pass@k readiness.",
            "pass_at_k_requires_multiple_samples_per_instance": True,
            "source": SOURCE,
            "provenance": "rg_baseline_metric_policy_v1",
        },
        "input_artifacts": artifact_summaries,
        "artifact_metrics": artifact_rows,
        "cross_artifact_notes": {
            "current_passk_status": "Most current artifacts have one sample per instance, so pass@k beyond k=1 is not yet populated. Run BoN/self-consistency artifacts to fill pass@5/pass@10.",
            "useful_now": ["mean_official_score", "nonzero_score_rate", "finish_reason_counts", "truncated_rate", "parseable_answer_rate", "mean_total_tokens"],
            "source": SOURCE,
            "provenance": "rg_baseline_metric_notes_v1",
        },
        "honesty": {
            "does_not_establish": "This artifact computes derived metrics over existing baseline artifacts. It does not add new model samples and does not compare our method.",
            "passk_limit": "pass@k for k>1 is meaningful only after repeated samples per source_index are generated.",
            "source": SOURCE,
            "provenance": "rg_baseline_metrics_honesty_v1",
        },
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute derived metrics for Reasoning Gym baseline artifacts.")
    parser.add_argument("--output", type=Path, default=Path("results/reasoning_gym_baselines/baseline_metrics_dashboard.json"))
    parser.add_argument("--inputs", default=",".join([
        "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_direct.json",
        "results/reasoning_gym_baselines/baseline_matrix_sudoku_l1_direct.json",
        "results/reasoning_gym_baselines/baseline_matrix_zebra_l1_direct.json",
        "results/reasoning_gym_baselines/baseline_matrix_graph_color_l1_thinking_pilot.json",
    ]))
    parser.add_argument("--k-values", default="1,5,10")
    run(parser.parse_args())


if __name__ == "__main__":
    main()