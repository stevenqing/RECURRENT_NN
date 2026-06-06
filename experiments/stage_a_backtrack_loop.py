"""Stage A controlled backtracking loop entrypoint.

This module owns the Stage A overnight grid contract: cell enumeration, sharding,
hard preflight checks for inherited parent artifacts, and result schemas. The
actual recurrent-depth parent operator/decoder adapter is intentionally not
reconstructed here; the run refuses to start until the inherited checkpoint,
bridge decoder, and teacher traces are present.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


PRIMARY_STACKS = ["rot_bound_single", "rot_factored", "gru", "tape", "rot_no_revert"]
PRIMARY_DS = [128, 256, 512]
PRIMARY_SEEDS = [42, 137]
SECONDARY_BRANCH_HEURISTICS = ["max_confidence", "mrv", "learned_head"]
SECONDARY_AUX_DEADEND = ["off", "on"]


@dataclass(frozen=True)
class StageACell:
    cell_index: int
    grid: str
    stack: str
    D: int
    seed: int
    branch_heuristic: str
    aux_deadend_loss: str
    expected_gate: str
    register_variant: str

    @property
    def name(self) -> str:
        return (
            f"{self.grid}_{self.stack}_D{self.D}_seed{self.seed}_"
            f"branch-{self.branch_heuristic}_deadend-{self.aux_deadend_loss}"
        )


def build_grid() -> list[StageACell]:
    cells: list[StageACell] = []
    index = 0
    for stack in PRIMARY_STACKS:
        for D in PRIMARY_DS:
            for seed in PRIMARY_SEEDS:
                cells.append(StageACell(
                    cell_index=index,
                    grid="primary",
                    stack=stack,
                    D=D,
                    seed=seed,
                    branch_heuristic="max_confidence",
                    aux_deadend_loss="off",
                    expected_gate="fail_is_bug" if stack.startswith("rot_") and stack != "rot_no_revert" else "fail_is_control",
                    register_variant=stack,
                ))
                index += 1
    for branch_heuristic in SECONDARY_BRANCH_HEURISTICS:
        for aux_deadend_loss in SECONDARY_AUX_DEADEND:
            cells.append(StageACell(
                cell_index=index,
                grid="secondary",
                stack="rot_bound_single",
                D=256,
                seed=42,
                branch_heuristic=branch_heuristic,
                aux_deadend_loss=aux_deadend_loss,
                expected_gate="fail_is_bug",
                register_variant="rot_bound_single",
            ))
            index += 1
    return cells


def shard_grid(num_shards: int, shard_index: int) -> list[StageACell]:
    if shard_index < 0 or shard_index >= num_shards:
        raise ValueError("shard_index must be in [0, num_shards)")
    return [cell for cell in build_grid() if cell.cell_index % num_shards == shard_index]


def _resolve(path_text: str, repo_root: Path) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path


def preflight(
    operator_ckpt: str,
    bridge_decoder: str,
    teacher_trace: str,
    output_dir: str,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "operator_ckpt": _resolve(operator_ckpt, repo),
        "bridge_decoder": _resolve(bridge_decoder, repo),
        "teacher_trace": _resolve(teacher_trace, repo),
        "module1_capacity": repo / "results/module1_capacity_perdepth_shards/results.json",
    }
    checks = []
    for name, path in paths.items():
        ok = path is not None and path.exists() and path.is_file()
        checks.append({"name": name, "path": str(path) if path is not None else "", "ok": ok})
    missing = [row for row in checks if not row["ok"]]
    payload = {
        "module": "stage_a_backtrack_loop",
        "status": "READY" if not missing else "PRECHECK_FAILED",
        "checks": checks,
        "missing": missing,
        "total_cells": len(build_grid()),
        "grid": [asdict(cell) | {"name": cell.name} for cell in build_grid()],
        "discipline": {
            "operator": "frozen inherited parent checkpoint",
            "trainable": ["controller", "h_work_gru", "non_inherited_register_readout"],
            "forbidden": ["qwen", "token_scratchpad", "teacher_action_injection_at_eval", "prefix_at_eval"],
        },
    }
    (output / "preflight.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def run_shard(
    output_dir: str,
    operator_ckpt: str,
    bridge_decoder: str,
    teacher_trace: str,
    num_shards: int,
    shard_index: int,
    device: str,
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    pre = preflight(operator_ckpt, bridge_decoder, teacher_trace, str(root), Path.cwd())
    selected = shard_grid(num_shards, shard_index)
    payload: dict[str, Any] = {
        "module": "stage_a_backtrack_loop",
        "status": pre["status"],
        "device": device,
        "shard_index": shard_index,
        "num_shards": num_shards,
        "selected_cells": len(selected),
        "total_cells": len(build_grid()),
        "cells": [asdict(cell) | {"name": cell.name} for cell in selected],
        "preflight": pre,
    }
    if pre["status"] != "READY":
        payload["message"] = "Stage A did not start because inherited parent artifacts are missing."
        (root / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise SystemExit(2)
    payload["status"] = "PARENT_ADAPTER_REQUIRED"
    payload["message"] = (
        "Preflight passed, but the recurrent-depth parent operator/bridge adapter "
        "is not present in this repository. Wire the inherited adapter here before "
        "running autonomous solve metrics."
    )
    (root / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    raise SystemExit(3)


def smoke(
    output_dir: str,
    operator_ckpt: str,
    bridge_decoder: str,
    teacher_trace: str,
    num_shards: int,
    shard_index: int,
    device: str,
) -> dict[str, Any]:
    import torch

    from register.vsa_stack import BoundSingleRegister, FactoredRegister, RotationVSAStack, TapeStack

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    selected = shard_grid(num_shards, shard_index)
    pre = preflight(operator_ckpt, bridge_decoder, teacher_trace, str(root), Path.cwd())
    torch_device = torch.device(device)
    if torch_device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA smoke requested but torch.cuda.is_available() is false")
    probe = torch.ones(8, device=torch_device)
    gpu_checksum = float((probe * 2).sum().item())

    bound = BoundSingleRegister(D=128, K_var=81, K_val=9, max_depth=8, seed=123, device=torch_device)
    bound.push(0, 10, 4)
    bound_var, bound_val, bound_margin = bound.decode_level(0)
    factored = FactoredRegister(D=128, K_var=81, K_val=9, max_depth=8, seed=123, device=torch_device)
    factored.push(0, 10, 4)
    factored_var, factored_val, factored_margin = factored.decode_level(0)
    rot = RotationVSAStack(D=128, K=81 * 9, max_depth=8, seed=123, device=torch_device)
    symbols = torch.tensor([10 * 9 + 4], device=torch_device)
    rot_h = rot.encode(symbols)
    rot_pred, rot_margin = rot.decode(rot_h, 1)
    tape = TapeStack()
    tape_pred, tape_margin = tape.decode(tape.encode(symbols), 1)

    register_checks = {
        "bound_single": {"ok": bound_var == 10 and bound_val == 4, "var": bound_var, "val": bound_val, "margin": bound_margin},
        "factored": {"ok": factored_var == 10 and factored_val == 4, "var": factored_var, "val": factored_val, "margin": factored_margin},
        "rot_symbol": {"ok": int(rot_pred[0].item()) == int(symbols[0].item()), "symbol": int(rot_pred[0].item()), "margin": float(rot_margin[0].item())},
        "tape": {"ok": int(tape_pred[0].item()) == int(symbols[0].item()), "symbol": int(tape_pred[0].item()), "margin": float(tape_margin[0].item())},
    }
    payload = {
        "module": "stage_a_backtrack_smoke",
        "status": "SMOKE_PASS" if all(row["ok"] for row in register_checks.values()) else "SMOKE_FAIL",
        "device": device,
        "cuda_visible": torch.cuda.is_available(),
        "cuda_device_name": torch.cuda.get_device_name(0) if torch_device.type == "cuda" and torch.cuda.is_available() else "",
        "gpu_checksum": gpu_checksum,
        "shard_index": shard_index,
        "num_shards": num_shards,
        "selected_cells": len(selected),
        "selected_cell_indices": [cell.cell_index for cell in selected],
        "total_cells": len(build_grid()),
        "register_checks": register_checks,
        "preflight_status": pre["status"],
        "preflight_missing": [row["name"] for row in pre["missing"]],
    }
    (root / "smoke.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage A latent backtracking overnight grid.")
    parser.add_argument("--mode", choices=["preflight", "overnight", "list-grid", "smoke"], default="preflight")
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--operator-ckpt", required=False, default="/recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt")
    parser.add_argument("--bridge-decoder", required=False, default="")
    parser.add_argument("--teacher-trace", required=False, default="internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl")
    parser.add_argument("--output-dir", default="results/stage_a_backtrack")
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    if args.mode == "list-grid":
        print(json.dumps({"total_cells": len(build_grid()), "cells": [asdict(cell) | {"name": cell.name} for cell in build_grid()]}, indent=2, sort_keys=True))
        return
    if args.mode == "preflight":
        payload = preflight(args.operator_ckpt, args.bridge_decoder, args.teacher_trace, args.output_dir, Path.cwd())
        print(json.dumps(payload, indent=2, sort_keys=True))
        if payload["status"] != "READY":
            raise SystemExit(2)
        return
    if args.mode == "smoke":
        payload = smoke(args.output_dir, args.operator_ckpt, args.bridge_decoder, args.teacher_trace, args.num_shards, args.shard_index, args.device)
        if payload["status"] != "SMOKE_PASS":
            raise SystemExit(4)
        return
    payload = run_shard(args.output_dir, args.operator_ckpt, args.bridge_decoder, args.teacher_trace, args.num_shards, args.shard_index, args.device)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()