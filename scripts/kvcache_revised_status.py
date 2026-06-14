"""Print progress for revised KV-cache graph_color sweeps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def _read_json(path: Path) -> object | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _row_count(payload: object | None) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return len(payload["rows"])
    return 0


def _payload_status(payload: object | None) -> str:
    if isinstance(payload, dict):
        return str(payload.get("status") or "dict")
    if isinstance(payload, list):
        return "checkpoint"
    return "missing_or_unreadable"


def _running_commands() -> list[str]:
    result = subprocess.run(
        ["ps", "-eo", "pid,pcpu,pmem,etime,args"],
        check=False,
        text=True,
        capture_output=True,
    )
    rows: list[str] = []
    for line in result.stdout.splitlines():
        if "analysis.kvcache_graph_color_search" in line and "ps -eo" not in line:
            rows.append(line.strip())
    return rows


def run(args: argparse.Namespace) -> None:
    root = args.root
    print(f"root={root}")
    print("\nactive_runners:")
    active = _running_commands()
    if active:
        for line in active:
            print(f"  {line}")
    else:
        print("  none")

    print("\nshards:")
    for bin_dir in sorted(path for path in root.glob("*") if path.is_dir()):
        print(f"  [{bin_dir.name}]")
        shard_indexes = sorted(
            {
                int(path.stem.split("_")[1])
                for path in bin_dir.glob("shard_*_checkpoint.json")
                if len(path.stem.split("_")) >= 3 and path.stem.split("_")[1].isdigit()
            }
            | {
                int(path.stem.split("_")[1])
                for path in bin_dir.glob("shard_*.json")
                if len(path.stem.split("_")) >= 2 and path.stem.split("_")[1].isdigit()
            }
        )
        if not shard_indexes:
            print("    no shards yet")
            continue
        for shard_index in shard_indexes:
            checkpoint = bin_dir / f"shard_{shard_index}_checkpoint.json"
            output = bin_dir / f"shard_{shard_index}.json"
            checkpoint_payload = _read_json(checkpoint)
            output_payload = _read_json(output)
            print(
                "    "
                f"shard={shard_index} "
                f"checkpoint_rows={_row_count(checkpoint_payload)} "
                f"output_status={_payload_status(output_payload)} "
                f"output_rows={_row_count(output_payload)}"
            )

    merged = args.merged
    merged_payload = _read_json(merged)
    print("\nmerged:")
    print(f"  path={merged} status={_payload_status(merged_payload)} rows={_row_count(merged_payload)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show revised KV-cache sweep progress.")
    parser.add_argument("--root", type=Path, default=Path("results/kvcache_graph_color/revised_bins"))
    parser.add_argument("--merged", type=Path, default=Path("results/kvcache_graph_color/revised_bins/merged_revised_bins.json"))
    run(parser.parse_args())


if __name__ == "__main__":
    main()