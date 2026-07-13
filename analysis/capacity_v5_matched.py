"""Run and analyze the SPEC v5 matched-load mechanism experiment."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from experiments.capacity.breakthrough import per_register_load_curve, run_matched_load
from experiments.capacity.stats import holm_bonferroni, mcnemar_exact
from experiments.capacity.width_wall import load_state_shards


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path), "rows": len(payload.get("rows", []))}), flush=True)


def _strip_raw(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    clean = []
    raw = []
    for row in rows:
        copy = dict(row)
        raw.extend(copy.pop("raw", []))
        clean.append(copy)
    return clean, raw


def _correct_by_n(raw: list[dict[str, Any]]) -> dict[int, list[bool]]:
    grouped: dict[int, dict[int, bool]] = {}
    for row in raw:
        grouped.setdefault(int(row["N"]), {})[int(row["trial"])] = bool(row["correct"])
    return {n_value: [trials[index] for index in sorted(trials)] for n_value, trials in grouped.items()}


def run_v5(
    state_dir: str,
    wall_result: str,
    out_dir: str,
    D: int = 2560,
    K: int = 9,
    widths: tuple[int, ...] = (512, 384),
    Ns: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8),
    reads: int = 300,
    seed: int = 0,
) -> dict[str, Any]:
    wall = json.loads(Path(wall_result).read_text(encoding="utf-8"))
    if wall.get("schema") != "bind_capacity_curve_v3" or wall.get("regime") != "D" or not wall.get("G2_prime_pass"):
        raise RuntimeError("E5 requires a passing D-regime v3 bind-wall artifact")
    W_star = int(wall["W_star_bind"])
    states, state_source = load_state_shards(state_dir)
    states = states[: int(state_source["unique_branch_state_bound"])]
    if int(states.shape[1]) != int(D) or int(state_source["K"]) != int(K):
        raise RuntimeError("state source does not match E5 D/K")
    loads = set(int(width) for width in widths)
    for width in widths:
        for n_value in Ns:
            loads.add(int(math.ceil(int(width) / int(n_value))))
    load_result = per_register_load_curve(None, D, K, sorted(loads), seed, whiten=True, instances=reads, branch_states=states)
    load_curve, _unused_raw = _strip_raw(load_result["curve"])
    load_raw = load_result["raw"]
    load_accuracy = {int(row["load"]): float(row["read_accuracy"]) for row in load_curve}
    root = Path(out_dir)
    _write(root / "per_register_load_curve.json", {
        "schema": "per_register_load_curve_v5",
        "D": int(D),
        "K": int(K),
        "seed": int(seed),
        "reads": int(reads),
        "states_source": state_source,
        "rows": load_curve,
    })
    _write(root / "raw" / "per_register_load_curve_raw.json", {"rows": load_raw})
    artifacts: dict[str, str] = {}
    arm_rows: dict[tuple[int, str], list[dict[str, Any]]] = {}
    arm_raw: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for width in widths:
        if width <= W_star:
            raise RuntimeError(f"E5 width {width} is not beyond W*={W_star}")
        single_accuracy = load_accuracy[int(width)]
        if single_accuracy + 1e-12 >= 0.9:
            raise RuntimeError(f"E5 width {width} is not a failing single-register condition")
        for arm in ("single", "consensus", "routing"):
            n_values = (1,) if arm == "single" else Ns
            rows = run_matched_load(
                None,
                D,
                K,
                int(width),
                n_values,
                arm,
                seed,
                whiten=True,
                instances=reads,
                branch_states=states,
                regime="D",
                W_star_bind=W_star,
                single_register_acc_at_W=single_accuracy,
            )
            clean, raw = _strip_raw(rows)
            stem = f"E5_W{int(width)}_{arm}"
            result_path = root / f"{stem}.json"
            raw_path = root / "raw" / f"{stem}_raw.json"
            _write(result_path, {
                "schema": "matched_load_v5",
                "arm": arm,
                "D": int(D),
                "K": int(K),
                "W": int(width),
                "W_star_bind": W_star,
                "single_register_acc_at_W": single_accuracy,
                "seed": int(seed),
                "reads": int(reads),
                "states_source": state_source,
                "rows": clean,
            })
            _write(raw_path, {"rows": raw})
            artifacts[f"W{width}_{arm}"] = str(result_path)
            arm_rows[(int(width), arm)] = clean
            arm_raw[(int(width), arm)] = raw
    p_values: dict[str, float] = {}
    paired_rows = []
    for width in widths:
        single = _correct_by_n(arm_raw[(int(width), "single")])[1]
        consensus = _correct_by_n(arm_raw[(int(width), "consensus")])
        for n_value in Ns:
            if int(n_value) == 1:
                continue
            candidate = consensus[int(n_value)]
            key = f"W{int(width)}_consensus_N{int(n_value)}_vs_single"
            p_value = mcnemar_exact(candidate, single)
            p_values[key] = p_value
            paired_rows.append({
                "key": key,
                "W": int(width),
                "N": int(n_value),
                "consensus_accuracy": sum(candidate) / len(candidate),
                "single_accuracy": sum(single) / len(single),
                "consensus_only": sum(a and not b for a, b in zip(candidate, single)),
                "single_only": sum(b and not a for a, b in zip(candidate, single)),
                "p_raw": p_value,
            })
    corrected = holm_bonferroni(p_values)
    for row in paired_rows:
        row["p_holm"] = corrected[row["key"]]
        row["holm_significant_0_05"] = corrected[row["key"]] < 0.05
    primary_width = int(widths[0])
    primary_consensus = arm_rows[(primary_width, "consensus")]
    primary_accuracies = [float(row["read_accuracy"]) for row in primary_consensus]
    nondecreasing = all(right + 1e-12 >= left for left, right in zip(primary_accuracies, primary_accuracies[1:]))
    significant_positive = any(
        row["W"] == primary_width
        and row["holm_significant_0_05"]
        and row["consensus_accuracy"] > row["single_accuracy"]
        for row in paired_rows
    )
    G5_pass = nondecreasing and significant_positive
    routing_checks = []
    for width in widths:
        for row in arm_rows[(int(width), "routing")]:
            load = int(row["per_register_load"])
            routing_checks.append({
                "W": int(width),
                "N": int(row["N"]),
                "per_register_load": load,
                "routing_accuracy": float(row["read_accuracy"]),
                "single_load_curve_accuracy": load_accuracy[load],
                "difference": float(row["read_accuracy"]) - load_accuracy[load],
            })
    return {
        "schema": "matched_load_mechanism_v5",
        "D": int(D),
        "K": int(K),
        "W_star_bind": W_star,
        "widths": [int(width) for width in widths],
        "Ns": [int(value) for value in Ns],
        "reads": int(reads),
        "seed": int(seed),
        "per_register_load_curve": load_curve,
        "routing_load_checks": routing_checks,
        "paired_tests": paired_rows,
        "G5_pass": G5_pass,
        "primary_consensus_nondecreasing": nondecreasing,
        "primary_consensus_significant_positive": significant_positive,
        "selected_thesis": "A_REDUNDANCY" if G5_pass else "B_LOAD_SPLITTING_ONLY",
        "artifacts": artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SPEC v5 matched-load mechanism test.")
    parser.add_argument("--states-dir", default="results/capacity/E0_geometry_qwen3_fp32_shards")
    parser.add_argument("--wall-result", default="results/capacity/E2_prime_bind_capacity_qwen3_fp32.json")
    parser.add_argument("--out-dir", default="results/capacity/v5_matched_load")
    parser.add_argument("--D", type=int, default=2560)
    parser.add_argument("--K", type=int, default=9)
    parser.add_argument("--widths", default="512,384")
    parser.add_argument("--Ns", default="1,2,3,4,5,6,7,8")
    parser.add_argument("--reads", type=int, default=300)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    widths = tuple(int(part) for part in args.widths.split(",") if part.strip())
    ns = tuple(int(part) for part in args.Ns.split(",") if part.strip())
    payload = run_v5(args.states_dir, args.wall_result, args.out_dir, args.D, args.K, widths, ns, args.reads, args.seed)
    out = Path(args.out_dir) / "summary.json"
    _write(out, payload)


if __name__ == "__main__":
    main()
