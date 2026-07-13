# Recurrent Parallel AppWorld Broad State-Transition Ordered-Entity Verifier v1

## Status

`FROZEN_BEFORE_STATE_TRANSITION_ORDERED_ENTITY_VERIFIER_OUTCOMES`

## Purpose

This verifier tests a simple ordered/cursor semantics for remaining state-transition entity fields. It excludes `spotify.add_song_to_playlist.playlist_id`, which is already covered by the created-playlist prior-effect verifier.

## Rule

A candidate is valid only if it equals the write-ordinal-th unique value for the same field name found in same-app pre-write read responses. If the sequence item is missing, fail closed.

## Non-Claim

This is a deterministic verifier baseline, not a model result and not a general state-transition solution. It may be unsafe; if so, preserve the unsafe result.

## Safety Gate

The gate requires zero `unsafe_unique_wrong`.

## Verdicts

- Safe: `RPD_APPWORLD_BROAD_STATE_TRANSITION_ORDERED_ENTITY_VERIFIER_SAFE`
- Unsafe: `RPD_APPWORLD_BROAD_STATE_TRANSITION_ORDERED_ENTITY_VERIFIER_UNSAFE`
- Protocol fail: `RPD_APPWORLD_BROAD_STATE_TRANSITION_ORDERED_ENTITY_VERIFIER_PROTOCOL_FAIL`