# EBW Track A Runner Smoke

## Status: **`RPD_EBW_TRACK_A_RUNNER_SMOKE_PASS`**

- Synthetic cases: 6
- Commit-live: 2
- Unsafe unique-wrong: 1
- Commit after repair: 1
- Parse-error cases: 1
- Synthetic GA-main pass: False
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Outcome Counts

| Outcome | Count |
|---|---:|
| abstain_competing_valid | 1 |
| abstain_no_valid | 2 |
| commit_live | 2 |
| unsafe_unique_wrong | 1 |

## Checks

- `contract_frozen`: **PASS**
- `preflight_ready`: **PASS**
- `lock_binding`: **PASS**
- `manifest_binding`: **PASS**
- `manifest_dev_excluded`: **PASS**
- `budget_retry`: **PASS**
- `total_cases`: **PASS**
- `commit_live`: **PASS**
- `unsafe_unique_wrong`: **PASS**
- `abstain_no_valid`: **PASS**
- `abstain_competing_valid`: **PASS**
- `commit_after_repair`: **PASS**
- `parse_error_cases`: **PASS**
- `ga_main_unsafe_fails`: **PASS**
- `sealed_closed`: **PASS**
- `no_model_or_external`: **PASS**
