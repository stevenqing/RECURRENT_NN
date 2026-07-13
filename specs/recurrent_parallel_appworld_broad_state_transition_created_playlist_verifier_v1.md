# Recurrent Parallel AppWorld Broad State-Transition Created-Playlist Verifier v1

## Status

`FROZEN_BEFORE_STATE_TRANSITION_CREATED_PLAYLIST_VERIFIER_OUTCOMES`

## Purpose

This verifier targets the only unsafe state-transition schema from the occurrence baseline: `spotify.add_song_to_playlist.playlist_id`. It tests a prior-effect proof: a playlist ID is valid only if it is the playlist ID returned by the most recent prior `spotify.create_playlist` write before adding a song to a playlist.

## Rule

- Target schema: `post.spotify.add_song_to_playlist.playlist_id`.
- Valid live or adversarial candidate: equals most recent prior `spotify.create_playlist` response `playlist_id`.
- Unsupported state-transition fields fail closed.

## Non-Claim

This is a narrow deterministic verifier baseline, not a general state-transition verifier and not a model result.

## Safety Gate

The gate requires zero `unsafe_unique_wrong`. If it fails, preserve the unsafe result.

## Verdicts

- Safe: `RPD_APPWORLD_BROAD_STATE_TRANSITION_CREATED_PLAYLIST_VERIFIER_SAFE`
- Unsafe: `RPD_APPWORLD_BROAD_STATE_TRANSITION_CREATED_PLAYLIST_VERIFIER_UNSAFE`
- Protocol fail: `RPD_APPWORLD_BROAD_STATE_TRANSITION_CREATED_PLAYLIST_VERIFIER_PROTOCOL_FAIL`