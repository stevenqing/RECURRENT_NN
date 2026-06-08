"""Monitor Track B TRM-class training jobs.

The trainer already writes JSONL progress rows. This sidecar turns per-job logs,
PIDs, and final acceptance files into stable monitor artifacts that can be read
without tailing long logs.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRAIN_EVENT = "trm_operator_train"
GEN_EVENTS = {"generate_6x6_start", "generate_6x6_progress", "generate_6x6_done"}
TENSORIZE_EVENTS = {"tensorize_start", "tensorize_progress", "tensorize_done"}
ERROR_MARKERS = ("Traceback", "RuntimeError", "CUDA out", "OutOfMemoryError")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _parse_json_log(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return events, errors
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if any(marker in line for marker in ERROR_MARKERS):
                errors.append(line[:500])
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events, errors[-10:]


def _generation_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[tuple[int, int, int], dict[str, Any]] = {}
    for event in events:
        if event.get("event") not in GEN_EVENTS:
            continue
        target = int(event.get("target") or event.get("n_instances") or event.get("instances") or 0)
        key = (int(event.get("min_depth") or -1), int(event.get("max_depth") or -1), target)
        current = rows.setdefault(key, {"min_depth": key[0], "max_depth": key[1], "target": target, "instances": 0, "done": False})
        if "instances" in event:
            current["instances"] = max(int(current.get("instances") or 0), int(event.get("instances") or 0))
        if event.get("event") == "generate_6x6_done":
            current["done"] = True
            current["examples"] = event.get("examples")
            current["instances"] = max(int(current.get("instances") or 0), int(event.get("instances") or 0))
        if target:
            current["fraction"] = min(1.0, float(current.get("instances") or 0) / target)
    return sorted(rows.values(), key=lambda row: (row["min_depth"], row["max_depth"], row["target"]))


def _latest_training(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    train_events = [event for event in events if event.get("event") == TRAIN_EVENT]
    if not train_events:
        return None
    latest = train_events[-1]
    step = int(latest.get("step") or 0)
    steps = int(latest.get("steps") or 0)
    row = dict(latest)
    row["fraction"] = min(1.0, step / steps) if steps else 0.0
    return row


def _tensorize_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("event") not in TENSORIZE_EVENTS:
            continue
        label = str(event.get("label") or "unknown")
        current = rows.setdefault(label, {"label": label, "rows": 0, "target": int(event.get("examples") or event.get("target") or 0), "done": False})
        if event.get("examples") or event.get("target"):
            current["target"] = max(int(current.get("target") or 0), int(event.get("examples") or event.get("target") or 0))
        if event.get("rows") is not None:
            current["rows"] = max(int(current.get("rows") or 0), int(event.get("rows") or 0))
        current["workers"] = event.get("workers", current.get("workers"))
        if event.get("event") == "tensorize_done":
            current["done"] = True
            current["rows"] = max(int(current.get("rows") or 0), int(event.get("rows") or 0))
        target = int(current.get("target") or 0)
        current["fraction"] = min(1.0, float(current.get("rows") or 0) / target) if target else 0.0
    return [rows[key] for key in sorted(rows)]


def _stage(alive: bool, acceptance: dict[str, Any] | None, events: list[dict[str, Any]], errors: list[str]) -> str:
    if acceptance:
        return "complete"
    if errors and not alive:
        return "failed"
    if any(event.get("event") == TRAIN_EVENT for event in events):
        return "training" if alive else "training_stopped_without_acceptance"
    if any(event.get("event") in TENSORIZE_EVENTS for event in events):
        return "tensorization" if alive else "tensorization_stopped_without_acceptance"
    if any(event.get("event") in GEN_EVENTS for event in events):
        return "data_generation" if alive else "generation_stopped_without_acceptance"
    return "starting" if alive else "not_running"


def _acceptance_summary(acceptance: dict[str, Any] | None) -> dict[str, Any] | None:
    if not acceptance:
        return None
    forced = acceptance.get("forced_only", {})
    return {
        "status": acceptance.get("status"),
        "G1": acceptance.get("G1"),
        "G2": acceptance.get("G2"),
        "single_step_forced_precision": forced.get("single_step_forced_precision"),
        "single_step_forced_recall": forced.get("single_step_forced_recall"),
        "checkpoint": acceptance.get("checkpoint"),
    }


def monitor_job(run_root: Path, pid_path: Path) -> dict[str, Any]:
    name = pid_path.stem
    pid = int(pid_path.read_text(encoding="utf-8").strip())
    alive = _pid_alive(pid)
    log_path = run_root / "logs" / f"{name}.log"
    out_dir = run_root / name
    if not out_dir.exists():
        parts = name.split("_gpu", 1)
        if len(parts) == 2:
            out_dir = run_root / f"{parts[0]}_gpu{parts[1]}"
    acceptance = _read_json(out_dir / "acceptance.json")
    events, errors = _parse_json_log(log_path)
    latest_training = _latest_training(events)
    payload = {
        "module": "monitor_track_b_trm",
        "updated_at": _utc_now(),
        "run_root": str(run_root),
        "job": name,
        "pid": pid,
        "pid_alive": alive,
        "stage": _stage(alive, acceptance, events, errors),
        "log_path": str(log_path),
        "log_bytes": log_path.stat().st_size if log_path.exists() else 0,
        "output_dir": str(out_dir),
        "generation": _generation_rows(events),
        "tensorization": _tensorize_rows(events),
        "training_latest": latest_training,
        "acceptance": _acceptance_summary(acceptance),
        "errors": errors,
        "last_json_event": events[-1] if events else None,
    }
    (out_dir / "monitor.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_root / "logs" / f"{name}.monitor.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def monitor_run(run_root: Path) -> dict[str, Any]:
    run_root.mkdir(parents=True, exist_ok=True)
    pid_paths = sorted(path for path in (run_root / "logs").glob("seed*.pid") if path.stem != "monitor")
    jobs = [monitor_job(run_root, pid_path) for pid_path in pid_paths]
    summary = {
        "module": "monitor_track_b_trm.summary",
        "updated_at": _utc_now(),
        "run_root": str(run_root),
        "n_jobs": len(jobs),
        "running": sum(1 for job in jobs if job.get("pid_alive")),
        "complete": sum(1 for job in jobs if job.get("stage") == "complete"),
        "failed": sum(1 for job in jobs if job.get("stage") == "failed"),
        "jobs": jobs,
    }
    (run_root / "monitor_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor Track B TRM jobs from logs and pid files.")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    run_root = Path(args.run_root)
    if args.once:
        print(json.dumps(monitor_run(run_root), indent=2, sort_keys=True))
        return
    while True:
        monitor_run(run_root)
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
