# AppWorld Broad Safe Derivation Ledger

## Status: **`RPD_APPWORLD_BROAD_SAFE_DERIVATION_LEDGER_V5_PASS`**

- Target instances: 1266
- Policy: path verifier v2 + literal verifier v1 + created-playlist verifier v1 + like-song verifier v1 + zero-unsafe ordered-entity schema slices + remaining state-transition fail closed
- Action correctness claim: No
- Argument values exported: No
- Response values exported: No
- Value hashes exported: No
- Fresh variations 10-12: sealed
- Model/GPU/Docker/external process actions: No

## Decision Counts

| Decision | Count |
|---|---:|
| commit_live | 334 |
| ambiguous_both_valid | 231 |
| abstain_no_valid | 701 |
| unsafe_unique_wrong | 0 |

## Family Decision Counts

### `filesystem_path_derivation_proof`

| Decision | Count |
|---|---:|
| commit_live | 75 |
| ambiguous_both_valid | 231 |
| abstain_no_valid | 241 |
| unsafe_unique_wrong | 0 |

### `literal_text_derivation_proof`

| Decision | Count |
|---|---:|
| commit_live | 46 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 78 |
| unsafe_unique_wrong | 0 |

### `state_transition_membership_proof`

| Decision | Count |
|---|---:|
| commit_live | 213 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 382 |
| unsafe_unique_wrong | 0 |

## Checks

- `contract_frozen`: **PASS**
- `parent_ledger`: **PASS**
- `path_verifier_safe`: **PASS**
- `literal_verifier_safe`: **PASS**
- `created_playlist_verifier_safe`: **PASS**
- `like_song_verifier_safe`: **PASS**
- `ordered_entity_verifier_recorded`: **PASS**
- `row_count`: **PASS**
- `unique_instance_ids`: **PASS**
- `decision_counts`: **PASS**
- `family_counts`: **PASS**
- `path_binding`: **PASS**
- `literal_binding`: **PASS**
- `created_playlist_binding`: **PASS**
- `like_song_binding`: **PASS**
- `ordered_entity_binding`: **PASS**
- `scope`: **PASS**
