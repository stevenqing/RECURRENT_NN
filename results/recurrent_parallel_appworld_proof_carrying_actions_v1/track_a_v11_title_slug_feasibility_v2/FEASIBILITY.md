# EBW Track A v11 Title-Slug Feasibility

## Status: **`RPD_EBW_TRACK_A_V11_TITLE_SLUG_FEASIBILITY_COMPLETE`**

- Target rows: 65
- Evaluation rows: 65
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Candidate Counts

| Label | Rows |
|---|---:|
| `title_slug_candidate_matches_live` | 65 |

## Decision Counts

| Decision | Rows |
|---|---:|
| `commit_live` | 65 |

## Interpretation

The title-slug proof frontier is sufficient for the post-v10 Simple Note export abstain class when the source note is bound to the latest matching pre-write `show_note` read. The deterministic candidate binds that title/content read to the task literal backup directory, applies whitespace-to-underscore slugging, appends `.md`, and passes adversarial uniqueness under path-shaped alternatives. This authorizes the grammar/parser gate before any model call.
