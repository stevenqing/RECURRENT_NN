"""Merge sharded clean-vs-polluted KV-cache decision probe outputs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from analysis.kvcache_decision_probe import SCHEMA_VERSION, STATUS_COMPLETE, _parse_ints, _summarize
from analysis.kvcache_graph_color_search import _write_json
from experiments.rung1_distributed_graph_coloring import SOURCE


MERGE_SCHEMA_VERSION = "kvcache_decision_probe_merged_v0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return list(payload), None
    if isinstance(payload, dict):
        return list(payload.get("rows", [])), payload
    return [], None


def run(args: argparse.Namespace) -> dict[str, Any]:
    rows_by_index: dict[int, dict[str, Any]] = {}
    payloads: list[dict[str, Any]] = []
    inputs: list[str] = []
    coverage: list[dict[str, Any]] = []
    for pattern in args.inputs:
        for path in sorted(Path().glob(pattern)):
            inputs.append(str(path))
            rows, payload = _read_rows(path)
            for row in rows:
                rows_by_index[int(row["row_index"])] = row
            if payload:
                payloads.append(payload)
                if not coverage and isinstance(payload.get("coverage"), list):
                    coverage = list(payload.get("coverage", []))
    rows = [rows_by_index[key] for key in sorted(rows_by_index)]
    n_values = _parse_ints(args.n_values)
    accuracy_by_N_kind, overall_by_N, fork = _summarize(rows, n_values)
    payload = {
        "schema_version": MERGE_SCHEMA_VERSION,
        "source_schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "config": {"inputs": args.inputs, "n_values": args.n_values},
        "input_files": inputs,
        "input_payloads": len(payloads),
        "coverage": coverage,
        "preflight_summary": {
            "evaluated_rows": len(rows),
            "unique_row_indices": len(rows_by_index),
            "scoring_mode": "batched_next_token_integer_choice",
            "shards": sorted({int(row.get("shard_index", -1)) for row in rows}),
        },
        "accuracy_by_N_kind": accuracy_by_N_kind,
        "overall_by_N": overall_by_N,
        "fork_verdicts": fork,
        "rows": rows,
        "source": SOURCE,
        "provenance": MERGE_SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge sharded KV-cache decision probe outputs.")
    parser.add_argument("--output", type=Path, default=Path("results/kvcache_decision_probe/part1/merged_decision_probe.json"))
    parser.add_argument("--inputs", nargs="+", default=["results/kvcache_decision_probe/part1/shard_*.json"])
    parser.add_argument("--n-values", default="0,2,4,8,16,32")
    run(parser.parse_args())


if __name__ == "__main__":
    main()