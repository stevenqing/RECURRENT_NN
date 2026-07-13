# EBW Track A Dev Slice v1

## Status

`FROZEN_DEV_SLICE_IDS_BEFORE_TRACK_A_TAG`

## Purpose

Freeze value-free dev slice IDs for Track A prompt examples and GA-dev checks. The dev slice is excluded from all opened-pool reported numbers.

## Selection Rule

For each Track A obligation, sort eligible opened-pool ledger v5 rows by `instance_id` and take the first 10.

| Obligation | Eligibility |
|---|---|
| `derived_path_binding` | filesystem path proof family, `commit_live` |
| `literal_intent_binding` | literal text proof family, `commit_live` |
| `prior_effect_binding` | created-playlist ledger source, `commit_live` |
| `ordered_role_binding` | like-song ledger source, `commit_live` |

The first selected row per obligation is the few-shot example ID.

## Output Boundary

The manifest may include instance IDs, task IDs, schema metadata, obligation labels, and ledger source. It must not include task text, argument values, response values, or value hashes.