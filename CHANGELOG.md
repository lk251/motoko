# Changelog

Motoko keeps a concise, user-facing changelog here because commit messages are
not the easiest place to review what changed after a long work session.

## Unreleased

- Expanded the agentic capability design note with the accepted skill package
  format, including the Hermes Agent comparison and Motoko's stricter
  per-script metadata and approval-contract path.
- Accepted the planner-boundary design for agentic capabilities: model plans
  must become typed Motoko action records, and code-owned validators decide
  what may run.
- Accepted the remaining agentic runner review items: realm/filesystem
  boundaries, scrubbed tool environments, session-repeat approvals, private
  ledgers, provenance, incremental evals, and the NixOS capability boundary.
- Added per-request llama.cpp thinking controls for the main chat route, with
  `MOTOKO_REASONING=off|low|default|high|max` presets and live dimmed
  `reasoning_content` display under an active `Thinking` TUI phase without
  storing reasoning text in conversations or content-free telemetry.
- Documented the remaining retrieval/lifecycle refactor follow-ups and added
  an explicit design gate for future skill-script execution, tool running, and
  user-approved goal loops.
- Added `docs/agentic-capability-design.md` to track the tool/script authority
  model, review checklist, and goal-loop design path.
- Added an internal, review-first `skill_manage` action layer for skill
  suggestions. Motoko can now propose creating a skill, patching an existing
  `SKILL.md`, or writing/removing confined support files under `references/`,
  `templates/`, or `scripts/`, while still requiring explicit acceptance and
  avoiding arbitrary script execution.
- Added first-class skill support-file inspection and progressive disclosure.
  `motoko skill support NAME [FILE]` and `/skill support NAME [FILE]` list or
  show confined support files, and relevant support-file excerpts can now enter
  chat context as visible `skill-support` sources.
- Made background skill review more Hermes-shaped without adding autonomous
  tools: explicit reusable-procedure phrases can trigger early review, and
  recently loaded skills are passed into the review prompt so suggestions
  prefer patching the skill that was actually in use.
- Moved top-level prompt context lane packing into the retrieval-service
  boundary. Chat, `/sources`, and retrieval preview now share a structured
  `context-package-v1` plan for lane source accounting.
- Added a shared retrieval-service result source summary so `retrieval-debug`
  reports production selected sources from the same result object used for chat
  context.
- Changed `/retrieval-preview` to read attached context from the structured
  context package instead of parsing it back out of the rendered system prompt.
- Moved the stale-superseded index cleanup decision/apply loop into the
  artifact-lifecycle boundary with filesystem operations supplied as injected
  callbacks.
- Registered foreground blocking commands with the content-free job supervisor,
  so `/study`, `/index`, and similar foreground work use the same job snapshot
  machinery while they run.
- Added `motoko-skill-v2` metadata and a pre-retrieval `retrieval_plan_v1`
  boundary so built-in skills can activate deterministic handlers before
  context packing instead of living only as final-prompt guidance.
- Added the roadmap and CLI surface for review-first skill suggestions, so
  Motoko can notice skill-worthy procedural knowledge during maintenance and
  ask for confirmation instead of silently writing skills.
- Added manual skill review and suggestion detail commands, so a user can ask
  Motoko to review a specific conversation for reusable procedures and inspect
  the proposed skill body before accepting or rejecting it.
- Added a code-owned skill handler/effect registry. Unsupported suggested
  handlers degrade to prompt-only skills, which preserves the planner boundary
  before any future script or tool work.
- Added deterministic skill schema upgrades through `motoko skill upgrade` and
  the cheap after-answer maintenance lane, so old learned `SKILL.md` files can
  converge to the current schema.
- Added `motoko skill plan` and `/skill plan` to inspect prompt-skill ranking
  and deterministic handler activation for a query without calling a model.
- Converted the built-in `org-temporal-retrieval` skill into a real retrieval
  skill that declares `builtin:org_temporal_latest_entries`; `/sources` now
  shows the activated skill plan and handler when source-scoped temporal
  retrieval runs.
- Added realm-local procedural skills: `motoko skill learn/show/delete`,
  `/skills`, and `/skill show/learn/delete`. Skills are selected into chat
  context only when relevant and appear in `/sources`; they are non-executable
  `SKILL.md` guidance under the current user's Motoko state.
- Added a built-in `org-temporal-retrieval` skill that describes source-scoped
  latest-dated-Org handling while keeping date/source selection deterministic in
  the retrieval layer.
