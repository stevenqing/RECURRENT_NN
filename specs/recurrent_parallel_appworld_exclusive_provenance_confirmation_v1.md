# AppWorld Exclusive Causal Provenance — Held-Out Confirmation v1

- Frozen date: 2026-07-12
- Status: frozen before confirmation outcomes
- Confirmation split: generated variations 7–9
- Development split: generated variations 4–6, already closed

Primary rule: commit a candidate iff it alone has nonzero typed causal provenance. Abstain when both or neither candidate has support. Tier magnitude cannot resolve competing lineages.

Execute all 24 hash-locked confirmation tasks from the eight complete AppWorld 0.2 generators. For each task, run the compiled validation solution under live tracing, produce at most four deterministic mutations per write and 12 per task, retain only strict evaluator-flipping counterfactuals, choose one mutation per call site, and cap at three pairs per task. Pair ordering and A/B parity remain identical to development.

Reference guards are old citation count and typed max-tier; they cannot alter the primary decision.

Confirmation PASS requires:

1. all 24 validation solutions/evaluators pass;
2. at least 20 strict pairs from at least 12 tasks and six generators;
3. exclusive-provenance coverage at least 0.50;
4. zero wrong exclusive commits;
5. no more wrong commits than typed max-tier;
6. exact immutable/task hashes and confirmation-only execution;
7. no protected trace export, model, GPU, Docker, or external-process action.

Run with Python bytecode writes disabled so imports cannot alter raw task hashes. Outputs contain identifiers, hashes, counts, tiers, choices, and aggregate metrics only.

This is held-out instance confirmation within the same eight generator families, not independent task-type confirmation and not a headline end-to-end agent result.
