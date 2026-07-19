# EBW Track A v37 Held-Out Control Summary

## Status: **`RPD_EBW_TRACK_A_V37_HELDOUT_CONTROL_SUMMARY_COMPLETE`**

- Fresh tasks: 24
- Value-free target instances: 169
- Executable held-out rows: 65
- Sealed variations 10-12 opened: Yes, after v30 freeze

## Control Table

| Control | Model calls | Commit | Abstain | Unsafe | Accepted repairs | Interpretation |
|---|---:|---:|---:|---:|---:|---|
| `one_shot_no_repair` | 65 | 62 | 3 | 0 | None | baseline proof-agent pass |
| `best_of_n_no_repair` | 24 | 62 | 3 | 0 | 0 | extra proof-sketch sampling does not recover held-out residuals |
| `freeform_repairagent_patch_json` | 1 | 62 | 3 | 0 | 0 | free-form patch parses but MetaVerifier rejects wrong slot |
| `structured_without_metaverifier` | 0 | None | None | None | 3 | compiler-only accepts bad slot controls; not safety-valid |
| `structured_with_metaverifier` | 1 | 65 | 0 | 0 | 1 | frozen primitive selection plus MetaVerifier closes held-out residuals |

## Interpretation

On the prospective held-out executable subset, generic proof-sketch test-time compute and free-form patch JSON do not recover the residuals. Structured primitive selection with the frozen MetaVerifier closes the held-out gap, while the no-MetaVerifier control shows that compiler-only acceptance would also admit bad slot choices.
