"""Fail-closed helpers for the six-line overnight run."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TASKS = ["horn_sat", "general_sat", "graph_coloring", "sudoku_4x4", "logic_grid"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True), flush=True)
    return payload


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _deadline_utc(hour: int) -> datetime:
    now = datetime.now(timezone.utc)
    deadline = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if deadline <= now:
        deadline += timedelta(days=1)
    return deadline


def block(args: argparse.Namespace) -> None:
    _write(Path(args.out), {
        "module": "overnight_six_lines",
        "generated_at": _now(),
        "line": args.line,
        "status": args.status,
        "reason": args.reason,
        "evidence": args.evidence,
        "fail_closed": True,
    })


def _acceptance_pass(path: Path) -> bool:
    payload = _load(path)
    if not payload:
        return False
    return (
        payload.get("operator_type") == "learned_recurrent"
        and float(payload.get("G1") or 0.0) >= 0.95
        and float(payload.get("G2") if payload.get("G2") is not None else 1.0) <= 0.05
        and payload.get("status") in {"G1_PASS", "G1_PASS_EARLY_STOP"}
    )


def line2_watch(args: argparse.Namespace) -> None:
    out = Path(args.out_dir)
    acceptance_paths = [Path(path) / "acceptance.json" for path in args.acceptance_dirs.split(",") if path]
    deadline = _deadline_utc(args.deadline_hour)
    selected: Path | None = None
    while datetime.now(timezone.utc) < deadline:
        for path in acceptance_paths:
            if _acceptance_pass(path):
                selected = path
                break
        if selected is not None:
            break
        time.sleep(args.poll_seconds)
    if selected is None:
        _write(out / "line2_stage_a_gate.json", {
            "module": "overnight_six_lines.line2_watch",
            "generated_at": _now(),
            "status": "CHAIN_NOT_RUN_GATES_PENDING",
            "acceptance_paths": [str(path) for path in acceptance_paths],
            "deadline_utc": deadline.isoformat(),
            "fail_closed": True,
        })
        return

    stage_out = out / "stage_a_from_learned_operator"
    command = [
        args.python_bin,
        "-m",
        "experiments.stage_a_backtrack_loop",
        "--mode",
        "overnight",
        "--output-dir",
        str(stage_out),
        "--device",
        args.device,
        "--learned-operator-acceptance",
        str(selected),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    _write(out / "line2_stage_a_gate.json", {
        "module": "overnight_six_lines.line2_watch",
        "generated_at": _now(),
        "status": "STAGE_A_ATTEMPTED_AFTER_G1_GATE" if completed.returncode == 0 else "STAGE_A_BLOCKED_AFTER_G1_GATE",
        "selected_acceptance": str(selected),
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "stage_a_results": str(stage_out / "results.json"),
        "fail_closed": completed.returncode != 0,
    })


def _shard_ready(path: Path) -> tuple[bool, dict[str, Any]]:
    payload = _load(path / "results.json")
    if not payload:
        return False, {"path": str(path), "exists": False}
    probe = payload.get("propagation_probe", {})
    settings = probe.get("settings", {})
    seeds = settings.get("seeds", [])
    ready = (
        int(settings.get("n_instances") or 0) >= 50
        and len(seeds) >= 2
        and settings.get("scale_grade") == "50x2"
        and str(probe.get("status", "")).startswith("MEASURED_50X2")
    )
    return ready, {"path": str(path), "exists": True, "ready_50x2": ready, "settings": settings, "status": probe.get("status")}


def line4_watch(args: argparse.Namespace) -> None:
    out = Path(args.out_dir)
    w3_root = Path(args.w3_output_dir)
    deadline = _deadline_utc(args.deadline_hour)
    shard_dirs = [w3_root / "propagation_shards" / task for task in TASKS]
    rows: list[dict[str, Any]] = []
    while datetime.now(timezone.utc) < deadline:
        statuses = [_shard_ready(path) for path in shard_dirs]
        rows = [row for _, row in statuses]
        if all(ok for ok, _ in statuses):
            command = [args.python_bin, "-m", "experiments.w3_qwen35_probe", "--output-dir", str(w3_root), "--merge-propagation-shards", ",".join(str(path) for path in shard_dirs)]
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
            _write(out / "line4_w3_50x2_merge.json", {
                "module": "overnight_six_lines.line4_watch",
                "generated_at": _now(),
                "status": "W3_50X2_MERGE_ATTEMPTED" if completed.returncode == 0 else "W3_50X2_MERGE_FAILED",
                "shards": rows,
                "command": command,
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-4000:],
                "stderr_tail": completed.stderr[-4000:],
                "fail_closed": completed.returncode != 0,
            })
            return
        time.sleep(args.poll_seconds)
    _write(out / "line4_w3_50x2_merge.json", {
        "module": "overnight_six_lines.line4_watch",
        "generated_at": _now(),
        "status": "W3_50X2_SHARDS_PENDING_NOT_MERGED",
        "shards": rows,
        "deadline_utc": deadline.isoformat(),
        "fail_closed": True,
    })


def line5_trm(args: argparse.Namespace) -> None:
    out = Path(args.out_dir)
    quarantine = Path(args.quarantine_dir)
    quarantine.mkdir(parents=True, exist_ok=True)
    checkpoint = Path(args.checkpoint) if args.checkpoint else None
    if checkpoint and checkpoint.exists():
        status = "TRM_CHECKPOINT_PRESENT_WRAPPER_PENDING"
        reason = "Checkpoint exists, but this repo has no audited TRM inference wrapper plus minimal-DPLL-depth grader yet."
    else:
        status = "CHECKPOINT_UNAVAILABLE_NOT_RUN"
        reason = "No Sudoku-Extreme checkpoint path was provided; train-to-spec is forbidden for this line."
    _write(out / "line5_trm_defensive.json", {
        "module": "overnight_six_lines.line5_trm",
        "generated_at": _now(),
        "status": status,
        "quarantine_dir": str(quarantine),
        "checkpoint": str(checkpoint) if checkpoint else "",
        "reason": reason,
        "forbidden": ["train_to_spec", "use_trm_as_stage_a_core_evidence"],
        "fail_closed": True,
    })


def line6_audit(args: argparse.Namespace) -> None:
    from tasks.sudoku.generator_9x9 import generate_9x9_by_depth_band

    out = Path(args.out_dir)
    rows = []
    for depth in [1, 2]:
        instances = generate_9x9_by_depth_band(depth, depth, args.n_instances, args.seed + depth)
        rows.append({"depth": depth, "requested": args.n_instances, "generated": len(instances), "forward_only_count": sum(1 for item in instances if item.dpll_backtrack_depth == 0)})
    ok = all(row["generated"] >= args.n_instances and row["forward_only_count"] == 0 for row in rows)
    _write(out / "line6_9x9_generator_audit.json", {
        "module": "overnight_six_lines.line6_audit",
        "generated_at": _now(),
        "status": "L3_DEPTH_1_2_GENERATOR_AUDIT_PASS" if ok else "L3_DEPTH_1_2_GENERATOR_AUDIT_FAIL_QUARANTINE_CAPACITY_TABLE",
        "rows": rows,
        "capacity_table_status": "CAN_QUOTE_TRUE_DIMS_AFTER_FRONTIER_RERUN" if ok else "DO_NOT_QUOTE_TRUE_DIMS_CAPACITY_TABLE_YET",
        "source": "tasks.sudoku.generator_9x9.generate_9x9_by_depth_band",
        "fail_closed": not ok,
    })


def rollup(args: argparse.Namespace) -> None:
    root = Path(args.run_root)
    artifacts = sorted(root.glob("line*/*.json")) + sorted(root.glob("*.json"))
    rows = []
    for path in artifacts:
        payload = _load(path)
        if payload:
            rows.append({"path": str(path), "status": payload.get("status"), "fail_closed": payload.get("fail_closed", False)})
    _write(root / "rollup.json", {
        "module": "overnight_six_lines.rollup",
        "generated_at": _now(),
        "status": "OVERNIGHT_ROLLUP_COMPLETE",
        "run_root": str(root),
        "artifacts": rows,
        "fail_closed_count": sum(1 for row in rows if row.get("fail_closed")),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="Six-line overnight fail-closed helpers.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("block")
    p.add_argument("--out", required=True)
    p.add_argument("--line", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--evidence", default="")
    p.set_defaults(func=block)

    p = sub.add_parser("line2-watch")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--acceptance-dirs", required=True)
    p.add_argument("--deadline-hour", type=int, default=6)
    p.add_argument("--poll-seconds", type=int, default=900)
    p.add_argument("--python-bin", default=os.environ.get("PYTHON_BIN", ".venv/bin/python"))
    p.add_argument("--device", default="cuda:3")
    p.set_defaults(func=line2_watch)

    p = sub.add_parser("line4-watch")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--w3-output-dir", default="results/w3_qwen35_probe")
    p.add_argument("--deadline-hour", type=int, default=6)
    p.add_argument("--poll-seconds", type=int, default=900)
    p.add_argument("--python-bin", default=os.environ.get("PYTHON_BIN", ".venv/bin/python"))
    p.set_defaults(func=line4_watch)

    p = sub.add_parser("line5-trm")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--quarantine-dir", default="artifacts/trm_defensive")
    p.add_argument("--checkpoint", default=os.environ.get("TRM_SUDOKU_EXTREME_CHECKPOINT", ""))
    p.set_defaults(func=line5_trm)

    p = sub.add_parser("line6-audit")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--n-instances", type=int, default=200)
    p.add_argument("--seed", type=int, default=6036)
    p.set_defaults(func=line6_audit)

    p = sub.add_parser("rollup")
    p.add_argument("--run-root", required=True)
    p.set_defaults(func=rollup)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()