- Documented the source-scoped temporal retrieval failure and its deterministic
  solution as Motoko's first Hermes-inspired skill/planner/handler pattern
  while keeping the adaptation dependency-free and bounded.
- Clarified deterministic temporal retrieval context: when Motoko selects the
  latest dated Org sections present in a source file, the prompt context and
  `/sources` now state those selected dates explicitly so the chat model does
  not assume missing intervening calendar days have entries.
- Moved live hybrid index retrieval into `motoko_core.retrieval_service`,
  including candidate fusion, injected vector/evidence/source callbacks, and
  hybrid rerank control, while keeping the root `motoko` executable as a
  compatibility facade.
- Moved attached-context rendering for indexes into the retrieval service, so
  chat context, retrieval previews, and source records use the same
  service-owned index retrieval path instead of bouncing through a root facade
  callback.
- Added deterministic temporal retrieval for dated Org/logbook questions, so
  "last", "latest", "today", "yesterday", and similar queries prefer the
  newest matching source evidence before ordinary semantic ranking.
- Made `motoko retrieval-eval` replay private per-realm feedback fixtures as
  evaluation rows, letting future retrieval changes be checked against real
  feedback without letting feedback directly mutate production ranking.
- Expanded index health with source lifecycle decisions for indexed files that
  changed, were deleted, or are now ignored by `.motokoignore`, including the
  recommended rebuild or derived-artifact cleanup action.
- Added an artifact lifecycle plan for source changes, with dependent
  vector/evidence/dossier/eval artifact counts surfaced in `index-storage` as
  rebuild-first work rather than deletion-safe cleanup.
- Made `Ctrl+C` in the TUI stop an active answer and clear queued prompts,
  matching `/stop`, instead of exiting while an answer worker may still be
  running. Idle `Ctrl+C` still exits.
- Added production selected-source summaries to `retrieval-debug`, so its
  lexical/evidence/vector diagnostics can be compared against the actual
  retrieval-service result that chat context would use.
- Added a live-subsystem refactor boundary: runtime context, typed command
  requests, job supervision, model-route readiness, retrieval-service wrapping,
  artifact lifecycle decisions, and content-free observability now have
  dedicated stdlib modules while the root `motoko` executable remains the
  compatibility facade.
- Added a chat context governor that estimates prompt size, uses the
  NixOS-declared default Qwen3.6 route for normal chat, and switches to
  approved quality/deep/max profiles only for explicit mode requests or prompts
  that need longer context.
- Updated chat route selection for explicit NixOS route profiles, so Motoko now
  honors `selection.default`, `selection.priority`, `route_profile`,
  `context_tokens`, `kv_offload`, and `kv_cache.location` instead of treating
  `qwen36-chat` or Q4 naming as canonical.
- Added content-free model-call telemetry plus `/last-call`,
  `motoko last-call`, and `motoko context-bench` so route choice, context
  pressure, timing, and estimated token rates can be inspected without storing
  prompt or response text.
- Added a short blinking `KV not in GPU` TUI status warning when the selected
  chat route declares RAM-backed KV with `--no-kv-offload`.
- Added `/rename` and guarded `/delete` for conversations. Conversation delete
  removes the chat plus Motoko-owned derived artifacts that explicitly reference
  that conversation, and new topic/memory dossiers record their owner
  conversation for future cleanup.
- Changed memory proposal requests to pass recent conversation turns as a
  quoted transcript inside a user message, avoiding assistant-prefill failures
  on Qwen thinking-mode worker routes.
- Changed TUI chat role labels to compact colored glyph markers, added
  phase-aware `Preparing`/`Answering` elapsed rows plus a final `Worked for`
  separator, and made prose wrapping prefer word boundaries while leaving code
  blocks literal.
- Added this changelog as the durable home for the short "what changed" lists
  from accepted Motoko work.
- Quieted stale maintenance from a different conversation on startup. Motoko
  still marks the old maintenance job abandoned, but no longer shows an alarming
  `sys abandoned interrupted maintenance...` line in a fresh chat.
- Added a durable background study job ledger in `study-jobs.jsonl`, plus
  interrupted-job detection for the current cheap catalog/planning pass.
- Added context planning lanes to the prompt and `/sources`, making the active
  context budget visible by lane.
- Expanded `/sources` with `why:` explanations so memories, conversations,
  dossiers, indexes, and chunks are easier to audit.
- Changed the TUI renderer to read terminal dimensions from the actual output
  file descriptor and added a stdlib pseudo-terminal resize/redraw check.
