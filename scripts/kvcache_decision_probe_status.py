"""Print progress for sharded KV-cache decision probe runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _rows_and_status(path: Path) -> tuple[int, str]:
    payload = _read_json(path)
    if isinstance(payload, list):
        return len(payload), "checkpoint"
    if isinstance(payload, dict):
        rows = payload.get("rows", [])
        return len(rows) if isinstance(rows, list) else 0, str(payload.get("status", "dict"))
    return 0, "missing_or_unreadable"


def _active_runners() -> list[str]:
    proc = subprocess.run(
        ["ps", "-eo", "pid,ppid,pcpu,pmem,etime,args"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    lines = []
    for line in proc.stdout.splitlines():
        if "analysis.kvcache_decision_probe" in line and "grep" not in line:
            lines.append(line.strip())
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Show KV-cache decision probe progress.")
    parser.add_argument("--root", type=Path, default=Path("results/kvcache_decision_probe/part1"))
    parser.add_argument("--merged", type=Path, default=Path("results/kvcache_decision_probe/part1/merged_decision_probe.json"))
    args = parser.parse_args()

    print(f"root={args.root}")
    print("\nactive_runners:")
    runners = _active_runners()
    if runners:
        for runner in runners:
            print(f"  {runner}")
    else:
        print("  none")

    print("\nshards:")
    for name in ["points_cache.json", "points_collect.json"]:
        path = args.root / name
        rows, status = _rows_and_status(path)
        payload = _read_json(path)
        extra = ""
        if isinstance(payload, dict):
            summary = payload.get("preflight_summary", {})
            if summary:
                extra = f" preflight_summary={summary}"
            elif isinstance(payload.get("points"), list):
                extra = f" points={len(payload.get('points', []))} preflight_rows={len(payload.get('preflight_rows', []))}"
        print(f"  {name}: status={status} rows={rows}{extra}")
    shard_paths = sorted(args.root.glob("shard_*_checkpoint.json"))
    if not shard_paths:
        print("  none")
    for checkpoint in shard_paths:
        rows, status = _rows_and_status(checkpoint)
        final = checkpoint.with_name(checkpoint.name.replace("_checkpoint", ""))
        final_rows, final_status = _rows_and_status(final)
        print(f"  {checkpoint.stem}: checkpoint_rows={rows} checkpoint_status={status} output_rows={final_rows} output_status={final_status}")

    rows, status = _rows_and_status(args.merged)
    print("\nmerged:")
    print(f"  path={args.merged} status={status} rows={rows}")


if __name__ == "__main__":
    main()