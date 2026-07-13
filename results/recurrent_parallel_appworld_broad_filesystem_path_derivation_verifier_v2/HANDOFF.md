# Broad Filesystem Path Derivation Verifier Handoff

## Status: **`RPD_APPWORLD_BROAD_FILESYSTEM_PATH_DERIVATION_VERIFIER_SAFE`**

This step implements the first value-bound derivation verifier after the occurrence baseline failed. It targets the largest unsafe surface: filesystem path derivation.

## Completed

- Preserved the v1 protocol failure caused by missing AppWorld runtime compatibility setup.
- Froze v2 as a runtime-only repair: install AppWorld v6 compatibility and update the AppWorld root before live trace execution.
- Kept verifier rules, target rows, adversarial candidate policy, and safety gate unchanged from v1.
- Evaluated all 547 filesystem path instances.
- Observed 0 trace failures.
- Reduced unsafe unique-wrong from the occurrence baseline's 316 filesystem-path cases to 0.
- Recovered 75 `commit_live` decisions.
- Exported no argument values, response values, or value hashes.
- Preserved sealed fresh variations 10-12.
- Used no model, GPU, Docker, or external-process intervention.

## Result

| Decision | Count |
|---|---:|
| `commit_live` | 75 |
| `ambiguous_both_valid` | 231 |
| `abstain_no_valid` | 241 |
| `unsafe_unique_wrong` | 0 |

## Schema Decisions

| Schema | Commit-live | Ambiguous | Abstain | Unsafe |
|---|---:|---:|---:|---:|
| `file_system.move_file.destination_file_path` | 75 | 0 | 156 | 0 |
| `file_system.move_file.source_file_path` | 0 | 231 | 0 | 0 |
| `file_system.create_file.file_path` | 0 | 0 | 67 | 0 |
| `file_system.compress_directory.directory_path` | 0 | 0 | 9 | 0 |
| `file_system.compress_directory.compressed_file_path` | 0 | 0 | 9 | 0 |

## Interpretation

The occurrence baseline was unsafe because it treated arbitrary path occurrence as evidence. The path derivation verifier adds a small but meaningful derivation constraint: for `move_file.destination_file_path`, the candidate must be tied to the sibling source path by basename preservation while the source path itself must be grounded in pre-write reads.

This is the first broad value-bound result that recovers commits while preserving the zero-unsafe safety gate. It is still narrow: unsupported path fields fail closed, and source paths remain ambiguous when multiple valid source-like paths exist.

## Key Artifacts

- Contract: `specs/recurrent_parallel_appworld_broad_filesystem_path_derivation_verifier_v2.json`
- Spec: `specs/recurrent_parallel_appworld_broad_filesystem_path_derivation_verifier_v2.md`
- Runner: `analysis/appworld_broad_filesystem_path_derivation_verifier.py`
- Report: `results/recurrent_parallel_appworld_broad_filesystem_path_derivation_verifier_v2/REPORT.md`
- Results: `results/recurrent_parallel_appworld_broad_filesystem_path_derivation_verifier_v2/results.json`
- Value-free rows: `results/recurrent_parallel_appworld_broad_filesystem_path_derivation_verifier_v2/rows.json`

## Next Route

The next derivation verifier should target literal text, where the occurrence baseline had 52 unsafe cases. The key change should be similar: require template/serialization structure rather than arbitrary text occurrence. After that, state-transition membership needs effect/cursor constraints to turn ambiguous membership into safe commits.