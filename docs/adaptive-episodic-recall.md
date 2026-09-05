# Adaptive Episodic Recall

Date: 2026-09-05
Status: experimental implementation on `feature/adaptive-episodic-recall`

## Goal

Motoko's long-conversation memory must not depend on one lossy summary. The
active model context can remain bounded while every raw conversation turn that
Motoko sees after this feature is installed remains recoverable as private,
realm-local evidence.

The design combines three layers:

1. **Cheap continuity**: compact conversation summaries, profile context,
   durable memories, recent turns, dossiers, and the existing HRAG pipeline.
2. **Lossless episodic history**: append-only raw conversation turns grouped by
   context-window lineage.
3. **Adaptive recall**: when a long conversation has history outside the active
   transcript, a bounded model planner may formulate specific questions about
   what it still needs, search raw history, inspect the retrieved evidence, and
   run one additional retrieval round before final synthesis.

This follows the useful architectural idea visible in Codex's experimental
context management without depending on Codex's private backend.

## Realm-local state

Raw history is Motoko-owned private state:

```text
~/.local/state/motoko/conversation-history/<conversation-id>.jsonl
~/.local/state/motoko/conversation-history/<conversation-id>.windows.jsonl
```

Each history row contains a stable message ID, ordinal, context-window ID, role,
raw content, content hash, and archival timestamp. Each closed-window row
records window lineage and ordinal bounds. `/sources` receives only
content-free provenance such as IDs, ordinal ranges, scores, and recall-round
metadata; it does not copy the raw correspondence into source diagnostics.

Conversation deletion removes these sidecars with the conversation.

## Compaction

Classic Motoko compaction remains useful as a cheap continuity layer, but it is
no longer allowed to be destructive:

```text
active messages
    |
    +--> append raw turns to episodic history
    |
    +--> summarize older turns
    |
    +--> seal context window
    |
    +--> retain bounded recent turns
    |
    '--> continue in a new context-window lineage
```

The summary is an index/hint. It is not the authoritative historical record.

## Adaptive recall loop

The initial prompt is still built by Motoko's existing retrieval system. If
the conversation is short and has no archived history outside the active
transcript, adaptive recall does nothing and makes no extra model call.

For a long/compacted conversation:

```text
user question
    |
    v
existing HRAG + memories + summary + recent context
    |
    v
structured recall planner
    |
    +--> sufficient ------------------------------+
    |                                            |
    '--> need_more_context                       |
             |                                   |
             v                                   |
       1-3 standalone history queries            |
             |                                   |
             v                                   |
       raw-history search + adjacent turns       |
             |                                   |
             v                                   |
       planner inspects recovered evidence       |
             |                                   |
             +--> sufficient --------------------+
             |
             '--> reformulate/search once more
                                                  |
                                                  v
                                            final answer
```

The default bound is two planner rounds, three queries per round, five evidence
spans per query, two adjacent turns on each side, and 24,000 characters of raw
history evidence. These are conservative safety/latency bounds, not a claim
that more retrieval is always better.

The planner emits structured retrieval actions only:

```json
{
  "status": "need_more_context",
  "queries": [
    {
      "query": "previous periods of reduced communication and how they resolved",
      "scope": "current_conversation",
      "purpose": "compare the current pattern with prior episodes"
    }
  ]
}
```

It is explicitly told not to answer the user and not to emit hidden reasoning.
The retrieval plan is inspectable.

## Search behavior

The first implementation deliberately keeps the raw-history search layer
simple and deterministic. It ranks exact phrases and overlapping terms, gives
a small container boost from conversation title/summary, and returns neighboring
turns around a matching message.

The important intelligence is the model's ability to formulate a targeted
lookup after understanding the problem. This is complementary to Motoko's
existing HRAG hierarchy rather than a replacement for it. Future evaluation
may justify embedding/reranker lanes over episodic rows, but they should be
added only when they improve measured recall over the simpler layer.

## Evidence precedence

For questions about what was actually said, what happened, or how an earlier
episode unfolded:

1. raw retrieved conversation turns are primary evidence;
2. summaries and durable memories are useful indexes/context;
3. if a summary or memory conflicts with raw history, Motoko should prefer the
   raw source and surface the conflict;
4. hypotheses and interpretations must not silently harden into facts merely
   because they appear in a model-generated summary.

This distinction is especially important for correspondence, relationship
analysis, and long-running personal conversations.

## Migration and limitations

This feature is lossless **from the point it is installed forward**. When an
older saved conversation is encountered, Motoko lazily archives whatever raw
messages are still present in its JSON file.

It cannot reconstruct turns that an older Motoko version already deleted during
destructive compaction. Existing summaries and memories remain available for
those historical gaps, but they must not be represented as raw evidence.

Message-level timestamps are preserved when present. Older conversation rows
that never stored per-message timestamps retain their ordinal/window provenance
but cannot acquire a truthful timestamp retroactively.

## Evaluation and failure taxonomy

Adaptive recall should be improved through Motoko's existing inspectable
feedback/eval loop. Retrieval failures should be classified separately:

- initial context retrieval missed relevant evidence;
- the recall planner failed to notice a knowledge gap;
- the planner formulated a poor retrieval query;
- raw-history search had poor recall;
- a future reranker discarded the correct evidence;
- the planner stopped too early;
- correct evidence was retrieved but final synthesis ignored it;
- a summary/durable memory contradicted raw history;
- a stale hypothesis or interpretation was treated as fact.

The goal is not that Motoko stores an ever-larger prompt. The goal is that she
can recover the relevant parts of an effectively unbounded private history
when the current question makes them matter.
