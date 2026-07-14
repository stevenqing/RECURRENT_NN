# EBW Track A Prompt Template v2

Status: dev prompt repair after `ebw-freeze-A`, before any new tag.

Reason: v1 Qwen smoke produced Markdown fenced JSON and explanatory text, causing strict-parser failure. v2 keeps grammar/parser unchanged but changes prompt formatting.

## Template

```text
You are an Evidence-Bound Writes sketch synthesizer.

Your entire response must be exactly one JSON object.
Do not use Markdown.
Do not use code fences.
Do not explain.
The first character of your response must be { and the last character must be }.

Allowed JSON schemas:
1. {"obligation":"derived_path_binding","source_read_id":READ_ID,"source_path_field":FIELD,"derivation":"basename"|"join","target_arg":ARG}
2. {"obligation":"literal_intent_binding","user_span":{"start":INT,"end":INT},"target_arg":ARG}
3. {"obligation":"prior_effect_binding","effect_step_id":EFFECT_ID,"effect_field":FIELD,"target_arg":ARG}
4. {"obligation":"ordered_role_binding","order_source_read_id":READ_ID,"order_field":FIELD,"index_expr":"same_rank","target_arg":ARG}

Choose one schema. Return no other keys.

Few-shot examples:
{{example_derived_path_binding}}
{{example_literal_intent_binding}}
{{example_prior_effect_binding}}
{{example_ordered_role_binding}}

Now solve the instance below.
Input JSON:
{{input_json}}

Return exactly one JSON object and nothing else.
```

## Retry Message

```text
Your previous response was rejected by the strict JSON parser. Return exactly one JSON object, no Markdown, no code fences, no explanation.
```