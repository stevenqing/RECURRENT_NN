"""Generate the untouched manifest for matched-window SAT route confirmation."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.multiagent_community_sat import classify_capacity, reference_metrics
from tasks.sat.community import generate_community_sat_candidate, verify_sat_assignment


CONTRACT_SCHEMA = "multiagent_sat_matched_route_confirmation_contract_v1"
MANIFEST_SCHEMA = "multiagent_sat_matched_route_confirmation_manifest_v1"
STATUS = "SAT_MATCHED_ROUTE_CONFIRMATION_MANIFEST_FROZEN"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render(payload: dict[str, Any]) -> str:
    audit = payload["audit"]
    lines = [
        "# Matched-Window SAT Confirmation Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        "- Instances: 200 untouched high-coupling, over-local-fit community-SAT instances",
        "- Bounded-arm outcomes generated/read: **No**",
        "- Selection: structural reference recovery metrics only",
        "- GPU/LLM use: none",
        "",
        "## Audit",
        "",
        "| Check | Result |",
        "|---|---:|",
    ]
    for key, value in audit["checks"].items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")
    lines.extend([
        "",
        f"- Candidates generated: `{payload['generation']['candidates_generated']}`",
        f"- Accepted: `{payload['generation']['accepted']}`",
        f"- Mean actual coupling: `{audit['mean_rho']:.4f}`",
        f"- Global recovery range: `{audit['global_recovery_range']}`",
        f"- Local recovery range: `{audit['local_recovery_range']}`",
        "",
        "## Prior-pool overlap",
        "",
    ])
    for key, value in audit["overlap"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Hashes", ""])
    for key, value in payload["hashes"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend([
        "",
        "The manifest is frozen before any matched-window confirmatory arm outcome.",
        "",
        "## Artifacts",
        "",
        "- [Instance manifest](instance_manifest.json)",
        "- [Generation JSON](generation.json)",
        "- [Confirmation contract](../../specs/multiagent_sat_matched_route_confirmation_v1.md)",
        "- [Development gate](../multiagent_sat_matched_route_development/DEVELOPMENT.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate matched-window SAT confirmation manifest.")
    parser.add_argument("--contract", type=Path, default=Path("specs/multiagent_sat_matched_route_confirmation_v1.json"))
    parser.add_argument("--development-gate", type=Path, default=Path("results/multiagent_sat_matched_route_development/results.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_sat_matched_route_manifest"))
    args = parser.parse_args()

    contract_path = _resolve(args.contract)
    development_path = _resolve(args.development_gate)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    development = json.loads(development_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "PREREGISTERED_BEFORE_MANIFEST_AND_OUTCOMES":
        raise ValueError("matched-route confirmation contract is not frozen")
    if development.get("status") != "SAT_MATCHED_ROUTE_DEV_GO_CONFIRMATION":
        raise ValueError("matched-route confirmation blocked by development gate")

    config = contract["manifest"]
    resources = contract["resources"]
    prior_paths = [_resolve(path) for path in config["required_zero_overlap"]]
    prior_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in prior_paths]
    prior_ids = {str(row["instance_id"]) for payload in prior_payloads for row in payload["rows"]}
    prior_hash_sets = {
        path.parent.name: {str(row["clause_sha256"]) for row in payload["rows"]}
        for path, payload in zip(prior_paths, prior_payloads)
    }

    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    for candidate_index in range(int(config["max_candidates"])):
        if len(rows) >= int(config["instances"]):
            break
        counters["generated"] += 1
        candidate = generate_community_sat_candidate(
            base_seed=int(config["base_seed"]),
            candidate_index=candidate_index,
            coupling="high",
            split=str(config["split"]),
        )
        planted = {int(variable): int(value) for variable, value in candidate["planted_assignment"].items()}
        if not verify_sat_assignment(candidate, planted):
            counters["planted_invalid"] += 1
            continue
        metrics = reference_metrics(
            candidate,
            r_value=int(resources["R"]),
            node_cap=int(resources["reference_cap"]),
        )
        if metrics is None:
            counters["reference_failed"] += 1
            continue
        counters["reference_solved"] += 1
        capacity = classify_capacity(metrics, int(resources["R"]))
        if capacity != "over_local_fit":
            counters[f"rejected_{capacity or 'outside_strata'}"] += 1
            continue
        row = {key: value for key, value in candidate.items() if key != "planted_assignment"}
        row.update(metrics)
        row.update({
            "capacity": "over_local_fit",
            "cell": "over_high",
            "selection_rule": "reference_recovery_stratum_only_no_evaluated_arm_outcomes",
            "planted_assignment_removed": True,
        })
        rows.append(row)
        counters["accepted"] += 1

    new_ids = {str(row["instance_id"]) for row in rows}
    new_hashes = {str(row["clause_sha256"]) for row in rows}
    overlap = {
        "all_prior_id_overlap": len(new_ids & prior_ids),
        **{
            f"{name}_clause_overlap": len(new_hashes & hashes)
            for name, hashes in sorted(prior_hash_sets.items())
        },
    }
    checks = {
        "complete_200": len(rows) == int(config["instances"]),
        "unique_ids": len(new_ids) == len(rows),
        "unique_clause_hashes": len(new_hashes) == len(rows),
        "zero_prior_overlap": all(value == 0 for value in overlap.values()),
        "planted_removed": all("planted_assignment" not in row and bool(row["planted_assignment_removed"]) for row in rows),
        "fixed_clause_count": all(int(row["n_clauses"]) == 192 and int(row["clause_size"]) == 3 for row in rows),
        "exact_high_coupling": all(str(row["coupling"]) == "high" and int(row["cross_clause_count"]) == 77 for row in rows),
        "over_local_fit_exact": all(
            int(row["global_recovery_distance"]) > int(resources["R"])
            and int(row["local_recovery_distance"]) <= int(resources["R"])
            for row in rows
        ),
        "reference_solved": all(bool(row["reference_solved"]) for row in rows),
        "selection_no_arm_outcomes": all(
            str(row["selection_rule"]) == "reference_recovery_stratum_only_no_evaluated_arm_outcomes"
            for row in rows
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"matched-route manifest audit failed: {checks}; overlap={overlap}")

    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "schema": MANIFEST_SCHEMA,
        "status": STATUS,
        "headline_eligible": False,
        "selection": "unlimited_reference_structure_only",
        "rows": rows,
    }
    manifest_path = output_dir / "instance_manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit = {
        "pass": True,
        "checks": checks,
        "overlap": overlap,
        "mean_rho": mean(float(row["rho_actual"]) for row in rows),
        "global_recovery_range": [min(int(row["global_recovery_distance"]) for row in rows), max(int(row["global_recovery_distance"]) for row in rows)],
        "local_recovery_range": [min(int(row["local_recovery_distance"]) for row in rows), max(int(row["local_recovery_distance"]) for row in rows)],
    }
    hashes = {
        "instance_manifest_sha256": _sha256(manifest_path),
        "contract_json_sha256": _sha256(contract_path),
        "contract_markdown_sha256": _sha256(REPO_ROOT / "specs/multiagent_sat_matched_route_confirmation_v1.md"),
        "development_gate_sha256": _sha256(development_path),
        "generator_sha256": _sha256(REPO_ROOT / "tasks/sat/community.py"),
        "frozen_solver_sha256": _sha256(REPO_ROOT / "experiments/multiagent_community_sat.py"),
        "matched_control_sha256": _sha256(REPO_ROOT / "experiments/multiagent_community_sat_route_controls.py"),
        "manifest_source_sha256": _sha256(Path(__file__)),
    }
    payload = {
        "schema": "multiagent_sat_matched_route_confirmation_generation_v1",
        "status": STATUS,
        "headline_eligible": False,
        "generation": {
            "split": str(config["split"]),
            "base_seed": int(config["base_seed"]),
            "max_candidates": int(config["max_candidates"]),
            "candidates_generated": counters["generated"],
            "accepted": len(rows),
            "counters": dict(counters),
            "evaluated_arm_outcomes_used": False,
        },
        "audit": audit,
        "hashes": hashes,
    }
    (output_dir / "generation.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "GENERATION.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": STATUS,
        "instances": len(rows),
        "candidates_generated": counters["generated"],
        "manifest_sha256": hashes["instance_manifest_sha256"],
        "report": str((output_dir / "GENERATION.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