- Added `/about` and `motoko about` with Motoko version, model badge, endpoint,
  and state/config paths.
- Reworked `/help` into categorized sections; in the TUI it now opens as a
  dismissible help view instead of being appended into the conversation.
- Kept the top status bar wrapping across as many lines as the current terminal
  can spare, and made it show memory and background-study phases explicitly.
- Changed automatic memory proposal work to run in a bounded helper process so a
  stuck local model call is terminated and reported instead of leaving
  `memory: proposing` visible forever.
- Added deterministic memory capture for explicit natural-language requests such
  as `remember that ...`.
- Kept TUI rendering away from the final terminal column to avoid tty/tmux wrap
  ambiguity in long composer lines.
- Documented that future HRAG quality work should happen through Motoko-owned
  runtime behavior and synthetic fixtures, without Codex reading Javier's
  personal documents.
- Added bounded heavy background refresh for attached stale document indexes or
  meaningful batches of new files, with visible `bg-heavy: indexing(model)`
  status and prompt queuing while the local model focuses on indexing.
- Added current-directory corpus learning: Motoko can ask to learn an
  allowlisted directory tree on first use, auto-attach an existing matching
  corpus index later, and keep separate derived artifacts per directory root.
- Added durable progress files for heavy corpus indexing, with TUI status
  showing file/chunk/model-call progress, elapsed time, and ETA.
- Added index-plan estimates for chunks and HRAG model calls so first corpus
  passes are easier to size before starting.
- Added Org-mode structured signals for headings, TODO states, priorities,
  deadlines, and schedules, and used them to improve task-priority retrieval
  from corpus indexes.
- Added ranked task candidates for priority/date/task questions so Motoko can
  show the model the most relevant Org tasks before answering.
- Added corpus health reporting in `/indexes`, including coverage percentage
  and counts of newly discovered or missing files.
- Reused the same progress/ETA status for heavy background refreshes of stale
  attached indexes, not only first-run corpus learning.
- Added `/tasks [QUERY]` and `motoko tasks QUERY` to inspect ranked Org task
  candidates from attached or relevant corpus indexes without waiting for a
  model answer.
- Added `motoko index-enrich INDEX_ID` and `motoko index-enrich --all` to add
  current structured signals to completed legacy indexes without rerunning
  expensive model summaries.
- Made the light background study loop perform bounded CPU-only signal
  enrichment automatically when old completed indexes need it, while refusing
  active indexes that are still being built.
- Added Corpus Profile v1, an inspectable derived artifact that maps file
  roles, task/date signals, tags, and planning cues for each index.
- Added `motoko corpus-profile` and `motoko index-upgrade` so old completed
  indexes can gain newer derived artifacts without discarding past work or
  rerunning model summaries.
- Added named model routes for chat, chunk summaries, file summaries, corpus
  synthesis, topic dossiers, memory/profile work, titles, and audits. Routes
  default to the existing endpoint until configured otherwise.
- Added an `index_label` route and `motoko model-eval` synthetic quality gate
  for comparing worker models on chunk, file, label/classification, and corpus
  fixtures before trusting them for bulk indexing.
- Added artifact provenance and `motoko index-quality` checks for summary
  schema, model route, prompt version, source fingerprint, quality status,
  structured signals, corpus profiles, and task/date preservation.
- Added a private model-output cache for deterministic background summary
  routes; true llama.cpp prompt/KV caching remains a NixOS model-service
  follow-up.
- Added per-user `ui.assistant_color` config so each account can give Motoko's
  assistant label its own validated terminal color.
- Added `MOTOKO_ALIAS_COLOR` as a NixOS-managed per-realm override for the
  assistant label color, falling back to purple when unset or invalid.
- Added render-time syntax highlighting for report-like output such as
  `/sources`, `/status`, `/model-routes`, `/identity`, `/permissions`, and
  retrieval diagnostics while keeping saved state and artifacts plain.
- Added deterministic answer-grounding audits to `/sources`, so each answer
  reports whether it had excerpt-level evidence, summary/memory context, stale
  context, or no usable grounding for a source-shaped question.
- Added `motoko retrieval-eval`, a no-model synthetic fixture gate for checking
  that retrieval selects expected files, chunks, dates, TODOs, paths, and rare
  terms before generation starts.
- Added `/retrieval-debug QUERY` and `motoko retrieval-debug QUERY` to explain
  file/chunk retrieval scoring, path boosts, task-signal boosts, freshness,
  vector/rerank state, and diagnosis notes.
