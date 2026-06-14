"""Merge KV-cache graph_color search outputs across shards and difficulty bins."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from analysis.kvcache_graph_color_search import STATUS_COMPLETE, _summarize, _write_json
from experiments.rung1_distributed_graph_coloring import REPO_ROOT, SOURCE, _rel


SCHEMA_VERSION = "kvcache_graph_color_merged_bins_v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_payload(path: Path) -> Any:
    path = path if path.is_absolute() else REPO_ROOT / path
    return json.loads(path.read_text(encoding="utf-8"))


def _row_key(row: dict[str, Any]) -> tuple[str, str, int, int]:
    return (str(row.get("difficulty_bin") or "unlabeled"), str(row["arm"]), int(row["R"]), int(row["source_index"]))


def run(args: argparse.Namespace) -> dict[str, Any]:
    rows_by_key: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    input_summaries: list[dict[str, Any]] = []
    for input_path in args.inputs:
        payload = _read_payload(input_path)
        payload_rows = payload.get("rows", []) if isinstance(payload, dict) else payload
        if not isinstance(payload_rows, list):
            raise ValueError(f"Input does not contain row list: {input_path}")
        for row in payload_rows:
            rows_by_key[_row_key(row)] = row
        input_summaries.append({"path": _rel(input_path if input_path.is_absolute() else REPO_ROOT / input_path), "status": payload.get("status") if isinstance(payload, dict) else "rows_only", "rows": len(payload_rows)})
    rows = list(rows_by_key.values())
    solve_by_R, decision_quality, fallback_rate, context_vs_depth, a_vs_c_by_depth, tokens, fork_verdicts = _summarize(rows)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_COMPLETE,
        "generated_at": _now(),
        "inputs": input_summaries,
        "n_rows": len(rows),
        "solve_by_R": solve_by_R,
        "decision_quality": decision_quality,
        "fallback_rate": fallback_rate,
        "context_vs_depth": context_vs_depth,
        "A_vs_C_by_depth": a_vs_c_by_depth,
        "tokens": tokens,
        "fork_verdicts": fork_verdicts,
        "rows": rows,
        "source": SOURCE,
        "provenance": SCHEMA_VERSION,
    }
    _write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge KV-cache graph_color shard/bin outputs.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()