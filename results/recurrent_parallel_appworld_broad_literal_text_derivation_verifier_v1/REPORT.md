# AppWorld Broad Literal Text Derivation Verifier

## Status: **`RPD_APPWORLD_BROAD_LITERAL_TEXT_DERIVATION_VERIFIER_SAFE`**

- Target instances: 124
- Evaluated instances: 124
- Unsafe unique-wrong: 0
- Action correctness claim: No
- Instruction text exported: No
- Argument values exported: No
- Response values exported: No
- Value hashes exported: No
- Fresh variations 10-12: sealed
- Model/GPU/Docker/external process actions: No

## Decision Counts

| Decision | Count |
|---|---:|
| commit_live | 46 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 78 |
| unsafe_unique_wrong | 0 |

## Schema Decisions

### `patch.simple_note.update_note.content`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 2 |
| unsafe_unique_wrong | 0 |

### `post.file_system.create_file.content`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 67 |
| unsafe_unique_wrong | 0 |

### `post.phone.send_text_message.message`

| Decision | Count |
|---|---:|
| commit_live | 6 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 2 |
| unsafe_unique_wrong | 0 |

### `post.spotify.create_playlist.title`

| Decision | Count |
|---|---:|
| commit_live | 4 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 0 |
| unsafe_unique_wrong | 0 |

### `post.venmo.create_payment_request.description`

| Decision | Count |
|---|---:|
| commit_live | 13 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 0 |
| unsafe_unique_wrong | 0 |

### `post.venmo.create_transaction.description`

| Decision | Count |
|---|---:|
| commit_live | 2 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 7 |
| unsafe_unique_wrong | 0 |

### `post.venmo.create_transaction_comment.comment`

| Decision | Count |
|---|---:|
| commit_live | 21 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 0 |
| unsafe_unique_wrong | 0 |

## Protocol Checks

- `contract_frozen`: **PASS**
- `preflight_ready`: **PASS**
- `parent_negative_preserved`: **PASS**
- `instance_manifest_binding`: **PASS**
- `target_instance_count`: **PASS**
- `schema_counts`: **PASS**
- `row_count`: **PASS**
- `trace_execution`: **PASS**
- `decision_labels`: **PASS**
- `scope`: **PASS**

## Safety Checks

- `no_unsafe_unique_wrong`: **PASS**
