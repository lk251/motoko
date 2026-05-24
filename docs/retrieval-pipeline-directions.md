# Possible Retrieval Pipeline Architectural Directions

Date: 2026-05-21

This document records a tentative architecture direction for Motoko's future
retrieval pipeline. It is not a commitment to implement every item here. The
goal is to preserve the current best judgment about what is likely to increase
Motoko's intelligence, competence, and careful source-grounded behavior.

## Summary

Embedding plus reranking is a strong core retrieval layer, but it is not the
whole architecture. For Motoko, the best-fit direction is a modular, hybrid,
hierarchical retrieval system:

```text
deterministic parsing/signals
+ lexical/exact retrieval
+ dense embeddings at several levels
+ structured task/date/entity/project indexes
+ hybrid candidate fusion
+ reranking over bounded evidence spans
+ careful context packing
+ final synthesis by the large model
+ grounding audit and user feedback loop
```

Retrieval should be treated as an evidence pipeline, not as one vector search.

## Architectural Principles

- Preserve a deterministic truth layer. Org headings, TODOs, priorities,
  deadlines, scheduled dates, file paths, timestamps, exact names, and source
  fingerprints should be parsed programmatically whenever possible. These
  signals are more authoritative than model summaries.
- Keep lexical and exact retrieval first-class. Dense embeddings are valuable
  for semantic recall, but names, dates, paths, commands, IDs, and TODO states
  often require exact or sparse retrieval.
- Use multiple levels of retrievable artifacts. Motoko should be able to
  retrieve raw source spans, Org subtrees, chunks, files, project/topic maps,
  corpus summaries, memories, conversation summaries, and task/date/entity
  objects.
- Rerank hierarchically. Prefer cheap container ranking first, then rank
  chunks or spans inside the best containers, then rerank the final candidate
  evidence before sending it to the chat model.
- Select source evidence, not just containers. If a retrieved chunk is large,
  split candidate spans into bounded subspans, score them, preserve parent
  provenance, and pass the best source evidence onward.
- Pack context deliberately. More context is not automatically better. Keep the
  final prompt focused, source-grounded, and auditable so relevant evidence is
  not buried in the middle of a long context.
- Treat reflection as inspectable audit. Prefer answer-grounding checks,
  retrieval diagnostics, stale-artifact warnings, and feedback-driven evals
  over hidden, uninspectable reasoning loops.

## Candidate Retrieval Hierarchy

Motoko should consider storing or deriving retrievable objects at these levels:

- **Span or subtree level:** Org dated sections, TODO subtrees, paragraphs,
  Markdown sections, email/message sections, and code/function-sized units.
- **Chunk level:** bounded raw source text chunks with source fingerprints and
  duplicate provenance.
- **File level:** file summaries, file roles, file labels, key entities,
  active tasks, dates, and relationships to other files.
- **Project/topic level:** project maps, topic dossiers, cross-file
  relationships, active obligations, and decision records.
- **Corpus level:** corpus summary, corpus profile, files by role, active
  project map, stale/suspicious artifact list, and open questions.
- **Memory/conversation level:** durable memories, conversation summaries,
  memory dossiers, and feedback records.

Each level may deserve its own lexical fields, embeddings, freshness metadata,
and quality/provenance fields.

## Hybrid Candidate Generation

For each query, Motoko should generate candidates from multiple lanes and then
fuse them:

- lexical or BM25-style exact search;
- path, filename, and rare-term matches;
- deterministic Org/task/date signals;
- dense embeddings over raw spans and chunks;
- dense embeddings over chunk/file/corpus summaries;
- memory and conversation retrieval;
- recency and freshness filters;
- explicit user hints such as named files, dates, projects, or focus terms.

The intended shape is hybrid candidate generation followed by reranking, not a
replacement of lexical retrieval with dense retrieval.

## Hierarchical Reranking

Reranking can happen at several levels:

- Rank likely files, projects, or topics cheaply.
- Rank chunks or structured objects inside those containers.
- Split large candidate spans into bounded subspans and rerank the subspans.
- Reassemble the best evidence under the chat-context budget.
- For high-value or ambiguous questions, optionally run a large-model audit of
  whether the selected evidence is sufficient and source-grounded.

This keeps expensive model work focused on the places where it can improve
answer quality, rather than spending it on every file or every chunk.

## Techniques Worth Considering

- **RAPTOR-like hierarchy:** recursive summaries and clustered topic/project
  maps can help broad questions such as "what matters most?" or "what changed
  across this corpus?"
- **GraphRAG-like relationship layer:** a lightweight, realm-local graph of
  people, projects, files, tasks, obligations, decisions, and dates may help
  cross-file reasoning. Start deterministic and inspectable before adding
  model-derived graph edges.
