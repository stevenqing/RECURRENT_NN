"""Preflight EBW Track A model launch without starting a model."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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


def git_rev_parse(rev: str) -> str:
    return subprocess.check_output(["git", "rev-parse", rev], cwd=REPO_ROOT, text=True).strip()


def gpu_snapshot() -> list[dict[str, Any]]:
    if subprocess.run(["bash", "-lc", "command -v nvidia-smi >/dev/null"], cwd=REPO_ROOT).returncode != 0:
        return []
    query = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,memory.free,memory.total", "--format=csv,noheader,nounits"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = []
    for line in query.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        output.append({"index": int(parts[0]), "name": parts[1], "free_memory_mib": int(parts[2]), "total_memory_mib": int(parts[3])})
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("specs/recurrent_parallel_ebw_track_a_model_launch_preflight_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_launch_preflight_v1"))
    args = parser.parse_args()
    contract_path = resolve(args.contract)
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite EBW Track A model launch preflight")

    contract = load_json(contract_path)
    execution_preflight_path = resolve(contract["execution_preflight"])
    execution_lock_path = resolve(contract["execution_lock"])
    runner_smoke_path = resolve(contract["runner_smoke"])
    model_record_path = resolve(contract["model_download_record"])
    run_output_dir = resolve(contract["output_dir"])
    execution_preflight = load_json(execution_preflight_path)
    execution_lock = load_json(execution_lock_path)
    runner_smoke = load_json(runner_smoke_path)
    model_record = load_json(model_record_path)
    tag_commit = git_rev_parse(f"{contract['expected_freeze_tag']}^{{commit}}")
    head_commit = git_rev_parse("HEAD")
    gpus = gpu_snapshot()
    eligible_gpus = [gpu for gpu in gpus if gpu["free_memory_mib"] >= contract["minimum_free_memory_mib"]]
    checks = {
        "contract_frozen": contract["status"] == "FROZEN_AFTER_EXECUTION_PREFLIGHT_BEFORE_MODEL_LAUNCH",
        "tag_commit": tag_commit == contract["expected_tag_commit"],
        "head_at_tag": head_commit == tag_commit,
        "execution_preflight_ready": execution_preflight["status"] == "RPD_EBW_TRACK_A_EXECUTION_PREFLIGHT_READY",
        "execution_lock_binding": file_hash(execution_lock_path) == execution_preflight["execution_lock_sha256"],
        "runner_smoke_pass": runner_smoke["status"] == "RPD_EBW_TRACK_A_RUNNER_SMOKE_PASS",
        "model_id": model_record.get("model_id") in contract["accepted_model_ids"],
        "model_snapshot_exists": Path(str(model_record.get("snapshot_path", ""))).exists(),
        "gpu_available": len(eligible_gpus) >= contract["allowed_gpu_count"],
        "run_output_absent": not run_output_dir.exists(),
        "sealed_closed": contract["sealed_variations_opened"] is False and execution_lock["sealed_variations_opened"] is False,
        "launch_authorized": contract["model_launch_authorized"] is True,
        "no_external_actions": contract["external_process_actions"] is False,
    }
    blocking_reasons = [name for name, ok in checks.items() if not ok]
    if not checks["contract_frozen"] or not checks["sealed_closed"] or not checks["no_external_actions"]:
        status = contract["verdicts"]["protocol_fail"]
    elif all(checks.values()):
        status = contract["verdicts"]["ready"]
    else:
        status = contract["verdicts"]["blocked"]

    output_dir.mkdir(parents=True)
    payload = {
        "schema": "ebw_track_a_model_launch_preflight_v1",
        "status": status,
        "checks": checks,
        "blocking_reasons": blocking_reasons,
        "gpu_snapshot": gpus,
        "eligible_gpus": eligible_gpus,
        "model_record": {"model_id": model_record.get("model_id"), "revision": model_record.get("revision"), "snapshot_path_exists": checks["model_snapshot_exists"]},
        "freeze_tag": contract["expected_freeze_tag"],
        "tag_commit": tag_commit,
        "model_launch_authorized": contract["model_launch_authorized"],
        "sealed_variations_opened": False,
        "external_process_actions": False,
        "contract_sha256": file_hash(contract_path),
    }
    write_json(output_dir / "preflight.json", payload)
    report = [
        "# EBW Track A Model Launch Preflight",
        "",
        f"## Status: **`{status}`**",
        "",
        f"- Freeze tag: `{contract['expected_freeze_tag']}`",
        f"- Tag commit: `{tag_commit}`",
        f"- Model record id: `{model_record.get('model_id')}`",
        f"- Eligible GPUs: {len(eligible_gpus)}",
        f"- Launch authorized: {contract['model_launch_authorized']}",
        "- Sealed variations 10-12 opened: No",
        "- Model process started: No",
        "",
        "## Blocking Reasons",
        "",
    ]
    report += [f"- `{reason}`" for reason in blocking_reasons] or ["- none"]
    report += ["", "## Checks", ""]
    report += [f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in checks.items()]
    (output_dir / "PREFLIGHT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": status, "blocking_reasons": blocking_reasons, "report": str((output_dir / "PREFLIGHT.md").relative_to(REPO_ROOT))}))
    if status == contract["verdicts"]["protocol_fail"]:
        raise RuntimeError(checks)


if __name__ == "__main__":
    main()