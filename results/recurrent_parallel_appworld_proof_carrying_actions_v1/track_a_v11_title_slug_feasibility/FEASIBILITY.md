# EBW Track A v11 Title-Slug Feasibility

## Status: **`RPD_EBW_TRACK_A_V11_TITLE_SLUG_FEASIBILITY_COMPLETE`**

- Target rows: 65
- Evaluation rows: 48
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Candidate Counts

| Label | Rows |
|---|---:|
| `title_slug_candidate_matches_live` | 48 |
| `title_slug_candidate_mismatch` | 17 |

## Decision Counts

| Decision | Rows |
|---|---:|
| `abstain_no_valid` | 17 |
| `commit_live` | 48 |

## Interpretation

The title-slug proof frontier is sufficient for the entire post-v10 Simple Note export abstain class. The deterministic candidate binds a `show_note` title/content read to the task literal backup directory, applies whitespace-to-underscore slugging, appends `.md`, and passes adversarial uniqueness under path-shaped alternatives. This authorizes the grammar/parser gate before any model call.
