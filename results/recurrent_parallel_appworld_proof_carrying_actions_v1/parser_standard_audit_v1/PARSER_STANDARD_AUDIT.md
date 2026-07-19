# EBW Parser Standard Audit

## Status: **`RPD_EBW_PARSER_STANDARD_AUDIT_COMPLETE`**

## Prior Baseline Standards

| Baseline family | Parser standard |
|---|---|
| EBW primary | strict full-text JSON object; no extraction or regex repair |
| KV-cache LFS/ToT/RAP | scan raw text for JSON objects and take a parseable object, usually last |
| ReasoningGym/externalization | accept fenced JSON and raw JSON candidates; often score last valid object |

## Smoke Parse Counts

| Smoke | Rows | Strict | First fenced | Last fenced | First raw | Last raw |
|---|---:|---:|---:|---:|---:|---:|
| v1 | 4 | 0 | 2 | 2 | 2 | 0 |
| v2 | 4 | 0 | 2 | 2 | 2 | 0 |

## Interpretation

Previous baselines were more permissive than EBW Track A's primary parser. That matters for fair baselines, but EBW cannot simply switch to last-object extraction: the Qwen smoke outputs echo prompt examples and templates, so an extractor can parse JSON that comes from the prompt rather than the model's intended final answer.

Recommendation: keep strict JSON as the primary safety gate, add a baseline-compatible tolerant-parser diagnostic arm, and fix generation with chat-template/stop-token protocol rather than regex repair.
