# KV-Cache Checkpoint Search v1

## Claim

The minimal non-monotone primitive a monotone transformer needs for search is restore-to-prior-state. For a transformer, the minimal exact restore is KV-cache truncation to a previously recorded sequence length. The bounded reversible register is therefore a bounded stack of KV-cache checkpoints. Forward generation remains pure propagation; learned policy is reserved for conflict-directed backjump target selection.

This line intentionally drops the symbolic register, textual register, and TTT-LoRA stack as the primary mechanism. Those remain historical alternatives and controls.

## Build Order

1. **KM-3 exactness gate**: prove cache truncation is exact before reading any search arm.
2. **Single-agent arm A**: KV-cache checkpoint search with branch forward pass and model-selected backjump target.
3. **Controls B/C/D**: re-encoded register, in-context suppression, and external symbolic/register controls.
4. **Backjump-only LoRA**: train only culprit/backjump target selection, not branch/forward propagation.
5. **Multi-agent cache extension**: per-agent KV caches plus shared `(agent, checkpoint)` stack.

## KM-3 Exactness Gate

The gate has two tests over checkpoints along a generated continuation:

- `resume_same`: crop a long cache to checkpoint length, feed the same next token, and compare logits to the original incremental run.
- `resume_different_equals_fresh`: crop a long cache to checkpoint length, feed a different next token, and compare logits to a fresh forward over `prefix + different_token`.

Kill condition: any argmax flip, cache sequence-length mismatch, unsupported cache crop path, or max absolute logit deviation above tolerance fails the gate. No A/B/C/D arm may be interpreted until this passes.

## Single-Agent Mechanism

For graph_color under official Reasoning Gym scoring:

- Branching keeps the full live-path context in the model cache.
- At each branch point, the harness records `(cache_seq_len, variable, tried_values)`.
- Dead-end triggers backjump target selection into the bounded checkpoint stack.
- Retract is implemented by truncating every layer KV tensor, or by `DynamicCache.crop`, to the selected checkpoint length.
- Tried-values bookkeeping is content-free DPLL trail bookkeeping and is the only non-neural state beside checkpoint integers.

## Multi-Agent Mechanism

Each agent owns its own KV cache and checkpoint stack. Cross-block conflicts are routed as messages carrying conflict information and target checkpoint metadata. The team arm has `K` caches with per-agent register `R`; monolith controls use one cache with `R` and `K*R` capacity.

## Honesty Rules

- Official scoring only.
- Batch size 1 for exact cache-control proof.
- Honest total token accounting.
- No LoRA or search-arm result is read before KM-3 passes.
- Backjump LoRA must be reported as target-selection learning only.
- If truncation does not beat in-context suppression, report that attention handles dead branches well enough in this regime.