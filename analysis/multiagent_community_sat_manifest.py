"""Freeze the independent community-SAT structural manifest without arm outcomes."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.multiagent_community_sat import generate_structural_pool


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _render(payload: dict[str, Any]) -> str:
    audit = payload["audit"]
    lines = [
        "# Independent Community SAT Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        "- Instances: 200 (50/cell)",
        "- Evaluated-arm outcomes generated/read: **No**",
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
        f"- Cell counts: `{json.dumps(audit['cell_counts'], sort_keys=True)}`",
        f"- Development clause overlap: `{audit['development_clause_overlap']}`",
        f"- Low/high rho: `{audit['mean_rho_low']:.4f}` / `{audit['mean_rho_high']:.4f}`",
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
        "The independent instance file was not used for smoke testing. All selection used only unlimited structural reference metrics defined before bounded-arm execution.",
        "",
        "## Artifacts",
        "",
        "- [Instance manifest](instance_manifest.json)",
        "- [Generation JSON](generation.json)",
        "- [Development gate](../multiagent_community_sat_development/DEVELOPMENT.md)",
        "- [Replication contract](../../specs/multiagent_community_sat_replication_contract_v1.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate independent community-SAT manifest.")
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_community_sat_manifest"))
    parser.add_argument("--development", type=Path, default=Path("results/multiagent_community_sat_development/smoke_results.json"))
    parser.add_argument("--development-manifest", type=Path, default=Path("results/multiagent_community_sat_development/instance_manifest.json"))
    parser.add_argument("--contract", type=Path, default=Path("specs/multiagent_community_sat_replication_contract_v1.json"))
    parser.add_argument("--base-seed", type=int, default=310000)
    parser.add_argument("--max-candidates-per-coupling", type=int, default=40000)
    parser.add_argument("--instances-per-cell", type=int, default=50)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--reference-cap", type=int, default=100000)
    args = parser.parse_args()
    development_path = _resolve(args.development)
    development_manifest_path = _resolve(args.development_manifest)
    contract_path = _resolve(args.contract)
    development = json.loads(development_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if development.get("status") != "SAT_DEVELOPMENT_GO":
        raise SystemExit("independent SAT pool blocked: development gate did not pass")
    expected = contract["splits"]["independent"]
    checks_config = {
        "base_seed": int(args.base_seed) == int(expected["base_seed"]),
        "max_candidates": int(args.max_candidates_per_coupling) == int(expected["max_candidates_per_coupling"]),
        "instances_per_cell": int(args.instances_per_cell) == int(expected["instances_per_cell"]),
        "register": int(args.register) == int(contract["resources"]["R"]),
        "reference_cap": int(args.reference_cap) == int(contract["resources"]["reference_cap"]),
    }
    if not all(checks_config.values()):
        raise ValueError(f"independent config differs from contract: {checks_config}")
    old_rows = list(json.loads(development_manifest_path.read_text(encoding="utf-8"))["rows"])
    old_ids = {str(row["instance_id"]) for row in old_rows}
    old_clause_hashes = {str(row["clause_sha256"]) for row in old_rows}
    rows, generation = generate_structural_pool(
        split="independent",
        base_seed=int(args.base_seed),
        max_candidates_per_coupling=int(args.max_candidates_per_coupling),
        instances_per_cell=int(args.instances_per_cell),
        r_value=int(args.register),
        reference_cap=int(args.reference_cap),
    )
    counts = Counter(str(row["cell"]) for row in rows)
    expected_counts = Counter({"under_low": 50, "under_high": 50, "over_low": 50, "over_high": 50})
    clause_overlap = len({str(row["clause_sha256"]) for row in rows} & old_clause_hashes)
    id_overlap = len({str(row["instance_id"]) for row in rows} & old_ids)
    low_rhos = [float(row["rho_actual"]) for row in rows if row["coupling"] == "low"]
    high_rhos = [float(row["rho_actual"]) for row in rows if row["coupling"] == "high"]
    audit_checks = {
        "pool_complete": bool(generation["complete"]) and counts == expected_counts,
        "unique_ids": len({str(row["instance_id"]) for row in rows}) == len(rows),
        "unique_clause_hashes": len({str(row["clause_sha256"]) for row in rows}) == len(rows),
        "no_development_id_overlap": id_overlap == 0,
        "no_development_clause_overlap": clause_overlap == 0,
        "planted_removed": all("planted_assignment" not in row and bool(row["planted_assignment_removed"]) for row in rows),
        "fixed_clause_count": all(int(row["n_clauses"]) == 192 for row in rows),
        "exact_coupling": all(int(row["cross_clause_count"]) == (19 if row["coupling"] == "low" else 77) for row in rows),
        "reference_solved": all(bool(row["reference_solved"]) for row in rows),
        "strata_exact": all(
            (row["capacity"] == "under" and int(row["global_recovery_distance"]) <= 8)
            or (
                row["capacity"] == "over_local_fit"
                and int(row["global_recovery_distance"]) > 8
                and int(row["local_recovery_distance"]) <= 8
            )
            for row in rows
        ),
        "selection_no_arm_outcomes": all(str(row["selection_rule"]) == "reference_recovery_stratum_only_no_evaluated_arm_outcomes" for row in rows),
    }
    audit = {
        "pass": all(audit_checks.values()),
        "checks": audit_checks,
        "cell_counts": dict(sorted(counts.items())),
        "development_id_overlap": id_overlap,
        "development_clause_overlap": clause_overlap,
        "mean_rho_low": mean(low_rhos),
        "mean_rho_high": mean(high_rhos),
        "global_recovery_range": [min(int(row["global_recovery_distance"]) for row in rows), max(int(row["global_recovery_distance"]) for row in rows)],
        "local_recovery_range": [min(int(row["local_recovery_distance"]) for row in rows), max(int(row["local_recovery_distance"]) for row in rows)],
    }
    if not audit["pass"]:
        raise RuntimeError(f"independent SAT manifest audit failed: {audit}")
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "schema": "multiagent_community_sat_independent_manifest_v1",
        "status": "SAT_INDEPENDENT_MANIFEST_FROZEN",
        "headline_eligible": False,
        "selection": "unlimited_reference_structure_only",
        "rows": rows,
    }
    (output_dir / "instance_manifest.json").write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hashes = {
        "instance_manifest_sha256": _sha256(output_dir / "instance_manifest.json"),
        "contract_sha256": _sha256(contract_path),
        "development_gate_sha256": _sha256(development_path),
        "development_manifest_sha256": _sha256(development_manifest_path),
        "generator_sha256": _sha256(REPO_ROOT / "tasks/sat/community.py"),
        "solver_sha256": _sha256(REPO_ROOT / "experiments/multiagent_community_sat.py"),
        "manifest_source_sha256": _sha256(Path(__file__)),
    }
    payload = {
        "schema": "multiagent_community_sat_independent_generation_v1",
        "status": "SAT_INDEPENDENT_MANIFEST_FROZEN",
        "headline_eligible": False,
        "config_checks": checks_config,
        "generation": generation,
        "audit": audit,
        "hashes": hashes,
    }
    (output_dir / "generation.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "GENERATION.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "instances": len(rows),
        "manifest_sha256": hashes["instance_manifest_sha256"],
        "report": str((output_dir / "GENERATION.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
