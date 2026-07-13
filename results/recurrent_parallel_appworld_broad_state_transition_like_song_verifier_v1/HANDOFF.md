# Broad State-Transition Like-Song Verifier Handoff

## Status: **`RPD_APPWORLD_BROAD_STATE_TRANSITION_LIKE_SONG_VERIFIER_SAFE`**

This step implements a schema-specific state-transition verifier for `spotify.like_song.song_id`.

## Completed

- Froze the like-song verifier contract before outcomes.
- Evaluated all 155 `spotify.like_song.song_id` instances.
- Split evidence semantics by trace shape:
  - queue tasks use `show_song_queue` ordering;
  - search tasks use `search_songs` ordering.
- Reduced ordered-entity baseline's 2 unsafe cases to 0.
- Recovered 149 `commit_live` decisions.
- Exported no argument values, response values, or value hashes.
- Preserved sealed fresh variations 10-12.
- Used no model, GPU, Docker, or external-process intervention.

## Result

| Decision | Count |
|---|---:|
| `commit_live` | 149 |
| `ambiguous_both_valid` | 0 |
| `abstain_no_valid` | 6 |
| `unsafe_unique_wrong` | 0 |

## Sequence Sources

| Source | Count |
|---|---:|
| `search` | 143 |
| `queue` | 12 |

## Interpretation

The broad ordered-entity verifier failed because it mixed different evidence roles. In queue tasks, `show_current_song` and `show_song_queue` both expose song IDs, but only the queue order is the write cursor. Splitting queue-order and search-result-order evidence removes the unsafe cases and recovers additional safe commits.

This reinforces the proof-carrying action thesis: the verifier must encode the relation between a candidate write and the specific evidence role, not just the field name or occurrence order.

## Key Artifacts

- Contract: `specs/recurrent_parallel_appworld_broad_state_transition_like_song_verifier_v1.json`
- Spec: `specs/recurrent_parallel_appworld_broad_state_transition_like_song_verifier_v1.md`
- Runner: `analysis/appworld_broad_state_transition_like_song_verifier.py`
- Report: `results/recurrent_parallel_appworld_broad_state_transition_like_song_verifier_v1/REPORT.md`
- Results: `results/recurrent_parallel_appworld_broad_state_transition_like_song_verifier_v1/results.json`
- Value-free rows: `results/recurrent_parallel_appworld_broad_state_transition_like_song_verifier_v1/rows.json`

## Next Route

Add this verifier to the safe ledger. Then target the remaining high-value state schemas with schema-specific role/effect constraints.