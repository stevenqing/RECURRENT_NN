# AppWorld Broad Filesystem Path Derivation Verifier

## Status: **`RPD_APPWORLD_BROAD_FILESYSTEM_PATH_DERIVATION_VERIFIER_SAFE`**

- Target instances: 547
- Evaluated instances: 547
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
| commit_live | 75 |
| ambiguous_both_valid | 231 |
| abstain_no_valid | 241 |
| unsafe_unique_wrong | 0 |

## Schema Decisions

### `post.file_system.compress_directory.compressed_file_path`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 9 |
| unsafe_unique_wrong | 0 |

### `post.file_system.compress_directory.directory_path`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 9 |
| unsafe_unique_wrong | 0 |

### `post.file_system.create_file.file_path`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 67 |
| unsafe_unique_wrong | 0 |

### `post.file_system.move_file.destination_file_path`

| Decision | Count |
|---|---:|
| commit_live | 75 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 156 |
| unsafe_unique_wrong | 0 |

### `post.file_system.move_file.source_file_path`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 231 |
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
