# AppWorld Broad State-Transition Ordered-Entity Verifier

## Status: **`RPD_APPWORLD_BROAD_STATE_TRANSITION_ORDERED_ENTITY_VERIFIER_UNSAFE`**

- Target instances: 577
- Evaluated instances: 577
- Unsafe unique-wrong: 28
- Action correctness claim: No
- Argument values exported: No
- Response values exported: No
- Value hashes exported: No
- Fresh variations 10-12: sealed
- Model/GPU/Docker/external process actions: No

## Decision Counts

| Decision | Count |
|---|---:|
| commit_live | 257 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 292 |
| unsafe_unique_wrong | 28 |

## Schema Decisions

### `delete.phone.delete_text_message.text_message_id`

| Decision | Count |
|---|---:|
| commit_live | 18 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 0 |
| unsafe_unique_wrong | 0 |

### `delete.phone.delete_voice_message.voice_message_id`

| Decision | Count |
|---|---:|
| commit_live | 22 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 0 |
| unsafe_unique_wrong | 0 |

### `delete.spotify.remove_album_from_library.album_id`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 6 |
| unsafe_unique_wrong | 2 |

### `delete.spotify.remove_song_from_library.song_id`

| Decision | Count |
|---|---:|
| commit_live | 2 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 27 |
| unsafe_unique_wrong | 3 |

### `delete.spotify.remove_song_from_playlist.playlist_id`

| Decision | Count |
|---|---:|
| commit_live | 2 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 24 |
| unsafe_unique_wrong | 2 |

### `delete.spotify.remove_song_from_playlist.song_id`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 26 |
| unsafe_unique_wrong | 2 |

### `delete.spotify.unfollow_artist.artist_id`

| Decision | Count |
|---|---:|
| commit_live | 1 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 4 |
| unsafe_unique_wrong | 0 |

### `patch.phone.update_alarm.alarm_id`

| Decision | Count |
|---|---:|
| commit_live | 2 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 4 |
| unsafe_unique_wrong | 1 |

### `patch.simple_note.update_note.note_id`

| Decision | Count |
|---|---:|
| commit_live | 2 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 0 |
| unsafe_unique_wrong | 0 |

### `patch.spotify.update_song_review.review_id`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 5 |
| unsafe_unique_wrong | 0 |

### `post.spotify.add_song_to_playlist.song_id`

| Decision | Count |
|---|---:|
| commit_live | 3 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 13 |
| unsafe_unique_wrong | 2 |

### `post.spotify.add_to_queue.song_id`

| Decision | Count |
|---|---:|
| commit_live | 3 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 0 |
| unsafe_unique_wrong | 0 |

### `post.spotify.download_song.song_id`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 23 |
| unsafe_unique_wrong | 2 |

### `post.spotify.follow_artist.artist_id`

| Decision | Count |
|---|---:|
| commit_live | 3 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 64 |
| unsafe_unique_wrong | 1 |

### `post.spotify.like_song.song_id`

| Decision | Count |
|---|---:|
| commit_live | 137 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 16 |
| unsafe_unique_wrong | 2 |

### `post.spotify.play_music.playlist_id`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 0 |
| unsafe_unique_wrong | 2 |

### `post.spotify.play_music.song_id`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 0 |
| unsafe_unique_wrong | 2 |

### `post.spotify.review_song.song_id`

| Decision | Count |
|---|---:|
| commit_live | 2 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 27 |
| unsafe_unique_wrong | 2 |

### `post.venmo.approve_payment_request.payment_request_id`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 8 |
| unsafe_unique_wrong | 1 |

### `post.venmo.deny_payment_request.payment_request_id`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 18 |
| unsafe_unique_wrong | 1 |

### `post.venmo.like_transaction.transaction_id`

| Decision | Count |
|---|---:|
| commit_live | 60 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 6 |
| unsafe_unique_wrong | 1 |

### `post.venmo.remind_payment_request.payment_request_id`

| Decision | Count |
|---|---:|
| commit_live | 0 |
| ambiguous_both_valid | 0 |
| abstain_no_valid | 21 |
| unsafe_unique_wrong | 2 |

## Protocol Checks

- `contract_frozen`: **PASS**
- `preflight_ready`: **PASS**
- `parent_negative_preserved`: **PASS**
- `created_playlist_preserved`: **PASS**
- `instance_manifest_binding`: **PASS**
- `target_instance_count`: **PASS**
- `schema_counts`: **PASS**
- `row_count`: **PASS**
- `trace_execution`: **PASS**
- `decision_labels`: **PASS**
- `scope`: **PASS**

## Safety Checks

- `no_unsafe_unique_wrong`: **FAIL**
