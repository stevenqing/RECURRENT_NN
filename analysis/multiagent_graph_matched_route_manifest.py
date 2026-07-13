"""Generate an untouched graph-color manifest for matched-window route confirmation."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT, _desired_capacity, _generate_pool


CONTRACT_SCHEMA = "multiagent_graph_matched_route_confirmation_contract_v1"
STATUS = "GRAPH_MATCHED_ROUTE_CONFIRMATION_MANIFEST_FROZEN"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _graph_hash(row: dict[str, Any]) -> str:
    payload = {
        "n_vertices": int(row["n_vertices"]),
        "k": int(row["k"]),
        "edges": sorted([list(map(int, edge)) for edge in row["edges"]]),
        "partitions": list(map(int, row["partitions"])),
        "order": list(map(int, row["order"])),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _render(payload: dict[str, Any]) -> str:
    audit = payload["audit"]
    lines = [
        "# Graph Matched-Window Route Confirmation Manifest",
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
        f"- Prior ID overlap: `{audit['prior_id_overlap']}`",
        f"- Prior canonical graph-hash overlap: `{audit['prior_graph_hash_overlap']}`",
        f"- Mean rho low/high: `{audit['mean_rho_low']:.4f}` / `{audit['mean_rho_high']:.4f}`",
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
        "The manifest is frozen before any matched-window confirmatory outcome.",
        "",
        "## Artifacts",
        "",
        "- [Instance manifest](instance_manifest.json)",
        "- [Generation JSON](generation.json)",
        "- [Confirmation contract](../../specs/multiagent_graph_matched_route_confirmation_v1.md)",
        "- [Development gate](../multiagent_graph_matched_route_development/DEVELOPMENT.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate graph matched-route confirmation manifest.")
    parser.add_argument("--contract", type=Path, default=Path("specs/multiagent_graph_matched_route_confirmation_v1.json"))
    parser.add_argument("--development-gate", type=Path, default=Path("results/multiagent_graph_matched_route_development/results.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_graph_matched_route_manifest"))
    parser.add_argument("--seed", type=int, default=206000)
    parser.add_argument("--instances-per-cell", type=int, default=50)
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--n-per-block", type=int, default=12)
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--d-local", type=int, default=5)
    parser.add_argument("--d-boundary", type=int, default=2)
    parser.add_argument("--under-depth", type=int, default=4)
    parser.add_argument("--over-depth", type=int, default=12)
    parser.add_argument("--low-b", type=int, default=2)
    parser.add_argument("--high-b", type=int, default=8)
    parser.add_argument("--edge-budget", type=int, default=96)
    parser.add_argument("--reference-node-cap", type=int, default=20000)
    parser.add_argument("--candidate-batch-size", type=int, default=96)
    parser.add_argument("--max-batches", type=int, default=40)
    args = parser.parse_args()

    contract_path = _resolve(args.contract)
    development_path = _resolve(args.development_gate)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    development = json.loads(development_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "PREREGISTERED_BEFORE_MANIFEST_AND_OUTCOMES":
        raise ValueError("graph matched-route confirmation contract is not frozen")
    if development.get("status") != "GRAPH_MATCHED_ROUTE_DEV_GO_CONFIRMATION":
        raise ValueError("graph matched-route confirmation blocked by development gate")
    expected = contract["manifest"]
    checks_config = {
        "seed": int(args.seed) == int(expected["base_seed"]),
        "instances_per_cell": int(args.instances_per_cell) == int(expected["instances_per_cell"]),
        "candidate_batch_size": int(args.candidate_batch_size) == int(expected["candidate_batch_size"]),
        "max_batches": int(args.max_batches) == int(expected["max_batches"]),
        "agents": int(args.agents) == int(expected["M"]),
        "register": int(args.register) == int(expected["R"]),
        "n_per_block": int(args.n_per_block) == int(expected["n_per_block"]),
        "k": int(args.k) == int(expected["k"]),
        "edge_budget": int(args.edge_budget) == int(expected["edge_budget"]),
        "low_b": int(args.low_b) == int(expected["low_b"]),
        "high_b": int(args.high_b) == int(expected["high_b"]),
        "under_depth": int(args.under_depth) == int(expected["under_depth"]),
        "over_depth": int(args.over_depth) == int(expected["over_depth"]),
        "reference_node_cap": int(args.reference_node_cap) == int(expected["reference_node_cap"]),
    }
    if not all(checks_config.values()):
        raise ValueError(f"graph manifest config mismatch: {checks_config}")

    prior_paths = [_resolve(path) for path in expected["required_zero_overlap"]]
    prior_rows = [row for path in prior_paths for row in json.loads(path.read_text(encoding="utf-8"))["rows"]]
    prior_ids = {str(row["instance_id"]) for row in prior_rows}
    prior_graph_hashes = {_graph_hash(row) for row in prior_rows}
    rows, generation = _generate_pool(args)
    counts = Counter(str(row["cell"]) for row in rows)
    expected_counts = Counter({"under_low": 50, "under_high": 50, "over_low": 50, "over_high": 50})
    ids = {str(row["instance_id"]) for row in rows}
    graph_hashes = {_graph_hash(row) for row in rows}
    id_overlap = len(ids & prior_ids)
    graph_overlap = len(graph_hashes & prior_graph_hashes)
    low_rhos = [float(row["rho_actual"]) for row in rows if row["coupling"] == "low"]
    high_rhos = [float(row["rho_actual"]) for row in rows if row["coupling"] == "high"]
    checks = {
        "pool_complete": counts == expected_counts and all(bool(item["complete"]) for item in generation),
        "unique_ids": len(ids) == len(rows),
        "unique_graph_hashes": len(graph_hashes) == len(rows),
        "zero_prior_id_overlap": id_overlap == 0,
        "zero_prior_graph_hash_overlap": graph_overlap == 0,
        "fixed_density_96": all(int(row["n_edges"]) == int(args.edge_budget) for row in rows),
        "reference_solved": all(bool(row["reference_solved"]) for row in rows),
        "capacity_strata_exact": all(_desired_capacity(row, str(row["capacity"]), int(args.register)) for row in rows),
        "target_depth_exact": all(int(row["reference_cross_agent_conflict_depth"]) == int(row["target_depth"]) for row in rows),
        "coupling_separated": mean(high_rhos) - mean(low_rhos) >= 0.15,
        "selection_rule_frozen": all(
            str(row["selection_rule"]) == "reference_recovery_distance_only_no_evaluated_arm_outcomes"
            for row in rows
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"graph matched-route manifest audit failed: {checks}")

    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "schema": "multiagent_graph_matched_route_confirmation_manifest_v1",
        "status": STATUS,
        "headline_eligible": False,
        "selection": "reference_structure_only_no_evaluated_arm_outcomes",
        "config": {
            key: value for key, value in vars(args).items()
            if key not in {"contract", "development_gate", "output_dir"}
        },
        "rows": rows,
    }
    manifest_path = output_dir / "instance_manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit = {
        "pass": True,
        "checks": checks,
        "cell_counts": dict(sorted(counts.items())),
        "prior_id_overlap": id_overlap,
        "prior_graph_hash_overlap": graph_overlap,
        "mean_rho_low": mean(low_rhos),
        "mean_rho_high": mean(high_rhos),
        "global_recovery_range": [min(int(row["global_recovery_distance"]) for row in rows), max(int(row["global_recovery_distance"]) for row in rows)],
        "local_recovery_range": [min(int(row["local_recovery_distance"]) for row in rows), max(int(row["local_recovery_distance"]) for row in rows)],
    }
    hashes = {
        "instance_manifest_sha256": _sha256(manifest_path),
        "contract_json_sha256": _sha256(contract_path),
        "contract_markdown_sha256": _sha256(REPO_ROOT / "specs/multiagent_graph_matched_route_confirmation_v1.md"),
        "development_gate_sha256": _sha256(development_path),
        "generator_sha256": _sha256(REPO_ROOT / "experiments/multiagent_capacity_coupling.py"),
        "frozen_controls_sha256": _sha256(REPO_ROOT / "experiments/multiagent_factorization_controls.py"),
        "matched_control_sha256": _sha256(REPO_ROOT / "experiments/multiagent_graph_route_controls.py"),
        "manifest_source_sha256": _sha256(Path(__file__)),
    }
    payload = {
        "schema": "multiagent_graph_matched_route_confirmation_generation_v1",
        "status": STATUS,
        "headline_eligible": False,
        "config_checks": checks_config,
        "generation": generation,
        "audit": audit,
        "hashes": hashes,
    }
    (output_dir / "generation.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "GENERATION.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": STATUS,
        "instances": len(rows),
        "manifest_sha256": hashes["instance_manifest_sha256"],
        "report": str((output_dir / "GENERATION.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
