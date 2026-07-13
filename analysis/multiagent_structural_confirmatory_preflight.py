"""Preflight the confirmatory factorization controls on development data only."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.multiagent_factorization_controls import (
    CONTROL_MODES,
    EQUIVALENCE_FIELDS,
    compare_shadow_to_frozen,
    run_factorized_control,
)
from experiments.multiagent_independent_local import _run_independent


EXPECTED_MECHANISM_SHA256 = "946782f3abff7026a98593fb3f3374ff020159f21303ccc442157ac6354244ba"
EXPECTED_DEVELOPMENT_MANIFEST_SHA256 = "151e8b2ed9976827bc0e6b1c7559c0cdeb29654527128ae20be311f23dd725ea"
REPLAY_FIELDS = EQUIVALENCE_FIELDS + (
    "penalized_work",
    "preserved_global_suffix_assignments",
    "preserved_dependency_unrelated_assignments",
    "rollback_events_with_global_preservation",
    "rollback_events_with_unrelated_preservation",
    "trace_sha256",
    "trace_event_count",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _protocol_checks(rows: list[dict[str, Any]], channel_cap: int) -> dict[str, bool]:
    return {
        "no_direct_cross_agent_mutation": all(int(row["cross_agent_direct_mutations"]) == 0 for row in rows),
        "owner_only_mutation": all(int(row["ownership_violations"]) == 0 for row in rows),
        "acyclic_priority": all(int(row["priority_direction_violations"]) == 0 for row in rows),
        "no_out_of_window_execution": all(int(row["out_of_window_rollback_executions"]) == 0 for row in rows),
        "window_occupancy_bounded": all(
            int(row["max_local_register"]) <= int(row["declared_per_agent_window"]) for row in rows
        ),
        "request_conservation": all(
            int(row["requests_sent"]) == int(row["requests_executed"]) + int(row["nacks"])
            and int(row["acknowledgements"]) == int(row["requests_sent"])
            and bool(row["request_lifecycle_valid"])
            for row in rows
        ),
        "channel_bounded": all(int(row["max_pending_requests"]) <= int(channel_cap) for row in rows),
        "no_global_trail": all(bool(row["no_global_trail"]) for row in rows),
        "independent_state": all(bool(row["independent_agent_state"]) for row in rows),
        "no_fallback": all(bool(row["no_oracle_or_model_fallback"]) for row in rows),
        "official_scoring": all(row["status"] != "OFFICIAL_SCORE_FAIL" for row in rows),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    mechanism_path = REPO_ROOT / "experiments/multiagent_independent_local.py"
    controls_path = REPO_ROOT / "experiments/multiagent_factorization_controls.py"
    prereg_path = REPO_ROOT / "specs/multiagent_structural_confirmatory_preregistration_v1.json"
    manifest_path = args.development_manifest if args.development_manifest.is_absolute() else REPO_ROOT / args.development_manifest
    hashes = {
        "mechanism_sha256": _sha256(mechanism_path),
        "controls_sha256": _sha256(controls_path),
        "preregistration_sha256": _sha256(prereg_path),
        "development_manifest_sha256": _sha256(manifest_path),
    }
    hash_checks = {
        "mechanism_frozen": hashes["mechanism_sha256"] == EXPECTED_MECHANISM_SHA256,
        "development_manifest_frozen": hashes["development_manifest_sha256"] == EXPECTED_DEVELOPMENT_MANIFEST_SHA256,
    }
    if not all(hash_checks.values()):
        raise ValueError(f"frozen hash mismatch: {hash_checks}")
    manifest = list(json.loads(manifest_path.read_text(encoding="utf-8"))["rows"])
    if len(manifest) != 64 or Counter(str(row["cell"]) for row in manifest) != Counter({
        "under_low": 16,
        "under_high": 16,
        "over_low": 16,
        "over_high": 16,
    }):
        raise ValueError("development manifest cardinality changed")

    mismatches = []
    shadow_rows = []
    for row in manifest:
        frozen = _run_independent(row, "independent_local_cbj", int(args.register), int(args.activation_cap), int(args.channel_cap))
        shadow = run_factorized_control(
            row,
            "queued_deepest",
            int(args.register),
            int(args.activation_cap),
            int(args.channel_cap),
            int(args.route_seed),
        )
        different = compare_shadow_to_frozen(frozen, shadow)
        if different:
            mismatches.append({
                "cell": row["cell"],
                "instance_id": row["instance_id"],
                "fields": different,
            })
        shadow_rows.append(shadow)

    selected = []
    for cell in ("under_low", "under_high", "over_low", "over_high"):
        selected.append(sorted((row for row in manifest if row["cell"] == cell), key=lambda row: row["instance_id"])[0])
    replay_mismatches = []
    smoke_rows = []
    for row in selected:
        for mode in ("central_deepest", "queued_random_valid", "queued_no_cross"):
            first = run_factorized_control(
                row,
                mode,
                int(args.register),
                int(args.activation_cap),
                int(args.channel_cap),
                int(args.route_seed),
            )
            second = run_factorized_control(
                row,
                mode,
                int(args.register),
                int(args.activation_cap),
                int(args.channel_cap),
                int(args.route_seed),
            )
            different = [field for field in REPLAY_FIELDS if first.get(field) != second.get(field)]
            if different:
                replay_mismatches.append({
                    "cell": row["cell"],
                    "instance_id": row["instance_id"],
                    "mode": mode,
                    "fields": different,
                })
            smoke_rows.append(first)

    protocol_rows = shadow_rows + smoke_rows
    protocol_checks = _protocol_checks(protocol_rows, int(args.channel_cap))
    gates = {
        "frozen_hashes": all(hash_checks.values()),
        "shadow_exact_all_64": not mismatches,
        "control_replay_deterministic": not replay_mismatches,
        "protocol_audit": all(protocol_checks.values()),
        "development_only": True,
    }
    passed = all(value for key, value in gates.items() if key != "development_only")
    return {
        "schema": "multiagent_structural_confirmatory_preflight_v1",
        "status": "CONFIRMATORY_PREFLIGHT_PASS" if passed else "CONFIRMATORY_PREFLIGHT_FAIL",
        "headline_eligible": False,
        "hashes": hashes,
        "hash_checks": hash_checks,
        "config": {
            "development_manifest": str(args.development_manifest),
            "register": int(args.register),
            "activation_cap": int(args.activation_cap),
            "channel_cap": int(args.channel_cap),
            "route_seed": int(args.route_seed),
        },
        "equivalence": {
            "rows": len(shadow_rows),
            "fields": list(EQUIVALENCE_FIELDS),
            "mismatches": mismatches,
        },
        "deterministic_replay": {
            "rows": len(smoke_rows),
            "fields": list(REPLAY_FIELDS),
            "mismatches": replay_mismatches,
        },
        "protocol": {
            "rows": len(protocol_rows),
            "checks": protocol_checks,
            "request_totals": {
                "sent": sum(int(row["requests_sent"]) for row in protocol_rows),
                "acknowledged": sum(int(row["acknowledgements"]) for row in protocol_rows),
                "nacks": sum(int(row["nacks"]) for row in protocol_rows),
                "out_of_window_executions": sum(
                    int(row["out_of_window_rollback_executions"]) for row in protocol_rows
                ),
            },
        },
        "smoke_summary": [
            {
                "cell": row["cell"],
                "arm": row["arm"],
                "status": row["status"],
                "solved": row["solved"],
                "aggregate_work": row["aggregate_work"],
                "parallel_rounds": row["parallel_rounds"],
                "preserved_dependency_unrelated_assignments": row["preserved_dependency_unrelated_assignments"],
            }
            for row in smoke_rows
        ],
        "gates": gates,
    }


def _render(payload: dict[str, Any]) -> str:
    gates = payload["gates"]
    lines = [
        "# Structural Confirmatory Control Preflight",
        "",
        f"- Status: **`{payload['status']}`**",
        "- Data: old 64-instance development manifest only",
        "- New confirmatory outcomes observed: **No**",
        "- GPU/LLM use: none",
        "",
        "## Gates",
        "",
        "| Gate | Result |",
        "|---|---:|",
    ]
    for key, value in gates.items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")
    lines.extend([
        "",
        "## Equivalence",
        "",
        f"The parameterized `queued_deepest` shadow matched the hash-locked successful arm on **{payload['equivalence']['rows']}/64** rows over all frozen core fields.",
        "",
        f"- Mismatches: `{len(payload['equivalence']['mismatches'])}`",
        f"- Deterministic control replays: `{payload['deterministic_replay']['rows']}`",
        f"- Replay mismatches: `{len(payload['deterministic_replay']['mismatches'])}`",
        "",
        "## Protocol",
        "",
    ])
    for key, value in payload["protocol"]["checks"].items():
        lines.append(f"- `{key}`: **{'PASS' if value else 'FAIL'}**")
    totals = payload["protocol"]["request_totals"]
    lines.extend([
        "",
        f"Requests sent/acknowledged: `{totals['sent']}` / `{totals['acknowledged']}`; out-of-window executions: `{totals['out_of_window_executions']}`.",
        "",
        "## Frozen hashes",
        "",
    ])
    for key, value in payload["hashes"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend([
        "",
        "## Artifacts",
        "",
        "- [Preflight JSON](preflight.json)",
        "- [Confirmatory preregistration](../../specs/multiagent_structural_confirmatory_preregistration_v1.md)",
        "- [Control implementation](../../experiments/multiagent_factorization_controls.py)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight structural confirmatory controls.")
    parser.add_argument(
        "--development-manifest",
        type=Path,
        default=Path("results/multiagent_core_2x2_preflight/instance_manifest.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/multiagent_structural_confirmatory_preflight"),
    )
    parser.add_argument("--register", type=int, default=8)
    parser.add_argument("--activation-cap", type=int, default=20000)
    parser.add_argument("--channel-cap", type=int, default=16)
    parser.add_argument("--route-seed", type=int, default=20260711)
    args = parser.parse_args()
    payload = run(args)
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "preflight.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "PREFLIGHT.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "report": str((output_dir / "PREFLIGHT.md").relative_to(REPO_ROOT)),
    }))
    if payload["status"] != "CONFIRMATORY_PREFLIGHT_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
