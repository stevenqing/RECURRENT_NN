"""Generate the canonical RECURRENT_NN experiment ledger."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

ARTIFACT_INDEX = {
    "canonical_repo_note": "CANONICAL_REPO.md",
    "environment_spec": "ENV_SPEC.md",
    "post_027_continuation_state": "results/continuation_state/post_027.json",
    "model_readiness": "results/model_readiness/readiness.json",
    "qwen3_4b_instruct_download": "results/model_download/qwen_download.json",
    "qwen3_4b_thinking_download": "results/model_download/thinking/qwen_download.json",
    "qwen3_5_4b_download": "results/model_download/qwen3_5_4b/qwen_download.json",
    "module1_capacity_perdepth": "results/module1_capacity_perdepth_shards/results.json",
    "module1_k_direction_corrected": "results/module1_capacity_benchmark_full_shards/k_direction_corrected.json",
    "module1_capacity_batching": "results/module1_capacity_batching_large/results.json",
    "gru_stack_smoke": "results/gru_stack_smoke/results.json",
    "gru_stack_grid_full_legacy": "results/gru_stack_grid_full/results.json",
    "gru_degeneracy_diagnostic": "results/gru_degeneracy_diagnostic/results.json",
    "gru_stack_grid_fair": "results/gru_stack_grid_fair/results.json",
    "gru_vs_structured_closeout": "results/gru_vs_structured_closeout/results.json",
    "m2_operator_probe": "results/m2_operator_probe/report.json",
    "m2_operator_fix_rescale": "results/m2_operator_probe/report_fix_rescale.json",
    "g1_fix_spec": "specs/g1_fix_spec.md",
    "stage_a_reconstructed_artifacts": "artifacts/stage_a/manifest.json",
    "stage_a_backtrack": "results/stage_a_backtrack/report.json",
    "post025_adapter_wiring": "results/stage_a_adapter_wiring/results.json",
    "post026_banded_gate_refusal": "results/stage_a_banded_gate_refusal/results.json",
    "post027_sudoku6_bridge": "results/stage_a_sudoku6_bridge/results.json",
    "w3_qwen35_probe_spec": "specs/w3_qwen35_probe_spec.md",
    "w3_qwen35_probe": "results/w3_qwen35_probe/results.json",
    "validation": "results/validation/validation.json",
}

LEGACY_ARCHIVE = {
    "preregistration": "results/preregistration/preregistration.json",
    "oracle_dataset": "results/oracle_dataset/summary.json",
    "operator_cache": "results/operator_cache/summary.json",
    "qwen_probe_cache": "results/operator_cache/qwen_probe_cache_summary.json",
    "qwen_128_cache": "results/operator_cache/qwen_128_cache_summary.json",
    "learned_wiring_qwen_128": "results/learned_wiring_qwen_128/results.json",
    "qwen_balanced_320_cache": "results/operator_cache/qwen_balanced_320_cache_summary.json",
    "learned_wiring_qwen_balanced_320": "results/learned_wiring_qwen_balanced_320/results.json",
    "two_by_two": "results/two_by_two/results.json",
    "d_stage_0": "results/d_stage_0/results.json",
    "d_stage_1": "results/d_stage_1/results.json",
    "d_stage_2": "results/d_stage_2/results.json",
    "d_stage_3": "results/d_stage_3/results.json",
    "verifier": "results/verifier/results.json",
    "ttt_scaffold": "results/ttt/results.json",
}


def _path(path_text: str) -> Path:
    return REPO_ROOT / path_text


def _read_json(path_text: str) -> Any | None:
    path = _path(path_text)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return lines


def _fmt(value: Any, digits: int = 4) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def _mean(row: dict[str, Any], key: str) -> Any:
    value = row.get(key)
    if isinstance(value, dict):
        return value.get("mean")
    return value


def _artifact_rows(index: dict[str, str]) -> list[list[str]]:
    return [[name, path, "yes" if _path(path).exists() else "missing"] for name, path in index.items()]


def _validation_rows(validation: dict[str, Any]) -> list[list[Any]]:
    checks = validation.get("checks", [])
    tiers = sorted({check.get("tier", "") for check in checks})
    rows = []
    for tier in tiers:
        tier_checks = [check for check in checks if check.get("tier") == tier]
        rows.append([tier, sum(check.get("status") == "PASS" for check in tier_checks), sum(check.get("status") == "FAIL" for check in tier_checks)])
    return rows


def _incremental_rows(data: dict[str, Any]) -> list[list[str]]:
    continuation = data.get("continuation") or {}
    items = {item.get("item"): item for item in continuation.get("items", [])}
    validation = data.get("validation") or {}
    closeout = data.get("gru_closeout") or {}
    stage_a = data.get("stage_a_report") or {}
    perdepth = data.get("perdepth") or {}
    m2 = data.get("m2_fix") or {}
    qwen35 = data.get("qwen35") or {}
    w3 = data.get("w3_probe") or {}
    return [
        ["001-018", "legacy scaffold and early Module 1 setup", "Archived", "Retained in reference archive; not front-page gate evidence."],
        ["019-020", "scaffold gates and old validation", "Demoted", "Constructed-true 2x2/D-stage/verifier gates moved to legacy archive."],
        ["021", "M2.0 frozen operator probe", "Done", "verdict=NEEDS_OPERATOR_FIX; low forced recall/precision blocks direct loop."],
        ["022", "M2.0 fix-rescale probe", "Done", f"verdict={m2.get('verdict')}; branch_decision={m2.get('branch_decision')}"],
        ["023", "Module 1 fair GRU closeout", "Done, not locked", f"classification={closeout.get('classification')}; max_ratio={_fmt(closeout.get('max_gru_to_structured_ratio'))}; lock={closeout.get('lock_structured_headline')}"] ,
        ["024", "Stage A reconstructed handoff", "Blocked", f"verdict={stage_a.get('verdict')}; statuses={stage_a.get('statuses')}; n_cells={stage_a.get('n_cells')}"] ,
        ["025", "adapter wiring pass", items.get("025", {}).get("status", "missing"), items.get("025", {}).get("summary", "not found in continuation state")],
        ["026", "banded Sudoku9 plus gate refusal", items.get("026", {}).get("status", "missing"), items.get("026", {}).get("summary", "not found in continuation state")],
        ["027", "Sudoku6 bridge G1", items.get("027", {}).get("status", "missing"), f"G1={items.get('027', {}).get('g1')}; {items.get('027', {}).get('summary', '')}"],
        ["P0", "ledger and validation housekeeping", "Updated", f"validation_checks={validation.get('summary', {}).get('n_checks')}; validation_passed={validation.get('passed')}"] ,
        ["W3.0", "Qwen3.5 checkpoint pin", "Done", f"model_id={qwen35.get('model_id')}; total_gib={_fmt(qwen35.get('total_gib'))}"],
        ["P1", "G1 fix spec and diagnostics", "Specified", "g1_fix_spec plus Stage A adapter/gate/Sudoku6 diagnostic artifacts are present; retraining not launched."],
        ["P2", "W3 Qwen3.5 probe", w3.get("integration_grade", "missing"), f"W3.0={w3.get('verdicts', {}).get('W3.0_checkpoint_pin')}; W3.1/W3.2 heavy probes not launched."],
        ["P3", "TRM defensive analysis", "Not launched", "No TRM checkpoint/test-set grading code is present in this repo yet."],
        ["Module1 law", "per-depth capacity", "Writable now", f"decision={perdepth.get('decision')}; open={perdepth.get('open')}; shards={perdepth.get('num_shards')}"] ,
    ]


def generate_experiment_log(output_dir: str = "results/experiment_log") -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    data = {
        "continuation": _read_json("results/continuation_state/post_027.json"),
        "readiness": _read_json("results/model_readiness/readiness.json"),
        "qwen_instruct": _read_json("results/model_download/qwen_download.json"),
        "qwen_thinking": _read_json("results/model_download/thinking/qwen_download.json"),
        "qwen35": _read_json("results/model_download/qwen3_5_4b/qwen_download.json"),
        "perdepth": _read_json("results/module1_capacity_perdepth_shards/results.json"),
        "gru_closeout": _read_json("results/gru_vs_structured_closeout/results.json"),
        "m2_fix": _read_json("results/m2_operator_probe/report_fix_rescale.json"),
        "stage_a_manifest": _read_json("artifacts/stage_a/manifest.json"),
        "stage_a_report": _read_json("results/stage_a_backtrack/report.json"),
        "post025_adapter_wiring": _read_json("results/stage_a_adapter_wiring/results.json"),
        "post026_banded_gate_refusal": _read_json("results/stage_a_banded_gate_refusal/results.json"),
        "post027_sudoku6_bridge": _read_json("results/stage_a_sudoku6_bridge/results.json"),
        "w3_probe": _read_json("results/w3_qwen35_probe/results.json"),
        "validation": _read_json("results/validation/validation.json"),
    }
    continuation = data["continuation"] or {}
    validation = data["validation"] or {}
    m2 = data["m2_fix"] or {}
    overall = m2.get("overall", {})
    qwen_branch = overall.get("branch", {}).get("qwen_guess", {})
    mrv_branch = overall.get("branch", {}).get("mrv", {})
    items = {item.get("item"): item for item in continuation.get("items", [])}
    g1 = items.get("027", {}).get("g1")

    tier_a = [
        "Module 1 capacity law: per-depth ceiling-free K-direction negative; bound_single best K_eff = D_over_ln_product with R2 about 0.99; factored best K_eff = D_over_ln_Kvar/max-factor with R2 about 0.98; capacity is linear in D for the measured construction.",
        "Ceiling-artifact resolution narrative for low-K frontier artifacts.",
        "Fair GRU 144-cell grid completed; all cells below structured; max GRU/structured ratio 0.9025; closeout honestly NOT_READY pending in-loop arbiter.",
        "TTT irreversibility remains real mechanism evidence when its non-scaffold artifact is present; the constructed scaffold gate is archived.",
        "M2.0 negatives: frozen Qwen operator still needs a fix; invalid qwen_guess rate and spike precision/recall asymmetry block direct loop use.",
    ]
    tier_b = [
        "Stage A in-loop proof blocks the core claim.",
        "Banded Sudoku9/6 readiness and fail-closed refusal are materialized in post-026 artifacts, with Sudoku6 data still recorded as continuation-state readiness rather than generated in-repo data.",
        "Fail-closed preflight is proven for missing/quarantined parent paths; unsafe paths are refused.",
        "Current blocker: G1 = 0.0 on the Sudoku6 bridge operator.",
    ]
    tier_c = [
        "W3 Qwen3.5 probe: checkpoint and metadata/capacity estimate are implemented; hidden-hook, gating-survival, native-delta, and W3.2 propagation probes are not launched.",
        "S2 accounting rides on the controlled relaunch.",
        "TRM defensive depth-ceiling analysis is not started.",
        "S3.1 integration is not started.",
    ]

    lines: list[str] = [
        "# RECURRENT_NN Controlled Backtracking Ledger",
        "",
        f"Generated at: {generated_at}",
        "",
        "Scope: canonical continuation ledger for `/home/aiscuser/RECURRENT_NN`. This replaces the older Stage D oracle-trace scaffold front page; legacy constructed scaffold gates are archived below.",
        "",
        "## Canonical Repo Decision",
        "",
        "- Canonical repo: `/home/aiscuser/RECURRENT_NN`",
        "- Legacy path `/home/aiscuser/stage_d_llm`: not present locally; old commands using that path are historical provenance text.",
        "- Module 1 artifacts are referenced from the current repo only; no local duplicate `stage_d_llm/results/` tree exists to de-duplicate.",
        "",
        "## Evidence Tiers",
        "",
        "### Tier A - Writable Now",
    ]
    lines.extend(f"- {item}" for item in tier_a)
    lines.extend(["", "### Tier B - In Flight, Blocks Core Claim"])
    lines.extend(f"- {item}" for item in tier_b)
    lines.extend(["", "### Tier C - Not Started"])
    lines.extend(f"- {item}" for item in tier_c)

    lines.extend(["", "## Current Gate And Blocker Status", ""])
    lines.extend(_table(["area", "status", "evidence"], [
        ["Module 1 capacity law", "GREEN", f"decision={data.get('perdepth', {}).get('decision')}; open={data.get('perdepth', {}).get('open')}; K_eff fits recorded"],
        ["Fair GRU closeout", "YELLOW", f"classification={data.get('gru_closeout', {}).get('classification')}; max_ratio={_fmt(data.get('gru_closeout', {}).get('max_gru_to_structured_ratio'))}; headline_locked={data.get('gru_closeout', {}).get('lock_structured_headline')}"] ,
        ["M2.0 frozen Qwen operator", "RED", f"verdict={m2.get('verdict')}; list_all_recall={_fmt(_mean(overall.get('list_all', {}), 'forced_recall'))}; single_precision={_fmt(_mean(overall.get('single_iterated', {}), 'per_call_precision'))}"],
        ["Branch policy", "YELLOW", f"qwen_nodes={_fmt(qwen_branch.get('mean_nodes_to_solve_or_cap'))}; mrv_nodes={_fmt(mrv_branch.get('mean_nodes_to_solve_or_cap'))}; qwen_invalid_rate={_fmt(qwen_branch.get('invalid_guess_rate'))}"],
        ["Stage A in-loop proof", "RED", f"n_cells={data.get('stage_a_report', {}).get('n_cells')}; statuses={data.get('stage_a_report', {}).get('statuses')}; G1={data.get('post027_sudoku6_bridge', {}).get('G1', g1)}"],
        ["W3 Qwen3.5", "YELLOW", f"integration_grade={data.get('w3_probe', {}).get('integration_grade')}; W3.0={data.get('w3_probe', {}).get('verdicts', {}).get('W3.0_checkpoint_pin')}"],
        ["Validation", "RED" if not validation.get("passed") else "GREEN", f"checks={validation.get('summary', {}).get('n_checks')}; pass={validation.get('summary', {}).get('n_pass')}; fail={validation.get('summary', {}).get('n_fail')}"] ,
    ]))

    lines.extend(["", "## Artifact Index", ""])
    lines.extend(_table(["artifact", "path", "present"], _artifact_rows(ARTIFACT_INDEX)))
    lines.extend(["", "## Incremental Run Items", ""])
    lines.extend(_table(["item", "name", "status", "key result"], _incremental_rows(data)))
    lines.extend(["", "## Validation Summary", ""])
    lines.extend(_table(["tier", "pass", "fail"], _validation_rows(validation)))
    lines.extend([
        "",
        "## P0/P1/P2/P3 Execution Notes",
        "",
        "- P0.1: `RECURRENT_NN` is declared canonical in `CANONICAL_REPO.md`; the old `stage_d_llm` path is not present locally.",
        "- P0.2: validation now emits many checks, including explicit red Stage A blockers, rather than one collapsed required-files failure.",
        "- P0.3: the front page now leads with evidence tiers and current blockers; constructed scaffold gates are demoted to the legacy archive.",
        "- P1: `specs/g1_fix_spec.md` plus adapter wiring, gate refusal, and Sudoku6 bridge diagnostic artifacts are present; the actual bridge retrain is not launched and G1 remains 0.0.",
        "- P2: `specs/w3_qwen35_probe_spec.md` and metadata-only W3 probe are present for `Qwen/Qwen3.5-4B`; hidden-hook and heavy propagation probes are still explicit follow-up jobs.",
        "- P3: TRM defensive analysis is not launched; no TRM checkpoint/test-set grading code is present in this repo yet.",
        "",
        "## Legacy Scaffold Archive",
        "",
        "The older 2x2, D-stage, verifier, and scaffold TTT entries are no longer front-page gate evidence. They were constructed scaffold outputs and are retained only as historical support/provenance. The real TTT irreversibility diagnostic remains Tier A mechanism evidence when its non-scaffold artifact is present.",
        "",
    ])
    lines.extend(_table(["legacy artifact", "path", "present"], _artifact_rows(LEGACY_ARCHIVE)))
    lines.extend(["", "## Standing Rules", ""])
    lines.extend(f"- {rule}" for rule in continuation.get("standing_rules", []))

    out = _path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / "experiment_log.md"
    json_path = out / "experiment_log.json"
    payload = {
        "generated_at": generated_at,
        "artifact_index": ARTIFACT_INDEX,
        "legacy_archive": LEGACY_ARCHIVE,
        "evidence_tiers": {"tier_a": tier_a, "tier_b": tier_b, "tier_c": tier_c},
        "incremental_items": _incremental_rows(data),
        "validation_summary": validation.get("summary", {}),
        "current_status": {
            "canonical_repo": "/home/aiscuser/RECURRENT_NN",
            "stage_a_blocker": "G1=0.0 on Sudoku6 bridge operator; autonomous Stage A cells unavailable",
            "w3_qwen35_checkpoint": data.get("qwen35", {}),
            "w3_qwen35_probe": data.get("w3_probe", {}),
            "p1_launched": False,
            "p2_launched": False,
            "p3_launched": False,
        },
    }
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"markdown": str(md_path.relative_to(REPO_ROOT)), "json": str(json_path.relative_to(REPO_ROOT)), **payload}


if __name__ == "__main__":
    print(json.dumps(generate_experiment_log(), indent=2, sort_keys=True))
