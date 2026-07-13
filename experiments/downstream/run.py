"""Run the SPEC v6 controlled downstream proxy benchmark.

This runner is useful for validating the coupled benchmark, method API, matched
budget accounting, and preregistered statistics. Its current symbolic operator
backend is deliberately ineligible for a real-Qwen downstream headline claim.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.capacity.stats import holm_bonferroni, mcnemar_exact
from experiments.downstream.dist_coloring import make_instance, with_frontier_width
from experiments.downstream.methods import METHODS, solve


REQUIRED_MAIN = (
    "A1_dfs_acache",
    "A4_beam_selfeval",
    "B1_self_consistency",
    "C1_debate",
    "C3_saga_rollback",
    "C4_sync_local",
    "D1_reversible_redundancy",
)


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path), "rows": len(payload.get("rows", []))}), flush=True)


def _parse_ints(text: str) -> list[int]:
    return [int(part) for part in text.split(",") if part.strip()]


def _parse_floats(text: str) -> list[float]:
    return [float(part) for part in text.split(",") if part.strip()]


def _summary(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    output = []
    for key, subset in sorted(groups.items(), key=lambda item: tuple(map(str, item[0]))):
        output.append({
            **dict(zip(keys, key)),
            "n": len(subset),
            "solve_rate": mean(float(row["solved"]) for row in subset),
            "joint_consistency_rate": mean(float(row["joint_consistency_rate"]) for row in subset),
            "mean_frontier_width_maintained": mean(float(row["frontier_width_maintained"]) for row in subset),
            "mean_forwards": mean(float(row["forwards"]) for row in subset),
            "mean_tokens": mean(float(row["tokens"]) for row in subset),
            "mean_forward_budget_utilization": mean(float(row["forwards"]) / max(float(row["budget"]), 1.0) for row in subset),
            "mean_token_budget_utilization": mean(float(row["tokens"]) / max(float(row["token_budget"]), 1.0) for row in subset),
            "mean_cross_partition_violations": mean(float(row["cross_partition_violations"]) for row in subset),
            "budget_compliance_rate": mean(float(row["forwards"] <= row["budget"]) for row in subset),
            "token_budget_compliance_rate": mean(float(row["tokens"] <= row["token_budget"]) for row in subset),
        })
    return output


def _paired_tests(
    rows: list[dict[str, Any]],
    wall: int,
    main_rho: float,
    default_n: int,
    methods: list[str],
) -> dict[str, Any]:
    index = {
        (
            row["phase"], row["seed"], row["W"], row["rho"],
            row["budget"], row["token_budget"], row["N"], row["method"],
        ): row
        for row in rows
    }
    p_values: dict[str, float] = {}
    tests = []
    competitors = sorted(method for method in methods if method != "D1_reversible_redundancy")
    for width in sorted({row["W"] for row in rows if row["phase"] == "main_width" and row["W"] > wall}):
        cap_pairs = sorted({
            (row["budget"], row["token_budget"])
            for row in rows
            if row["phase"] == "main_width" and row["W"] == width
        })
        for budget, token_budget in cap_pairs:
            for competitor in competitors:
                ours = []
                theirs = []
                for seed in sorted({row["seed"] for row in rows if row["phase"] == "main_width"}):
                    common = ("main_width", seed, width, main_rho, budget, token_budget, default_n)
                    left = index.get((*common, "D1_reversible_redundancy"))
                    right = index.get((*common, competitor))
                    if left is not None and right is not None:
                        ours.append(bool(left["solved"]))
                        theirs.append(bool(right["solved"]))
                if not ours:
                    continue
                key = f"W{width}_B{budget}_D1_vs_{competitor}"
                p_value = mcnemar_exact(ours, theirs)
                p_values[key] = p_value
                tests.append({
                    "key": key,
                    "W": width,
                    "budget": budget,
                    "token_budget": token_budget,
                    "competitor": competitor,
                    "n_pairs": len(ours),
                    "D1_only": sum(left and not right for left, right in zip(ours, theirs)),
                    "competitor_only": sum(right and not left for left, right in zip(ours, theirs)),
                    "D1_solve_rate": mean(map(float, ours)),
                    "competitor_solve_rate": mean(map(float, theirs)),
                    "solve_rate_difference": mean(map(float, ours)) - mean(map(float, theirs)),
                    "p_raw": p_value,
                })
    corrected = holm_bonferroni(p_values)
    for row in tests:
        row["p_holm"] = corrected[row["key"]]
        row["holm_significant_0_05"] = corrected[row["key"]] < 0.05
    max_pairs = max((row["n_pairs"] for row in tests), default=0)
    minimum_raw_p = 2.0 ** (1 - max_pairs) if max_pairs else 1.0
    best_case_first_holm_p = min(1.0, len(tests) * minimum_raw_p)
    return {
        "family_size": len(tests),
        "competitor_count": len(competitors),
        "max_pairs_per_test": max_pairs,
        "minimum_attainable_raw_p": minimum_raw_p,
        "best_case_first_holm_p": best_case_first_holm_p,
        "family_can_reject_at_0_05": best_case_first_holm_p < 0.05,
        "tests": tests,
    }


def _compute_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            row["phase"], row["seed"], row["W"], row["rho"],
            row["budget"], row["token_budget"], row["N"],
        )
        groups[key].append(row)
    comparable = [subset for subset in groups.values() if len(subset) > 1]
    forward_ratios = []
    token_ratios = []
    for subset in comparable:
        forwards = [int(row["forwards"]) for row in subset]
        tokens = [int(row["tokens"]) for row in subset]
        if min(forwards) > 0:
            forward_ratios.append(max(forwards) / min(forwards))
        if min(tokens) > 0:
            token_ratios.append(max(tokens) / min(tokens))
    return {
        "matching_rule": "identical_forward_and_token_caps_not_identical_realized_spend",
        "all_rows_within_forward_budget": all(row["forwards"] <= row["budget"] for row in rows),
        "all_rows_within_token_budget": all(row["tokens"] <= row["token_budget"] for row in rows),
        "all_rows_proxy_backend": all(row["evaluation_mode"] == "calibrated_symbolic_operator_proxy_v6" for row in rows),
        "token_accounting_present": all("tokens" in row and "token_budget" in row for row in rows),
        "cap_matched_comparison_groups": len(comparable),
        "exact_realized_forward_spend_matched": all(len({row["forwards"] for row in subset}) == 1 for subset in comparable),
        "exact_realized_token_spend_matched": all(len({row["tokens"] for row in subset}) == 1 for subset in comparable),
        "maximum_realized_forward_ratio": max(forward_ratios, default=1.0),
        "maximum_realized_token_ratio": max(token_ratios, default=1.0),
    }


def _frontier_audit(rows: list[dict[str, Any]], wall: int) -> dict[str, Any]:
    main_d1 = [
        row for row in rows
        if row["phase"] == "main_width" and row["method"] == "D1_reversible_redundancy"
    ]
    configured = [row for row in main_d1 if row["W"] > wall]
    actual = [row for row in configured if row["frontier_width_maintained"] > wall]
    return {
        "wall": int(wall),
        "configured_D1_rows_past_wall": len(configured),
        "actual_D1_rows_past_wall": len(actual),
        "actual_D1_past_wall_solved": sum(bool(row["solved"]) for row in actual),
        "maximum_main_D1_frontier": max((row["frontier_width_maintained"] for row in main_d1), default=0),
        "configured_width_is_not_treated_as_maintained_width": True,
        "main_actual_past_wall_observed": bool(actual),
    }


def _coupling_audit(manifest: list[dict[str, Any]]) -> dict[str, Any]:
    by_seed: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in manifest:
        by_seed[int(row["seed"])].append(row)
    errors = [abs(float(row["rho_actual"]) - float(row["rho_target"])) for row in manifest]
    within_rounding = [
        abs(float(row["rho_actual"]) - float(row["rho_target"])) <= 0.5 / max(int(row["n_edges"]), 1) + 1e-12
        for row in manifest
    ]
    return {
        "edge_count_matched_across_rho_per_seed": all(len({row["n_edges"] for row in subset}) == 1 for subset in by_seed.values()),
        "max_abs_rho_error": max(errors, default=0.0),
        "all_rhos_within_one_edge_rounding": all(within_rounding),
        "edge_counts_by_seed": {
            str(seed): sorted({int(row["n_edges"]) for row in subset})
            for seed, subset in sorted(by_seed.items())
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    methods = [item for item in args.methods.split(",") if item]
    unknown = set(methods) - METHODS
    if unknown:
        raise ValueError(f"unknown methods: {sorted(unknown)}")
    widths = _parse_ints(args.widths)
    rhos = _parse_floats(args.rhos)
    budgets = _parse_ints(args.budgets)
    token_budgets = (
        _parse_ints(args.token_budgets)
        if args.token_budgets
        else [int(budget) * int(args.tokens_per_forward) for budget in budgets]
    )
    if len(token_budgets) != len(budgets):
        raise ValueError("--token-budgets must have the same number of entries as --budgets")
    budget_pairs = list(zip(budgets, token_budgets))
    n_values = _parse_ints(args.n_values)
    seeds = list(range(args.seed, args.seed + args.instances))
    instance_cache = {}
    manifest = []
    for rho in sorted(set(rhos + [args.main_rho, args.n_rho])):
        for seed in seeds:
            instance = make_instance(args.n, args.k, args.partitions, rho, seed)
            instance_cache[(rho, seed)] = instance
            manifest.append({
                "instance_id": instance.instance_id,
                "seed": seed,
                "n": instance.n,
                "k": instance.k,
                "P": instance.P,
                "rho_target": rho,
                "rho_actual": instance.rho_actual,
                "n_edges": len(instance.edges),
            })
    rows = []
    # Main width sweep at fixed coupling.
    for width in widths:
        for budget, token_budget in budget_pairs:
            for seed in seeds:
                instance = with_frontier_width(instance_cache[(args.main_rho, seed)], width)
                for method in methods:
                    result = solve(
                        instance, method, budget, N=args.default_n, w=width,
                        seed=seed, token_budget=token_budget,
                    )
                    rows.append({"phase": "main_width", "seed": seed, "rho": args.main_rho, "W": width, **result})
    # Coupling mechanism sweep just past the wall.
    for rho in rhos:
        for budget, token_budget in budget_pairs:
            for seed in seeds:
                instance = with_frontier_width(instance_cache[(rho, seed)], args.mechanism_width)
                for method in methods:
                    result = solve(
                        instance, method, budget, N=args.default_n,
                        w=args.mechanism_width, seed=seed, token_budget=token_budget,
                    )
                    rows.append({"phase": "mechanism_rho", "seed": seed, "rho": rho, "W": args.mechanism_width, **result})
    # N-scaling for D1 versus self-consistency at high coupling.
    for n_value in n_values:
        for budget, token_budget in budget_pairs:
            for seed in seeds:
                instance = with_frontier_width(instance_cache[(args.n_rho, seed)], args.n_width)
                for method in ("D1_reversible_redundancy", "B1_self_consistency"):
                    result = solve(
                        instance, method, budget, N=n_value, w=args.n_width,
                        seed=seed, token_budget=token_budget,
                    )
                    rows.append({"phase": "n_scaling", "seed": seed, "rho": args.n_rho, "W": args.n_width, **result})
    summary_keys = ("method", "W", "rho", "budget", "token_budget", "N")
    main_summary = _summary([row for row in rows if row["phase"] == "main_width"], summary_keys)
    mechanism_summary = _summary([row for row in rows if row["phase"] == "mechanism_rho"], summary_keys)
    n_summary = _summary([row for row in rows if row["phase"] == "n_scaling"], summary_keys)
    paired = _paired_tests(rows, args.wall, args.main_rho, args.default_n, methods)
    d1_high = [row for row in mechanism_summary if row["method"] == "D1_reversible_redundancy" and row["rho"] == max(rhos)]
    b1_high = [row for row in mechanism_summary if row["method"] == "B1_self_consistency" and row["rho"] == max(rhos)]
    proxy_separation = any(
        ours["solve_rate"] > baseline["solve_rate"]
        for ours in d1_high
        for baseline in b1_high
        if (ours["budget"], ours["token_budget"]) == (baseline["budget"], baseline["token_budget"])
    )
    compute_audit = _compute_audit(rows)
    frontier_audit = _frontier_audit(rows, args.wall)
    coupling_audit = _coupling_audit(manifest)
    significant_wins = [
        row["key"] for row in paired["tests"]
        if row["holm_significant_0_05"] and row["solve_rate_difference"] > 0
    ]
    significant_losses = [
        row["key"] for row in paired["tests"]
        if row["holm_significant_0_05"] and row["solve_rate_difference"] < 0
    ]
    proxy_design_interpretable = all((
        compute_audit["all_rows_within_forward_budget"],
        compute_audit["all_rows_within_token_budget"],
        coupling_audit["edge_count_matched_across_rho_per_seed"],
        coupling_audit["all_rhos_within_one_edge_rounding"],
        frontier_audit["main_actual_past_wall_observed"],
        paired["family_can_reject_at_0_05"],
    ))
    headline_block_reasons = [
        "The operator backend is a calibrated symbolic proxy, not the frozen Qwen operator.",
        "Named external methods are behavioral proxy implementations, not canonical baseline code rerun on this instance set.",
    ]
    if not compute_audit["exact_realized_forward_spend_matched"] or not compute_audit["exact_realized_token_spend_matched"]:
        headline_block_reasons.append("Methods share forward/token caps but do not have identical realized spend.")
    if not frontier_audit["main_actual_past_wall_observed"]:
        headline_block_reasons.append("The main sweep did not actually maintain a frontier beyond the calibrated wall.")
    if not paired["family_can_reject_at_0_05"]:
        headline_block_reasons.append("The paired-instance count cannot attain Holm significance for the declared family size.")
    payload = {
        "schema": "downstream_dist_coloring_v6_proxy",
        "evaluation_mode": "calibrated_symbolic_operator_proxy_v6",
        "headline_eligible": False,
        "headline_block_reason": " ".join(headline_block_reasons),
        "headline_block_reasons": headline_block_reasons,
        "config": vars(args),
        "budget_pairs": [
            {"forward_budget": int(forward_budget), "token_budget": int(token_budget)}
            for forward_budget, token_budget in budget_pairs
        ],
        "instance_manifest": manifest,
        "rows": rows,
        "main_summary": main_summary,
        "mechanism_summary": mechanism_summary,
        "n_scaling_summary": n_summary,
        "paired_tests": paired,
        "compute_parity": compute_audit,
        "frontier_audit": frontier_audit,
        "coupling_audit": coupling_audit,
        "method_fidelity": {
            "canonical_external_baselines": False,
            "behavioral_proxy_methods": True,
            "real_frozen_qwen_operator": False,
        },
        "gates": {
            "proxy_D1_gt_B1_high_rho_some_budget": proxy_separation,
            "proxy_design_interpretable": proxy_design_interpretable,
            "shared_forward_and_token_cap_compliance": bool(
                compute_audit["all_rows_within_forward_budget"]
                and compute_audit["all_rows_within_token_budget"]
            ),
            "exact_realized_compute_match": bool(
                compute_audit["exact_realized_forward_spend_matched"]
                and compute_audit["exact_realized_token_spend_matched"]
            ),
            "rho_isolated_at_fixed_density": bool(
                coupling_audit["edge_count_matched_across_rho_per_seed"]
                and coupling_audit["all_rhos_within_one_edge_rounding"]
            ),
            "main_actual_past_wall_observed": frontier_audit["main_actual_past_wall_observed"],
            "holm_family_power_possible": paired["family_can_reject_at_0_05"],
            "holm_significant_D1_wins": significant_wins,
            "holm_significant_D1_losses": significant_losses,
            "formal_downstream_claim_pass": False,
        },
        "verdict": "PROXY_ONLY_NO_DOWNSTREAM_HEADLINE",
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run controlled SPEC v6 downstream proxy benchmark.")
    parser.add_argument("--out-dir", default="results/downstream")
    parser.add_argument("--n", type=int, default=24)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--partitions", type=int, default=4)
    parser.add_argument("--instances", type=int, default=8)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--widths", default="64,128,155,256,512")
    parser.add_argument("--rhos", default="0,0.1,0.25,0.5,0.75")
    parser.add_argument("--budgets", default="256,512")
    parser.add_argument("--token-budgets", default="")
    parser.add_argument("--tokens-per-forward", type=int, default=80)
    parser.add_argument("--main-rho", type=float, default=0.25)
    parser.add_argument("--mechanism-width", type=int, default=256)
    parser.add_argument("--n-rho", type=float, default=0.75)
    parser.add_argument("--n-width", type=int, default=256)
    parser.add_argument("--n-values", default="1,2,3,4,5,6,7,8")
    parser.add_argument("--default-n", type=int, default=4)
    parser.add_argument("--wall", type=int, default=155)
    parser.add_argument("--methods", default=",".join(sorted(METHODS)))
    args = parser.parse_args()
    payload = run(args)
    root = Path(args.out_dir)
    _write(root / "results.json", payload)
    _write(root / "summary.json", {key: value for key, value in payload.items() if key not in {"rows", "instance_manifest"}})
    _write(root / "instance_manifest.json", {"rows": payload["instance_manifest"]})


if __name__ == "__main__":
    main()
