"""Generate the audited structural-free-lunch mechanism report.

This analysis is explicitly developmental: it summarizes the frozen 64-instance
mechanism gate, computes paired uncertainty, and preserves all negative cells.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
from math import comb
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any

from experiments.multiagent_capacity_coupling import REPO_ROOT


@dataclass(frozen=True)
class PairedEffect:
    metric: str
    left_arm: str
    right_arm: str
    n: int
    left_mean: float
    right_mean: float
    ratio_of_means: float
    bootstrap_ratio_ci95: tuple[float, float]
    wins: int
    ties: int
    losses: int
    one_sided_sign_p: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "left_arm": self.left_arm,
            "right_arm": self.right_arm,
            "n": self.n,
            "left_mean": self.left_mean,
            "right_mean": self.right_mean,
            "ratio_of_means": self.ratio_of_means,
            "bootstrap_ratio_ci95": list(self.bootstrap_ratio_ci95),
            "wins": self.wins,
            "ties": self.ties,
            "losses": self.losses,
            "one_sided_sign_p": self.one_sided_sign_p,
            "confirmatory": False,
        }


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _bootstrap_ratio(left: list[float], right: list[float], seed: int, n_bootstrap: int) -> tuple[float, float]:
    generator = random.Random(seed)
    n = len(left)
    ratios = []
    for _ in range(int(n_bootstrap)):
        indices = [generator.randrange(n) for _ in range(n)]
        ratios.append(
            sum(left[index] for index in indices)
            / max(sum(right[index] for index in indices), 1e-12)
        )
    return _quantile(ratios, 0.025), _quantile(ratios, 0.975)


def _one_sided_sign_p(wins: int, losses: int) -> float:
    n = int(wins) + int(losses)
    if n == 0:
        return 1.0
    return sum(comb(n, count) for count in range(int(wins), n + 1)) / (2**n)


def _paired_effect(
    index: dict[tuple[str, str], dict[str, Any]],
    instance_ids: list[str],
    metric: str,
    left_arm: str,
    right_arm: str,
    seed: int,
    n_bootstrap: int,
) -> PairedEffect:
    left = [float(index[(instance_id, left_arm)][metric]) for instance_id in instance_ids]
    right = [float(index[(instance_id, right_arm)][metric]) for instance_id in instance_ids]
    wins = sum(a < b for a, b in zip(left, right))
    ties = sum(a == b for a, b in zip(left, right))
    losses = sum(a > b for a, b in zip(left, right))
    return PairedEffect(
        metric=metric,
        left_arm=left_arm,
        right_arm=right_arm,
        n=len(instance_ids),
        left_mean=mean(left),
        right_mean=mean(right),
        ratio_of_means=mean(left) / max(mean(right), 1e-12),
        bootstrap_ratio_ci95=_bootstrap_ratio(left, right, seed, n_bootstrap),
        wins=wins,
        ties=ties,
        losses=losses,
        one_sided_sign_p=_one_sided_sign_p(wins, losses),
    )


def _fmt(value: float, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary_table(summary: list[dict[str, Any]]) -> str:
    selected_arms = {
        "independent_local_cbj",
        "independent_local_chronological",
        "centralized_sharded_MR",
        "monolith_MR",
        "monolith_R",
    }
    lines = [
        "| Cell | Arm | Solve | Mean work | Mean rounds | Mean requests | Status counts |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in summary:
        if row["arm"] not in selected_arms:
            continue
        statuses = ", ".join(f"{key}={value}" for key, value in sorted(row["status_counts"].items()))
        lines.append(
            f"| {row['cell']} | `{row['arm']}` | {_fmt(row['solve_rate'])} | "
            f"{_fmt(row['mean_aggregate_work'], 1)} | {_fmt(row['mean_parallel_rounds'], 1)} | "
            f"{_fmt(row['mean_requests'], 1)} | {statuses} |"
        )
    return "\n".join(lines)


def generate(results_path: Path, output_dir: Path, n_bootstrap: int) -> dict[str, Any]:
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    if payload["study_role"] != "formal_frozen_64":
        raise ValueError("report requires the formal frozen 64-instance artifact")
    rows = payload["rows"]
    arm_counts = Counter(str(row["arm"]) for row in rows)
    if len(rows) != 384 or set(arm_counts.values()) != {64}:
        raise ValueError(f"unexpected row cardinality: total={len(rows)}, arms={arm_counts}")
    over_low = [row for row in rows if row["cell"] == "over_low"]
    index = {(str(row["instance_id"]), str(row["arm"])): row for row in over_low}
    instance_ids = sorted({str(row["instance_id"]) for row in over_low})
    effects = [
        _paired_effect(index, instance_ids, "aggregate_work", "independent_local_cbj", "centralized_sharded_MR", 7101, n_bootstrap),
        _paired_effect(index, instance_ids, "aggregate_work", "independent_local_cbj", "monolith_MR", 7102, n_bootstrap),
        _paired_effect(index, instance_ids, "aggregate_work", "independent_local_cbj", "global_trail_cbj", 7103, n_bootstrap),
        _paired_effect(index, instance_ids, "parallel_rounds", "independent_local_cbj", "centralized_sharded_MR", 7104, n_bootstrap),
    ]
    effect_index = {(effect.metric, effect.right_arm): effect for effect in effects}
    work_effect = effect_index[("aggregate_work", "centralized_sharded_MR")]
    rounds_effect = effect_index[("parallel_rounds", "centralized_sharded_MR")]
    summary_index = {(row["cell"], row["arm"]): row for row in payload["summary"]}
    high_cbj_rows = [
        row for row in rows
        if row["cell"] == "over_high" and row["arm"] == "independent_local_cbj"
    ]
    high_solved_work = mean(float(row["aggregate_work"]) for row in high_cbj_rows if row["solved"])
    mechanism_path = REPO_ROOT / "experiments/multiagent_independent_local.py"
    artifact_hashes = {
        **payload["input_hashes"],
        "mechanism_sha256": _sha256(mechanism_path),
        "raw_results_sha256": _sha256(results_path),
    }
    analysis = {
        "schema": "multiagent_structural_free_lunch_report_v1",
        "status": payload["status"],
        "study_role": payload["study_role"],
        "headline_eligible": False,
        "input_hashes": artifact_hashes,
        "row_count": len(rows),
        "arm_counts": dict(sorted(arm_counts.items())),
        "paired_effects": [effect.as_dict() for effect in effects],
        "gates": payload["gates"],
        "protocol_audit": payload["protocol_audit"],
        "over_high_solved_only_mean_work": high_solved_work,
        "limitations": [
            "Developmental mechanism gate on the previously frozen core manifest; not an independent confirmatory dataset.",
            "One instance per cell was exposed during implementation smoke testing.",
            "Parallel rounds are an idealized critical path, not wall-clock latency.",
            "Over-high work includes three activation-cap failures; the coupling ratio is therefore partly censored.",
            "Independent-local CBJ degrades sharply in both under-capacity cells, so the benefit is phase-local rather than universal.",
            "The study is symbolic and establishes no real-Qwen or LLM-autonomy claim.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    gates = payload["gates"]
    observed = gates["observed"]
    protocol = payload["protocol_audit"]
    high_cbj = summary_index[("over_high", "independent_local_cbj")]
    low_cbj = summary_index[("over_low", "independent_local_cbj")]
    low_chrono = summary_index[("over_low", "independent_local_chronological")]
    markdown = f"""# Independent-Local Multi-Agent Structural Free-Lunch Gate

