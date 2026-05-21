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
- Added deterministic answer-grounding audits to `/sources`, so each answer
  reports whether it had excerpt-level evidence, summary/memory context, stale
  context, or no usable grounding for a source-shaped question.
- Added `motoko retrieval-eval`, a no-model synthetic fixture gate for checking
  that retrieval selects expected files, chunks, dates, TODOs, paths, and rare
  terms before generation starts.
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