- Added `/retrieval-preview QUERY` and `motoko retrieval-preview QUERY` to show
  the selected source context before a model is called, making prompt-use
  failures easier to distinguish from retrieval failures.
- Added `/index-storage` and `motoko index-storage` to audit derived index
  storage, duplicate chunk references, missing duplicate targets, orphan chunk
  files, and safe cleanup opportunities without deleting anything.
- Added `evidence-store-v1`, a deterministic hierarchical evidence store for
  indexed corpora. Evidence rows cover Org days, Org tasks, headings,
  paragraphs, and bounded text windows with file/chunk/span provenance, and can
  be built or inspected with `/evidence-build`, `/evidence-query`,
  `motoko evidence-build`, and `motoko evidence-query`.
- Made the light background study loop perform one bounded CPU-lane evidence
  refresh when an index lacks a current evidence store, and added
  `motoko evidence-refresh` for explicit refreshes.
- Added `/vector-plan` and `motoko vector-plan` as a read-only readiness report
  for embedding/reranker storage, including sizing, provenance,
  invalidation, privacy, and eval gates.
- Added `/vector-build`, `/vector-query`, `motoko vector-build`, and
  `motoko vector-query` for a deterministic `lexical-hash-v1` vector baseline
  that tests vector storage and query plumbing without starting model workers.
- Added `motoko vector-eval` and `/vector-eval` so the deterministic vector
  baseline is checked against the synthetic retrieval fixtures without calling
  a model.
- Added catalog-discovered `embedding-v1` vector stores. When
  `local-models.json` exposes a realm-local `/v1/embeddings` route,
  `motoko vector-build --method auto` uses it; `lexical-hash-v1` remains the
  no-model control path, and `motoko vector-eval --method embedding-v1` can
  measure the embedding route explicitly.
- Added explicit `motoko vector-query --rerank QUERY` support for
  catalog-discovered `/v1/rerank` routes, so reranker precision can be
  inspected directly.
- Added `motoko vector-refresh` and bounded background vector refresh so fresh
  indexes can gradually acquire `embedding-v1` stores. Normal retrieval now
  uses a fresh embedding store as an additive semantic recall source while
  keeping lexical/task/path retrieval visible as the control path.
- Changed normal retrieval to attempt embedding plus rerank by default when a
  fresh embedding store and NixOS-declared `/v1/rerank` route are available,
  with an embedding-only fallback if reranking is unavailable or fails.
- Changed normal retrieval again to use true hybrid candidate generation:
  lexical/path matches, deterministic Org/task signals, evidence rows, and
  embedding rows are unioned and deduplicated before the combined set is
  reranked.
- Changed retrieval excerpts to honor exact dates and "last/latest/recent"
  Org-date queries as mandatory evidence inside a selected chunk, so
  chronological files such as `logbook.org` show the newest dated `** do`/`** log`
  sections instead of only the beginning of a large chunk.
- Added bounded evidence-span selection inside retrieved chunks. Motoko now
  scores Org headings, Markdown headings, dated sections, term windows, and
  text windows, then can use the approved embedding/reranker routes on the
  top large chunks before building chat/source excerpts.
- Split long candidate spans into bounded worker-sized subspans with parent
  provenance before embedding/reranker scoring, so large headings can be scored
  without overflowing small worker context windows.
- Expanded `/sources` span labels so multi-span date selections are easier to
  audit from the chat screen.
- Made embedding vector refresh route-aware and parallel across batches up to
  the NixOS-declared `maxParallel`, with batch/parallel metadata shown in
  vector refresh/store reports.
- Raised the embedding refresh cap to 32, added row-throughput ETA messages,
  and made excessive parallelism degrade by checkpointing completed rows and
  retrying remaining batches at lower parallelism.
- Added adaptive embedding batch sizing so bg-heavy vector refresh creates
  enough requests to use approved parallel worker slots even for small corpora.
- Made embedding and reranker vector routes fail fast when their declared
  local model files are missing, instead of sitting in socket activation while
  appearing to vectorize.
- Added realm-local embedding vector progress checkpoints so interrupted
  vector refreshes can resume from completed rows when the source and
  embedding route/model/dimensions still match.
- Changed embedding inputs to bounded source-linked subchunk rows, so long
  chunks stay inside the embedding route context limit while preserving parent
  file/chunk provenance and head/tail recall.
