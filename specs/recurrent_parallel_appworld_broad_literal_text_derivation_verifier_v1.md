# Recurrent Parallel AppWorld Broad Literal Text Derivation Verifier v1

## Status

`FROZEN_BEFORE_LITERAL_TEXT_DERIVATION_VERIFIER_OUTCOMES`

## Purpose

This verifier targets literal text fields after the occurrence baseline produced 52 unsafe unique-wrong cases. The rule is intentionally conservative: text is valid only if it is explicitly quoted in the task instruction.

## Rules

- Extract quoted literal spans from the task instruction.
- Normalize whitespace and compare exact string equality.
- Apply the same rule to live and adversarial candidates.
- Unquoted, composed, serialized, or file-content text fails closed in v1 unless it is exactly a quoted instruction literal.

## Safety Gate

The gate requires zero `unsafe_unique_wrong`. If it fails, preserve the unsafe result.

## Non-Claim

This is not a full text derivation proof. It only tests whether explicit instruction-literal binding can safely recover a subset of text writes.