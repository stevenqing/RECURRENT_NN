"""Generate the untouched high-coupling SAT route-confirmation manifest."""

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


CONTRACT_SCHEMA = "multiagent_sat_route_confirmation_contract_v1"
MANIFEST_SCHEMA = "multiagent_sat_route_confirmation_manifest_v1"
STATUS = "SAT_ROUTE_CONFIRMATION_MANIFEST_FROZEN"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render(payload: dict[str, Any]) -> str:
    audit = payload["audit"]
    lines = [
        "# Community-SAT Route Confirmation Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        "- Instances: 200 untouched `over_high` community-SAT instances",
        "- Selection inputs: unlimited structural reference metrics only",
        "- Bounded-arm outcomes generated/read: **No**",
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
        f"- Development clause overlap: `{audit['development_clause_overlap']}`",
        f"- Prior-independent clause overlap: `{audit['prior_independent_clause_overlap']}`",
        f"- Mean actual coupling: `{audit['mean_rho']:.4f}`",
        f"- Global recovery range: `{audit['global_recovery_range']}`",
        f"- Local recovery range: `{audit['local_recovery_range']}`",
        "",
        "## Hashes",
        "",
    ])
    for key, value in payload["hashes"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend([
        "",
        "The manifest is now frozen. No route-arm outcome was available during acceptance.",
        "",
        "## Artifacts",
        "",
        "- [Instance manifest](instance_manifest.json)",
        "- [Generation JSON](generation.json)",
        "- [Preregistration](../../specs/multiagent_sat_route_confirmation_v1.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate independent SAT route-confirmation manifest.")
    parser.add_argument("--contract", type=Path, default=Path("specs/multiagent_sat_route_confirmation_v1.json"))
    parser.add_argument("--development-manifest", type=Path, default=Path("results/multiagent_community_sat_development/instance_manifest.json"))
    parser.add_argument("--prior-independent-manifest", type=Path, default=Path("results/multiagent_community_sat_manifest/instance_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_sat_route_manifest"))
    args = parser.parse_args()

    contract_path = _resolve(args.contract)
    development_path = _resolve(args.development_manifest)
    prior_path = _resolve(args.prior_independent_manifest)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "PREREGISTERED_BEFORE_MANIFEST_AND_OUTCOMES":
        raise ValueError("route-confirmation contract is not frozen")

    manifest_config = contract["manifest"]
    resources = contract["resources"]
    base_seed = int(manifest_config["base_seed"])
    max_candidates = int(manifest_config["max_candidates"])
    target_instances = int(manifest_config["instances"])
    r_value = int(resources["R"])
    reference_cap = int(resources["reference_cap"])
    split = str(manifest_config["split"])

    prior_payloads = [
        json.loads(development_path.read_text(encoding="utf-8")),
        json.loads(prior_path.read_text(encoding="utf-8")),
    ]
    old_rows = [row for payload in prior_payloads for row in payload["rows"]]
    old_ids = {str(row["instance_id"]) for row in old_rows}
    development_hashes = {str(row["clause_sha256"]) for row in prior_payloads[0]["rows"]}
    prior_hashes = {str(row["clause_sha256"]) for row in prior_payloads[1]["rows"]}

    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    for candidate_index in range(max_candidates):
        if len(rows) >= target_instances:
            break
        counters["generated"] += 1
        candidate = generate_community_sat_candidate(
            base_seed=base_seed,
            candidate_index=candidate_index,
            coupling="high",
            split=split,
        )
        planted = {int(variable): int(value) for variable, value in candidate["planted_assignment"].items()}
        if not verify_sat_assignment(candidate, planted):
            counters["planted_invalid"] += 1
            continue
        metrics = reference_metrics(candidate, r_value=r_value, node_cap=reference_cap)
        if metrics is None:
            counters["reference_failed"] += 1
            continue
        counters["reference_solved"] += 1
        capacity = classify_capacity(metrics, r_value)
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

    dev_overlap = len({str(row["clause_sha256"]) for row in rows} & development_hashes)
    prior_overlap = len({str(row["clause_sha256"]) for row in rows} & prior_hashes)
    id_overlap = len({str(row["instance_id"]) for row in rows} & old_ids)
    checks = {
        "complete_200": len(rows) == target_instances,
        "unique_ids": len({str(row["instance_id"]) for row in rows}) == len(rows),
        "unique_clause_hashes": len({str(row["clause_sha256"]) for row in rows}) == len(rows),
        "zero_prior_id_overlap": id_overlap == 0,
        "zero_development_clause_overlap": dev_overlap == 0,
        "zero_prior_independent_clause_overlap": prior_overlap == 0,
        "planted_removed": all("planted_assignment" not in row and bool(row["planted_assignment_removed"]) for row in rows),
        "fixed_clause_count": all(int(row["n_clauses"]) == 192 and int(row["clause_size"]) == 3 for row in rows),
        "exact_high_coupling": all(str(row["coupling"]) == "high" and int(row["cross_clause_count"]) == 77 for row in rows),
        "over_local_fit_exact": all(
            str(row["capacity"]) == "over_local_fit"
            and int(row["global_recovery_distance"]) > r_value
            and int(row["local_recovery_distance"]) <= r_value
            for row in rows
        ),
        "reference_solved": all(bool(row["reference_solved"]) for row in rows),
        "selection_no_arm_outcomes": all(
            str(row["selection_rule"]) == "reference_recovery_stratum_only_no_evaluated_arm_outcomes"
            for row in rows
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"route manifest audit failed: {checks}")

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
        "development_clause_overlap": dev_overlap,
        "prior_independent_clause_overlap": prior_overlap,
        "prior_id_overlap": id_overlap,
        "mean_rho": mean(float(row["rho_actual"]) for row in rows),
        "global_recovery_range": [
            min(int(row["global_recovery_distance"]) for row in rows),
            max(int(row["global_recovery_distance"]) for row in rows),
        ],
        "local_recovery_range": [
            min(int(row["local_recovery_distance"]) for row in rows),
            max(int(row["local_recovery_distance"]) for row in rows),
        ],
    }
    hashes = {
        "instance_manifest_sha256": _sha256(manifest_path),
        "contract_json_sha256": _sha256(contract_path),
        "contract_markdown_sha256": _sha256(REPO_ROOT / "specs/multiagent_sat_route_confirmation_v1.md"),
        "development_manifest_sha256": _sha256(development_path),
        "prior_independent_manifest_sha256": _sha256(prior_path),
        "generator_sha256": _sha256(REPO_ROOT / "tasks/sat/community.py"),
        "solver_sha256": _sha256(REPO_ROOT / "experiments/multiagent_community_sat.py"),
        "manifest_source_sha256": _sha256(Path(__file__)),
    }
    payload = {
        "schema": "multiagent_sat_route_confirmation_generation_v1",
        "status": STATUS,
        "headline_eligible": False,
        "generation": {
            "split": split,
            "base_seed": base_seed,
            "max_candidates": max_candidates,
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
