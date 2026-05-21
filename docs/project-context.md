# Motoko Project Context

Date: 2026-05-17

Motoko was split out of `nixos-configs` into this repository so her code,
tests, and main documentation can evolve independently while NixOS keeps only
host integration policy.

## Current Role

Motoko is Javier's local terminal personal assistant for the HB3 `personal`
realm, and a small local repo-review helper for the `mares` and `javier`
realms. She is meant to feel conversational and useful for private daily notes,
documents, memory, local Qwen chat, and bounded source-repo inspection.

She is intentionally not:

- Texere;
- Hermes;
- a provider gateway;
- an autonomous host-admin agent;
- a LangChain/LangGraph application;
- a web UI.

## Host Integration

The active NixOS integration lives in `/home/javier/repos/nixos-configs`.

Current intended deployment:

- Motoko is packaged as this repository's `packages.x86_64-linux.default`.
- `nixos-configs` consumes Motoko through a private mbp111 Git flake input.
- HB3 installs Motoko for `personal`, `mares`, and `javier`.
- Motoko state is per-user under `~/.local/state/motoko`; config is per-user
  under `~/.config/motoko`.
- Motoko identity is per-user in `~/.config/motoko/config.json`; the repo name
  and executable stay `motoko`.
- `personal` has local-model access but no Hermes/provider-key group access.
- `mares` is non-sudo and can use Motoko for work/repo review without inheriting
  Javier's personal Motoko state.
- `javier` can use Motoko for admin-side NixOS review with deliberately smaller
  source-index limits.
- NixOS exposes approved local model routes through
  `~/.config/motoko/local-models.json`.
- The HB3 local model manager kind is `systemd-socket-worker`: Motoko consumes
  per-realm Unix sockets such as `unix:///run/motoko-llm/<realm>/<route>.sock`,
  while llama.cpp runs as realm-specific worker users such as `mares-llm` or
  `personal-llm`.
- Motoko may use `motoko-model list/info/verify/start/stop/status` for
  user-visible model service operations, but must not call `systemctl`
  directly or assume the current user owns llama.cpp.
- Older or ad-hoc environments can still use the loopback MTP llama.cpp
  endpoint, `http://127.0.0.1:8083/v1/chat/completions`.

Repository conventions:

- The expected development checkouts are `/home/javier/repos/motoko` and
  `/home/mares/repos/motoko`.
- The private source-of-truth remote is normally `origin =
  mbp111:/home/javier/git/motoko.git`; public mirrors such as `github` or
  `codeberg` may exist but must be verified with `git remote -v` before use.
- `mares` has normal development authority for Motoko source work and can
  commit accepted changes locally in this repository. Pushing still requires an
  explicit user request and a verified target remote.
- Deploying a new Motoko package to HB3 is separate from source development:
  Javier/admin owns the `nixos-configs` flake-input update, review, rebuild,
  and switch.

## Security Shape

Motoko's security comes from the HB3 account split and conservative local
behavior:

- no provider API keys;
- no Hermes dependency;
- no Texere dependency;
- no sudo or service-control authority;
- no database server;
- no pip/npm/runtime dependency installs;
- explicit document allowlists;
- structured per-user identity in `~/.config/motoko/config.json`;
- per-user feature permissions in `~/.config/motoko/config.json`;
- fixed read-only repo commands only in `repo-review` mode;
- source documents are read-only;
- memory, indexes, and topics stay under Motoko-owned state paths.

Pydantic, containers, and other larger machinery are deliberately absent for
now. If personal memory/RAG becomes sensitive enough to need a harder boundary,
the preferred next review is a NixOS container or KVM VM for the personal
assistant state while keeping GPU inference on the HB3 host.

## Product Direction

Motoko should become better by becoming more inspectable, trustworthy, and
ergonomic before becoming more agentic.

Accepted directions:

- source provenance for every answer;
- memory review, edit, delete, importance, pinning, and duplicate handling;
- automatic but inspectable memory maintenance;
- compacted conversations;
- explicit profile dossiers from memories and conversations;
- hierarchical document indexes;
- durable progress and ETA reporting for heavy corpus indexing;
- deterministic Org-mode task/headline/deadline signals inside corpus indexes;
- deterministic CPU lanes for parsing, fingerprints, corpus health, artifact
  upgrades, lexical retrieval, and other reliable non-LLM work;
- named local-model routes for repetitive small-model work, large-model
  synthesis/audits, and interactive chat;
- artifact provenance and quality gates for model-derived summaries before
  routing background work to smaller worker models;
