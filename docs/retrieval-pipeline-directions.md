# Possible Retrieval Pipeline Architectural Directions

Date: 2026-05-21
Last updated: 2026-09-06

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

## Research Note: delta-mem And Model-Side Online Memory

Lei et al. (2026), *delta-mem: Efficient Online Memory for Large Language
Models*, is relevant to Motoko because it challenges the assumption that all
long-horizon memory should be implemented as retrieval plus text inserted into
the prompt. It should be treated as a possible complement to Motoko's hybrid
retrieval stack, not as evidence that Motoko should replace RAG.

### What the paper does

`delta-mem` augments a frozen Transformer backbone with a small learned memory
adapter and a fixed-size online state of associative memory. The online state is
updated as new tokens or interaction segments arrive. Its write rule is based
on a gated delta rule: information that the state already predicts produces a
small update, while the residual or surprising part produces a larger write.
The current hidden state also controls how strongly old state is retained.

At read time, the current hidden state queries the associative memory state. The
readout does not return source text. Instead, learned projections turn it into
low-rank corrections on the query and output sides of the backbone's attention
computation. The paper studies token-state, sequence-state, and multi-state
write strategies, which provide different trade-offs between recency, noise,
and interference.

The headline configuration uses an 8 x 8 online memory state. On the paper's
Qwen3-4B-Instruct benchmark suite, the best delta-mem variant raises the reported
average from 46.79 to 51.66. MemoryAgentBench rises from 29.54 to 38.85 for the
best variant on that benchmark, and LoCoMo from 40.79 to 49.12. A BM25 RAG
baseline is also included and scores below the frozen backbone in that specific
experimental setup. That result is useful evidence that naive text retrieval
can be noisy, but it should not be generalized into "delta-mem beats RAG" for
Motoko: Motoko's current retrieval stack is substantially more structured than
that BM25 baseline, and Motoko has provenance and deterministic-truth
requirements that an opaque associative state cannot satisfy by itself.

The method is lightweight relative to full fine-tuning, but it is not a
zero-training or prompt-only technique. The paper reports about 4.87M trainable
parameters for its rank-8 SSW/TSW configurations (about 0.12% of the 4B
backbone) and 19.47M for MSW (about 0.48%). The public implementation currently
ships a delta-mem adapter for Qwen3-4B-Instruct-2507.

### Fit with current Motoko

Motoko currently talks to operator-approved local llama.cpp routes and treats
retrieved source evidence, provenance, deterministic Org/task/date signals, and
inspectability as first-class requirements. A faithful delta-mem implementation
would therefore not be a drop-in change to `motoko_core/retrieval_service.py`.
It requires model-specific trained projections plus inference-time access to
hidden states and attention computation, so it belongs primarily at the model
runtime/backend boundary.

The most promising architecture is consequently two-channel memory:

1. **Explicit evidence memory:** Motoko's existing HRAG/retrieval path remains
   authoritative for facts that must be inspectable, source-linked, dated,
   quoted, contradicted, deleted, or audited.
2. **Implicit associative state:** a delta-mem-like mechanism may eventually
   provide cheap history-conditioned steering, helping the model carry useful
   patterns or associations without injecting every relevant historical token
   into the active prompt.

This separation is especially compatible with the deferred
`Production-grade long-horizon personal memory and adaptive recall` project in
`docs/deferred-projects.md`. Raw historical evidence must remain recoverable and
authoritative even if an online latent state becomes useful for steering.

### Ideas worth borrowing before model-runtime integration

Several ideas are applicable to Motoko even if delta-mem itself is not yet
supported by the serving stack:

- **Separate memory state from memory steering.** Motoko already spends effort
  on what to store and retrieve. Evals should also distinguish whether correct
  evidence was retrieved from whether the selected evidence actually changed
  the final answer in the desired way. This mirrors the paper's distinction
  between memory representation and how memory influences the backbone.
