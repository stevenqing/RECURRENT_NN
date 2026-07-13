# Recurrent Parallel AppWorld Broad Value-Bound Witness Preflight v1

## Status

`FROZEN_BEFORE_BROAD_VALUE_BOUND_WITNESS_OUTCOMES`

## Purpose

This protocol expands the locked schema-level witness sketches into opened broad-pool write-field instances. It prepares value-bound verifier development without exporting argument values, response values, or value hashes.

## Scope

- Input pool: `external_repos/appworld_generated_broad_schema_v1`
- Included schema-level sketches: 35
- Target write-field instances: 1266
- Tasks with target instances: 70
- Included proof families:
  - `state_transition_membership_proof`
  - `filesystem_path_derivation_proof`
  - `literal_text_derivation_proof`

## Instance Manifest Policy

Rows may include task id, generator id, variation, call index, method, app, API, field name, proof family, write ordinal, and pre-read counts. Rows must not include raw argument values, response values, protected task text, or value hashes.

## Expected Counts

| Proof family | Target instances |
|---|---:|
| `state_transition_membership_proof` | 595 |
| `filesystem_path_derivation_proof` | 547 |
| `literal_text_derivation_proof` | 124 |

Every target instance must have at least one pre-write read. Same-app pre-write reads are not required because some derivations are intentionally cross-app.

## Non-Claim

This is not a verifier result and not an action-correctness result. It only confirms that value-bound verifier development has a value-free instance manifest with pre-write read context.

## Verdicts

- Ready: `RPD_APPWORLD_BROAD_VALUE_BOUND_WITNESS_PREFLIGHT_READY`
- Blocked: `RPD_APPWORLD_BROAD_VALUE_BOUND_WITNESS_PREFLIGHT_BLOCKED`
- Protocol fail: `RPD_APPWORLD_BROAD_VALUE_BOUND_WITNESS_PROTOCOL_FAIL`