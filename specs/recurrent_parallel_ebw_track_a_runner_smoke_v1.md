# EBW Track A Runner Smoke v1

## Status

`FROZEN_SYNTHETIC_RUNNER_SMOKE_BEFORE_MODEL_OUTCOMES`

## Purpose

Test Track A parser, retry, barrier, repair attribution, dev-slice exclusion, and GA-main aggregation with synthetic model outputs. This smoke does not run a model and does not open sealed variations 10-12.

## Synthetic Coverage

- Unique valid live commit.
- Parse error fail-closed abstention.
- One retry producing `commit_after_repair`.
- Competing valid proofs -> no commit.
- No valid proof -> no commit.
- Synthetic wrong unique commit -> counted as `unsafe_unique_wrong` and GA-main fails.

## Expected Result

The smoke passes only if the synthetic unsafe case is counted as unsafe and GA-main is marked failed. This checks the safety accounting path before any model run.