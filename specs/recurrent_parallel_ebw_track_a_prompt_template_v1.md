# EBW Track A Prompt Template v1

Status: template skeleton frozen before `ebw-freeze-A`; few-shot example bodies must be filled from the frozen dev slice and hashed before the tag.

## System Message

You synthesize one Evidence-Bound Writes obligation sketch. You do not decide whether to commit. The deterministic verifier will decide validity. Return strict JSON only.

## User Message Template

```text
Task:
{{task_text}}

Candidate action:
{{candidate_action_json}}

Immutable pre-write reads:
{{pre_write_reads_json}}

Prior effects:
{{prior_effects_json}}

Allowed obligations:
1. derived_path_binding
2. literal_intent_binding
3. prior_effect_binding
4. ordered_role_binding

Return one strict JSON object matching exactly one grammar:

derived_path_binding:
{"obligation":"derived_path_binding","source_read_id":...,"source_path_field":...,"derivation":"basename"|"join","target_arg":...}

literal_intent_binding:
{"obligation":"literal_intent_binding","user_span":{"start":...,"end":...},"target_arg":...}

prior_effect_binding:
{"obligation":"prior_effect_binding","effect_step_id":...,"effect_field":...,"target_arg":...}

ordered_role_binding:
{"obligation":"ordered_role_binding","order_source_read_id":...,"order_field":...,"index_expr":"same_rank","target_arg":...}

Do not include explanations. Do not include verifier decisions.
```

## Retry Message

```text
Your previous output was not valid JSON for the frozen grammar. Emit valid JSON only.
```

## Few-Shot Slots

The final Track A freeze tag must replace these placeholders with four examples, one per obligation, drawn from the frozen dev slice of at most 40 opened instances. The dev slice ids and prompt hash must be recorded before any reported opened-pool or sealed-pool run.

```text
{{example_derived_path_binding}}
{{example_literal_intent_binding}}
{{example_prior_effect_binding}}
{{example_ordered_role_binding}}
```