"""Write a compact JSON/Markdown summary for the GPU4-7 overnight run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import Counter
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT


def _load(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_overnight_gpu4_7"))
    args = parser.parse_args()
    root = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    decision_path = REPO_ROOT / "results/multiagent_real_qwen_decision_gate/evaluation_v2.json"
    end_path = REPO_ROOT / "results/multiagent_real_qwen_end_to_end/dev_results.json"
    decision = _load(decision_path)
    end = _load(end_path)
    status = "COMPLETE" if decision and end else ("DECISION_COMPLETE" if decision else "PENDING")
    payload = {
        "schema": "multiagent_overnight_gpu4_7_summary_v1",
        "status": status,
        "decision_gate": decision,
        "end_to_end": end,
        "headline_eligible": False,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Multi-Agent GPU4–7 Overnight Summary",
        "",
        "> **Subsequent research status (2026-07-11):** The later 200-instance symbolic structural confirmation failed its equal-memory solve and failure-penalized work gates. No new Qwen confirmatory run is authorized from this development signal. See [structural closeout](../multiagent_structural_confirmatory/CLOSEOUT.md).",
        "",
        "> **Second-substrate status (2026-07-12):** Community SAT replicated the symbolic tail-risk/coupling boundary, strengthening a negative resource-evaluation paper direction. It does not revive the earlier Qwen route result or authorize a real-LLM confirmatory run. See [cross-substrate synthesis](../multiagent_cross_substrate_tail_risk/SUMMARY.md).",
        "",
        "> **Route-confirmation status (2026-07-12):** A new preregistered 200-instance SAT-high route study returned `SAT_ROUTE_CONFIRMATION_NO_GO`; deepest routing was not materially or statistically better than random-valid routing. This independently closes the Qwen target-routing premise. See [route closeout](../multiagent_sat_route_confirmation/CLOSEOUT.md).",
        "",
        "> **Capacity-valid repair status (2026-07-12):** A subsequent control repair filtered targets by bounded recovery validity before deepest priority and independently reproduced strong route/work effects on 200 new SAT instances. The strict equal-memory solve-NI gate narrowly failed, and deterministic routing already solved 0.975, so this does not revive a Qwen run. See [capacity-valid synthesis](../multiagent_capacity_valid_route_tail_control/SUMMARY.md).",
        "",
        "> **Graph replication status (2026-07-12):** The same deterministic capacity-valid route passed every frozen gate on a new graph-color pool, matching equal-memory monolith solve at 0.990 with 0.373× penalized work. This establishes a cross-substrate symbolic mechanism and further reduces the scientific value of replacing it with Qwen calls. See [graph closeout](../multiagent_graph_matched_route_confirmation/CLOSEOUT.md).",
        "",
        f"- Status: **{status}**",
        "- Model: `Qwen/Qwen3.5-4B`",
        "- Physical GPUs: 4–7",
        "- Evidence tier: development gate only; not headline eligible",
        "",
        "## Decision Gate",
        "",
    ]
    if decision:
        lines += [
            f"- Status: `{decision.get('status')}`",
            f"- Harvested samples: {decision.get('harvested_samples')} / {decision.get('expected_samples')}",
            f"- Gates: `{json.dumps(decision.get('gates', {}), sort_keys=True)}`",
            "",
            "| Cell | Event | n | Parse | Valid | Exact | Mean total tokens |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
        for row in decision.get("summary", []):
            lines.append(
                f"| {row['cell']} | {row['event']} | {row['n']} | {row['parse_rate']:.3f} | "
                f"{row['valid_rate']:.3f} | {row['exact_rate']:.3f} | {row['mean_total_tokens']:.1f} |"
            )
    else:
        lines.append("Decision evaluation has not completed.")
    lines += ["", "## End-to-End Development", ""]
    if end:
        lines += [
            f"- Status: `{end.get('status')}`",
            f"- Episodes: {end.get('completed_episodes')} / {end.get('expected_episodes')}",
            "",
            "| Cell | Policy | n | Solve | Mean calls | Mean tokens |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for row in end.get("summary", []):
            lines.append(
                f"| {row['cell']} | {row['policy']} | {row['n']} | {row['solve_rate']:.3f} | "
                f"{row['mean_llm_calls']:.1f} | {row['mean_total_tokens']:.1f} |"
            )
        lines += [
            "",
            "### Global policy readout",
            "",
            "| Policy | n | Solve | Total calls | Total tokens | Failure statuses |",
            "|---|---:|---:|---:|---:|---|",
        ]
        global_rows = []
        for policy in sorted({row["policy"] for row in end.get("rows", [])}):
            subset = [row for row in end.get("rows", []) if row["policy"] == policy]
            status_counts = dict(Counter(str(row.get("status")) for row in subset))
            global_rows.append({
                "policy": policy,
                "n": len(subset),
                "solve_rate": mean(float(row.get("solved", False)) for row in subset),
                "calls": sum(int(row.get("llm_calls", 0)) for row in subset),
                "tokens": sum(int(row.get("total_tokens", 0)) for row in subset),
                "status_counts": status_counts,
            })
            lines.append(
                f"| {policy} | {len(subset)} | {global_rows[-1]['solve_rate']:.3f} | "
                f"{global_rows[-1]['calls']} | {global_rows[-1]['tokens']} | `{json.dumps(status_counts, sort_keys=True)}` |"
            )
        by_policy = {row["policy"]: row for row in global_rows}
        lines += [
            "",
            "### Development interpretation",
            "",
            f"- Symbolic branch + Qwen route solved {by_policy.get('symbolic_branch_qwen_route', {}).get('solve_rate', 0.0):.3f}; symbolic branch + symbolic route solved {by_policy.get('symbolic_branch_symbolic_route', {}).get('solve_rate', 0.0):.3f}.",
            f"- Qwen branch + symbolic route solved {by_policy.get('qwen_branch_symbolic_route', {}).get('solve_rate', 0.0):.3f}; full Qwen branch + route solved {by_policy.get('qwen_branch_qwen_route', {}).get('solve_rate', 0.0):.3f}.",
            "- The dominant Qwen-branch failures were call-cap exhaustion, search exhaustion, and fail-closed invalid branches. High local validity on isolated branch prompts did not imply good sequential search control.",
            "- The route policy initially looked more promising than the branch policy in this eight-instance development read, but the later symbolic structural confirmation and dedicated SAT route confirmation did not support escalation.",
        ]
    else:
        lines.append("End-to-end development is pending or was blocked by the decision gate.")
    lines += [
        "",
        "## Honesty Boundary",
        "",
        "This overnight run is a development gate on the frozen preflight manifest. It does not establish a multi-agent paper claim. Subsequent independent symbolic studies failed the required escalation gates, so no Qwen confirmatory run is authorized from this result.",
        "",
        "## Artifacts",
        "",
        "- [Decision evaluation](../multiagent_real_qwen_decision_gate/evaluation_v2.json)",
        "- [End-to-end development](../multiagent_real_qwen_end_to_end/dev_results.json)",
        "- [End-to-end checkpoint](../multiagent_real_qwen_end_to_end/checkpoint.json)",
        "- [Symbolic preflight](../multiagent_core_2x2_preflight/PREFLIGHT_SUMMARY.md)",
    ]
    (root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"path": str((root / 'SUMMARY.md').relative_to(REPO_ROOT)), "status": status}), flush=True)


if __name__ == "__main__":
    main()
