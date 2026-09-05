# Deferred Strategic Projects

Date: 2026-09-05

This file preserves important Motoko projects that are intentionally deferred rather than abandoned. Agents working in this repository should read it before making substantial changes to memory, retrieval, context management, conversation storage, model orchestration, or long-running chat behavior.

Deferred means: do not assume the project should be implemented immediately or displace current hardening work, but do not delete, narrow, or contradict the direction without an explicit design decision.

## Production-grade long-horizon personal memory and adaptive recall

Status: deferred strategic project. An experimental foundation exists on `feature/adaptive-episodic-recall`; see `docs/adaptive-episodic-recall.md` on that branch.

### Goal

Motoko should support very long personal conversations—potentially months or years of correspondence, life discussion, relationship analysis, projects, and decisions—without requiring the active model prompt to contain the entire history and without allowing one lossy summary to become the only surviving representation of the past.

The target behavior is not merely “better RAG.” Motoko should be able to notice that an answer depends on information she does not currently have in working context, formulate specific retrieval questions in light of the problem she is solving, search the private historical corpus for those missing facts, inspect the returned evidence, refine the search if necessary, and only then synthesize the answer.

For personal correspondence and relationship/life analysis in particular, raw historical evidence must remain distinguishable from Motoko-authored summaries, hypotheses, memories, and interpretations.

### Experimental foundation

The feature branch establishes several important candidate invariants:

- append-only realm-local raw episodic conversation history;
- stable message IDs, ordinals, context-window lineage, and content hashes;
- non-destructive compaction: summaries remain continuity hints while raw turns survive;
- a bounded structured recall planner that can ask targeted questions about older history;
- up to two inspectable recall rounds with adjacent-turn recovery;
- content-safe source provenance for recovered history;
- raw conversation evidence taking precedence over conflicting model-generated summaries;
- a failure taxonomy suitable for `/down`, retrieval-debug, and eval-driven iteration;
- a session kill switch and bounded resource use.

This foundation should be reviewed through real use before being treated as the final architecture.

### Deferred build-out

The longer-term project should investigate and, where evals justify it, build the following.

1. **Unify episodic history with Motoko's HRAG stack.** Raw messages, exchanges, context windows, conversations, and cross-conversation topics should become first-class retrievable evidence objects. Preserve lexical/exact search, but allow embeddings, hierarchical retrieval, reranking, temporal filters, entity cues, and source-span selection to participate when they measurably improve recall.

2. **Generalize model-directed retrieval beyond conversation text.** The reasoning model should be able to formulate bounded retrieval questions over the appropriate private sources: episodic history, durable memories, memory dossiers, indexed documents, topic dossiers, structured tasks/dates, and other allowed evidence. The model chooses what it needs; code-owned retrieval services enforce scope, budgets, and provenance.

3. **Add a typed working-state / notes layer.** Preserve useful state across context-window resets without conflating different epistemic categories. Candidate types include `direct_fact`, `user_statement`, `quoted_correspondence`, `preference`, `decision`, `plan`, `hypothesis`, `interpretation`, `open_question`, and `current_working_state`. Notes should carry source message IDs where possible, creation/confirmation timestamps, supersession links, and validity intervals when relevant.

4. **Make context-window rollover a first-class mechanism.** Long chats should be able to start a clean active model context while retaining a small trustworthy bootstrap: identity/personality, stable profile, high-value memories, working state, a compact thread/window hint, recent turns, and fresh query-specific retrieval. Earlier windows remain searchable rather than being irreversibly compressed into one summary.

5. **Support bounded multi-hop recall.** For difficult questions, allow the model to decompose the information need into multiple explicit subquestions, retrieve separately, inspect the evidence, and perform another bounded lookup when the first evidence changes what should be asked. Keep the plan inspectable; do not store hidden chain-of-thought.

6. **Improve temporal and relational retrieval for personal history.** Long-running personal use needs strong handling of chronology, repeated patterns, named people, relationships, prior periods with similar dynamics, commitments, plans, contradictions, and how earlier uncertainties eventually resolved. Prefer deterministic time/source metadata when available and model-derived relationships only when provenance remains visible.

7. **Preserve epistemic provenance.** A user's or correspondent's direct statement is not the same thing as Motoko's interpretation. A hypothesis that was plausible three months ago must not harden into a fact simply because it was summarized repeatedly. Raw evidence should remain reachable from derived memories and notes, and conflicts should be surfaced rather than silently reconciled.

8. **Build long-horizon evals from real failure classes.** Extend the existing retrieval/feedback framework to distinguish at least: planner failed to notice a knowledge gap; poor retrieval question; search recall failure; ranking failure; correct evidence retrieved but ignored; premature stopping; stale derived memory; summary/history conflict; temporal confusion; and interpretation treated as fact. Use private user feedback as eval fixtures without exposing the underlying corpus.

9. **Optimize latency and model routing only after quality is measurable.** The highest-quality chat/reasoning model may be the right recall planner for difficult personal questions, while cheaper local workers may be appropriate for indexing, embeddings, candidate generation, or maintenance. Route decisions should be evidence-driven and should not weaken recall quality simply to save a model call.

10. **Keep the system local, inspectable, and user-controlled.** Conversation deletion must delete owned episodic sidecars and derived artifacts. `/sources` and debugging surfaces should explain why historical evidence was retrieved without unnecessarily reproducing private correspondence. New background indexing or memory maintenance must remain bounded, visible, pauseable, and realm-local.

### Non-goals

- Do not solve long-horizon memory by stuffing an ever-growing transcript into every prompt.
- Do not make summaries or memories the authoritative replacement for raw history.
- Do not add hidden autonomous loops or stored chain-of-thought.
- Do not require a cloud memory backend, provider API keys, or a database server.
- Do not add a vector database dependency merely because the corpus is large; use existing dependency-light stores until measured requirements justify a reviewed change.
- Do not allow model-generated interpretations of personal events to masquerade as direct evidence.

### Success criteria

This project is successful when a user can maintain extremely long personal conversations with Motoko and reasonably expect that, when an old detail becomes relevant, Motoko can recover the right underlying evidence even if it was not selected by the initial prompt or preserved in a summary. Retrieval should be bounded and auditable, raw evidence should remain authoritative, and failures should leave enough structured diagnostics to improve the system iteratively.

The desired end state is not that Motoko “remembers everything in context.” It is that she can reliably determine what she needs to remember, recover it from an effectively unbounded private history, and distinguish what actually happened from what she or the user once inferred about it.