- **Late-interaction or multi-vector retrieval:** ColBERT-style approaches can
  improve fine-grained retrieval over single-vector embeddings, but they add
  complexity and storage cost. Motoko's bounded subspan embeddings are a
  pragmatic intermediate step before considering true late interaction.
- **Query planning and decomposition:** for multi-hop questions, split the
  query into subquestions, retrieve separately, and synthesize from combined
  evidence.
- **Feedback learning:** thumbs-up/down plus free-text corrections should feed
  retrieval, rerank, prompt, and answer-quality evals. Feedback remains
  per-realm and under the current user's Motoko state.

## Recommended Next Architectural Step

The next high-value direction is a persistent hierarchical evidence store:

- make Org subtrees, TODO items, dated daily sections, and important spans
  first-class retrievable objects;
- attach lexical terms, structured signals, embeddings, provenance, and
  freshness metadata directly to those objects;
- use those objects in hybrid retrieval before falling back to broad chunks;
- keep `/retrieval-debug`, `/retrieval-preview`, and `/sources` able to show
  exactly which object and source span was selected.

This should improve Motoko's effective intelligence more than adding another
model immediately, because it gives the existing models better evidence.

## Procedural Skill Candidate: Source-Scoped Temporal Retrieval

A useful recent failure pattern was the query "summarize the last N days
present in logbook.org". The retrieval layer could find `logbook.org`, but the
answer sometimes inferred missing adjacent calendar days or allowed dated
sections from other Org files to satisfy the request. The user intent was not
"today and yesterday"; it was "the newest distinct dated sections that actually
exist in this named source file".

The general solution is not a permanent note about one query. It is a
deterministic retrieval procedure:

- detect temporal wording such as "last/latest N days present";
- detect an explicit source path or filename when the query names one;
- scope candidate generation to that source before considering other files;
- parse dated Org headings and choose the newest distinct dates present in the
  scoped source;
- include one bounded, source-linked excerpt per selected date;
- state the selected dates in prompt context and `/sources`, so the chat model
  does not assume missing intervening calendar days have entries.

This is a good future skills/tools candidate when Motoko studies Hermes Agent
or similar systems. As a **skill**, it captures the repeatable debugging lesson
and the checklist an assistant should follow. As a **tool**, it is the
deterministic source-scoped date selector that enforces the rule. The tool
should own source selection and date extraction; the skill should only describe
when and why to use that procedure. That split keeps Motoko source-grounded and
prevents prompt-only advice from becoming hidden retrieval policy.

Motoko now ships this as the built-in `org-temporal-retrieval` procedural
skill with `motoko-skill-v2` metadata. The skill declares the
`builtin:org_temporal_latest_entries` handler, and a pre-retrieval
`retrieval_plan_v1` activates that handler before context packing when the
query asks for latest/recent dated entries in a named Org source. The
deterministic source/date selector still enforces evidence selection; the skill
supplies durable trigger metadata, procedure, and provenance. That is the
intended architecture for similar cases: skills preserve procedural knowledge,
planners decide whether the skill should affect a subsystem, and handlers
perform bounded inspectable work.

Future skill work should add support files and carefully constrained scripts
only after the planner/handler boundary is stable. Scripts are useful when they
turn repeatable procedures into deterministic probes or transforms, but they
must not become broad shell execution, cross-realm access, or a way around
document allowlists.

## Evaluation Requirements

Future retrieval work should be gated by inspectable evals that measure:

- recall of correct files, chunks, Org subtrees, dates, TODOs, and rare terms;
- ranking quality before and after reranking;
- whether exact/date/path queries preserve deterministic truth;
- whether broad planning questions select the right hierarchy level;
- whether source excerpts are actually present in final context;
- whether stale artifacts are detected;
- whether user feedback exposes repeatable retrieval or prompt failures.

The quality bar is not "the answer sounds good." The quality bar is that Motoko
selects the right evidence, shows why it was selected, answers from that
evidence, and leaves enough audit trail to diagnose failures.

## References

- RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval:
  <https://arxiv.org/abs/2401.18059>
- Microsoft GraphRAG:
  <https://www.microsoft.com/en-us/research/project/graphrag/>
- Modular RAG:
  <https://arxiv.org/abs/2407.21059>
- Jina-ColBERT-v2 and late-interaction retrieval:
  <https://arxiv.org/abs/2408.16672>
- Self-RAG:
  <https://arxiv.org/abs/2310.11511>
- Lost in the Middle:
  <https://arxiv.org/abs/2307.03172>
