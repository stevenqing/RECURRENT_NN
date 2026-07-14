# EBW Track A Prompt Template v3

Status: dev chat-prompt repair after v2 smoke, before any new tag.

Reason: v2 changed the wording but still fed the model a full Markdown template as a raw completion prompt. Qwen often produced a fenced JSON candidate and then continued the template text, so strict full-text JSON parsing stayed at 0.0.

v3 separates human-readable protocol text from executable model prompt assets. The runner should render chat-template messages, seed the assistant with `{`, and stop generation once the strict Track A parser accepts the prefilled object. The EBW primary gate remains strict full-text JSON; tolerant JSON extraction is only a diagnostic/baseline-compatible parser arm.

The executable template lives in `recurrent_parallel_ebw_track_a_prompt_template_v3.json`.