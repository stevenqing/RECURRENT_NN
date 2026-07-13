# AppWorld Typed Provenance — Reserved-Variation Development v1

- Frozen date: 2026-07-12
- Status: frozen before reserved-variation outcomes
- Split: train only
- Task types: the 10 multi-app train types

For each task type, exclude the variation used by A3 semantic-mutation development and choose the lowest-hash remaining variation. Execute the current validation solution under environment-native live tracing, recording runtime arguments/responses and a checkpoint before each state-mutating call.

Generate at most 12 deterministic mutations per task. Retain only successful writes whose complete live suffix executes and whose official evaluator fails. Select one lowest-hash mutation per call site and at most three sites per type.

Compare:

1. old citation-count guard from A4;
2. typed guard using only maximum evidence tier, deduplicated records, and abstention on equal tiers.

Typed evidence tiers are frozen as task-goal literal > joint record matching changed plus common anchor fields > direct changed-field occurrence. Repetition count cannot break ties.

Development GO requires at least 10 pairs over at least five types, typed coverage at least 0.50, typed covered accuracy at least 0.80, zero typed wrong choices, and no worse safety than the old guard. This is a reserved-variation development test, not independent task-type confirmation.
