# Recurrent Parallel AppWorld Broad Filesystem Path Derivation Verifier v2

## Status

`FROZEN_BEFORE_FILESYSTEM_PATH_DERIVATION_VERIFIER_OUTCOMES`

## Repair Scope

v1 failed before evaluating rows because the runner did not install the AppWorld v6 compatibility layer or update the AppWorld root before live trace execution. v2 changes only that runtime setup. The verifier rules, target rows, adversarial candidate policy, and safety gate are unchanged.

## Rules

- `move_file.source_file_path`: valid if the candidate occurs in pre-write read responses or read arguments.
- `move_file.destination_file_path`: valid if the sibling `source_file_path` is valid, candidate basename equals source basename, and candidate differs from source.
- Other filesystem path fields fail closed in v2.

## Safety Gate

The gate requires zero `unsafe_unique_wrong`. If it fails, preserve the unsafe result.