- synthetic worker-model evaluation fixtures that compare route outputs without
  requiring Codex to read Javier's personal corpora;
- topic dossiers and deeper dossiers over already indexed material;
- per-user permission modes for chat-only, document reads/indexing, and
  read-only repo review;
- per-user identity labels for `personal`, `mares`, and `javier` without
  splitting the codebase or renaming the repository;
- fixed repo status/diff/log/review commands that attach bounded summaries as
  context without arbitrary shell execution;
- TTY-friendly terminal ergonomics;
- no new runtime dependencies unless the benefit is reviewed and concrete.

Avoid for now:

- autonomous file editing;
- broad filesystem crawling without explicit allowlists;
- provider/API key handling;
- browser UI;
- vector database dependencies;
- role-playing multi-agent abstractions;
- hidden background state that cannot be inspected from the CLI.

## Javier's Interface Preferences

Current UI direction:

- Motoko's name in chat should use per-user `ui.assistant_color` from
  `~/.config/motoko/config.json`, with `MOTOKO_ALIAS_COLOR` allowed as the
  NixOS-managed per-realm override; the default remains purple.
- Motoko's assistant label is `Motoko`, without a `>` suffix; color carries
  the role distinction.
- System/status lines use compact `sys`, not `System>`.
- User input prompt should be just `>`, not `You>`.
- Titles, command text, and supporting UI can be turquoise.
- Raw TTY usability matters as much as graphical terminals.
- Slash-command suggestions should visibly scroll as the selection moves.
- Emacs-style editing keys should work in the TUI:
  - `Ctrl+A` beginning of line;
  - `Ctrl+E` end of line;
  - `Ctrl+B` backward char;
  - `Ctrl+F` forward char;
  - `Alt+B` backward word;
  - `Alt+F` forward word;
  - `Ctrl+K` kill to end of line;
  - `Ctrl+Y` yank killed text;
  - `Ctrl+P` previous suggestion/history;
  - `Ctrl+N` next suggestion/history.
- Conversation lists should use compact relative times while preserving full
  timestamps in JSON state.
- Resume/list columns should be readable and compact:
  `created`, `updated`, `branch`, `conversation`.
- Recent saved conversations should be available as bounded, inspectable context
  in new chats. Durable memories remain separate from this recency recall.
- Query-focused memory dossiers should be available when Javier wants Motoko to
  study a subject across saved memories and prior conversations before
  continuing the chat.
- `/study QUERY` is the explicit bounded study command. It should prefer
  reusing existing topic or memory dossiers, then build a topic dossier from
  attached/relevant indexes, then fall back to a memory/conversation dossier.
- The TUI should show the active model badge, including MTP/port information
  such as `qwen3.6-27b-mtp:8083`.
- Background study may refresh the private context catalog, note stale indexes,
  and suggest relevant existing dossiers. Heavy background model work should be
  opt-in, such as `MOTOKO_BACKGROUND_PROFILE=1` for idle profile refreshes, so
  the background loop does not compete with active chat. It must not silently
  crawl broad new directories or build large document indexes.
- Background study should leave a durable job trail in Motoko state. For the
  current cheap catalog/planning pass, recovery means detecting the interrupted
  job, recording that fact, and recomputing from current state. Future heavier
  study jobs should use the same ledger to resume at a finer granularity.
- `/sources` should explain why context was included and show context planning
  lanes, not merely list raw source objects.
- Report-like output such as `/sources`, `/status`, `/model-routes`,
  `/identity`, `/permissions`, and retrieval diagnostics should be syntax
  highlighted at terminal render time without storing ANSI escapes in
  conversation state.
- Background memory work should report the actual phase and recover cleanly
  from interruption instead of leaving an indefinite spinner.
- The default spinner should be ASCII everywhere. Braille is an explicit opt-in
  because the Linux TTY/Terminus path can render braille as square fallback
  glyphs.

## Near-Term Next Improvement

Immediate retrieval-grounding plan:

The highest-value work is to make sure indexed corpus knowledge is actually
used reliably in chat. When Javier asks "what are tomorrow's
highest-priority tasks?", Motoko should retrieve the relevant Org/task
artifacts, show enough source provenance to be trusted, synthesize a useful
answer, and then leave an inspectable answer-grounding audit. This serves both
guiding values: it directly increases her intelligence/competence, and it is
the kind of careful, end-to-end behavior that makes her feel thoughtfully
crafted rather than merely full of background machinery.

