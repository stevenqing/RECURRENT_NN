"""Generate the untouched structural confirmatory manifest without arm outcomes."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT, _desired_capacity, _generate_pool


EXPECTED_PREFLIGHT_STATUS = "CONFIRMATORY_PREFLIGHT_PASS"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate(
    rows: list[dict[str, Any]],
    generation: list[dict[str, Any]],
    old_ids: set[str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    counts = Counter(str(row["cell"]) for row in rows)
    expected_counts = Counter({
        "under_low": int(args.instances_per_cell),
        "under_high": int(args.instances_per_cell),
        "over_low": int(args.instances_per_cell),
        "over_high": int(args.instances_per_cell),
    })
    low_rhos = [float(row["rho_actual"]) for row in rows if row["coupling"] == "low"]
    high_rhos = [float(row["rho_actual"]) for row in rows if row["coupling"] == "high"]
    ids = [str(row["instance_id"]) for row in rows]
    overlap = sorted(set(ids) & old_ids)
    checks = {
        "pool_complete": counts == expected_counts and all(bool(item["complete"]) for item in generation),
        "unique_instance_ids": len(ids) == len(set(ids)),
        "no_development_overlap": not overlap,
        "fixed_density_96": all(int(row["n_edges"]) == int(args.edge_budget) for row in rows),
        "reference_solved": all(bool(row["reference_solved"]) for row in rows),
        "capacity_strata_exact": all(
            _desired_capacity(row, str(row["capacity"]), int(args.register)) for row in rows
        ),
        "target_depth_exact": all(
            int(row["reference_cross_agent_conflict_depth"]) == int(row["target_depth"])
            for row in rows
        ),
        "coupling_separated": mean(high_rhos) - mean(low_rhos) >= 0.15,
        "headline_ineligible": all(not bool(row.get("headline_eligible", True)) for row in rows),
        "selection_rule_frozen": all(
            str(row["selection_rule"]) == "reference_recovery_distance_only_no_evaluated_arm_outcomes"
            for row in rows
        ),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "cell_counts": dict(sorted(counts.items())),
        "development_overlap": overlap,
        "mean_rho_low": mean(low_rhos),
        "mean_rho_high": mean(high_rhos),
        "rho_gap": mean(high_rhos) - mean(low_rhos),
        "global_recovery_distance_range": [
            min(int(row["global_recovery_distance"]) for row in rows),
            max(int(row["global_recovery_distance"]) for row in rows),
        ],
        "local_recovery_distance_range": [
            min(int(row["local_recovery_distance"]) for row in rows),
            max(int(row["local_recovery_distance"]) for row in rows),
        ],
    }


def _render(payload: dict[str, Any]) -> str:
    audit = payload["audit"]
    lines = [
        "# Independent Structural Confirmatory Manifest",
        "",
        f"- Status: **`{payload['status']}`**",
        "- Evaluated-arm outcomes generated/read: **No**",
        "- Instances: **200** (50 per cell)",
        "- GPU/LLM use: none",
        "",
        "## Structural audit",
        "",
        "| Check | Result |",
        "|---|---:|",
    ]
    for key, value in audit["checks"].items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")
    lines.extend([
        "",
        f"- Cell counts: `{json.dumps(audit['cell_counts'], sort_keys=True)}`",
        f"- Development-manifest overlap: `{len(audit['development_overlap'])}`",
        f"- Mean rho low/high: `{audit['mean_rho_low']:.4f}` / `{audit['mean_rho_high']:.4f}`",
        f"- Rho gap: `{audit['rho_gap']:.4f}`",
        f"- Global recovery-distance range: `{audit['global_recovery_distance_range']}`",
        f"- Local recovery-distance range: `{audit['local_recovery_distance_range']}`",
        "",
        "## Frozen hashes",
        "",
    ])
    for key, value in payload["hashes"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend([
        "",
        "## Honesty boundary",
        "",
        "The manifest was selected only by frozen reference structure and fixed-density normalization. This report contains no proposed/control-arm solve or work measurement. The instance file must remain unread by implementation smoke tests before the one-shot confirmatory execution.",
        "",
        "## Artifacts",
        "",
        "- [Instance manifest](instance_manifest.json)",
        "- [Generation metadata](generation.json)",
        "- [Confirmatory preregistration](../../specs/multiagent_structural_confirmatory_preregistration_v1.md)",
        "- [Control preflight](../multiagent_structural_confirmatory_preflight/PREFLIGHT.md)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate untouched structural confirmatory instances.")
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_structural_confirmatory_manifest"))
    parser.add_argument("--development-manifest", type=Path, default=Path("results/multiagent_core_2x2_preflight/instance_manifest.json"))
    parser.add_argument("--preflight", type=Path, default=Path("results/multiagent_structural_confirmatory_preflight/preflight.json"))
    parser.add_argument("--preregistration", type=Path, default=Path("specs/multiagent_structural_confirmatory_preregistration_v1.json"))
    parser.add_argument("--seed", type=int, default=106000)
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
    parser.add_argument("--max-batches", type=int, default=30)
    args = parser.parse_args()

    preflight_path = args.preflight if args.preflight.is_absolute() else REPO_ROOT / args.preflight
    prereg_path = args.preregistration if args.preregistration.is_absolute() else REPO_ROOT / args.preregistration
    development_path = args.development_manifest if args.development_manifest.is_absolute() else REPO_ROOT / args.development_manifest
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    if preflight.get("status") != EXPECTED_PREFLIGHT_STATUS:
        raise SystemExit("confirmatory manifest blocked: control preflight did not pass")
    expected = prereg["manifest_generation"]
    frozen_config_checks = {
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
    if not all(frozen_config_checks.values()):
        raise ValueError(f"manifest config differs from preregistration: {frozen_config_checks}")

    old_rows = list(json.loads(development_path.read_text(encoding="utf-8"))["rows"])
    old_ids = {str(row["instance_id"]) for row in old_rows}
    rows, generation = _generate_pool(args)
    audit = _validate(rows, generation, old_ids, args)
    if not audit["pass"]:
        raise RuntimeError(f"confirmatory manifest audit failed: {audit}")

    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    manifest_payload = {
        "schema": "multiagent_structural_confirmatory_manifest_v1",
        "status": "CONFIRMATORY_MANIFEST_FROZEN",
        "headline_eligible": False,
        "selection": "reference_structure_only_no_evaluated_arm_outcomes",
        "config": {
            key: value
            for key, value in vars(args).items()
            if key not in {"output_dir", "development_manifest", "preflight", "preregistration"}
        },
        "rows": rows,
    }
    _write(output_dir / "instance_manifest.json", manifest_payload)
    manifest_sha = _sha256(output_dir / "instance_manifest.json")
    hashes = {
        "instance_manifest_sha256": manifest_sha,
        "preregistration_sha256": _sha256(prereg_path),
        "control_preflight_sha256": _sha256(preflight_path),
        "development_manifest_sha256": _sha256(development_path),
        "mechanism_sha256": _sha256(REPO_ROOT / "experiments/multiagent_independent_local.py"),
        "controls_sha256": _sha256(REPO_ROOT / "experiments/multiagent_factorization_controls.py"),
        "manifest_generator_sha256": _sha256(Path(__file__)),
    }
    generation_payload = {
        "schema": "multiagent_structural_confirmatory_generation_v1",
        "status": "CONFIRMATORY_MANIFEST_FROZEN",
        "headline_eligible": False,
        "frozen_config_checks": frozen_config_checks,
        "generation": generation,
        "audit": audit,
        "hashes": hashes,
    }
    _write(output_dir / "generation.json", generation_payload)
    (output_dir / "GENERATION.md").write_text(_render(generation_payload), encoding="utf-8")
    print(json.dumps({
        "status": generation_payload["status"],
        "instances": len(rows),
        "manifest_sha256": manifest_sha,
        "report": str((output_dir / "GENERATION.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
