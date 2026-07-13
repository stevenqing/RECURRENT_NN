# Broad Literal Text Derivation Verifier Handoff

## Status: **`RPD_APPWORLD_BROAD_LITERAL_TEXT_DERIVATION_VERIFIER_SAFE`**

This step implements a conservative value-bound verifier for literal text fields. It accepts only exact quoted literals from the task instruction after whitespace normalization, and otherwise fails closed.

## Completed

- Froze the literal text derivation verifier contract before outcomes.
- Evaluated all 124 literal-text instances from the opened broad pool.
- Used live AppWorld traces internally.
- Required exact match to quoted instruction literals.
- Reduced literal-text unsafe unique-wrong from the occurrence baseline's 52 cases to 0.
- Recovered 46 `commit_live` decisions.
- Exported no instruction text, argument values, response values, or value hashes.
- Preserved sealed fresh variations 10-12.
- Used no model, GPU, Docker, or external-process intervention.

## Result

| Decision | Count |
|---|---:|
| `commit_live` | 46 |
| `ambiguous_both_valid` | 0 |
| `abstain_no_valid` | 78 |
| `unsafe_unique_wrong` | 0 |

## Schema Decisions

| Schema | Commit-live | Abstain | Unsafe |
|---|---:|---:|---:|
| `phone.send_text_message.message` | 6 | 2 | 0 |
| `spotify.create_playlist.title` | 4 | 0 | 0 |
| `venmo.create_payment_request.description` | 13 | 0 | 0 |
| `venmo.create_transaction.description` | 2 | 7 | 0 |
| `venmo.create_transaction_comment.comment` | 21 | 0 | 0 |
| `simple_note.update_note.content` | 0 | 2 | 0 |
| `file_system.create_file.content` | 0 | 67 | 0 |

## Interpretation

The occurrence baseline was unsafe because arbitrary text in pre-write reads could validate a wrong candidate. Requiring exact quoted instruction literals is conservative but safe: it recovers explicit user-provided notes/messages/comments/titles while failing closed on composed text and file content.

This is a second positive value-bound derivation verifier: it recovers commits while preserving the zero-unsafe safety gate.

## Key Artifacts

- Contract: `specs/recurrent_parallel_appworld_broad_literal_text_derivation_verifier_v1.json`
- Spec: `specs/recurrent_parallel_appworld_broad_literal_text_derivation_verifier_v1.md`
- Runner: `analysis/appworld_broad_literal_text_derivation_verifier.py`
- Report: `results/recurrent_parallel_appworld_broad_literal_text_derivation_verifier_v1/REPORT.md`
- Results: `results/recurrent_parallel_appworld_broad_literal_text_derivation_verifier_v1/results.json`
- Value-free rows: `results/recurrent_parallel_appworld_broad_literal_text_derivation_verifier_v1/rows.json`

## Next Route

Combine the current safe path and literal verifiers into a broad safe ledger, while leaving state-transition membership fail-closed until effect/cursor semantics are implemented.