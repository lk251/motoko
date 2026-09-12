# Motoko Personal-Conversation Long-Horizon Handoff

This handoff is intentionally generic. It contains no user-specific names, relationship history, life events, private correspondence, or other personal details. Use synthetic or explicitly authorized fixtures for evaluation.

## Goal

Turn Motoko into an excellent local system for very long, text-heavy personal conversations, including careful advice about interpersonal and relationship questions.

The intended downstream model today is approximately Qwen3.8-27B running locally. Future local models will be stronger, so the harness should remain model-agnostic and improve as the reasoning model improves.

Do not begin by assuming this is merely a new RAG pipeline, and do not begin by creating a new repository. First inspect the existing Motoko architecture and all current or deferred work related to long-horizon memory, retrieval, conversation compaction, context management, and agentic recall. Then decide the right architecture from evidence.

## Desired behavior

The target workload has characteristics such as:

- months or eventually years of conversational history;
- mostly text;
- many thousands of user/assistant turns;
- changing facts and circumstances;
- recurring people, relationships, events, themes, decisions, and preferences;
- earlier interpretations that may later turn out to have been wrong;
- important direct quotations and exact wording;
- repeated discussion of the same topic over time;
- large quantities of low-signal discussion around a smaller amount of high-value evidence;
- questions whose answer may depend on information far outside the active context window.

The system must not solve this by stuffing the entire history into every prompt, nor by treating one recursively compressed summary as the authoritative past.

The desired shape is:

```text
bounded active context
    +
small trustworthy working state / notes
    +
lossless searchable historical windows
    +
model-directed iterative retrieval
```

For a difficult query, the reasoning model should be able to:

1. understand the current question and currently available context;
2. notice which historical information may be missing;
3. formulate targeted information needs or search queries;
4. search the appropriate historical sources;
5. inspect the returned evidence;
6. follow adjacent turns or source references when necessary;
7. reformulate or issue additional searches when the first retrieval is insufficient;
8. explicitly decide when enough evidence is present;
9. only then produce the final answer.

This must be bounded and inspectable, not an uncontrolled recursive agent.

## Phase 0: inspect everything before designing

Before changing code:

- update your understanding of current `master`;
- read `AGENTS.md` and relevant architecture/project-context documentation;
- inspect all local and remote branches and all worktrees, not only branches visible on GitHub;
- run `git branch -a` and `git worktree list`;
- inspect relevant diffs and branch-specific work-item notes;
- do not assume unpushed `codex/*` branches are absent.

At minimum investigate:

- `feature/adaptive-episodic-recall`;
- `docs/adaptive-episodic-recall.md` on that branch;
- `docs/deferred-projects.md`;
- `docs/retrieval-pipeline-directions.md`;
- `docs/recuris-experiential-working-memory-research-note.md`;
- `docs/selective-forgetting-memory-research-note.md`;
- `docs/procedural-graphs-research-note.md`;
- every other research note or bibliography item concerning memory, retrieval, long context, context rollover, episodic memory, working memory, adaptive recall, agentic retrieval, RAG, reranking, query planning, or context compression.

Also inspect the locally preserved/deferred branches mentioned in `docs/deferred-projects.md`, where available, especially:

- `codex/memory-source-lifecycle`;
- `codex/episodic-history-durability`;
- `codex/recall-quality-gates`;
- any newer branches or worktrees created since that document.

Read underlying papers when necessary instead of relying only on Motoko's summaries. Determine whether newer research changes the design.

Also inspect the recent open-source OpenAI Codex experimental context-management implementation, especially:

- history tools;
- notes tools;
- context-window IDs;
- token-budget or fresh-context rollover;
- model-directed recovery of earlier windows.

Separate useful architectural ideas from components that depend on OpenAI's private backend. Motoko needs a fully local, Motoko-owned equivalent.

## Phase 1: make an architecture decision

Before implementation, write a concise decision comparing:

A. a separate new harness/repository;
B. a separate Motoko fork or long-lived variant;
C. a first-class modular capability inside Motoko, activated through a profile/mode;
D. another architecture if clearly superior.

The working hypothesis is:

```text
Motoko
  + general long-horizon memory/context subsystem
  + personal-conversation profile
```

Treat this as a hypothesis, not an instruction. Reject it if repository inspection shows a compelling reason.

Also decide explicitly whether the feature should be understood primarily as:

