# W3 Qwen3.5 Probe Spec

Canonical checkpoint: `Qwen/Qwen3.5-4B`.

Local download record:

```text
results/model_download/qwen3_5_4b/qwen_download.json
```

## Purpose

Decide the S3.1 integration grade before building the integration path:

- alongside: Qwen3.5 is useful as an external operator beside the structured state
- in-state: Qwen3.5 hidden state can carry stack-like information directly enough to target in-state integration
- do-not-integrate-yet: probes do not support integration beyond metadata/checkpoint readiness

## Required Subprobes

W3.0 checkpoint pin and state hooks:

```bash
~/.local/bin/uv run --python .venv/bin/python python -m experiments.w3_qwen35_probe --output-dir results/w3_qwen35_probe
```

W3.1 capacity at real GDN dimensions:

- record hidden size, layer count, and attention head count
- map real hidden size to Module 1 fitted capacity bands
- keep this as a planning estimate, not proof of native stack behavior

W3.1 gating-decay stack survival:

- run only with `--load-model`
- test whether encoded stack probes survive repeated current-node forward passes
- output a survival curve and an integration-grade recommendation

W3.1 native-delta-rule-as-stack gap:

- compare native hidden deltas against explicit structured register push/pop targets
- output a gap score and failure modes

W3.2 propagation probe with Qwen3-4B delta table:

- reuse the M2.0 task suite and compare `Qwen/Qwen3.5-4B` against `Qwen/Qwen3-4B-Instruct-2507`
- report per-task verdicts; do not accept ordering-only passes

## Red Lines

- Do not silently substitute another model family.
- If `Qwen/Qwen3.5-4B` cannot load, use the smallest-size fallback only when explicitly flagged in the result.
- Keep per-task verdicts.
- Keep invalid move and parse failure rates in the verdict.
