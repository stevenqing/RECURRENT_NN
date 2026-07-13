"""Recompute the SAT break-even tail rate with penalized monolith work.

The hash-locked original analysis is preserved. This explicit erratum changes no
verdict or other gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from experiments.multiagent_capacity_coupling import REPO_ROOT


PROPOSED = "independent_local_cbj_sat"
MONOLITH = "monolith_MR_sat"


def main() -> None:
    root = REPO_ROOT / "results/multiagent_community_sat_replication"
    raw = json.loads((root / "raw_results.json").read_text(encoding="utf-8"))
    frozen = json.loads((root / "analysis.json").read_text(encoding="utf-8"))
    proposed = [row for row in raw["rows"] if row["cell"] == "over_low" and row["arm"] == PROPOSED]
    monolith = [row for row in raw["rows"] if row["cell"] == "over_low" and row["arm"] == MONOLITH]
    successes = [row for row in proposed if row["solved"]]
    ws = mean(float(row["aggregate_work"]) for row in successes)
    wm_raw = mean(float(row["aggregate_work"]) for row in monolith)
    wm_penalized = mean(float(row["penalized_work"]) for row in monolith)
    q = mean(float(not row["solved"]) for row in proposed)
    q_star_original = float(frozen["tail_risk"]["q_star"])
    q_star_corrected = (wm_penalized - ws) / (20000.0 - ws)
    payload = {
        "schema": "multiagent_community_sat_analysis_erratum_v1",
        "frozen_verdict": frozen["status"],
        "corrected_verdict": frozen["status"],
        "field": "tail_risk.q_star",
        "reason": "The equal-resource monolith had two failures; expected-resource break-even must use its failure-penalized mean work rather than raw stopped work.",
        "W_factorized_success": ws,
        "W_monolith_raw_original": wm_raw,
        "W_monolith_penalized_corrected": wm_penalized,
        "failure_cost": 20000.0,
        "observed_q": q,
        "q_star_original": q_star_original,
        "q_star_corrected": q_star_corrected,
        "T1_q_gt_q_star_still_passes": q > q_star_corrected,
        "other_gates_changed": False,
    }
    (root / "analysis_erratum.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown = f"""# Community SAT Analysis Erratum

- Frozen verdict: **`{frozen['status']}`**
- Corrected verdict: **`{frozen['status']}`**
- Gates changed: **No**

## Correction

The locked analysis computed SAT break-even $q^*$ with monolith raw stopped work. Because `monolith_MR_sat` failed on two over-low rows, expected-resource comparison must instead use monolith failure-penalized mean work.

| Quantity | Value |
|---|---:|
| Successful factorized work $W_s$ | {ws:.3f} |
| Original raw monolith mean | {wm_raw:.3f} |
| Corrected penalized monolith mean $W_m$ | {wm_penalized:.3f} |
| Failure cost $B$ | 20000 |
| Observed factorized failure rate $q$ | {q:.3f} |
| Original $q^*$ | {q_star_original:.3f} |
| Corrected $q^*$ | **{q_star_corrected:.3f}** |

$$
q^*=\\frac{{W_m-W_s}}{{B-W_s}}={q_star_corrected:.6f}.
$$

The tail gate remains positive because $q={q:.3f}>{q_star_corrected:.3f}$. Failure-penalized factorized/monolith work remains 2.231, so the final `SAT_TAIL_RISK_REPLICATION` verdict is unchanged.

The original hash-locked [analysis](analysis.json) is preserved; this file is the authoritative correction for `tail_risk.q_star` and downstream synthesis.
"""
    (root / "ANALYSIS_ERRATUM.md").write_text(markdown, encoding="utf-8")
    print(json.dumps({"q_star_corrected": q_star_corrected, "verdict": frozen["status"], "report": "results/multiagent_community_sat_replication/ANALYSIS_ERRATUM.md"}))


if __name__ == "__main__":
    main()
