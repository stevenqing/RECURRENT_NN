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


def _path(output_dir: Path, preferred: str, fallback: str) -> Path:
    preferred_path = output_dir / preferred
    return preferred_path if preferred_path.exists() else output_dir / fallback


def _metric_mean(value: Any) -> Any:
    if isinstance(value, dict) and "mean" in value:
        return value["mean"]
    return value


def build_report(output_dir: str = "results/m2_operator_probe") -> dict[str, Any]:
    out = Path(output_dir)
    probe_path = _path(out, "operator_probe_fix_rescale.json", "operator_probe.json")
    rollout_path = _path(out, "branch_rollout_fix_rescale.json", "branch_rollout.json")
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    rollout = json.loads(rollout_path.read_text(encoding="utf-8"))
    if probe.get("module") == "m2_operator_probe_fix_rescale":
        report = _build_fix_rescale_report(out, probe_path, rollout_path, probe, rollout)
        (out / "report_fix_rescale.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (out / "report_fix_rescale.md").write_text(_markdown(report), encoding="utf-8")
        return report
    report = {
        "module": "m2_operator_report",
        "probe_path": str(probe_path),
        "branch_rollout_path": str(rollout_path),
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


def _build_fix_rescale_report(out: Path, probe_path: Path, rollout_path: Path, probe: dict[str, Any], rollout: dict[str, Any]) -> dict[str, Any]:
    list_by_task = probe["summary"]["list_all"]["by_task"]
    single_by_task = probe["summary"]["single_iterated"]["by_task"]
    branch_by_task = rollout["summary"]["by_task"]
    tasks = sorted(set(single_by_task) | set(branch_by_task))
    by_task = {}
    for task in tasks:
        by_task[task] = {
            "verdict": probe.get("per_task_verdicts", {}).get(task),
            "list_all": list_by_task.get(task),
            "single_iterated": single_by_task.get(task),
            "branch": branch_by_task.get(task),
        }
    branch_overall = rollout["summary"]["overall"]
    qwen_nodes = branch_overall.get("qwen_guess", {}).get("mean_nodes_to_solve_or_cap")
    mrv_nodes = branch_overall.get("mrv", {}).get("mean_nodes_to_solve_or_cap")
    branch_decision = "symbolic_mrv_default"
    if qwen_nodes is not None and mrv_nodes is not None and qwen_nodes < mrv_nodes:
        branch_decision = "qwen_guess_beats_mrv_reconsider"
    return {
        "module": "m2_operator_report_fix_rescale",
        "probe_path": str(probe_path),
        "branch_rollout_path": str(rollout_path),
        "seeds": probe.get("seeds"),
        "n_instances": probe.get("n_instances"),
        "task_types": probe.get("task_types"),
        "overall": {
            "list_all": probe["summary"]["list_all"]["overall"],
            "single_iterated": probe["summary"]["single_iterated"]["overall"],
            "branch": branch_overall,
        },
        "by_task": by_task,
        "rendering_comparison": probe.get("rendering_comparison"),
        "routing": probe.get("routing"),
        "branch_decision": branch_decision,
        "verdict": "PER_TASK_ROUTING",
    }


def _markdown(report: dict[str, Any]) -> str:
    if report.get("module") == "m2_operator_report_fix_rescale":
        lines = ["# M2.0 Fix-And-Rescale Operator Probe", "", f"Verdict: `{report['verdict']}`", "", f"Branch decision: `{report['branch_decision']}`", "", "## Routing", ""]
        routing = report.get("routing") or {}
        lines.append("- pass_tasks: `" + json.dumps(routing.get("pass_tasks", []), sort_keys=True) + "`")
        lines.append("- fix_tasks: `" + json.dumps(routing.get("fix_tasks", []), sort_keys=True) + "`")
        lines.extend(["", "## Overall", ""])
        lines.append("- list_all: `" + json.dumps(report["overall"].get("list_all"), sort_keys=True) + "`")
        lines.append("- single_iterated: `" + json.dumps(report["overall"].get("single_iterated"), sort_keys=True) + "`")
        lines.append("- branch: `" + json.dumps(report["overall"].get("branch"), sort_keys=True) + "`")
        lines.extend(["", "## Rendering", ""])
        lines.append("`" + json.dumps(report.get("rendering_comparison"), sort_keys=True) + "`")
        lines.extend(["", "## By Task", ""])
        for task, values in report["by_task"].items():
            lines.append(f"### {task}")
            lines.append(f"- verdict: `{values.get('verdict')}`")
            lines.append("- list_all: `" + json.dumps(values.get("list_all"), sort_keys=True) + "`")
            lines.append("- single_iterated: `" + json.dumps(values.get("single_iterated"), sort_keys=True) + "`")
            lines.append("- branch: `" + json.dumps(values.get("branch"), sort_keys=True) + "`")
        lines.append("")
        return "\n".join(lines)
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