The implementation path is:

- evaluate retrieval quality before generation, using synthetic corpus fixtures
  that prove the right files, chunks, dates, TODOs, paths, and rare terms are
  selected;
- add a deterministic answer-grounding audit to `/sources`, so each answer says
  whether it had excerpt-level evidence, only summary/memory context, stale
  context, or no usable grounding;
- add `retrieval-debug` before embeddings/rerankers, so real-use failures can
  be separated into recall, ranking, stale data, chunking, summary, or
  prompt/final-synthesis problems quickly;
- add no-model retrieval previews that show the exact selected context before
  generation, so users can tell whether the right evidence reached the prompt;
- keep final user-facing chat on the strongest configured chat route while
  smaller routes continue to help with summaries, labels, dossiers, and other
  bounded background work after they pass evals;
- make prompts cache-friendly and reuse Motoko-owned compressed context and
  output caches, while leaving true prompt/KV reuse to the NixOS llama.cpp
  service layer;
- keep auditing derived index storage alongside vector stores: report duplicate
  reference chunks, unique stored chunk bodies, logical corpus bytes, stored
  bytes, missing duplicate targets, and superseded partial/index cleanup
  opportunities. Cleanup should start as inspectable safe-GC planning, not
  aggressive deletion.
- keep embedding/reranker storage behind explicit schema, provenance,
  invalidation, migration, privacy boundaries, eval fixtures, and NixOS service
  contracts.
- treat reflection as a recurring audit layer rather than an end-of-roadmap
  feature: answer audits, retrieval audits, memory audits, stale-artifact
  checks, and later deeper model audits should keep running throughout Motoko's
  improvement path.
- grow reasoning as explicit, inspectable planning and audit behavior rather
  than hidden chain-of-thought: query decomposition, retrieval planning,
  evidence sufficiency checks, source-conflict checks, answer-grounding review,
  stale-artifact review, and memory/index audits. Reflection is one recurring
  audit component of this broader reasoning layer.

The highest-ROI next engineering improvement is improving the quality of
profile dossiers and document-derived dossiers after real personal documents
are added inside the `personal` realm. Codex should not need access to those
documents; improvements should be made through synthetic fixtures, user-visible
reports, and Motoko-owned runtime behavior. The regression suite now includes a
small fake OpenAI-compatible test server, a pseudo-terminal render harness, and
an evaluation harness for study reuse, context sufficiency, and background
study state, so Motoko can test streaming, maintenance, recall, profile, TUI,
and study behavior without requiring Qwen, llama.cpp, or Javier's personal
documents to be available to Codex.

Current sequencing notes:

- The strongest-chat-route rule is an operating constraint, not a large pending
  implementation. Keep enforcing it while routing smaller worker models only to
  bounded summary, label, dossier, and audit tasks that pass evals.
- Prompt and output caching already exists for deterministic model-derived
  background artifacts. The remaining prompt/KV-cache work belongs mostly to
  the NixOS llama.cpp service layer. Motoko reads declared route cache policy
  from `~/.config/motoko/local-models.json`, reports it in `/model-routes`,
  and keeps prompts stable, explicit, and easy to cache.
- Embedding and reranker routes are now expected to be discovered from
  NixOS-owned `~/.config/motoko/local-models.json` by `kind`, `tasks`,
  `endpoint_paths`, dimensions, and advertised parallelism. Motoko stores
  vectors only in the current user's state, keeps `lexical-hash-v1` as the
  deterministic control path, uses fresh embedding stores as additive semantic
  recall, and keeps lexical/task/path evidence visible in diagnostics.
- Javier explicitly chose on 2026-05-21 to take the measured risk of moving
  normal retrieval into hybrid embedding/rerank retrieval now, rather than
  waiting for more real-world diagnostics. Treat this as a reversible trial:
  if quality, latency, or stability fails strongly, consider reverting to
  commit `44922c3` (`Use embedding stores for retrieval`) and reintroducing
  hybrid rerank more slowly.
- The intended retrieval shape is hybrid candidate generation, not semantic
  replacement: lexical/path/date/task candidates, deterministic Org/task
  candidates, and embedding candidates should be unioned, deduplicated, and
  then reranked together. Exact and structured signals are still first-class
  because the big chat model can only reason over evidence that retrieval
  actually selected.
- Bg-heavy vectorization should use the approved embedding route efficiently:
  batch source chunks, issue concurrent embedding requests up to the
  NixOS-declared route `maxParallel`, expose batch/parallel metadata in status
  or reports, and remain bounded by the per-realm local-model service rather
  than managing llama.cpp directly.