- **Residual/novelty-aware writes.** The delta rule suggests a useful heuristic
  for derived memories, dossiers, and summaries: avoid repeatedly writing
  information already represented, and spend update budget on new,
  contradictory, or prediction-error-like information. Any Motoko version must
  preserve provenance rather than treating novelty scores as truth.
- **Multiple memory timescales/states.** The paper's multi-state variant is a
  useful design prompt for Motoko's explicit memory hierarchy: recent working
  state, conversation/episode state, and durable topic/person/project state may
  deserve separate update rates and retention policies rather than one blended
  summary.
- **Fixed-cost associative side signal.** A Motoko-native experiment could test
  a very small per-realm associative state over existing embedding-space
  signals and use it only as an additional candidate/rerank feature. This would
  not reproduce delta-mem, because the paper's benefit comes from coupling the
  state to hidden activations and attention. It would be a separately evaluated
  systems hypothesis, and retrieved source spans would remain the evidence.
- **Benchmark memory mechanisms against each other.** LoCoMo and
  MemoryAgentBench are useful external references for future eval design. For
  Motoko, the more important gate is an internal long-horizon suite that
  measures exact historical recall, chronology, contradiction handling,
  ranking, answer grounding, source provenance, latency, and failure recovery.

### Possible future experiment

Do not replace the current hybrid retrieval system with delta-mem now. Keep the
paper on the research watchlist and consider a backend experiment when all of
the following are true:

- a compatible adapter exists for a Motoko-approved local backbone, or there is
  a justified plan to train one;
- the local serving runtime can expose or implement the required online-memory
  read/write and attention-correction hooks without weakening the NixOS-owned
  model boundary;
- the online state has explicit realm/conversation lifecycle semantics,
  including reset, deletion, persistence, migration, and crash behavior;
- evaluation compares `HRAG only`, `associative state only` where meaningful,
  and `HRAG + associative state` rather than treating the mechanisms as
  mutually exclusive;
- gains survive Motoko's provenance and source-grounding requirements and are
  large enough to justify the added runtime and model-specific complexity.

If those gates are met, delta-mem is attractive precisely because it may let
Motoko reserve prompt tokens for high-value explicit evidence while carrying a
small amount of additional historical signal outside the text context.

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
present in sample-journal.org". The retrieval layer could find `sample-journal.org`, but the
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

Motoko also ships the built-in `org-structural-query` skill with the
`builtin:org_structural_query` handler. It is the same architecture applied to
natural-language Org structure questions: the user can ask for entries or tasks
with a tag, TODO state, priority, deadline, scheduled timestamp, dated heading,
or named Org source without typing an Org query language. The handler parses
Org headings and inherited tags programmatically, selects bounded evidence rows,
records the activated skill/handler in `/sources`, and lets the final model
synthesize from that evidence. Evidence stores moved to `evidence-store-v2` /
`evidence-input-v2`, and embedding inputs moved to `embedding-input-v3`, so old
evidence/vector artifacts are rebuilt by the existing background refresh path
rather than silently reused with weaker Org metadata.

Motoko now has an internal review-first `skill_manage` action layer for
`create`, `patch`, `write_file`, and `remove_file` suggestions. Support files
are useful for preserving references, templates, and script-like deterministic
procedures under an existing skill package. They are inspectable with
`motoko skill support`, and bounded matching excerpts may be selected as
`skill-support` sources when the parent skill is relevant. They remain stored
text assets unless a later reviewed runner gives them bounded execution
authority. Scripts must not become broad shell execution, cross-realm access,
or a way around document allowlists.

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

- Lei, J., Zhang, D., Li, J., Wang, W., Fan, K., Liu, X., Liu, Q., Ma, X., Chen,
  B., and Poria, S. (2026). *delta-mem: Efficient Online Memory for Large
  Language Models*. arXiv:2605.12357:
  <https://arxiv.org/abs/2605.12357>
- Official delta-mem implementation:
  <https://github.com/declare-lab/delta-Mem>
- Di Zhang post that prompted this research note:
  <https://x.com/di_zhang_fdu/status/2096496854255226927>
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
