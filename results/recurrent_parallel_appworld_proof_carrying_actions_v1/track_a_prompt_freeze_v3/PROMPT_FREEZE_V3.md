# EBW Track A Prompt Freeze v3

## Status: **`RPD_EBW_TRACK_A_PROMPT_V3_READY_NOT_TAGGED`**

- Prompt assets SHA256: `465cd9b4dd2c8516a9bc67a737796e6a96c44dd475cb03346f6adeb72eb21ea4`
- Prompt protocol: `chat_template_json_prefill_v3`
- Repair scope: chat-template messages, output-only examples, assistant `{` prefill, parser-based stop
- Primary parser: strict full-text JSON only
- Tolerant extraction: diagnostic/baseline-compatible only
- Few-shot output examples: 4
- Sealed variations 10-12 opened: No
- Model/GPU/Docker/external process actions: No

## Examples

| Obligation | Instance ID | Task | Target schema |
|---|---|---|---|
| derived_path_binding | 0102e82d8497e0999342 | 34d9492_1 | post.file_system.move_file.destination_file_path |
| literal_intent_binding | 01ca5949827114b14bb5 | afc0fce_1 | post.venmo.create_transaction_comment.comment |
| ordered_role_binding | 020155d9fe91086024c3 | 57c3486_2 | post.spotify.like_song.song_id |
| prior_effect_binding | 09a4f1b2a3e3e95be5d7 | 6171bbc_2 | post.spotify.add_song_to_playlist.playlist_id |
