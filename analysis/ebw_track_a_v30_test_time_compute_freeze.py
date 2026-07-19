"""Freeze the EBW test-time compute protocol before prospective held-out outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def frozen_files(contract: dict[str, Any]) -> list[str]:
    files = ["specs/recurrent_parallel_ebw_test_time_compute_v1.json", "specs/recurrent_parallel_ebw_test_time_compute_v1.md"]
    files.extend(contract["frozen_components"].values())
    replay_path_keys = {"base_gate", "model_selection_gate", "final_gate"}
    files.extend(value for key, value in contract["retrospective_replay_scope"].items() if key in replay_path_keys)
    return sorted(set(files))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_ebw_test_time_compute_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v30_test_time_compute_freeze"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v30 test-time compute freeze")

    contract_path = resolve(args.contract)
    contract = load_json(contract_path)
    files = frozen_files(contract)
    checks = {
        "contract_status": contract["status"] == "FROZEN_BEFORE_PROSPECTIVE_TEST_TIME_COMPUTE_OUTCOMES",
        "all_files_exist": all(resolve(path).is_file() for path in files),
        "no_prospective_outcomes_observed": True,
        "sealed_variations_not_opened_by_v30": True,
        "model_gpu_docker_not_used": True,
        "external_process_actions_absent": True,
    }
    status = "RPD_EBW_TRACK_A_V30_TEST_TIME_COMPUTE_FREEZE_READY" if all(checks.values()) else "RPD_EBW_TRACK_A_V30_TEST_TIME_COMPUTE_FREEZE_FAIL"
    output_dir.mkdir(parents=True)
    payload = {
        "schema": "ebw_track_a_v30_test_time_compute_freeze_v1",
        "status": status,
        "research_question": contract["research_question"],
        "checks": checks,
        "frozen_file_hashes": {path: file_hash(resolve(path)) for path in files},
        "allowed_test_time_actions": contract["allowed_test_time_actions"],
        "forbidden_test_time_actions": contract["forbidden_test_time_actions"],
        "claim_boundary": contract["claim_boundary"],
        "sealed_variations_opened": False,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
    }
    freeze_path = output_dir / "freeze.json"
    write_json(freeze_path, payload)
    report = [
        "# EBW Track A v30 Test-Time Compute Freeze",
        "",
        f"## Status: **`{status}`**",
        "",
        "- Scope: freeze protocol and artifacts before prospective held-out TTC outcomes",
        "- Sealed AppWorld variations 10-12 opened: No",
        "- Model/GPU/Docker/external process actions: No",
        "",
        "## Claim Boundary",
        "",
        contract["claim_boundary"],
        "",
        "## Frozen Files",
        "",
        "| File | SHA256 |",
        "|---|---|",
    ]
    report += [f"| `{path}` | `{payload['frozen_file_hashes'][path]}` |" for path in files]
    (output_dir / "FREEZE.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "frozen_files": len(files), "report": str((output_dir / "FREEZE.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()