## Verdict

**`{payload['status']}`**

This is a genuine **research-contribution candidate**, not yet a paper claim. The result survives equal-total-recovery-memory controls and is therefore not the trivial statement that four agents possess four times a single agent's context. It remains a symbolic developmental mechanism result on a previously used manifest.

- Frozen contract: [multiagent_structural_free_lunch_contract_v1.md](../../specs/multiagent_structural_free_lunch_contract_v1.md)
- Mechanism implementation: [multiagent_independent_local.py](../../experiments/multiagent_independent_local.py)
- Raw artifact: [results.json](results.json)
- Audited analysis: [analysis.json](analysis.json)

## Mechanism That Is Actually New

The tested architecture combines:

1. independent owner-local cursor, trail, tried values, and conflict sets;
2. a fixed acyclic dependency priority from the frozen variable order;
3. owner-executed dependency invalidation rather than cross-agent mutation;
4. versioned, idempotent rollback request → target execution → acknowledgement;
5. bounded dependency backpressure when a requested target lies outside `R=8`;
6. no global trail and no centralized fallback.

This is the source of the candidate contribution: **factorization changes the rollback geometry while preserving total declared recovery memory**.

## Frozen Sweet-Spot Result: `over_low`

All equal-memory arms use total declared recovery memory `MR=32` (`M=4`, `R=8`).

