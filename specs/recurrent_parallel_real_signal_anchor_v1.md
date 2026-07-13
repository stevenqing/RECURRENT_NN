# Frozen-Qwen Recurrent Correction Signal Anchor v1

- Frozen date: 2026-07-12
- Status: frozen before model outcomes
- Prerequisite: `RPD_COST_SENSITIVE_CROSS_SUBSTRATE_CONFIRMATION_PASS`
- Role: measure a real frozen-model correction signal and place it on the confirmed cost-sensitive phase law

## Model and prompt

- model: `Qwen/Qwen3.5-4B` at commit `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`, loaded from the existing local cache only;
- thinking mode: disabled;
- temperature: 0;
- dtype: bfloat16;
- batch size: 8;
- maximum formatted input tokens: 4,096 with no truncation;
- max output tokens: 64;
- JSON schema: `{"needs_correction": boolean, "confidence": number}`;
- confidence semantics: the model's probability that its emitted Boolean decision is correct;
- no oracle label, planted solution, candidate cost, or future trajectory information appears in prompts.

Execution uses exactly one approved physical GPU (2 or 3), exposed alone as `cuda:0`. The runner checks that the selected card has no compute process before importing/loading the model and fails closed otherwise.

The prompt exposes only one local agent's deployment-visible state:

- local assignment;
- bounded locally valid candidate alternatives;
- bounded local graph edges or SAT clauses;
- parent boundary message;
- cross-partition graph edges or SAT clauses;
- current recurrent round and diameter;
- fixed instruction to decide whether local state should change.

Ground-truth correction labels are stored in a separate hash-locked adjudication manifest. The model runner reads only the prompt manifest.

## Prompt manifest

Use already exposed independent cost-sensitive graph/SAT pools only for anchor development.

Target balanced prompt cells:

- substrates graph/SAT;
- diameters 2/4/8/16;
- truth live/dead correction labels;
- 16 prompts per cell;
- 256 prompts total.

States are harvested from perfect-signal recurrent trajectories. Selection is deterministic by prompt hash after deduplication, with at most one state per source instance in each substrate/diameter/truth cell.

## Metrics

- parse and schema-valid rate;
- false-positive rate $\eta_{fp}$ on live states;
- false-negative rate $\eta_{fn}$ on correction-required states;
- balanced accuracy;
- Brier score;
- expected calibration error with five fixed bins;
- prompt/output/total tokens;
- latency if endpoints provide timing.

## Gates

- A0 manifest: 256 unique prompts, 16/cell, no forbidden fields, prompt-only label replay, blinded label file, input-token cap, and deterministic hashes/replay.
- A1 generation: parse≥0.95, valid confidence≥0.95, no fallback.
- A2 signal quality: balanced accuracy≥0.70 and both eta_fp/eta_fn<0.40.
- A3 calibration: Brier below 0.25 and ECE≤0.15.
- A4 cost placement: empirical eta_fp is inserted into the frozen cost-sensitive objective without schedule retuning; empirical eta_fn is a feasibility gate because it was absent from the confirmed phase law; measured token, latency, and query costs are reported separately and do not silently change the objective's units.

## Verdicts

- all gates: `RPD_REAL_SIGNAL_ANCHOR_PASS`;
- manifest only with unavailable GPU: `RPD_REAL_SIGNAL_ANCHOR_READY_BLOCKED_GPU`;
- model quality fail: `RPD_REAL_SIGNAL_ANCHOR_MODEL_FAIL`;
- manifest/protocol fail: `RPD_REAL_SIGNAL_ANCHOR_PROTOCOL_FAIL`.

The anchor does not itself establish end-to-end LLM-agent improvement. A model-facing claim additionally requires running the frozen cost-sensitive policy with the real judge against symbolic/noisy controls.
