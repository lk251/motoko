# Changelog

Motoko keeps a concise, user-facing changelog here because commit messages are
not the easiest place to review what changed after a long work session.

## Unreleased

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
