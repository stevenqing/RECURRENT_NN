# EBW Track A Artifact Handoff

## Status: **`TRACK_A_FREEZE_READINESS_READY_NOT_TAGGED`**

This step implements the first Track A artifacts for LLM obligation-sketch synthesis, freezes value-free dev slice IDs, fills four few-shot example bodies, and records the prompt hash. It does not create `ebw-freeze-A` and does not open sealed variations 10-12.

## Completed

- Implemented strict Track A JSON parser for four obligation patterns.
- Implemented parser fail-closed behavior: no regex extraction, no schema repair, exact keys only.
- Implemented EBW typed-reason enum constants.
- Implemented unique-validity barrier helper.
- Implemented one-round repair payload helper that exposes only typed reason and failing element id.
- Added standard-library unit tests for parser and barrier behavior.
- Added Track A budget config.
- Added prompt template skeleton with few-shot slots.
- Frozen Track A dev slice IDs: 40 instances, 10 per obligation.
- Recorded one value-free few-shot example ID per obligation.
- Filled four few-shot examples from the frozen dev slice.
- Recorded prompt template hash: `6d1904dae3fc0b7b2273a754afcd6be2c89a754aaf1cddf5ddcef0e3806ea218`.
- Added executable runner/cap config for Track A.
- Audited GA-dev and GA-main asserts against the freeze spec.
- Audited baseline arms and call/token caps.
- Wrote execution lock for pre-tag freeze readiness.

## Validation

- `python -m json.tool config/ebw_track_a_budget_v1.json`: PASS
- `python -m py_compile experiments/ebw_obligation_sketch.py analysis/test_ebw_obligation_sketch.py`: PASS
- `python -m unittest -q analysis.test_ebw_obligation_sketch`: PASS, 5 tests
- VS Code errors: 0 for the new parser/test/config/template files

## New Artifacts

- Parser/barrier helper: `experiments/ebw_obligation_sketch.py`
- Tests: `analysis/test_ebw_obligation_sketch.py`
- Budget config: `config/ebw_track_a_budget_v1.json`
- Prompt template skeleton: `specs/recurrent_parallel_ebw_track_a_prompt_template_v1.md`
- Dev slice contract: `specs/recurrent_parallel_ebw_track_a_dev_slice_v1.json`
- Dev slice manifest: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_dev_slice_v1/dev_slice_manifest.json`
- Dev slice report: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_dev_slice_v1/DEV_SLICE.md`
- Prompt freeze builder: `analysis/ebw_track_a_prompt_freeze.py`
- Filled prompt template: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v1/track_a_prompt_template_filled.md`
- Prompt freeze report: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_freeze_v1/PROMPT_FREEZE.md`
- Runner config: `config/ebw_track_a_runner_v1.json`
- Freeze-readiness audit: `analysis/ebw_track_a_freeze_readiness.py`
- Freeze-readiness report: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_freeze_readiness_v1/FREEZE_READINESS.md`

## Not Yet Frozen

The following are still required before `ebw-freeze-A`:

- commit all freeze artifacts;
- create the git tag `ebw-freeze-A` only after artifacts are committed.

## Safety Boundary

No model was run. No sealed variation was opened. The filled prompt template contains opened dev-slice task context for four examples; sealed data remains untouched.