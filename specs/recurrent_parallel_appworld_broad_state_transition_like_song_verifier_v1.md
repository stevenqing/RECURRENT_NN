# Recurrent Parallel AppWorld Broad State-Transition Like-Song Verifier v1

## Status

`FROZEN_BEFORE_STATE_TRANSITION_LIKE_SONG_VERIFIER_OUTCOMES`

## Purpose

This verifier targets `spotify.like_song.song_id`, the highest-volume state-transition schema. The broad ordered-entity baseline was unsafe because it mixed current-song and queue-song evidence. This verifier uses queue-specific ordering when a queue is present, and search-result ordering otherwise.

## Rules

- If `spotify.show_song_queue` appears before the target write, candidate must equal the write-ordinal-th `song_id` from the most recent prior queue response.
- Otherwise, candidate must equal the write-ordinal-th unique `song_id` from prior `spotify.search_songs` responses.
- Missing sequence item fails closed.

## Non-Claim

This is a deterministic verifier baseline, not a model result and not a general Spotify verifier.

## Safety Gate

The gate requires zero `unsafe_unique_wrong`.