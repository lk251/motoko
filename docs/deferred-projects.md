# Deferred Strategic Projects

Date: 2026-09-09

This file preserves important Motoko projects that are intentionally deferred rather than abandoned. Agents working in this repository should read it before making substantial changes to memory, retrieval, context management, conversation storage, model orchestration, or long-running chat behavior.

Deferred means: do not assume the project should be implemented immediately or displace current hardening work, but do not delete, narrow, or contradict the direction without an explicit design decision.

## Local ~27B NixOS engineering agent for `nixos-configs`

Status: deferred design and evaluation project. See
[`docs/nixos-configs-local-engineering-agent.md`](nixos-configs-local-engineering-agent.md).

The narrow goal is to make locally served Qwen3.8-27B and future models in the
same practical size/hardware class as capable as possible when working on the
separate `nixos-configs` repository and the NixOS systems it declares. The
project deliberately reframes the problem from "better repository RAG" to a
NixOS-specific engineering Agent-Computer Interface with deterministic Nix
semantics, worktree isolation, validation, Git/source evidence, optional
retrieval, and eventually bounded live-system observation and reviewed actions.

Prototype and benchmark this externally before assuming it belongs inside
Motoko. The linked design compares OpenHands SDK and the already integrated
OpenWorker path, defines a private `nixos-configs` eval/ablation plan, and
preserves Motoko's current no-arbitrary-shell/no-host-admin boundary unless a
later explicit design review changes it.

## Prioritized hardening and memory work, 2026-09-08

Implementation is **deferred at the maintainer's request** after the initial
parallel work session. The ranked requirements below remain the future queue.
Useful implementation and tests are committed in independent local
branches/worktrees; the saved-work table records exact revisions and remaining
gaps. Incomplete work must remain unmerged. Passing existing tests alone does
not complete an item's acceptance criteria. Completing this queue does not
implicitly enable the full experimental adaptive-recall system or abandon the
strategic project below.

This ordering follows the repository's values: improve intelligence by keeping
evidence correct and recoverable; make everyday controls dependable; enforce
the operator's declared authority; then measure more ambitious recall. The
initial audit covered all major subsystems at `3fe714e` and the experimental
memory branch at `1aaea10`, using synthetic state and local test endpoints.
It was not an exhaustive line-by-line verification or a live private-data audit.

1. **Memory corrections and forgetting must propagate to derived context.**
   Status: **deferred, incomplete**. Branch: `codex/memory-source-lifecycle`.
   Editing or forgetting a memory currently leaves obsolete profile text in
   later prompts; automatic profile refresh compares new source IDs and misses
   edits and removals. Declare source revisions/dependencies for profiles and
   memory dossiers, immediately exclude invalid derived context, and preserve
   unaffected artifacts. Include conservative legacy handling, bounded light
   CPU invalidation/migration, and visible resumable heavy rebuilding. Acceptance
   must exercise the actual next prompt after edits/deletion, transitive dossier
   dependencies, restart, source changes during rebuilding, and unrelated
   artifact preservation. Forgetting a curated memory does not silently delete
   independent original documents or conversation evidence.

2. **Preserve raw conversation evidence across compaction and interruption.**
   Status: **deferred, incomplete**. Branch: `codex/episodic-history-durability`.
   Extract and harden the raw-history foundation from
   `feature/adaptive-episodic-recall` without enabling its model planner. Archive
   raw turns durably before replacing active context with a summary/recent
   suffix. Preserve stable message IDs, ordinals and context-window lineage;
   ensure idempotence across repeated saves, retries, restart and stale
   snapshots. Recover or fail visibly on truncated tails/read errors, enforce
   durable write ordering, and keep ordinary append work independent of the
   conversation's full lifetime length. Include bounded resumable legacy
   migration in the light lane and complete owned-sidecar/cache deletion.
   Already discarded historical turns cannot be reconstructed; document that
   limitation. Verify recovery and migration using synthetic histories.

3. **Cancellation must interrupt stalled model and tool I/O.**
   Status: **implemented and validated locally; review deferred**.
   Branch: `codex/cancel-stalled-io`.
   The current stop path can block the terminal input/render owner while
   closing an HTTP response whose worker is stuck reading. Give transport
   cancellation a bounded unblock/cleanup path across headers, streaming and
   nonstream responses on supported TCP and Unix transports. Verify that
   `/stop` and Ctrl+C restore usable input, clear queued prompts, release model
   residency, preserve interrupted state and permit the next answer. Cover
   stalled streams in PTY tests. Also harden the approved skill runner's stdin
   backpressure and live output bounds; cancellation/timeouts must cover input
   delivery and collection, with an explicit descendant cleanup policy and
   durable results. Keep these runner changes within the existing authority
   contract and use separately scoped commits where appropriate.

4. **Enforce goal scope and cumulative budgets during execution.**
   Status: **deferred, incomplete**. Branch: `codex/goal-scope-budgets`.
   A goal scoped to one project currently accepts confirmed writes into a
   different globally allowlisted project; resumed model planning can exceed
   its consumed call allowance. Intersect global permissions, canonical goal
   scope, effects, tools and current confirmation in explicit execution,
   proposal validation, apply, managed worktrees and resume. Reserve/persist
   spending before starting calls, retain consumed budgets after interruption,
   and enforce elapsed-time limits with documented pause semantics. Acceptance
   includes cross-project refusal, legitimate scoped worktree operations,
   exhausted/retried/resumed budgets and adversarial action-eval fixtures.

