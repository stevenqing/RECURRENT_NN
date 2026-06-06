"""Aggregate M2.0 frozen operator probe reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _get(data: dict[str, Any], path: list[str], default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def verdict(probe: dict[str, Any], rollout: dict[str, Any]) -> str:
    parse_rate = _get(probe, ["summary", "overall", "parse_success_rate"], 0.0) or 0.0
    recall = _get(probe, ["summary", "overall", "forced_recall"], 0.0) or 0.0
    fixpoint_rate = _get(probe, ["summary", "overall", "fixpoint_reach_rate"], 0.0) or 0.0
    status_recall = _get(probe, ["summary", "overall", "status_contradiction_recall"], None)
    branch = _get(rollout, ["summary", "overall"], {})
    qwen = branch.get("qwen_guess", {})
    random = branch.get("random", {})
    branch_ok = False
    if qwen.get("solve_rate") is not None and random.get("solve_rate") is not None:
        branch_ok = (qwen["solve_rate"] > random["solve_rate"]) or (
            qwen["solve_rate"] == random["solve_rate"] and (qwen.get("mean_nodes_to_solve_or_cap") or 10**9) <= (random.get("mean_nodes_to_solve_or_cap") or 10**9)
        )
    if parse_rate < 0.9 or recall < 0.35 or fixpoint_rate < 0.5:
        return "NEEDS_OPERATOR_FIX"
    if status_recall is not None and status_recall < 0.5 and branch_ok:
        return "VERIFIER_LOAD_BEARING"
    if branch_ok:
        return "PREMISE_HOLDS"
    return "NEEDS_OPERATOR_FIX"


def build_report(output_dir: str = "results/m2_operator_probe") -> dict[str, Any]:
    out = Path(output_dir)
    probe = json.loads((out / "operator_probe.json").read_text(encoding="utf-8"))
    rollout = json.loads((out / "branch_rollout.json").read_text(encoding="utf-8"))
    report = {
        "module": "m2_operator_report",
        "probe_path": str(out / "operator_probe.json"),
        "branch_rollout_path": str(out / "branch_rollout.json"),
        "overall": {
            "parse_success_rate": _get(probe, ["summary", "overall", "parse_success_rate"]),
            "forced_recall": _get(probe, ["summary", "overall", "forced_recall"]),
            "raw_precision": _get(probe, ["summary", "overall", "raw_precision"]),
            "fixpoint_rounds": _get(probe, ["summary", "overall", "mean_fixpoint_rounds"]),
            "fixpoint_reach_rate": _get(probe, ["summary", "overall", "fixpoint_reach_rate"]),
            "status_contradiction_recall": _get(probe, ["summary", "overall", "status_contradiction_recall"]),
            "branch": _get(rollout, ["summary", "overall"]),
        },
        "by_task": {
            task: {
                "probe": probe["summary"]["by_task"].get(task),
                "branch": rollout["summary"]["by_task"].get(task),
            }
            for task in sorted(set(probe["summary"]["by_task"]) | set(rollout["summary"]["by_task"]))
        },
        "parse_failure_modes": probe["summary"].get("failure_modes", {}),
        "status_confusion": probe["summary"].get("status_confusion", {}),
    }
    report["verdict"] = verdict(probe, rollout)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def _markdown(report: dict[str, Any]) -> str:
    overall = report["overall"]
    lines = ["# M2.0 Operator Competence Probe", "", f"Verdict: `{report['verdict']}`", "", "## Overall", ""]
    for key in ["parse_success_rate", "forced_recall", "raw_precision", "fixpoint_rounds", "fixpoint_reach_rate", "status_contradiction_recall"]:
        lines.append(f"- {key}: `{overall.get(key)}`")
    lines.append("- branch: `" + json.dumps(overall.get("branch"), sort_keys=True) + "`")
    lines.extend(["", "## By Task", ""])
    for task, values in report["by_task"].items():
        lines.append(f"### {task}")
        lines.append("- probe: `" + json.dumps(values.get("probe"), sort_keys=True) + "`")
        lines.append("- branch: `" + json.dumps(values.get("branch"), sort_keys=True) + "`")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="results/m2_operator_probe")
    args = parser.parse_args()
    print(json.dumps(build_report(args.output_dir), indent=2, sort_keys=True))