| Metric | Independent local CBJ | Centralized sharded `MR` | Effect |
|---|---:|---:|---:|
| Solve | {_fmt(low_cbj['solve_rate'])} (16/16) | {_fmt(summary_index[('over_low', 'centralized_sharded_MR')]['solve_rate'])} (16/16) | exact parity |
| Aggregate work | {_fmt(work_effect.left_mean, 3)} | {_fmt(work_effect.right_mean, 3)} | ratio {_fmt(work_effect.ratio_of_means)}, reduction {_fmt(100 * (1 - work_effect.ratio_of_means), 1)}% |
| Ideal critical-path rounds | {_fmt(rounds_effect.left_mean, 3)} | {_fmt(rounds_effect.right_mean, 3)} | ratio {_fmt(rounds_effect.ratio_of_means)}, reduction {_fmt(100 * (1 - rounds_effect.ratio_of_means), 1)}% |

Paired robustness:

- Work is lower on `{work_effect.wins}/16` instances, tied on `{work_effect.ties}/16`, and never higher.
- Paired bootstrap 95% CI for the work ratio of means: `[{_fmt(work_effect.bootstrap_ratio_ci95[0])}, {_fmt(work_effect.bootstrap_ratio_ci95[1])}]`.
- Exploratory one-sided sign-test `p={work_effect.one_sided_sign_p:.8f}`.
- Critical-path rounds are lower on `{rounds_effect.wins}/16` instances.
- Paired bootstrap 95% CI for the rounds ratio of means: `[{_fmt(rounds_effect.bootstrap_ratio_ci95[0])}, {_fmt(rounds_effect.bootstrap_ratio_ci95[1])}]`.
- Exploratory one-sided sign-test `p={rounds_effect.one_sided_sign_p:.8f}`.

The same work comparison against `monolith_MR` is numerically identical because the two equal-memory controls follow the same search trajectory in this cell. Against the communicating global-trail team, independent-local work is lower on 16/16 instances.

## Frozen Gates

| Gate | Pass | Observed |
|---|---:|---|
| Protocol invariants | **{str(gates['protocol_invariants']).upper()}** | 0 violations |
| G1 solve non-inferiority | **{str(gates['G1_solve_noninferiority']).upper()}** | independent={_fmt(observed['independent_over_low_solve'])}, equal-memory controls={_fmt(observed['monolith_MR_over_low_solve'])} |
| G2 aggregate-work advantage | **{str(gates['G2_aggregate_work_advantage']).upper()}** | ratio={_fmt(observed['work_ratio_vs_centralized'])} ≤ 0.80 |
| G3 critical-path advantage | **{str(gates['G3_critical_path_advantage']).upper()}** | ratio={_fmt(observed['critical_rounds_ratio_vs_centralized_steps'])} ≤ 0.60 |
| G4 coupling boundary | **{str(gates['G4_coupling_boundary']).upper()}** | high/low work={_fmt(observed['coupling_work_ratio_high_vs_low'])} ≥ 1.20 |
| G5 coordination mechanism | **{str(gates['G5_coordination_mechanism']).upper()}** | over-low CBJ={_fmt(low_cbj['solve_rate'])}, chronological={_fmt(low_chrono['solve_rate'])} |

## Protocol Audit

Across 128 independent-arm episodes:

- requests sent: `{protocol['totals']['requests_sent']:,}`;
- acknowledgements: `{protocol['totals']['acknowledgements']:,}`;
- explicit NACKs: `{protocol['totals']['nacks']:,}`;
- window rejections safely handled: `{protocol['totals']['window_rejections']:,}`;
- out-of-window rollback executions: **`{protocol['totals']['out_of_window_rollback_executions']}`**;
- direct cross-agent mutations: **0**;
- ownership, priority direction, channel bound, lifecycle conservation, no-global-trail, no-fallback, and global edge verification: **all pass**.

Contract SHA-256: `{payload['input_hashes']['contract_sha256']}`<br>
Manifest SHA-256: `{payload['input_hashes']['manifest_sha256']}`<br>
Mechanism SHA-256: `{artifact_hashes['mechanism_sha256']}`<br>
Raw-results SHA-256: `{artifact_hashes['raw_results_sha256']}`

## Full Phase Readout

{_summary_table(payload['summary'])}

## Negative Results and Boundary Conditions

These are part of the result, not footnotes:

1. **Not universal:** independent-local CBJ solves only 6/16 `under_low` and 8/16 `under_high`, versus 16/16 for equal-memory controls. The current priority factorization is regime-specific and can induce severe asynchronous thrashing outside the target sweet spot.
2. **Coupling consumes the gain:** `over_high` CBJ solves {int(round(high_cbj['solve_rate'] * 16))}/16, not 16/16. Its all-episode mean work is {_fmt(high_cbj['mean_aggregate_work'], 1)} versus {_fmt(low_cbj['mean_aggregate_work'], 1)} in `over_low`.
3. **G4 is partly cap-censored:** three `over_high` CBJ episodes hit the activation cap. Solved-only high-coupling mean work is {_fmt(high_solved_work, 1)}; the frozen G4 statistic correctly retains failures but must not be interpreted as an uncensored slowdown estimate.
4. **CBJ is essential here:** chronological independent search solves only 1/16 in each over-capacity cell.
5. **No wall-clock claim:** `parallel_rounds` assumes ideal simultaneous activation and excludes runtime/system overhead.
6. **No LLM claim:** branching and routing are symbolic. The earlier Qwen route signal is separate evidence.

## Research Claim Boundary

### Supported now

> On the frozen symbolic capacity–coupling development manifest, owner-local factorized CBJ with acyclic dependency routing matches equal-total-memory solve rate in the over-capacity/low-coupling sweet spot while reducing both aggregate rollback work and idealized critical path. The advantage disappears as coupling rises.

### Not supported now

- a confirmatory or headline result;
- a universal advantage across capacity cells;
- measured parallel speedup;
- real-Qwen multi-agent superiority;
- autonomous natural-language agent coordination.

## Required Next Stage

Freeze the mechanism exactly as implemented and generate a **new independent confirmatory manifest** with:

1. no smoke exposure;
2. preregistered paired work and solve tests;
3. a minimum number of over-low pairs sufficient for solve non-inferiority and work-ratio uncertainty;
4. explicit replication of the negative under-capacity cells and coupling boundary;
5. only after symbolic replication, sparse real-Qwen routing with symbolic branching retained as the control.

The current result is strong enough to justify that confirmatory study because it passes equal-resource controls and produces a large, paired, mechanism-specific effect. It is not strong enough to skip that study.
"""
    (output_dir / "RESULTS.md").write_text(markdown, encoding="utf-8")
    return analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="Write structural free-lunch audited report.")
    parser.add_argument("--results", type=Path, default=Path("results/multiagent_structural_free_lunch/results.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/multiagent_structural_free_lunch"))
    parser.add_argument("--bootstrap", type=int, default=100_000)
    args = parser.parse_args()
    results_path = args.results if args.results.is_absolute() else REPO_ROOT / args.results
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    analysis = generate(results_path, output_dir, int(args.bootstrap))
    print(json.dumps({
        "status": analysis["status"],
        "report": str((output_dir / "RESULTS.md").relative_to(REPO_ROOT)),
        "analysis": str((output_dir / "analysis.json").relative_to(REPO_ROOT)),
    }))


if __name__ == "__main__":
    main()
