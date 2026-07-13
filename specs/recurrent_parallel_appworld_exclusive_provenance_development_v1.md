# AppWorld Exclusive Causal Provenance — Development v1

- Date: 2026-07-12
- Phase: post-NO_GO development on already opened development data
- Confirmation split: still sealed

The generated typed max-tier guard reduced wrong commits from three to one but failed its zero-wrong gate. Its sole error selected tier 3 over tier 1: both candidates had causal provenance, so tier magnitude converted causal ambiguity into a forced commit.

Define **exclusive causal provenance**:

- choose A only when A has nonzero typed provenance and B has none;
- choose B only when B has nonzero typed provenance and A has none;
- abstain when both candidates have provenance, regardless of tier magnitude;
- abstain when neither candidate has provenance.

This is a recurrent commit rule: evidence authorizes a barrier commit only when support is exclusive. Competing causal lineages trigger another round, specialist escalation, or rollback rather than an irreversible write.

Evaluate the rule using only public tier summaries from:

1. the 36 certified generated development pairs;
2. the earlier 15 reserved-train development pairs as a secondary non-independent check.

Development GO requires generated coverage at least 0.50, zero wrong choices, no loss in the number of correct commits versus typed max-tier, zero wrong choices on the historical development set, exact input certification, and no confirmation/model/GPU/Docker/external-process use.

This is explicitly method selection on development data. It cannot serve as confirmation. A GO only permits freezing the rule before opening generated variations 7–9.