5. **Strengthen retrieval and adaptive-memory evaluation before rollout.**
   Status: **deferred, not started**. Branch: `codex/recall-quality-gates`.
   Extend the small positive-only retrieval gate with distractor corpora larger
   than retrieval budgets, expected/forbidden evidence, ranking measurements,
   temporal/exact facts, corrections, stale/deleted sources, scope changes and
   final prompt packing. Treat feedback as reviewed fixture seeds rather than
   assuming previously selected sources are correct. Distinguish evidence
   availability from correct final-answer use. Add bounded synthetic long
   histories and planner-off/planner-on comparisons for adjacent-turn recall,
   raw-evidence/summary conflicts, latency, calls, cancellation and budgets.
   The experimental branch must not reuse deleted or out-of-scope cached text,
   call a model from no-model preview, hide planner diagnostics, or perform
   unbounded lifetime scans before rollout. Preserve inspectable plans and
   failure diagnostics. Live answer-quality measurements must use synthetic or
   deliberately authorized private fixtures and approved model routes.

Every completed implementation needs relevant focused regressions, the
applicable evaluation/PTY gates, and `nix flake check` before committing code.
Branch notes must record implementation, validation evidence, remaining work
and merge readiness. Broad facade refactoring, new research integrations and
larger memory abstractions remain below these concrete repairs in this queue.

### Saved work and resumption notes

All five review branches start from the documentation baseline `4194832`.
Their implementation has not been merged into master or pushed. Worktree paths
below are relative to the primary checkout; `git worktree list` reports their
current absolute locations. Keep the branches and worktrees for future work.

| Priority | Local branch | Saved commit | Worktree | Snapshot status |
| --- | --- | --- | --- | --- |
| 1 | `codex/memory-source-lifecycle` | `12cf12d` | `../motoko-memory-source-lifecycle` | Incomplete implementation; checks pass |
| 2 | `codex/episodic-history-durability` | `59302c5` | `../motoko-episodic-history-durability` | Incomplete implementation; checks pass |
| 3 | `codex/cancel-stalled-io` | `696a6aa` | `../motoko-cancel-stalled-io` | Implemented and validated locally; review pending |
| 4 | `codex/goal-scope-budgets` | `81a48fe` | `../motoko-goal-scope-budgets` | Incomplete implementation; checks pass |
| 5 | `codex/recall-quality-gates` | `635d2e5` | `../motoko-recall-quality-gates` | Requirements only; no implementation |

Each branch contains `docs/work-items/<branch-suffix>.md`, with its full
acceptance checklist, implementation notes and remaining work. For example:

```bash
git show codex/memory-source-lifecycle:docs/work-items/memory-source-lifecycle.md
git diff 4194832..codex/memory-source-lifecycle
```

- **Memory lifecycle:** source revision manifests, transitive profile/dossier
  dependencies, prompt-time suppression, bounded light migration and durable
  heavy rebuild jobs are saved. Six focused lifecycle tests cover next-prompt
  changes, interruption/checkpoint reuse, restart and deleted targets. Remaining:
  independent review, broader changed-source/checkpoint isolation, migration
  fairness, empty-source handling, prompt/report coverage and cleanup review.
- **Raw history:** a standard-library SQLite store saves immutable raw evidence
  and context-window lineage before replacing the active JSON projection.
  Recovery, deletion tombstones, initial light migration and nine focused tests
  are saved. Remaining: shared mutable conversation races, real crash/concurrent
  process coverage, strict experimental JSONL import, truly bounded discovery
  and oversized migration, pagination boundary coverage and cleanup audit.
  Old turns already discarded by legacy compaction cannot be recreated.
- **Cancellation:** request-owned socket shutdown keeps the terminal owner out
  of blocking response close. The approved runner bounds stdin delivery,
  output capture and process-group cleanup. TCP/Unix stalled-header/body,
  TLS-handshake, real PTY recovery and durable runner-result checks passed.
  Review the direct-endpoint policy (no environment proxy or redirects), the
  platform resolver limitation and process-group containment limits in the
  branch note. Combined goal-budget deadline behavior remains untested.
- **Goals:** canonical scope checks, worktree mappings, per-run locks, durable
  spending reservations, deadline tokens and additive legacy upgrades are
  saved with twelve focused tests. Remaining: a direct-helper confirmation gap
  in `apply_goal_run_record`, planner step-accounting consistency, adversarial
  action-eval fixtures, broader managed-worktree/migration coverage and the
  independent execution-boundary review. The normal CLI apply path still
  checks confirmation; the new helper needs its own refusal check.
- **Recall evaluation:** only the acceptance note is saved. Begin here after
  higher-priority foundations are ready. The original experiment remains at
  `feature/adaptive-episodic-recall` (`1aaea10`), in
  `../motoko-adaptive-episodic-recall`. Its cache invalidation, no-model preview,
  unbounded history scans and planner diagnostics still need the review and
  gates described above.

All four code snapshots passed `nix flake check` on x86_64-linux before their
preservation commits, including relevant syntax, regression, evaluation and
terminal checks. Other platforms were not executed. The requirements-only
branch passed documentation whitespace validation. No live model or private
corpus was used for these checks.

Resume one branch at a time from its work-item note. The memory, archive and
goal commits are explicitly WIP. Review overlaps in the main facade and state
helpers when integrating; independently passing branches are not evidence that
their combination is correct. In particular, validate memory invalidation
against archived conversation revisions and goal deadlines against the new
transport cancellation before any combined merge.

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
