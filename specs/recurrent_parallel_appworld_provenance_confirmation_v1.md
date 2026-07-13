# AppWorld A5 — Deterministic Provenance Guard Confirmation v1

- Frozen date: 2026-07-12
- Status: frozen before dev semantic-mutation outcomes
- Development prerequisite: `RPD_APPWORLD_A4_DETERMINISTIC_PROVENANCE_GO`
- Confirmation split: previously unused multi-app dev task types
- Model/GPU: none

## Frozen method

Use the exact A4 mutation generator and provenance extractor without changes:

- one lowest-hash variation from each independent multi-app dev task type;
- at most 24 deterministic candidate mutations per task;
- retain only writes that succeed, whose unchanged official suffix completes, and whose final official evaluator fails;
- select one lowest-hash strict mutation per call site, then at most three lowest-hash sites per task type;
- pair each mutation with the original correct call;
- count candidate-specific field-compatible citations over the complete committed prefix;
- choose the candidate with more citations; ties abstain.

No prompt, LLM, evaluator output, future call, solution, or protected app content is used by the guard at decision time.

## Gates

- V0 integrity: A4 deterministic GO and all source/code locks pass; all official baseline traces pass.
- V1 yield: at least 10 strict pairs spanning at least five of seven dev task types.
- V2 coverage: non-abstaining coverage at least 0.50.
- V3 safety: zero incorrect non-abstaining choices.
- V4 evidence: covered accuracy at least 0.80 and exact one-sided binomial $p<0.05$ against chance 0.50.
- V5 scope: dev only, one variation per type, no test/model/GPU/Docker, protected details absent from exports.

All gates yield `RPD_APPWORLD_A5_PROVENANCE_CONFIRMATION_PASS`; otherwise `RPD_APPWORLD_A5_PROVENANCE_NO_GO`, or `RPD_APPWORLD_A5_PROTOCOL_FAIL` for V0/V5 failure.

A pass supports a selective provenance guard for pre-commit proposal verification. It does not establish end-to-end task-completion improvement; that requires integrating the guard into matched recurrent and monolithic agent runs.
