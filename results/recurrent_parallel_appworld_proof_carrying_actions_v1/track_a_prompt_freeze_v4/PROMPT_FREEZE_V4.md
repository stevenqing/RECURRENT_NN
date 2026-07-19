# EBW Track A Prompt Freeze v4

## Status: **`RPD_EBW_TRACK_A_PROMPT_V4_READY_NOT_TAGGED`**

- Prompt assets SHA256: `223b1f6de57bab171ba71a8fbe4eb4b450d7b9747a7553182ab9686fce3511a5`
- Parent v3 assets SHA256: `465cd9b4dd2c8516a9bc67a737796e6a96c44dd475cb03346f6adeb72eb21ea4`
- Prompt protocol: `chat_template_json_prefill_role_constrained_v4`
- Repair scope: role-constrained prompt over v3 chat-template/prefill/stop protocol
- Primary parser: strict full-text JSON only
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Role Constraint Policy

| Source | Required obligation |
|---|---|
| filesystem_path_derivation_proof | derived_path_binding |
| literal_text_derivation_proof | literal_intent_binding |
| state_transition_created_playlist_playlist_id | prior_effect_binding |
| state_transition_membership_default | ordered_role_binding |
