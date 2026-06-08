"""Progress monitor and checkpoint writer for overnight run roots."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _tail_jsonl(path: Path, max_rows: int = 5) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_rows:]
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _tail_text(path: Path, max_chars: int = 2000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def _tail_log_json(path: Path, max_rows: int = 5) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows[-max_rows:]


def _pid_running(pid: int) -> bool:
    try:
        Path(f"/proc/{pid}").stat()
        return True
    except FileNotFoundError:
        return False


def _gpu_snapshot() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,memory.used,memory.total,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        output = subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL, timeout=5.0)
    except (OSError, subprocess.SubprocessError):
        return {"available": False}
    rows = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        rows.append({"index": int(parts[0]), "memory_used_mib": float(parts[1]), "memory_total_mib": float(parts[2]), "utilization_gpu_percent": float(parts[3])})
    return {"available": True, "rows": rows}


def snapshot(run_root: Path) -> dict[str, Any]:
    logs = run_root / "logs"
    line_rows = []
    for pid_path in sorted(logs.glob("*.pid")):
        name = pid_path.stem
        if name == "overnight_monitor":
            continue
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = -1
        status_path = logs / f"{name}.status"
        log_path = logs / f"{name}.log"
        line_dir = run_root / name
        if name == "line1_headline":
            line_dir = run_root / "line1_headline"
        elif name == "line2_track_b_diagnostic":
            line_dir = run_root / "line2_track_b_diagnostic"
        elif name == "line3_qwen_d1_decode":
            line_dir = run_root / "line3_qwen_d1_decode"
        elif name == "line4_d3":
            line_dir = run_root / "line4_d3"
        json_outputs = sorted(str(path.relative_to(run_root)) for path in line_dir.glob("*.json")) if line_dir.exists() else []
        progress_rows = []
        for progress_path in sorted(line_dir.glob("*.jsonl")):
            progress_rows.extend(_tail_jsonl(progress_path, 3))
        latest_progress = progress_rows[-1] if progress_rows else None
        if isinstance(latest_progress, dict) and "bins" in latest_progress:
            checkpoint_dir = line_dir / "checkpoints"
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_path = checkpoint_dir / "mining_latest.json"
            existing = _load_json(checkpoint_path)
            existing_module = existing.get("module") if isinstance(existing, dict) else ""
            if existing_module != "overnight_headline.mine_pool.checkpoint":
                checkpoint_path.write_text(json.dumps({
                    "module": "monitor_overnight_progress.mining_count_checkpoint",
                    "generated_at": _now(),
                    "status": "COUNT_ONLY_PROGRESS_CHECKPOINT",
                    "line": name,
                    "bins": latest_progress.get("bins"),
                    "chunk_index": latest_progress.get("chunk_index"),
                    "source": str(progress_path.relative_to(run_root)),
                    "limitation": "Current process started before internal selected-instance checkpoint support; this checkpoint preserves progress counts, not candidate rows.",
                }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result_statuses = []
        for json_path in sorted(line_dir.glob("*.json")):
            payload = _load_json(json_path)
            if payload:
                result_statuses.append({"path": str(json_path.relative_to(run_root)), "status": payload.get("status"), "fail_closed": payload.get("fail_closed", False)})
        line_rows.append({
            "name": name,
            "pid": pid,
            "running": _pid_running(pid) if pid > 0 else False,
            "status_file": status_path.read_text(encoding="utf-8").strip() if status_path.exists() else "",
            "log_tail": _tail_text(log_path),
            "log_json_tail": _tail_log_json(log_path),
            "json_outputs": json_outputs,
            "result_statuses": result_statuses,
            "progress_tail": progress_rows,
        })
    return {
        "module": "monitor_overnight_progress",
        "generated_at": _now(),
        "status": "RUNNING" if any(row["running"] for row in line_rows) else "ALL_LINES_EXITED",
        "run_root": str(run_root),
        "lines": line_rows,
        "gpu_snapshot": _gpu_snapshot(),
    }


def run(args: argparse.Namespace) -> None:
    run_root = Path(args.run_root)
    checkpoint_dir = run_root / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    progress_path = run_root / "monitor_progress.jsonl"
    iteration = 0
    while True:
        payload = snapshot(run_root)
        payload["iteration"] = iteration
        latest = checkpoint_dir / "monitor_latest.json"
        latest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        numbered = checkpoint_dir / f"monitor_{iteration:05d}.json"
        numbered.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"generated_at": payload["generated_at"], "iteration": iteration, "status": payload["status"], "lines": [{"name": row["name"], "running": row["running"], "status_file": row["status_file"], "result_statuses": row["result_statuses"], "progress_tail": row["progress_tail"][-1:] if row["progress_tail"] else [], "log_json_tail": row["log_json_tail"][-2:] if row["log_json_tail"] else []} for row in payload["lines"]]}, sort_keys=True) + "\n")
        print(json.dumps({"event": "monitor_checkpoint", "iteration": iteration, "status": payload["status"], "latest": str(latest)}, sort_keys=True), flush=True)
        if payload["status"] == "ALL_LINES_EXITED" or iteration >= args.max_iterations:
            break
        iteration += 1
        time.sleep(args.interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor overnight run progress and write checkpoints.")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--max-iterations", type=int, default=720)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()