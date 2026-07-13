# AppWorld Broad State-Transition Like-Song Verifier

## Status: **`RPD_APPWORLD_BROAD_STATE_TRANSITION_LIKE_SONG_VERIFIER_SAFE`**

- Target instances: 155
- Evaluated instances: 155
- Unsafe unique-wrong: 0
- Action correctness claim: No
- Argument values exported: No
- Response values exported: No
- Value hashes exported: No
- Fresh variations 10-12: sealed
- Model/GPU/Docker/external process actions: No

## Decision Counts

| Decision | Count |
|---|---:|
| commit_live | 149 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 6 |
| unsafe_unique_wrong | 0 |

## Sequence Sources

| Source | Count |
|---|---:|
| queue | 12 |
| search | 143 |

## Protocol Checks

- `contract_frozen`: **PASS**
- `preflight_ready`: **PASS**
- `parent_ordered_recorded`: **PASS**
- `instance_manifest_binding`: **PASS**
- `target_instance_count`: **PASS**
- `row_count`: **PASS**
- `trace_execution`: **PASS**
- `decision_labels`: **PASS**
- `scope`: **PASS**

## Safety Checks

- `no_unsafe_unique_wrong`: **PASS**
