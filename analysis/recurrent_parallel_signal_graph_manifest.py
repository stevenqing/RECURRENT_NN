"""Generate the untouched recurrent signal-noise graph confirmation manifest."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.signal.long_diameter_graph import canonical_graph_hash, generate_long_diameter_graph, public_instance, reference_engagement, verify_coloring


CONTRACT_SCHEMA = "recurrent_parallel_signal_graph_confirmation_contract_v1"
STATUS = "RPD_SIGNAL_GRAPH_MANIFEST_FROZEN"


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render(payload: dict[str, Any]) -> str:
    audit = payload["audit"]
    lines = [
        "# Recurrent Signal-Noise Graph Confirmation Manifest",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        "- Instances: 200 (50/diameter)",
        "- Signal-system outcomes generated/read: **No**",
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
        f"- Diameter counts: `{json.dumps(audit['diameter_counts'], sort_keys=True)}`",
        f"- Development ID/hash overlap: `{audit['development_id_overlap']}/{audit['development_hash_overlap']}`",
        f"- Fixed edges local/cross/total: `{audit['local_edges']}/{audit['cross_edges']}/{audit['edge_count']}`",
        f"- Rollback ranges: `{json.dumps(audit['rollback_ranges'], sort_keys=True)}`",
        f"- Candidate-check ranges: `{json.dumps(audit['candidate_check_ranges'], sort_keys=True)}`",
        "",
        "## Hashes",
        "",
    ])
    for key, value in payload["hashes"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend([
        "",
        "The manifest is frozen before recurrent signal-policy execution.",
        "",
        "## Artifacts",
        "",
        "- [Instance manifest](instance_manifest.json)",
        "- [Generation JSON](generation.json)",
        "- [Confirmation contract](../../specs/recurrent_parallel_signal_graph_confirmation_v1.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate graph signal-noise confirmation manifest.")
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_signal_graph_confirmation_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_signal_graph_manifest"))
    args = parser.parse_args()
    contract_path = _resolve(args.contract)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("status") != "FROZEN_BEFORE_MANIFEST_AND_OUTCOMES":
        raise ValueError("graph signal confirmation contract is not frozen")
    prerequisite_path = _resolve(contract["prerequisite"])
    prerequisite = json.loads(prerequisite_path.read_text(encoding="utf-8"))
    if prerequisite.get("status") != "RPD_SIGNAL_PHASE_DIAMETER_CANDIDATE" or not prerequisite.get("independent_confirmation_authorized"):
        raise ValueError("graph signal confirmation blocked by development gate")
    development_path = _resolve(contract["development_manifest"])
    development = list(json.loads(development_path.read_text(encoding="utf-8"))["rows"])
    old_ids = {str(row["instance_id"]) for row in development}
    old_hashes = {str(row["graph_sha256"]) for row in development}
    config = contract["manifest"]

    rows: list[dict[str, Any]] = []
    reference_rows = []
    generation_counts = {}
    for diameter in map(int, config["diameters"]):
        accepted = 0
        generated = 0
        for candidate_index in range(int(config["max_candidates_per_diameter"])):
            if accepted >= int(config["instances_per_diameter"]):
                break
            generated += 1
            full = generate_long_diameter_graph(base_seed=int(config["base_seed"]), candidate_index=candidate_index, diameter=diameter, split=str(config["split"]))
            planted = {int(key): int(value) for key, value in full["planted_assignment"].items()}
            if not verify_coloring(full, planted):
                continue
            public = public_instance(full)
            reference = reference_engagement(public)
            if not reference.solved or int(reference.true_rollbacks) < int(config["minimum_true_rollbacks"]):
                continue
            public["graph_sha256"] = canonical_graph_hash(public)
            public["reference_true_rollbacks"] = int(reference.true_rollbacks)
            public["reference_candidate_checks"] = int(reference.candidate_checks)
            public["reference_completion_queries"] = int(reference.completion_queries)
            rows.append(public)
            reference_rows.append({
                "instance_id": public["instance_id"],
                "partition_diameter": diameter,
                "true_rollbacks": int(reference.true_rollbacks),
                "candidate_checks": int(reference.candidate_checks),
            })
            accepted += 1
        generation_counts[str(diameter)] = generated

    counts = Counter(int(row["partition_diameter"]) for row in rows)
    ids = {str(row["instance_id"]) for row in rows}
    hashes = {str(row["graph_sha256"]) for row in rows}
    rollback_ranges = {str(diameter): [min(row["true_rollbacks"] for row in reference_rows if row["partition_diameter"] == diameter), max(row["true_rollbacks"] for row in reference_rows if row["partition_diameter"] == diameter)] for diameter in map(int, config["diameters"])}
    check_ranges = {str(diameter): [min(row["candidate_checks"] for row in reference_rows if row["partition_diameter"] == diameter), max(row["candidate_checks"] for row in reference_rows if row["partition_diameter"] == diameter)] for diameter in map(int, config["diameters"])}
    difficulty_overlap = max(value[0] for value in rollback_ranges.values()) <= min(value[1] for value in rollback_ranges.values()) and max(value[0] for value in check_ranges.values()) <= min(value[1] for value in check_ranges.values())
    checks = {
        "complete_200": len(rows) == 200 and all(counts[diameter] == 50 for diameter in map(int, config["diameters"])),
        "unique_ids": len(ids) == len(rows),
        "unique_hashes": len(hashes) == len(rows),
        "zero_development_id_overlap": not bool(ids & old_ids),
        "zero_development_hash_overlap": not bool(hashes & old_hashes),
        "exact_diameter": all(int(row["partition_diameter"]) in set(map(int, config["diameters"])) for row in rows),
        "fixed_density": len({(int(row["n_edges"]), int(row["n_local_edges"]), int(row["n_cross_edges"])) for row in rows}) == 1,
        "rollback_engaged": all(int(row["reference_true_rollbacks"]) >= int(config["minimum_true_rollbacks"]) for row in rows),
        "difficulty_overlap": difficulty_overlap,
        "planted_removed": all("planted_assignment" not in row and bool(row["planted_assignment_removed"]) for row in rows),
        "selection_no_arm_outcomes": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"graph signal manifest audit failed: {checks}")

    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_payload = {"schema": "recurrent_parallel_signal_graph_manifest_v1", "status": STATUS, "headline_eligible": False, "rows": rows}
    manifest_path = output_dir / "instance_manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit = {
        "pass": True,
        "checks": checks,
        "diameter_counts": {str(key): value for key, value in sorted(counts.items())},
        "development_id_overlap": len(ids & old_ids),
        "development_hash_overlap": len(hashes & old_hashes),
        "edge_count": int(rows[0]["n_edges"]),
        "local_edges": int(rows[0]["n_local_edges"]),
        "cross_edges": int(rows[0]["n_cross_edges"]),
        "rollback_ranges": rollback_ranges,
        "candidate_check_ranges": check_ranges,
        "generation_candidates": generation_counts,
    }
    file_hashes = {
        "instance_manifest_sha256": _sha256(manifest_path),
        "contract_json_sha256": _sha256(contract_path),
        "contract_markdown_sha256": _sha256(REPO_ROOT / "specs/recurrent_parallel_signal_graph_confirmation_v1.md"),
        "prerequisite_sha256": _sha256(prerequisite_path),
        "development_manifest_sha256": _sha256(development_path),
        "graph_generator_sha256": _sha256(REPO_ROOT / "experiments/signal/long_diameter_graph.py"),
        "detector_sha256": _sha256(REPO_ROOT / "experiments/signal/detector.py"),
        "engine_sha256": _sha256(REPO_ROOT / "experiments/recurrent_parallel_core.py"),
        "manifest_source_sha256": _sha256(Path(__file__)),
    }
    payload = {"schema": "recurrent_parallel_signal_graph_generation_v1", "status": STATUS, "headline_eligible": False, "audit": audit, "reference_rows": reference_rows, "hashes": file_hashes}
    (output_dir / "generation.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "GENERATION.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({"status": STATUS, "instances": len(rows), "manifest_sha256": file_hashes["instance_manifest_sha256"], "report": str((output_dir / "GENERATION.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()