- Dense embedding stores should be invalidated and rebuilt from saved
  source/index material when their vector schema, source fingerprint,
  embedding route, model, or dimensions change. Do not try to mathematically
  upgrade old embedding coordinates across incompatible models; treat
  re-vectorization as the inspectable heavy-work migration path.
- Embedding vector refresh should checkpoint completed rows under realm-local
  Motoko state and resume from that progress when the source fingerprint and
  embedding route/model/dimensions still match. If those keys change, discard
  the partial vector progress and rebuild from source/index material.
- User feedback should accumulate as private per-realm evaluation data. Store
  ratings and notes under the active user's Motoko state, keep them out of the
  conversation transcript, and use them to guide future retrieval/rerank/prompt
  evals. Do not let feedback directly mutate ranking behavior without an
  inspectable evaluation gate.
- Reflection should grow as specific inspectable audits: answer grounding,
  retrieval preview/debug, index storage health, memory maintenance health, and
  later model-assisted audit passes. Do not build an opaque open-ended
  self-reflection loop.

## Roadmap Candidates

The following path looks attractive, but it is not mandatory and should remain
subject to measurement: design a retrieval layer that combines lexical search,
embedding recall, reranker precision, and deterministic extraction through
NixOS-declared local model routes and Motoko-owned derived state.

This could improve more than index construction. Embeddings, rerankers, and
better token/accounting machinery could help artifact formation, memory recall,
HRAG retrieval, topic dossiers, domain-specific intelligence, and local-model
efficiency. The likely shape is:

- keep lexical/BM25-style search for exact names, dates, IDs, paths, commands,
  issue numbers, and rare terms;
- add exact or model-aware token accounting for chunk budgets, truncation
  checks, context-pressure estimates, and compression-ratio reporting, while
  keeping structure-aware chunking primary;
- consider embedding indexes for raw chunks, chunk summaries, file summaries,
  labels, entity/project names, memories, dossiers, and conversation summaries,
  keeping raw-source vectors separate from summary vectors;
- consider reranker models after lexical and embedding recall produce candidate
  chunks, so Motoko sends better-grounded, smaller prompts to the LLM;
- expand deterministic extractors for emails, URLs, paths, dates, times,
  amounts, Git hashes, issue IDs, Org metadata, and other syntax-shaped facts;
- consider parser-backed artifacts for Org, Markdown, email, source code,
  configs, package manifests, and PDFs only after the dependency tradeoff is
  reviewed;
- improve deduplication and boilerplate handling through hashing,
  normalized-text comparison, simhash/minhash-style fingerprints, email
  quote/signature stripping, and later embedding similarity if an embedding
  store exists;
- consider a content-addressed derived-text store once the storage audit proves
  it is worthwhile, so chunk text can be stored once by SHA256 while indexes
  keep per-file/per-chunk provenance references;
- use lightweight classifiers or routing models only for uncertain cases after
  deterministic file/path/content heuristics are exhausted.
- add bounded reasoning passes only when they produce inspectable artifacts:
  retrieval plans, source-grounding audits, contradiction checks, stale-context
  warnings, memory/index health audits, and later model-assisted review passes.
  Do not store hidden chain-of-thought; store concise decisions, evidence, and
  audit outcomes.

As embedding and reranker services become available, Motoko should keep the
storage format, artifact provenance, versioning, invalidation, migration, eval
fixtures, privacy/realm boundaries, and NixOS deployment shape explicit. The
point is to make the retrieval layer measurably smarter, not to accumulate
infrastructure.

## NixOS-Facing Model Boundary

Motoko has repo-local support for named model routes and deterministic
model-output caching. NixOS owns approved model files, worker users, sockets,
VRAM residency, service hardening, and llama.cpp flags. Motoko owns route
selection, provenance, quality gates, private output-cache hits, and graceful
user-visible handling of queued/loading/missing-model states. Do not fake
server-side KV caching inside Motoko; prompt-prefix/KV reuse belongs in the
deployed local model service if measurement shows it is worthwhile.

When NixOS declares route cache fields such as `route.cache.prompt`,
`reuseMinTokens`, `cacheRamMiB`, `slotPromptSimilarity`, `metrics`, and
`metrics_endpoint`, Motoko should treat them as declared service capabilities
for display and measurement. Motoko must not call `/slots`, use persistent slot
files, log request/response content, or write corpus-derived data outside the
current user's Motoko state.
