# EBW Track A Execution Preflight

## Status: **`RPD_EBW_TRACK_A_EXECUTION_PREFLIGHT_READY`**

- Freeze tag: `ebw-freeze-A`
- Tag commit: `eba53babec790a9d3b3839fd45f2ee4627228427`
- Prompt SHA256: `6d1904dae3fc0b7b2273a754afcd6be2c89a754aaf1cddf5ddcef0e3806ea218`
- Opened instances: 1266
- Dev slice excluded: 40
- Reportable opened instances: 1226
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Proof Family Counts

| Proof family | Reportable instances |
|---|---:|
| filesystem_path_derivation_proof | 537 |
| literal_text_derivation_proof | 114 |
| state_transition_membership_proof | 575 |

## Checks

- `contract_frozen`: **PASS**
- `tag_commit`: **PASS**
- `head_at_tag`: **PASS**
- `readiness_status`: **PASS**
- `readiness_lock_binding`: **PASS**
- `runner_config_tag`: **PASS**
- `prompt_status`: **PASS**
- `prompt_hash`: **PASS**
- `budget_caps`: **PASS**
- `parser_exists`: **PASS**
- `dev_status`: **PASS**
- `opened_count`: **PASS**
- `reportable_count`: **PASS**
- `no_dev_overlap`: **PASS**
- `unique_reportable_ids`: **PASS**
- `safe_ledger`: **PASS**
- `ga_asserts`: **PASS**
- `baseline_arms`: **PASS**
- `sealed_closed`: **PASS**
- `no_model_or_external`: **PASS**
