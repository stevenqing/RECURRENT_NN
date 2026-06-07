# Log Item Contract

Every completed workstream writes a new incremental item in `results/experiment_items/`. Numbering continues from `028` in the canonical `RECURRENT_NN` ledger.

An item is itself an acceptance artifact. If required fields are missing, the workstream is not done and validation must add a red check.

## Required Top-Level Fields

- `schema_version`: currently `log_item_contract_v1`
- `item_number`
- `name`
- `status`
- `purpose`: one paragraph naming the spec task and claim it bears on
- `code_added_used`
- `commands`: exact reproducible commands
- `artifacts`: paths
- `provenance`: devices, seeds, dataset version, depth-histogram reference, calibration/threshold file paths
- `result_tables`: workstream-specific tables; every numeric column needs provenance tags
- `honesty`: caveats plus `does_not_establish`
- `decision`: gate outcomes with numbers and next-step routing

## Global Rules

- Formula-derived values may never appear in an `observed` column.
- A PASS row must include the number that passed.
- Per-task or per-cell spread must not be hidden behind an aggregate verdict.
- Depth fields must not be derived from node caps or ordering-only proxies.
- No ledger may be generated from a non-canonical repo.

## P0 Required Tables

- `validation_registry_before_after`: total check count and restored checks/statuses.
- `ledger_reconciliation`: 025/026/027 folded, canonical repo declared, artifact de-duplication.
- `report_front_page`: evidence tiers lead, falsified scaffold gates moved to legacy archive, TTT diagnostic retained/relabeled.

## P1.1a Required Tables

- training-curve summary: initial loss, final loss, moved yes/no.
- single-step forced precision/recall by depth with n states.
- iterative stick-reason histogram: `no_commit`, `wrong_commit`, `criterion_never_met`.
- train-vs-eval encoding byte-diff identical yes/no.
- decision branch: objective-wiring, commit-criterion, or budget, with deciding numbers.

## P1.1b Required Tables

- per-seed G1/G2/G3, converged flag, steps/epochs, deep supervision, EMA, augmentation factor, schedule.
- single-step accuracy vs autonomous solve over training.
- red-line attestation: L1-L2 banded only, no TRM checkpoint, init hash.
- per-seed gate outcomes and shipped seed.

## P1.1c Required Tables

- per dataset depth bin: target n, achieved n, generation cost, achievable-frontier statement if short.
- L3 counts at depth 1 and 2.
- L3/L4 forward-only symbolic solve fraction, asserted zero.

## P1.2 Required Tables

- per arm depth-1 gate outcome with applied reverts and restore-decode accuracy.
- curriculum stage log.
- eval-path external-stack assertion trigger count, expected zero.

## P1.3 Required Tables

- gate table per cell: expected vs observed; kv_snapshot expected PASS.
- L4 separation table: arm x depth-bin solve_rate, applied_reverts, revert_success.
- Module-1 overlay: D -> predicted band read from calibration vs observed solve frontier.
- arbiter table for the 0.9025 cell.
- spill table and resource table.
- curriculum ablation row.
- preflight G1/G2/G3 echoed verbatim.

## P2 Required Tables

- model card table from HF snapshot.
- state hook round-trip result.
- capacity at real GDN dimensions.
- decay survival per level and fitted half-life.
- native-rule gap table.
- propagation per-task with Qwen3-4B delta and branch rollout row.
- echo of `verdicts.json` fields.

## P3 Required Tables

- TRM accuracy by minimal-DPLL-backtrack-depth bin, n per bin, grader version.
- framing line: defensive analysis; TRM is not a comparator and enters no comparison table.
- confirmation/refutation decision and collapse depth if any.
