"""Write a morning report for Stage A latent backtracking."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _line(text: str = "") -> str:
    return text + "\n"


def report(output_dir: str = "results/stage_a_backtrack") -> dict[str, Any]:
    root = Path(output_dir)
    results_path = root / "results.json"
    if not results_path.exists():
        raise FileNotFoundError(f"missing merged Stage A results: {results_path}")
    data = json.loads(results_path.read_text(encoding="utf-8"))
    verdict = "PRECHECK_FAILED" if data.get("preflight_failed") else "NEEDS_REVIEW"
    if data.get("n_cells", 0) > 0 and not data.get("preflight_failed"):
        verdict = "RESULTS_AVAILABLE"
    lines = []
    lines.append(_line("# Stage A Backtracking In The Head Report"))
    lines.append(_line(f"Verdict: `{verdict}`"))
    lines.append(_line(f"Shards: `{data.get('n_shards', 0)}`"))
    lines.append(_line(f"Cells with results: `{data.get('n_cells', 0)}`"))
    lines.append(_line(f"Shard statuses: `{data.get('statuses', [])}`"))
    if data.get("preflight_failed"):
        lines.append(_line("## Preflight"))
        lines.append(_line("Stage A did not start because inherited parent artifacts were missing or incomplete. This is intentional: the job must not silently rebuild or substitute the frozen parent operator, bridge decoder, or teacher traces."))
        for shard in data.get("shards", []):
            missing = shard.get("preflight", {}).get("missing", [])
            if missing:
                lines.append(_line(f"- {shard.get('path')}: missing `{[row.get('name') for row in missing]}`"))
    lines.append(_line("## Gate Table"))
    lines.append(_line("| grid | stack | D | n | gate_pass_rate | mean_max_solve_depth |"))
    lines.append(_line("| --- | --- | --- | --- | --- | --- |"))
    for row in data.get("summary", []):
        lines.append(_line(f"| {row.get('grid')} | {row.get('stack')} | {row.get('D')} | {row.get('n')} | {row.get('gate_pass_rate')} | {row.get('mean_max_solve_depth')} |"))
    lines.append(_line("## Decision Rule"))
    lines.append(_line("Stage A is confirmed only if rot_* passes the depth-1 gate and solve depth tracks Module-1 capacity while beating gru and rot_no_revert. A rot_* depth-1 failure is treated as wiring bug, not capacity evidence."))
    report_md = root / "report.md"
    report_json = root / "report.json"
    payload = {"module": "stage_a_backtrack_report", "verdict": verdict, "source": str(results_path), "statuses": data.get("statuses", []), "n_cells": data.get("n_cells", 0)}
    report_md.write_text("".join(lines), encoding="utf-8")
    report_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"report_md": str(report_md), "report_json": str(report_json), **payload}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write Stage A latent backtracking report.")
    parser.add_argument("--output-dir", default="results/stage_a_backtrack")
    args = parser.parse_args()
    print(json.dumps(report(args.output_dir), indent=2, sort_keys=True))