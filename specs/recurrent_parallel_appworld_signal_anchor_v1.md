# AppWorld A3 — Semantic Write-Signal Anchor v1

- Frozen date: 2026-07-12
- Status: frozen before prompt generation and model outcomes
- Prerequisite: `RPD_APPWORLD_A2_CONTROLLER_PASS`
- Source: train-only semantic-mutation development; dev/test untouched

## Label object

The A3 judge verifies a proposed state-mutating API call before barrier commit. It does not judge whether a post-hoc state is globally unrecoverable.

For an official train trace and write call $a$ at prefix state $s$, construct deterministic argument mutations $\tilde a$. A strict correction pair is retained only when:

1. the original full trace passes the official evaluator;
2. $\tilde a$ itself executes successfully;
3. the unchanged official suffix after $\tilde a$ executes completely;
4. the final official evaluator fails.

The original proposal is labeled live (`needs_correction=false`); the successful-but-harmful mutation is labeled dead (`needs_correction=true`). API-level failures and mutations whose suffix still passes are excluded.

This establishes harmfulness under a frozen continuation, not impossibility under every future repair policy.

## Frozen selection

- one development variation per independent multi-app train task type, already measured before this lock;
- one strict dead mutation per `(task_type, call_index)`, lowest mutation hash;
- at most three call sites per task type, lowest pair hash;
- expected 15 pairs / 30 prompts / 7 task types;
- live and dead members share identical instruction, prefix history, API schema, and pair ID; only candidate arguments differ.

## Deployment-visible prompt

- train task instruction;
- candidate app and API name;
- public API purpose and parameter schema;
- redacted candidate arguments;
- at most four immediately preceding committed calls;
- compact redacted API responses from those calls;
- exact JSON response schema: `{"needs_correction": boolean, "confidence": number}`;
- confidence means probability that the emitted Boolean decision is correct.

The prompt excludes mutation type, altered field identity, original/dead pairing, official future calls, suffix outcome, evaluator result, solution code, ground-truth metadata, passwords, access tokens, payment-card data, and labels.

## Model

- `Qwen/Qwen3.5-4B`;
- revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`;
- local files only;
- thinking disabled;
- bfloat16, temperature zero, batch size 8;
- maximum input 4,096 tokens and output 64 tokens;
- strict JSON, no repair fallback.

## Gates

- S0 source: A2 pass and frozen development result hashes.
- S1 labels: exactly 15 balanced pairs across 7 task types; every dead action and full suffix succeeds, then evaluator fails.
- S2 visibility: pair context matches except candidate arguments; forbidden content and secrets absent; labels stored separately.
- S3 prompt: 30 unique prompts, deterministic replay, pinned tokenizer, no truncation.
- S4 model: parse rate at least 0.95; pooled balanced accuracy at least 0.70; both false-positive and false-negative rates below 0.40.
- S5 scope: statistics cluster by task type and report pair-level outcomes; no end-to-end completion claim.

Manifest-only status is `RPD_APPWORLD_A3_SIGNAL_READY_BLOCKED_GPU`. A model pass is `RPD_APPWORLD_A3_SIGNAL_PASS`; quality failure is `RPD_APPWORLD_A3_SIGNAL_MODEL_FAIL`; integrity failure is `RPD_APPWORLD_A3_SIGNAL_PROTOCOL_FAIL`.
