# Community SAT Analysis Amendment v1

- Frozen date: 2026-07-12
- Timing: after structural manifest generation, before any independent arm outcome
- Parent contract: [Community SAT Tail-Risk Replication Contract](multiagent_community_sat_replication_contract_v1.md)
- Generator, instances, arms, resources, thresholds, and verdict families changed: **No**

This amendment resolves two phrases that were underspecified in the parent contract.

## F1 paired-win count

The `>=35/50 paired wins` condition uses **failure-penalized work on all 50 paired over-low instances**. The separate ratio condition continues to use raw work only among jointly solved pairs.

This prevents an early failed run with artificially small raw work from being counted as a frequent-case win.

## Strong-positive solve non-inferiority

For both `monolith_MR_sat` and `centralized_sharded_MR_sat`, strong-positive solve non-inferiority requires:

1. observed proposed-minus-control solve difference ≥ -0.10; and
2. one-sided 95% Clopper–Pearson upper bound on control-only discordance ≤0.10.

Strong-positive work requires paired failure-penalized proposed/control ratio bootstrap upper 95% bound ≤0.80 for both controls.

## Statistical constants

- bootstrap replicates: 100,000;
- bootstrap is paired for same-instance contrasts;
- alpha: 0.05;
- fixed bootstrap seeds are written in analysis output;
- no supporting p-value may rescue a failed frozen effect gate.