- Marked embedding vector stores stale when the vector schema, source
  fingerprint, embedding input schema/split policy, embedding route, model, or
  dimensions change, so background refresh rebuilds incompatible dense vectors
  from source/index material instead of treating them as migratable.
- Added `/feedback up|down|ok [TEXT]`, `/up`, `/down`, and `motoko feedback`
  to record private per-realm answer feedback outside the conversation
  transcript for future retrieval/rerank/prompt evaluation.
- Added `/feedback-eval` and `motoko feedback-eval` to convert private answer
  feedback into per-realm evaluation fixtures without directly changing
  retrieval or ranking behavior.
- Made Unix-socket model calls retry transient connection resets whether the
  NixOS-declared backend reports activating or active, so chat requests are
  less likely to fail during model socket activation, handoff, or route churn.
- Made TUI prompt submission append and save the user turn immediately, then
  run topic/dossier attachment and retrieval preparation inside the answer
  worker so slow pre-answer context work does not make Enter feel ignored.
- Added `/models`, `/model-status`, `/model-stop ROUTE`, `motoko models`, and
  `motoko model-stop` so local model worker state and explicit release can be
  inspected or controlled through the approved `motoko-model` helper, without
  direct systemd access or automatic stop-on-exit.
- Made slow TUI report commands such as `/status`, `/about`, `/sources`,
  `/models`, retrieval previews/debug reports, task reports, and vector
  query/eval reports run in background report workers so Enter is acknowledged
  immediately and rendering stays responsive.
- Kept bg-heavy elapsed-time display stable across vectorization progress-line
  updates, instead of resetting the counter on every batch status update.
- Made the Nix flake wrapper export `MOTOKO_REVISION`, so `/about` can show the
  packaged source revision even when the executable lives outside a Git
  checkout.
- Made `/model-routes` display NixOS-declared route cache policy and
  content-free metrics endpoints from `local-models.json` while keeping prompt
  and KV caching service-owned.
- Documented a tentative roadmap candidate for future retrieval components,
  including embedding stores, rerankers, token accounting, richer lexical
  retrieval, deterministic extractors, parser-backed artifacts, deduplication,
  and lightweight classifiers.
- Moved enduring repository/remotes/deployment guidance out of the completed
  handoff path and clarified that worker-model candidates should be rechecked
  against the latest available model generation before installation.
- Fixed index listing so `INDEX.progress.json` job files are never treated as
  completed document indexes.
- Made heavy corpus indexing checkpoint completed files into partial indexes,
  resume after timeout/pause/interruption, rescan for newly added files, and
  expose `/pause`, `/resume-work`, and `motoko index-resume`.
- Suppressed superseded failed partial indexes from unfinished-work prompts,
  completions, and current-directory learning offers when a newer completed
  index exists for the same corpus.
- Made context catalog/retrieval prefer the newest completed index per corpus
  family and replace older attached indexes with newer completed ones before
  starting another heavy refresh.
- Added `motoko index-repair` and `/index-repair` for targeted quality repair
  of fresh indexes, including empty chunk summaries and affected file/corpus
  summaries.
- Made idle background study run a bounded quality-repair pass on fresh indexes
  that fail `motoko index-quality`.

## 2026-05-18

- Added `/new [TITLE]` and `motoko new`.
- Added `/study QUERY` and `motoko study QUERY` for bounded study passes that
  reuse existing dossiers before building new derived context.
- Made the TUI spinner default to the tty-safe ASCII `-/|\` animation; braille
  remains available only by explicit opt-in.
- Made the TUI input renderer terminal-cell aware to reduce cursor drift on
  wrapped prompts and wide Unicode text.
- Added local-model visibility through a compact model badge such as
  `qwen3.6-27b-mtp:8083`.
- Added generated conversation titles after the first few messages while
  preserving manually set titles.
- Added a low-cost idle background study loop that refreshes the private
  context catalog and records study suggestions without silently crawling new
  directories or competing with chat.
- Kept heavier idle profile refresh opt-in with `MOTOKO_BACKGROUND_PROFILE=1`.
- Added regression and evaluation coverage for memory dossiers, context
  sufficiency, study reuse, spinner behavior, generated titles, and dropdown
  scrolling.

## 2026-05-17

- Split Motoko into this standalone repository and flake.
- Kept NixOS host integration in `nixos-configs`; Motoko's source, tests, and
  main documentation now live here.
- Documented Motoko as a small, dependency-free terminal personal assistant for
  the HB3 `personal` realm.