- a retrieval pipeline;
- a memory subsystem;
- a context-management subsystem;
- an agentic retrieval loop;
- or a composition of those things.

Define the boundaries.

## Epistemic layers

Preserve at least these separately:

### 1. Raw episodic evidence

Actual user/assistant turns and explicitly imported correspondence. This is authoritative for what was actually said.

### 2. Derived durable knowledge

Stable preferences, facts, decisions, recurring entities, and similar durable material. Derived items should retain provenance where practical.

### 3. Working state

What matters to the current conversational problem: open questions, current situation, unresolved decisions, active hypotheses, and latest direct evidence.

### 4. Interpretations and hypotheses

Model conclusions must remain distinguishable from direct evidence. A plausible interpretation repeated in summaries must not silently become a fact.

### 5. Recent active context

A bounded recent conversational suffix for conversational continuity.

Older raw history must remain recoverable after compaction. Summaries are indexes or hints, not replacements for original evidence.

## Personal-conversation requirements

### Chronology

Questions often depend on temporal ordering. Timestamp and ordinal information should be strong retrieval signals.

### Supersession and correction

Later information may weaken, replace, or contradict earlier beliefs. Retrieval must not treat old and current states as equally authoritative.

### Direct evidence versus interpretation

Support distinctions such as:

```text
user_statement
correspondent_statement
quoted_correspondence
observed_event
assistant_interpretation
user_hypothesis
assistant_hypothesis
preference
decision
plan
open_question
settled_conclusion
```

Do not require every historical turn to be perfectly classified at ingestion time. These may be derived metadata or indexes over canonical raw history.

### Repeated low-signal analysis

A long conversation may contain hundreds of turns about ambiguous, low-signal material. The system should be able to retain the conclusion that a class of evidence was judged low-signal without letting repetition make it appear more evidentially important.

### Exact recall

Sometimes exact wording matters. Preserve source spans and neighboring turns.

### Pattern comparison

Some questions require retrieving multiple earlier episodes rather than a single semantically nearest chunk. The planner should be able to request a set of episodes and compare them chronologically.

## Model-directed / agentic retrieval

Evaluate at least these two styles:

### A. Planner-based adaptive recall

```text
initial context
  -> planner
  -> retrieval
  -> planner/sufficiency check
  -> optional second retrieval
  -> final answer
```

### B. Tool-using main-model loop

Give the answer model bounded tools conceptually like:

```text
history.search(...)
history.read(...)
history.expand_neighbors(...)
memory.search(...)
dossier.read(...)
timeline.search(...)
notes.read(...)
```

Allow iterative use before answering.

Determine experimentally which design works better with a local ~27B model given quality, latency, context use, and implementation complexity. A hybrid is acceptable.

Regardless of implementation:

- keep retrieval plans/actions inspectable;
- do not store or expose hidden chain-of-thought;
- enforce code-owned call/token/time/result budgets;
- prevent infinite retrieval loops;
- deduplicate already-seen evidence;
- maintain stable provenance IDs;
- allow the planner to say `sufficient`;
- allow it to say `need_more_context`;
- make premature stopping measurable in evals.

## Retrieval architecture

Do not reduce historical search to embeddings alone.

Evaluate a hybrid system containing, where useful:

- exact / lexical / BM25 retrieval;
- dense semantic retrieval;
- hierarchical retrieval over conversation -> episode/window -> turn/span;
- timestamp and ordinal filtering;
- named-entity cues;
- topic/conversation/thread filters;
- adjacent-turn recovery;
- candidate fusion;
- local reranking;
- optional query decomposition;
- optional relationship/temporal side indexes;
- explicit source-span recovery before final synthesis.

Use the research already in the repository to decide which techniques deserve implementation.

In particular:

- do not replace raw turns with a knowledge graph;
- if a graph is useful, treat it as a provenance-linked side index;
- consider hot/warm/cold treatment of rebuildable derived indexes rather than destructively forgetting personal history;
- consider Recuris's lesson that explicit working state may be more valuable than simply accumulating more memories;
- do not introduce procedural-graph machinery into personal conversation unless evaluation demonstrates a relevant benefit.

## Context assembly

Design a deliberate context package rather than concatenating top-k chunks.

A likely package may contain:

- system/personality/profile;
- stable high-value personal context;
- current typed working state;
- recent active conversation;
- compact thread/window summary as a navigation hint;
- directly retrieved raw evidence;
- optionally selected durable memories/dossiers;
- provenance or confidence information required by the model.

The final context should privilege relevant source evidence over redundant derived summaries. Measure context-token cost explicitly.

## Personal-conversation profile

Keep domain behavior separate from generic retrieval machinery.

Do not contaminate repository/code/NixOS behavior with personal-conversation-specific heuristics.

Prefer something conceptually like:

```text
generic Motoko memory/retrieval/context infrastructure
                  |
          domain/profile policy
          /                 \
    repository/code       personal-conversation
```

The personal profile may adjust retrieval weighting, temporal/entity handling, prompt guidance, working-state schema, evidence-type priors, and answer behavior. Canonical storage, provenance, retrieval APIs, lifecycle, and security should remain general where possible.

Do not overfit the profile to any one person, relationship, or real-life history.

## Evaluation is required

Do not judge the architecture by whether a few demonstrations feel good.

Build a synthetic or sanitized long-horizon personal-conversation evaluation suite containing months of simulated history, multiple people and topics, repeated discussions, contradictory hypotheses, corrections, changing plans, distractor material, and old but important facts.

Include cases such as:

- recall an old but decisive event;
- compare several earlier episodes;
- reconstruct chronology around an event;
- identify the latest state after older statements were superseded;
- recover exact quoted wording;
- distinguish direct evidence from an old model hypothesis;
- remember an established user preference;
- remember a decision already made and avoid reopening it unnecessarily;
- ignore a large volume of semantically similar but low-signal distractors;
- retrieve a rare important fact despite recency bias;
- detect that current context is already sufficient and perform no extra retrieval;
- detect that context is insufficient and retrieve;
- perform a second search because the first search changes the information need.

Measure separately:

- evidence recall;
- precision / distractor contamination;
- temporal-order accuracy;
- supersession accuracy;
- hypothesis-as-fact errors;
- final-answer faithfulness to retrieved evidence;
- planner failure to notice missing context;
- poor planner query;
- retrieval miss;
- reranking miss;
- premature stopping;
- correct evidence retrieved but ignored;
- context tokens;
- model calls;
- latency.

Compare at minimum:

1. current `master` behavior;
2. current adaptive-episodic-recall experiment;
3. the proposed improved architecture;
4. planner disabled versus enabled;
5. where practical, an oracle-evidence condition that supplies the correct historical evidence directly, so retrieval limitations can be separated from reasoning-model limitations.

## Implementation and Git rules

After the architecture review:

- continue on the dedicated `motoko-personal` branch or create a subordinate worktree from it as appropriate;
- do not merge to `master`;
- preserve useful work from existing experimental/deferred branches rather than blindly reimplementing it;
- port or cherry-pick only after understanding branch divergence;
- keep commits logically separated;
- add migrations for state/schema changes;
- preserve deletion/privacy semantics;
- run focused tests plus `nix flake check`;
- document remaining risks and failed experiments.

If foundational hardening work in deferred branches is required before the feature can safely work, integrate or finish that foundation on this feature branch rather than bypassing it.

Pay particular attention to:

- raw episodic-history durability;
- memory/profile invalidation after correction or forgetting;
- retrieval quality gates;
- stale/deleted evidence;
- bounded scanning of very long histories.

## Deliverables

Before substantial implementation, create:

`docs/personal-conversation-long-horizon-design.md`

It should contain:

- repository and research findings;
- architecture alternatives;
- chosen architecture and rationale;
- existing branch work to reuse;
- data model;
- retrieval loop;
- context assembly;
- evaluation design;
- migration/privacy implications;
- implementation phases.

Then implement the smallest coherent version needed to test the central hypothesis.

Do not implement every research idea at once.

The central hypothesis is:

```text
A bounded local model with lossless episodic history,
trustworthy working state, and intelligent iterative retrieval
can answer long-running personal-conversation questions substantially
better than the same model relying on recent context plus one summary
or ordinary one-shot RAG.
```

Prioritize proving or disproving that hypothesis.

When finished, report:

- architecture decision;
- exact branch and commits;
- existing Motoko work reused;
- research ideas accepted or rejected and why;
- evaluation results against baselines;
- known failure modes;
- recommended next experiment;
- whether this should eventually merge into general Motoko or remain an optional profile.