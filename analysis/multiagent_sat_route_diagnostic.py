"""Post-hoc diagnostic for the failed SAT route-identifiability confirmation."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT


DEEPEST = "independent_local_cbj_sat"
RANDOM = "independent_local_random_valid_sat"
CENTRAL = "factorized_central_cbj_sat"
MONOLITH = "monolith_MR_sat"
FAILURE_CAP = 20000.0


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _mean(rows: list[dict[str, Any]], field: str) -> float | None:
    return mean(float(row[field]) for row in rows) if rows else None


def _fmt(value: float | None, digits: int = 3) -> str:
    return "NA" if value is None else f"{float(value):.{digits}f}"


def diagnose(raw: dict[str, Any], frozen: dict[str, Any]) -> dict[str, Any]:
    rows = list(raw["rows"])
    index = {(str(row["instance_id"]), str(row["arm"])): row for row in rows}
    ids = sorted({str(row["instance_id"]) for row in rows})
    pair_groups: dict[str, list[str]] = {
        "both_solve": [],
        "deepest_only": [],
        "random_only": [],
        "neither": [],
    }
    for instance_id in ids:
        deepest = bool(index[(instance_id, DEEPEST)]["solved"])
        random_valid = bool(index[(instance_id, RANDOM)]["solved"])
        key = (
            "both_solve" if deepest and random_valid
            else "deepest_only" if deepest
            else "random_only" if random_valid
            else "neither"
        )
        pair_groups[key].append(instance_id)

    both = pair_groups["both_solve"]
    deepest_both = [index[(instance_id, DEEPEST)] for instance_id in both]
    random_both = [index[(instance_id, RANDOM)] for instance_id in both]
    deepest_success = [index[(instance_id, DEEPEST)] for instance_id in ids if index[(instance_id, DEEPEST)]["solved"]]
    deepest_failure = [index[(instance_id, DEEPEST)] for instance_id in ids if not index[(instance_id, DEEPEST)]["solved"]]
    random_failure = [index[(instance_id, RANDOM)] for instance_id in ids if not index[(instance_id, RANDOM)]["solved"]]
    monolith = [index[(instance_id, MONOLITH)] for instance_id in ids]
    central_failure_ids = {
        instance_id for instance_id in ids if not index[(instance_id, CENTRAL)]["solved"]
    }
    deepest_failure_ids = {
        instance_id for instance_id in ids if not index[(instance_id, DEEPEST)]["solved"]
    }
    shared_failures = len(central_failure_ids & deepest_failure_ids)

    w_success = _mean(deepest_success, "aggregate_work") or FAILURE_CAP
    w_monolith = _mean(monolith, "penalized_work") or FAILURE_CAP
    q = len(deepest_failure) / len(ids)
    q_star = (
        (w_monolith - w_success) / (FAILURE_CAP - w_success)
        if w_success < w_monolith and w_success < FAILURE_CAP
        else None
    )
    both_ratio = (
        (_mean(deepest_both, "aggregate_work") or 0.0)
        / max(_mean(random_both, "aggregate_work") or 0.0, 1e-12)
    )
    prior = {
        "n": 50,
        "solve_difference": 0.18,
        "deepest_solve": 0.68,
        "random_solve": 0.50,
        "penalized_work_ratio": 0.6887509392887379,
    }
    current = {
        "n": 200,
        "solve_difference": float(frozen["primary_solve"]["solve_difference"]),
        "deepest_solve": float(frozen["primary_solve"]["left_solve_rate"]),
        "random_solve": float(frozen["primary_solve"]["right_solve_rate"]),
        "penalized_work_ratio": float(frozen["primary_penalized_work"]["ratio_of_means"]),
    }
    control_matching = {}
    for arm in (DEEPEST, RANDOM, CENTRAL):
        arm_rows = [index[(instance_id, arm)] for instance_id in ids]
        control_matching[arm] = {
            "mean_requests": _mean(arm_rows, "requests_sent"),
            "mean_nacks": _mean(arm_rows, "nacks"),
            "mean_window_rejections": _mean(arm_rows, "window_rejections"),
            "mean_activations": _mean(arm_rows, "activations"),
        }
    return {
        "schema": "multiagent_sat_route_confirmation_diagnostic_v1",
        "status": "POSTHOC_ROUTE_EFFECT_NONREPLICATION",
        "headline_eligible": False,
        "frozen_verdict_unchanged": frozen["status"],
        "pair_groups": {key: len(value) for key, value in pair_groups.items()},
        "jointly_solved": {
            "n": len(both),
            "deepest_mean_raw_work": _mean(deepest_both, "aggregate_work"),
            "random_mean_raw_work": _mean(random_both, "aggregate_work"),
            "deepest_over_random_raw_work_ratio": both_ratio,
            "deepest_work_wins": sum(
                float(left["aggregate_work"]) < float(right["aggregate_work"])
                for left, right in zip(deepest_both, random_both)
            ),
            "ties": sum(
                float(left["aggregate_work"]) == float(right["aggregate_work"])
                for left, right in zip(deepest_both, random_both)
            ),
        },
        "failure_mechanics": {
            "deepest_failure_count": len(deepest_failure),
            "deepest_failure_statuses": dict(Counter(str(row["status"]) for row in deepest_failure)),
            "deepest_failure_mean_raw_work": _mean(deepest_failure, "aggregate_work"),
            "random_failure_count": len(random_failure),
            "random_failure_statuses": dict(Counter(str(row["status"]) for row in random_failure)),
            "random_failure_mean_raw_work": _mean(random_failure, "aggregate_work"),
            "central_failure_count": len(central_failure_ids),
            "deepest_central_shared_failures": shared_failures,
            "shared_fraction_of_deepest_failures": shared_failures / max(len(deepest_failure_ids), 1),
        },
        "tail_boundary": {
            "W_success_deepest": w_success,
            "W_monolith_penalized": w_monolith,
            "failure_cap": FAILURE_CAP,
            "q": q,
            "q_star": q_star,
            "q_above_q_star": q_star is not None and q > q_star,
            "deepest_monolith_penalized_ratio": float(
                frozen["secondary_controls"]["deepest_vs_monolith_work"]["ratio_of_means"]
            ),
        },
        "effect_stability": {
            "exposed_prior_secondary": prior,
            "independent_confirmation": current,
            "solve_difference_shrinkage": current["solve_difference"] - prior["solve_difference"],
            "work_ratio_shift": current["penalized_work_ratio"] - prior["penalized_work_ratio"],
        },
        "control_matching": {
            "policy_metrics": control_matching,
            "candidate_filter_asymmetry": True,
            "detail": "The frozen random-valid policy prefilters targets by the owner window; frozen deepest attempts priority targets before window rejection/NACK rerouting.",
            "scope": "The no-go rejects the frozen operational deepest policy, not every deepest ranking over a matched window-valid candidate set.",
        },
        "interpretation": [
            "The prior SAT-high route signal did not survive a sole-primary independent study.",
            "Deepest routing trades fewer quick EXHAUSTED failures for expensive activation-cap failures; its expected-work advantage over random-valid is not identified.",
            "Near-complete failure overlap with same-order central factorization again localizes the tail to factorized search geometry rather than queued delivery.",
            "The tail-risk result strengthens, and Qwen remains unauthorized; a new matched-window symbolic control is required before interpreting pure target ranking.",
        ],
    }


def _render(payload: dict[str, Any]) -> str:
    pair = payload["pair_groups"]
    joint = payload["jointly_solved"]
    failure = payload["failure_mechanics"]
    tail = payload["tail_boundary"]
    stability = payload["effect_stability"]
    matching = payload["control_matching"]["policy_metrics"]
    return "\n".join([
        "# SAT Route Confirmation Diagnostic",
        "",
        "> Post-hoc mechanism diagnostic. It cannot change the frozen `SAT_ROUTE_CONFIRMATION_NO_GO` verdict.",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        "## Paired outcome decomposition",
        "",
        "| Outcome | Instances |",
        "|---|---:|",
        f"| Both solve | {pair['both_solve']} |",
        f"| Deepest only | {pair['deepest_only']} |",
        f"| Random-valid only | {pair['random_only']} |",
        f"| Neither solves | {pair['neither']} |",
        "",
        "The route policies disagree often, but the disagreements are nearly balanced. This is why the net solve difference is only 0.04 despite 86 discordant instances.",
        "",
        "## Conditional work",
        "",
        f"- Jointly solved instances: `{joint['n']}`.",
        f"- Deepest/random raw-work ratio: `{_fmt(joint['deepest_over_random_raw_work_ratio'])}`.",
        f"- Deepest raw-work wins/ties: `{joint['deepest_work_wins']}/{joint['ties']}`.",
        "",
        "## Failure geometry",
        "",
        f"- Deepest failures: `{failure['deepest_failure_count']}`; statuses `{json.dumps(failure['deepest_failure_statuses'], sort_keys=True)}`; mean stopped raw work `{_fmt(failure['deepest_failure_mean_raw_work'], 1)}`.",
        f"- Random-valid failures: `{failure['random_failure_count']}`; statuses `{json.dumps(failure['random_failure_statuses'], sort_keys=True)}`; mean stopped raw work `{_fmt(failure['random_failure_mean_raw_work'], 1)}`.",
        f"- Same-order central shared `{failure['deepest_central_shared_failures']}/{failure['deepest_failure_count']}` deepest failures (`{_fmt(failure['shared_fraction_of_deepest_failures'])}`).",
        "",
        "Deepest routing converts many quick search exhaustions into long activation-cap trajectories. That can improve solve on some instances but does not create a stable expected-work advantage.",
        "",
        "## Tail boundary on the new pool",
        "",
        f"- Successful deepest work $W_s$: `{_fmt(tail['W_success_deepest'], 1)}`.",
        f"- Penalized monolith work $W_m$: `{_fmt(tail['W_monolith_penalized'], 1)}`.",
        f"- Deepest failure rate $q$: `{_fmt(tail['q'])}`.",
        f"- Break-even $q^*$: `{_fmt(tail['q_star'])}`.",
        f"- Failure-penalized deepest/monolith ratio: `{_fmt(tail['deepest_monolith_penalized_ratio'])}`.",
        "",
        "## Effect stability",
        "",
        f"- Exposed 50-instance secondary solve difference: `{_fmt(stability['exposed_prior_secondary']['solve_difference'])}`; independent 200-instance difference: `{_fmt(stability['independent_confirmation']['solve_difference'])}`.",
        f"- Exposed penalized-work ratio: `{_fmt(stability['exposed_prior_secondary']['penalized_work_ratio'])}`; independent ratio: `{_fmt(stability['independent_confirmation']['penalized_work_ratio'])}`.",
        "",
        "## Control-matching audit",
        "",
        "| Frozen policy | Mean requests | Mean NACKs | Mean window rejections | Mean activations |",
        "|---|---:|---:|---:|---:|",
        f"| Deepest | {_fmt(matching[DEEPEST]['mean_requests'], 1)} | {_fmt(matching[DEEPEST]['mean_nacks'], 1)} | {_fmt(matching[DEEPEST]['mean_window_rejections'], 1)} | {_fmt(matching[DEEPEST]['mean_activations'], 1)} |",
        f"| Random-valid | {_fmt(matching[RANDOM]['mean_requests'], 1)} | {_fmt(matching[RANDOM]['mean_nacks'], 1)} | {_fmt(matching[RANDOM]['mean_window_rejections'], 1)} | {_fmt(matching[RANDOM]['mean_activations'], 1)} |",
        f"| Central deepest | {_fmt(matching[CENTRAL]['mean_requests'], 1)} | {_fmt(matching[CENTRAL]['mean_nacks'], 1)} | {_fmt(matching[CENTRAL]['mean_window_rejections'], 1)} | {_fmt(matching[CENTRAL]['mean_activations'], 1)} |",
        "",
        "The frozen random-valid arm filters targets to the current owner window before selection, while frozen deepest may request an out-of-window priority target and receive a NACK. The no-go therefore applies to these complete operational policies. It does not isolate deepest-versus-random ranking over an identical candidate set.",
        "",
        "## Research decision",
        "",
        "Do not launch Qwen target routing from this premise. First test a symbolic `deepest-window-valid` control that differs from random-valid only in target ranking. This is a new development mechanism and requires another untouched confirmation before any model use.",
        "",
        "## Artifacts",
        "",
        "- [Frozen route result](RESULTS.md)",
        "- [Diagnostic JSON](diagnostic.json)",
        "- [Cross-substrate tail-risk synthesis](../multiagent_cross_substrate_tail_risk/SUMMARY.md)",
        "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose failed SAT route confirmation.")
    parser.add_argument("--raw", type=Path, default=Path("results/multiagent_sat_route_confirmation/raw_results.json"))
    parser.add_argument("--analysis", type=Path, default=Path("results/multiagent_sat_route_confirmation/analysis.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_sat_route_confirmation"))
    args = parser.parse_args()
    raw = json.loads(_resolve(args.raw).read_text(encoding="utf-8"))
    frozen = json.loads(_resolve(args.analysis).read_text(encoding="utf-8"))
    if frozen.get("status") != "SAT_ROUTE_CONFIRMATION_NO_GO":
        raise ValueError("diagnostic expects the frozen route-confirmation no-go result")
    payload = diagnose(raw, frozen)
    output_dir = _resolve(args.output_dir)
    (output_dir / "diagnostic.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "DIAGNOSTIC.md").write_text(_render(payload), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "report": str((output_dir / "DIAGNOSTIC.md").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
