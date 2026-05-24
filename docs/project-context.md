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
- source documents are read-only except for typed, confirmed
  `project_file_write` actions under the reviewed agentic boundary;
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
- deterministic `.motokoignore` corpus-selection rules for excluding archival
  or irrelevant files from automatic indexing without weakening allowlists;
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

- autonomous file editing outside typed, confirmed Motoko action records;
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
- Chat body assistant and system rows use compact `›` markers instead of text
  labels; the active answer status row uses `● Preparing (...)` or
  `● Answering (...)`, and completed answers leave a dim `Worked for ...`
  separator across the chat width.
- The bottom status line should not duplicate chat activity from the in-chat
  active answer row. It should keep the conversation title, model identity, and
  background/maintenance status such as `bg: idle`, `bg-light`, or `bg-heavy`.
- Prose in the prompt and main chat should wrap on word boundaries when
  possible; code/preformatted text should remain literal and easy to copy.
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
  - `Alt+Backspace` delete previous word;
  - `Ctrl+K` kill to end of line;
  - `Ctrl+Y` yank killed text;
  - `Ctrl+P` previous suggestion/history;
  - `Ctrl+N` next suggestion/history.
- Empty prompts should recall prior user prompts from the current conversation
  with Up/Ctrl+P, including after resuming a saved chat.
- Brand-new chats that still contain no real chat messages when Motoko exits
  should be pruned instead of polluting the conversation list.
- `/stop` should cancel the current answer during preparation or streaming and
  discard queued prompts from accidental paste batches; `/clear-queue` should
  discard queued prompts without stopping the active answer.
- `Ctrl+C` should stop an active answer and discard queued prompts in the same
  safe path as `/stop`; when Motoko is idle, `Ctrl+C` exits the TUI.
- Conversation lists should use compact relative times while preserving full
  timestamps in JSON state.
- Resume/list columns should be readable and compact:
  `created`, `updated`, `branch`, `conversation`.
- Recent saved conversations should be available as bounded, inspectable context
  in new chats. Durable memories remain separate from this recency recall.
- Query-focused memory dossiers should be available when Javier wants Motoko to
  study a subject across saved memories and prior conversations before
  continuing the chat.
- Skill learning should stay review-first: after-answer maintenance may suggest
  reusable procedures, and `/skill review` or `motoko skill review [ID]` may
  run that review explicitly, but Motoko should not silently create, patch, or
  execute learned skills.
- Skill handlers and effects must pass through a code-owned allowlist. Unknown
  model-suggested handlers degrade to prompt-only guidance rather than gaining
  retrieval, filesystem, shell, or other behavioral power.
- Skill schema changes should have deterministic migrations. `motoko skill
  upgrade` and the cheap maintenance pass rewrite old learned `SKILL.md` files
  into the current schema instead of relying on chat memory or one-off manual
  repair.
- Skill planning should be inspectable without model calls. `/skill plan QUERY`
  should show prompt skill selection and deterministic handler activation
  before any future scripts or tools can affect behavior.
- Tool planning should be inspectable without model calls. `/tools` should list
  the current skill-tool catalog, and `/action plan QUERY` should propose typed
  action records from known tools without running anything.
- Agentic action safety should be eval-gated. `/action-eval` and
  `motoko action-eval` run deterministic no-model fixtures for project-write
  confirmation, `.motokoignore` denial, blocked script-owned writes, explicit
  goal runs, and budget refusal; `--write` saves the report under the current
  user's Motoko state.
- Goal-loop planning and execution should stay explicit and inspectable.
  `/goal plan OBJECTIVE`, `/goal list`, and `/goal preview FILE` may create or
  show `motoko-goal-loop-v1` records. `/goal run FILE --yes` may run only an
  explicit action list already present in the record, within declared budgets,
  and each action still passes through the same validator, confirmation, and
  ledger path. This is not an autonomous model-planning loop yet.
- Skill-management actions should stay review-first and allowlisted. Motoko may
  propose `create`, `patch`, and support-file updates, but accepting them must
  flow through code-owned validators. Support files are confined to
  `references/`, `templates/`, and `scripts/`. Scripts are inert until they
  have adjacent `*.tool.json` metadata, current fingerprint approval, and a
  typed action record accepted by Motoko validators. The first runner can
  execute only approved stdlib Python skill tools with low-risk effects,
  bounded time/output, scrubbed environment, and private realm-local results;
  arbitrary scripts, shell, network, service control, privileged actions, and
  script-owned project-file writes remain blocked. Project mutation is allowed
  only through Motoko's typed, code-owned `project_file_write` action, with an
  allowlisted path, `.motokoignore` enforcement, exact session confirmation,
  overwrite hash checks, atomic writes, and content-safe ledgers.
  `/action ledger` and `/action result` should make tool runs inspectable while
  hiding private stdout/stderr/result content unless the owning user explicitly
  asks for it.
  Support files should be inspectable with explicit commands and loaded into
  chat only by bounded progressive disclosure when they match the current
  prompt.
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
- Report-like output such as `/sources`, `/status`, `/model-routes`, `/models`,
  `/identity`, `/permissions`, and retrieval diagnostics should be syntax
  highlighted at terminal render time without storing ANSI escapes in
  conversation state.
- TUI report commands that may touch indexes, helper processes, route status,
  or retrieval diagnostics should acknowledge Enter immediately and run their
  report-building work off the input/render path. They should open a temporary
  page, not append routine report text to the chat body.
- Keep the composer visually close to the chat body; avoid fixed separator
  lines unless a future terminal architecture clearly needs them.
- The TUI uses a Codex-style append-only transcript with a bottom composer and
  status area. Normal terminal scrollback should show chat history; only the
  composer/status/live-answer area should be redrawn in place.
- Background memory work should report the actual phase and recover cleanly
  from interruption instead of leaving an indefinite spinner.
- The TUI should not show a spinner by default. Legacy line-mode spinners are
  opt-in; use ASCII before braille because the Linux TTY/Terminus path can
  render braille as square fallback glyphs.

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
  opportunities. Cleanup must be conservative and inspectable: stale
  superseded index snapshots may be deleted only after a newer fresh family
  index exists and any duplicate references in that newer index have been
  materialized so the replacement remains self-contained.
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
  exposes content-free worker state through `/models`, and keeps prompts
  stable, explicit, and easy to cache.
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
- After retrieval selects a large chunk, excerpt selection must still be
  source-aware. For chronological Org files, exact-date queries and
  last/latest/recent dated-entry queries should extract the matching dated
  heading sections as mandatory evidence from inside the chunk so
  preview/chat/topic/rerank context contains the relevant `** do`/`** log`
  material rather than only the start of the file.
- Treat that as one instance of a broader "right container, wrong span" class.
  Motoko now has a deterministic `evidence-store-v1` layer for indexed corpora:
  Org days, Org tasks, headings, paragraphs, and bounded text windows become
  first-class source-linked evidence rows. Retrieval should keep using these
  rows in the hybrid candidate set, vectorizing them alongside raw chunks, and
  surfacing selected evidence ids/spans in `/sources` so failures can be
  diagnosed as retrieval, span selection, rerank, or final synthesis problems.
- Bg-heavy vectorization should use the approved embedding route efficiently:
  batch source chunks, issue concurrent embedding requests up to the
  NixOS-declared route `maxParallel` with a Motoko-side cap of 32, expose
  batch/row/parallel/ETA metadata in status or reports, and remain bounded by
  the per-realm local-model service rather than managing llama.cpp directly.
  Batch sizing should adapt to the corpus size so small corpora still create
  enough requests to fill approved route slots. If a route cannot sustain the
  requested parallelism, save completed rows and retry remaining work at lower
  parallelism before failing.
  Embedding inputs should be bounded at the Motoko layer as well as by the
  model service. Long chunks should be split into bounded, overlapping,
  source-linked subchunk rows that retain the parent file/chunk/hash
  provenance, instead of relying on one oversized request or lossy whole-chunk
  truncation.
- Dense embedding stores should be invalidated and rebuilt from saved
  source/index material when their vector schema, source fingerprint,
  embedding input schema/split policy, embedding route, model, or dimensions
  change. Do not try to mathematically upgrade old embedding coordinates
  across incompatible models or incompatible input semantics; treat
  re-vectorization as the inspectable heavy-work migration path.
- Embedding vector refresh should checkpoint completed rows under realm-local
  Motoko state and resume from that progress when the source fingerprint and
  embedding route/model/dimensions/input policy still match. If those keys
  change, discard the partial vector progress and rebuild from source/index
  material.
- User feedback should accumulate as private per-realm evaluation data. Store
  ratings and notes under the active user's Motoko state, keep them out of the
  conversation transcript, expose `motoko feedback-eval` as the inspectable
  fixture-export path, and use those fixtures to guide future
  retrieval/rerank/prompt evals. Do not let feedback directly mutate ranking
  behavior without an inspectable evaluation gate.
- Reflection should grow as specific inspectable audits: answer grounding,
  retrieval preview/debug, index storage health, memory maintenance health, and
  later model-assisted audit passes. Do not build an opaque open-ended
  self-reflection loop.

## Internal Refactor Roadmap

Motoko should be refactored incrementally, not rewritten. The current single
script has grown large enough that careful internal boundaries will improve
maintainability, testing, and future intelligence work, but every step must
preserve the stable `motoko` command, stdlib-only runtime, per-realm state
boundaries, and existing schema/migration rules.

Baseline evidence from 2026-05-23:

- `motoko` is about 20k lines with hundreds of top-level functions.
- The largest functions include chat/TUI dispatch, vector-store building,
  retrieval, CLI dispatch, and report formatting.
- Terminal rendering, text utilities, state layout, model I/O, indexing,
  retrieval, vector stores, dossiers, memory, and command dispatch currently
  live in one import surface.

Refactor rules:

- Avoid a big-bang rewrite. Each step should be behavior-preserving and
  separately testable.
- Keep the root `motoko` executable as the compatibility facade until later
  phases prove a new entrypoint is safe.
- Add no runtime dependencies without Javier's explicit approval.
- Do not change private state formats or derived-artifact schemas unless the
  same change includes an upgrade or source-reprocessing path.
- Prefer extracting pure helpers first, then boundaries with side effects, and
  leave the TUI/control-flow split until enough low-level code is already
  isolated.
- Run the syntax, regression, evaluation, TTY, whitespace, and flake checks
  before committing refactor steps.

Phased plan:

1. Architecture baseline. Record the intended subsystem boundaries, metrics,
   invariants, and validation path in docs before moving code.
2. Extract pure utilities first. Move text, time, ANSI/style, width/wrapping,
   and report-highlighting helpers into an internal stdlib package while
   preserving root-level imports for tests and compatibility.
3. Extract state, paths, and JSON I/O. Centralize config/state path resolution,
   atomic JSON writes, JSONL append/read helpers, locks, and timestamp helpers.
   This creates a reliable foundation for migrations and background job
   checkpointing.
4. Extract the model boundary. Isolate route discovery, Unix-socket HTTP,
   retry/loading behavior, endpoint errors, cache-policy reporting, and
   request construction. This is the right place to enforce "no request body in
   logs" and preserve NixOS-owned service control. This phase should be split:
   transport/cancel/response helpers first, route-catalog/config discovery
   second, and request construction/error diagnostics last.
5. Extract corpus selection and freshness. Move allowlists, `.motokoignore`,
   skip rules, fingerprints, source metadata, and stale/deleted-source handling
   behind a corpus-selection API.
6. Extract retrieval layers. Separate lexical/structured candidate generation,
   evidence-store spans, vector-store recall, rerank fusion, source packing,
   and retrieval diagnostics. Keep hybrid retrieval inspectable and keep
   lexical/structured evidence first-class.
7. Extract memory and conversation services. Separate conversation storage,
   rename/delete/prune behavior, recency context, explicit memories, memory
   maintenance, and user-feedback eval fixtures from chat orchestration.
8. Refactor the TUI last. Split rendering, input editing, overlay pages,
   background worker/report tasks, answer streaming/cancellation, and scrollback
   behavior after the supporting services are importable and tested.
9. Unify command dispatch. Replace the very large CLI/TUI command conditionals
   with a small command registry only after service boundaries exist, so each
   command has a narrow handler and test surface.

Current implementation progress:

- Steps 1 and 2 are complete: the roadmap exists, and pure text/time/terminal
  helpers live in `motoko_core.text` and `motoko_core.terminal`.
- Step 3 is complete for the first state layer: realm-local state/config path
  constructors, atomic writes, JSON loading, and JSONL helpers live in
  `motoko_core.state`.
- Step 4 has started: Unix-socket HTTP transport, loading/transient detection,
  cancellation helpers, and JSON response parsing live in
  `motoko_core.model_io`.
- Step 4 now also has route-catalog helpers in `motoko_core.model_routes`:
  route names/descriptions, local model catalog loading, route normalization,
  endpoint-path normalization, cache-policy normalization, capability lookup,
  and merged local route summaries.
- Step 4 now also has request transport/request-construction helpers in
  `motoko_core.model_io`: chat payload construction, Unix-socket/openai HTTP
  request handling with injected retry/timeouts, streaming event parsing, JSON
  response parsing, cancellation checks, loading/transient detection, and
  shared model-request failure formatting.
- Step 4 now also has pure model-service formatting helpers in
  `motoko_core.model_services`: helper route names, content-free
  `motoko-model status` parsing/compaction, route cache-policy report
  formatting, and service selector token generation.
- Step 4 now also has reusable `motoko-model` helper orchestration in
  `motoko_core.model_services`: helper subprocess execution, status retrieval
  with bounded diagnostics, activation-state parsing, and verify hints for
  group membership, missing model files, helper availability, download URLs,
  and hashes. The root script keeps thin wrappers so tests and runtime
  monkeypatching still exercise the live facade.
- Step 4 now also has live model-service row/report/control assembly in
  `motoko_core.model_services`: service row merging, route selector
  resolution, `/models` report formatting, individual service-status
  formatting, and `/model-stop` report formatting. The root script still owns
  live model route discovery and invokes `motoko-model`; it does not call
  `systemctl` and does not log request or response bodies.
- Step 4 is effectively complete. Future model-boundary changes should be
  tactical follow-ups, not blockers for moving to corpus selection/freshness.
- Step 5 has started: corpus-selection constants, text-file detection,
  `.motokoignore` parsing/matching, source-selection policy fingerprints,
  candidate discovery, ignored-path examples, and selection-policy staleness
  checks live in `motoko_core.corpus_selection`.
- Step 5 now also has source-file metadata helpers in
  `motoko_core.corpus_selection`: streaming SHA256 file hashes, stored
  source-fingerprint construction, and per-file freshness/staleness checks for
  missing, changed, and metadata-only-changed files. The root script still
  exposes compatibility imports for callers and tests.
- Step 5 now also has whole-index freshness aggregation in
  `motoko_core.corpus_selection`, with artifact-health checks supplied as an
  injected warning provider from the root script. This keeps source-selection
  and source-staleness policy together without merging it into derived-artifact
  migration logic.
- Step 5 now also has the document allowlist file helpers in
  `motoko_core.corpus_selection`: reading allowed directories, appending new
  entries, and enforcing that document reads/indexing remain under an allowed
  path. The root script still owns user-facing commands and the Nix-managed
  configuration error wording.
- Step 5 is effectively complete. Future corpus-selection changes should be
  tactical follow-ups unless a new source-policy feature changes the boundary.
- Step 6 has started with pure lexical retrieval helpers in
  `motoko_core.retrieval`: tokenization, BM25-like lexical scoring, path
  mention boosts, and base hybrid-candidate scoring. The root script still owns
  live retrieval orchestration, evidence/vector/rerank calls, and source
  packing.
- Step 6 now also has deterministic evidence-span helpers in
  `motoko_core.retrieval`: exact date mentions, recent dated Org sections,
  nested dated-section pruning, mandatory date evidence spans, and query-term
  window excerpts. These preserve the "right container, wrong span" fix as a
  reusable retrieval primitive.
- Step 6 now also has pure source-span selection in `motoko_core.retrieval`:
  Org/Markdown heading spans, rolling text windows, base evidence-span
  generation, lexical evidence-span scoring, budget fitting, and
  non-overlapping span selection. Model-assisted span embedding/reranking stays
  in the root script for now because it still depends on live route discovery
  and local-model calls.
- Step 6 now also has query-aware content packing in `motoko_core.retrieval`,
  with model-assisted span scoring supplied as an injected callback from the
  root script. This keeps deterministic excerpt selection importable while
  preserving the NixOS-owned local-model route boundary.
- Step 6 now also has pure hybrid candidate bookkeeping and evidence excerpt
  packing in `motoko_core.retrieval`. Live hybrid orchestration still stays in
  the root script where it can call index stores, vector stores, rerank routes,
  and source-content readers explicitly.
- Step 6 now also has retrieval score-part assembly and debug-diagnosis helpers
  in `motoko_core.retrieval`, with task-signal boosts injected by the root
  script. This keeps lexical/path scoring and failure classification reusable
  without absorbing Org/task signal ownership yet.
- Step 6 now also has bounded model-subspan preparation in
  `motoko_core.retrieval`, with input size and per-parent subspan limits passed
  in from the root script. Environment/config reads remain in `motoko`; pure
  model-input slicing is importable.
- Step 6 now also has context-item rendering in `motoko_core.retrieval`, with
  index/topic/dossier loading and retrieval supplied as callbacks from the root
  script. This keeps source rendering, repo/file context formatting, and
  unavailable-source warnings importable while preserving realm-local state and
  live retrieval ownership in `motoko`.
- Step 6 now also has answer-grounding audit logic in
  `motoko_core.retrieval`, parameterized by schema/version, timestamps, and
  source-kind policy from the root script. `/sources` and answer audit
  behavior remain unchanged, but the reasoning about strong evidence, context
  evidence, stale warnings, and recommended actions is importable and tested.
- Step 6 now also has context-plan construction and formatting in
  `motoko_core.retrieval`, with the root script supplying the active prompt
  budget. This keeps `/retrieval-preview` and system-prompt context planning
  behavior stable while making the lane accounting independently testable.
- Step 6 now also has context-sufficiency policy in `motoko_core.retrieval`,
  with live ranked topics, dossiers, indexes, and attached-item ids supplied by
  the root script. This keeps the "answer now versus suggest /study" note
  importable without moving persistence or index discovery into core retrieval.
- Step 6 now also has pure `/retrieval-preview` report assembly in
  `motoko_core.retrieval`. The root script still builds live prompts, sources,
  and formatted source lists, but prompt-section extraction, source-kind counts,
  truncation, and diagnostic report layout are importable and tested.
- Step 6 now also has pure retrieval eval/debug report formatting in
  `motoko_core.retrieval`. The root script still builds and saves reports from
  live indexes, evidence stores, and vector stores, while core owns the
  inspectable diagnostic text layout.
- Step 6 now also has pure vector-store primitives in
  `motoko_core.vector_store`: embedding/rerank response parsing, dense and
  sparse vector normalization/scoring, embedding input splitting, bounded
  embedding text assembly, and vector-query option parsing. The root facade
  still owns live route I/O, store construction, persistence, and refresh
  orchestration.
- Step 6 now also has vector plan/refresh/query/eval report formatting in
  `motoko_core.vector_store`, keeping text layout importable while the root
  facade continues to own freshness checks, live vector queries, and CLI/TUI
  command plumbing.
- Step 6 now also has `/sources` report formatting in `motoko_core.sources`,
  including source span details and context-lane explanations. The root facade
  still gathers live source records from conversations, indexes, memory,
  dossiers, and repo attachments.
- Step 6 now also has worker-model eval prompt/scoring helpers in
  `motoko_core.evals`: JSON artifact extraction, required/forbidden fact
  checks, strict worker prompt construction, and score assembly. The root
  facade still owns fixture selection, model calls, timing, and report writes.
- Step 6 now also has index-storage audit report formatting in
  `motoko_core.index_storage`. The root facade still performs live filesystem
  scans, index/partial enumeration, and cleanup safety decisions.
- Step 7 has started with pure conversation-record helpers in
  `motoko_core.conversations`: new conversation record construction,
  empty-chat detection, recall text generation, and bounded model transcript
  rendering. Persistence, deletion, artifact cleanup, and memory maintenance
  still stay in the root script.
- Step 7 now also has conversation JSON persistence helpers in
  `motoko_core.conversations`: save, close/prune empty, and list records using
  explicit state paths supplied by the root script. Conversation deletion and
  cross-artifact cleanup still stay in `motoko` until the memory/artifact
  boundary is split.
- Step 7 now also has reusable conversation-reference cleanup helpers in
  `motoko_core.conversations`: recursive JSON reference detection, JSONL
  rewriting, and deletion of JSON artifacts that reference a conversation.
  The high-level delete command still stays in the root script because it
  coordinates memories, feedback, study jobs, topics, dossiers, and profile
  state.
- Step 7 now also has durable memory-row helpers in `motoko_core.memory`: memory
  ID creation, row normalization, bounded JSONL loading, and atomic row
  writing. The root script still owns user-facing memory commands,
  maintenance, proposal generation, ranking, and source rendering.
- Step 7 now also has deterministic memory scoring in `motoko_core.memory`:
  duplicate detection, tag derivation, conversation-aware query text, relevance
  scoring, and ranked memory selection. The root script still loads realm-local
  memory state and renders selected memories into chat context.
- Step 7 now also has memory list/search report formatting in
  `motoko_core.memory`. The root script still loads, mutates, and searches
  realm-local memory rows, while core owns the inspectable text layout for
  memory reports.
- Step 7 now also has durable-memory prompt context rendering in
  `motoko_core.memory`. The root script still loads and ranks realm-local
  memories, while core owns the bounded memory text and source-record shape
  inserted into chat prompts.
- Step 7 now also has durable memory-maintenance checkpoint helpers in
  `motoko_core.maintenance`: maintenance state read/write, clear,
  incomplete-job detection, begin/update, and interrupted-job resume/abandon
  decisions. The root script still owns when maintenance runs and all model
  proposal calls.
- Step 7 now also has private feedback/eval shaping in
  `motoko_core.feedback`: rating normalization, last-message selection,
  source compaction, response-feedback row construction, eval fixture/report
  construction, eval report formatting, and `/feedback` command parsing. The
  root script still owns realm selection and state-path writes.
- Step 7 now also has profile dossier rendering helpers in
  `motoko_core.profile`. Profile source gathering, model synthesis, and
  realm-local writes remain in the root script, while `/profile` formatting and
  chat prompt profile source rendering are importable and tested.
- Step 7 now also has memory-dossier list/show report formatting in
  `motoko_core.dossiers`. Dossier loading, selector prompts, model-backed
  dossier construction, and state writes remain in the root script.
- Step 7 now also has memory-dossier retrieval/source packing in
  `motoko_core.dossiers`. The root script still loads selected dossiers and
  supplies retrieval budgets, while core ranks dossier memory/conversation
  excerpts and returns prompt text plus source records.
- Step 7 now also has conversation-delete support helpers in
  `motoko_core.conversations`: JSON row filtering for conversation references
  and delete-report formatting. The root script still coordinates the actual
  deletion across memories, feedback, study jobs, dossiers, profile state, and
  conversation files.
- Step 7 now also has recent-conversation context rendering in
  `motoko_core.conversations`. Ranking and live conversation selection remain
  in the root script for now, while bounded text/source rendering for chat
  prompt context is importable and tested.
- Step 7 now also has recent-conversation ranking policy in
  `motoko_core.conversations`. The root script still loads and timestamp-sorts
  saved chats from realm-local state, while core owns the recency/relevance
  lane selection and score annotations.
- Step 8 has started with pure TUI prompt-editing helpers in
  `motoko_core.input_edit`: word-left/right cursor movement, word deletion,
  previous/next input-history selection, resumed-chat history seeding, and
  bounded history append policy. Terminal rendering and command dispatch still
  stay in `motoko`.
- Step 8 now also has pure TUI overlay/dropdown formatting in
  `motoko_core.tui_render`. Terminal control, scrollback synchronization, live
  answer display, and command dispatch still stay in `motoko`.
- Step 8 now also has message-to-display-line formatting in
  `motoko_core.tui_render`, including user/assistant/system/error markers,
  code-block wrapping, and worked-answer markers. The root TUI still owns live
  timing, terminal writes, and scrollback synchronization.
- Step 8 now also has pure bottom-area terminal sequence builders in
  `motoko_core.tui_render`: clearing previously rendered bottom rows and
  writing line blocks at the cursor. The root TUI still decides when to emit
  those sequences.
- Step 8 now also has bottom status-line rendering and background-study label
  policy in `motoko_core.tui_render`. The root TUI still owns live timers,
  terminal writes, and state transitions, while core owns the display text
  composition for queued prompts, reports, memory maintenance, and study lanes.
- Step 8 now also has pure bottom-area frame composition in
  `motoko_core.tui_render`. The root TUI still gathers live-answer, dropdown,
  input, and status rows and emits terminal control sequences, while core owns
  live-output clipping, row ordering, and cursor placement.
- Step 8 now also has pure overlay-page frame helpers in
  `motoko_core.tui_render`: scroll clamping, fixed-height row padding, and
  screen-sequence composition. The root TUI still owns alternate-screen state
  and terminal writes.
- Step 8 now also has pure live-answer display composition in
  `motoko_core.tui_render`. The root TUI still owns timing state and answer
  lifecycle events, while core owns active-answer markers and body formatting.
- Step 8 also has direct tty/input regression coverage for the new pure input
  editing and TUI rendering helpers, in addition to the existing
  pseudo-terminal resize/render check.
- Step 9 has started with small command-list helpers in `motoko_core.commands`:
  slash command value normalization, compact command-menu text, and sorted
  command-name extraction. The large TUI and line-mode dispatch conditionals
  still stay in `motoko` until a command registry can be introduced safely.
- Step 9 now also has shared report-command request parsing in the root script,
  backed by `motoko_core.commands` primary/body helpers, so read-only report
  commands such as `/about`, `/sources`, `/status`, `/model-routes`,
  `/models`, `/retrieval-eval`, `/feedback-eval`, `/retrieval-debug`,
  `/retrieval-preview`, `/identity`, and `/permissions` use the same resolver
  in TUI and line mode. State-changing command families still stay in explicit
  dispatch until they can be moved behind focused tests.
- Step 9 now also centralizes feedback command detection around exact slash
  command primaries (`/feedback`, `/up`, `/down`) so the TUI and line mode no
  longer duplicate prefix checks, and near-miss commands cannot be parsed as
  feedback by accident.
- Step 9 now also shares evidence report-command dispatch for
  `/evidence-build`, `/evidence-refresh`, and `/evidence-query`, so those
  report-style commands use the same request builder in the TUI and line mode
  while preserving realm-local evidence-store behavior.
- Step 9 now also shares vector report-command dispatch for `/vector-plan`,
  `/vector-build`, `/vector-refresh`, `/vector-query`, and `/vector-eval`.
  Vector commands still run through the existing realm-local vector-store
  builders and query paths; the refactor only unifies command routing.
- Step 9 now also routes `/model-stop` through a shared command request helper.
  Service control remains limited to the approved `motoko-model` helper path;
  the refactor only removes duplicated TUI/line-mode selector handling.
- Step 9 now also shares report-style index command dispatch for
  `/index-quality`, `/index-storage`, `/index-cleanup`, `/index-repair`, and
  `/tasks`. Print-only index commands remain explicit until they have
  formatter functions instead of captured stdout.
- Step 9 now also gives `/indexes` and `/corpus-profile` formatter-backed
  output, so they can use the shared index report-command path without
  redirecting stdout from report worker threads.
- Step 9 now also gives topic and dossier list/show commands formatter-backed
  output (`/topics`, `/topic-show`, `/dossiers`, `/dossier-show`) and routes
  them through a shared read-only report-command helper.
- Step 9 now also gives read-only memory/profile/personality commands
  formatter-backed output (`/memories`, `/memory review`, `/memory search`,
  `/profile`, `/personality`) and routes them through a shared report-command
  helper. Memory mutation commands remain explicit until their update helpers
  return structured results instead of printing.
- Step 9 now also gives memory mutation helpers return-value forms and routes
  `/remember`, `/forget`, `/memory edit`, `/memory importance`, `/memory pin`,
  and `/memory unpin` through one shared command helper while preserving the
  existing CLI print wrappers.
- Step 9 now also removes the TUI's ad hoc stdout-capture helper by giving the
  remaining captured commands return-value paths (`/index-plan`,
  `/permissions set`, and profile display after `/profile-refresh`).
- Step 9 now routes `/index-plan PATH` through the shared index report helper
  and `/permissions set MODE` through a small settings command helper, reducing
  another pair of TUI/line-mode duplicate branches.
- Step 9 now also routes context attachment commands (`/read`, `/attach-index`,
  `/attach-topic`, `/attach-dossier`) through a shared helper that mutates the
  current conversation context and returns an explicit status string.
- Step 9 now has a shared command-request dispatcher for all command families
  that already expose the `(label, callable)` shape. The TUI and line mode
  still keep special control-flow commands explicit, but report-like,
  settings, context-attachment, and memory mutation families now share one
  dispatch path.
- Step 9 now also routes `/repo status|diff|log|review` through the shared
  command-request path. Repo reports still attach bounded read-only context to
  the current conversation, but TUI and line mode no longer duplicate the
  parsing, saving, and report construction logic.
- Step 9 now also routes `/title` and `/rename` through a shared conversation
  mutation helper backed by `motoko_core.conversations`, so manual title state
  is updated in one place across TUI and line mode.
- Step 9 now also has a shared blocking-command request path for foreground
  work commands: `/index`, `/index-resume`, `/resume-work`, `/topic`,
  `/deepen`, `/dossier`, `/study`, `/compact`, `/profile-refresh`, and
  `/memorize`. The TUI still runs these as foreground blocking jobs so prompts
  and durable checkpoints behave as before, but command parsing and context
  attachment are no longer duplicated with line mode.
- Step 9 now also has shared conversation lifecycle helpers for starting,
  resuming, deleting, and banner-formatting chats, plus a shared private
  feedback command request for `/feedback`, `/up`, and `/down`.
- Step 9 now routes `/help` through the shared report-command path. The
  remaining explicit TUI/line-mode slash branches are session/control commands
  whose behavior is intentionally UI-specific: menu display, exit, new/resume,
  stop, queue clearing, pause, delete confirmation, shared reports, and
  foreground blocking work.
- Step 9 is effectively complete for the current single-file facade: command
  families with shared semantics now resolve through small request builders,
  while true control-flow commands remain explicit at the TUI or line-mode
  boundary. Future command work should be tactical, such as moving these root
  request builders behind narrower service modules after those services are
  extracted further.
- The current refactor milestone is complete for the safe pure-helper/service
  boundary pass. The root `motoko` facade still intentionally owns live
  orchestration: argparse setup, model-backed indexing/vector builds, retrieval
  over live stores, background study/maintenance threads, TUI event draining,
  terminal mode changes, and compatibility wrappers used by tests. Those areas
  should move only behind narrower designs with focused tests, because they
  coordinate cancellation, persistence, per-realm state, terminal recovery, and
  local model route side effects.

### Live Subsystem Extraction Plan

The next refactor phase is live subsystem extraction. This phase is riskier
than the safe pure-helper pass because it touches timing, cancellation,
checkpoint durability, terminal recovery, local-model route behavior, and
realm-local state mutation. It should still be completed incrementally and
with narrow commits, but the goal is a real service boundary rather than
leaving all orchestration in the root `motoko` facade.

Completion criteria:

1. Characterization coverage exists before moving live behavior. Tests must
   cover the policies for stop/cancel, queued prompt handling, job
   pause/resume/checkpoint shape, route-loading diagnostics, conversation
   lifecycle cleanup, stale/deleted source handling, and status/progress
   rendering.
2. A runtime context object carries realm, state/config paths, model route
   catalog facts, cancellation/job hooks, and content-free status metadata
   without exposing prompts, responses, filenames from private corpora, or
   retrieved context to admin-owned logs.
3. Command execution has an explicit boundary. Commands should resolve to
   typed requests such as report, mutation, foreground job, background job, or
   session control before the TUI or line-mode shell decides how to execute
   them.
4. A job supervisor owns live job identity, lane/kind metadata, cooperative
   cancellation, progress events, durable checkpoint metadata, and safe
   recovery decisions. It must support visible `bg-heavy` work, lighter
   maintenance work, and prompt queuing without losing completed work after
   interruption.
5. A model route manager owns route readiness, approved `motoko-model`
   helper interaction, loading/backoff diagnostics, timeout policy, and
   content-free telemetry. It must not call `systemctl`, select arbitrary
   model paths, or write request/response bodies outside user-owned Motoko
   state.
6. A retrieval service owns live hybrid retrieval orchestration: lexical and
   structured candidates, evidence-store spans, vector recall, rerank fusion,
   source packing, source records, and diagnostics. Lexical/structured truth
   remains first-class rather than being replaced by vector retrieval.
7. An artifact lifecycle service owns stale/deleted/ignored source cleanup
   decisions across indexes, vector stores, evidence stores, dossiers,
   feedback fixtures, memories, profile state, and conversation-derived
   artifacts. Schema changes must still include deterministic upgrades or
   source reprocessing paths.
8. The TUI event loop routes blocking work through explicit job/event paths
   while keeping terminal writes single-owned. This should improve `/stop`,
   queued prompts, visible progress, and terminal recovery without introducing
   rendering races.
9. Observability remains content-free outside the user's Motoko state. Status,
   last-call, model, job, and progress reports should explain what is
   happening without logging prompts, responses, private filenames, summaries,
   memories, or retrieved snippets to admin-owned services.
10. The phase ends with a soak/eval gate: full automated validation plus an
   interactive checklist covering retrieval quality, source grounding,
   `/sources`, stale edits, deleted/ignored files, vector refresh, feedback
   evals, interruption, memory maintenance, and model-route loading failures.

Implementation notes:

- The root `motoko` executable should remain the stable compatibility facade
  until these services are demonstrably safe.
- Each extracted live subsystem should be constructed so it can be tested with
  fake callbacks and temporary realm-local state.
- If extraction reveals that a planned step would weaken cancellation,
  checkpoint durability, per-realm boundaries, or terminal recovery, revise the
  local design and complete the revised step before moving on.

Soak/eval checklist for the end of this phase:

- `nix develop --command python3 -m py_compile motoko motoko_core/*.py
  tests/motoko_tty.py tests/motoko_regression.py tests/motoko_eval.py`
- `nix develop --command python3 tests/motoko_tty.py`
- `nix develop --command python3 tests/motoko_regression.py`
- `nix develop --command python3 tests/motoko_eval.py`
- `git diff --check`
- `nix flake check`
- Interactive after deployment: start Motoko in an indexed corpus, ask a
  grounded document question, inspect `/sources`, run `/retrieval-preview`,
  run `/retrieval-debug`, edit or delete an indexed source, confirm freshness
  warnings or cleanup decisions, run `/vector-refresh`, record feedback with
  `/up` or `/down`, run `/feedback-eval`, test `/stop` during preparing and
  answering, test `/pause` during heavy work, and verify `/status`,
  `/last-call`, `/models`, and job/progress reports remain content-free.

Current implementation progress:

- Step 1 is complete for this phase: existing regression coverage already
  characterizes stop/cancel, queue clearing, model-loading diagnostics,
  stale-source handling, index/vector pause/resume, conversation cleanup, and
  render responsiveness; new checks cover typed command metadata, runtime
  context shape, job snapshots, retrieval-service wrapping, artifact lifecycle
  decisions, and observability scrubbing.
- Step 2 is complete: `motoko_core.runtime` defines the runtime context and
  `format_about`/`format_status` expose only content-free runtime schema and
  route facts.
- Step 3 is complete: `motoko_core.commands` now has typed `CommandRequest`
  records, and shared command builders classify report, mutation, and
  foreground-job requests while preserving the legacy tuple facade.
- Step 4 is complete for the root facade: `motoko_core.jobs` provides the
  in-process job supervisor, cooperative stop/pause flags, content-free
  snapshots, checkpoint/progress metadata, and formatting; TUI answer,
  report, maintenance, study, and cwd-index workers are registered there.
- Step 5 is complete: `motoko_core.model_manager` is the model-route readiness
  boundary over the approved `motoko-model` helper path, and `/status` uses it
  for chat-route state without logging request or response bodies.
- Step 6 is complete for the current facade: `motoko_core.retrieval_service`
  wraps live attached-context retrieval through injected callbacks, while
  concrete index/vector/evidence/rerank stores remain explicitly owned by the
  root process.
- Step 7 is complete for current cleanup decisions:
  `motoko_core.artifact_lifecycle` owns source/artifact lifecycle decision
  records and stale superseded index cleanup now records the lifecycle
  decision behind each dry-run, deletion, or block.
- Step 8 is complete for this pass: TUI live worker creation now goes through
  the job supervisor while terminal writes remain single-owned by the TUI.
- Step 9 is complete for this pass: `motoko_core.observability` provides
  content-free report scrubbing and `/status` identifies its observability
  schema.
- Step 10 is complete as an automated gate in this repository; the manual
  interactive checklist above remains the deployment soak path after Javier
  updates the Motoko flake input and rebuilds.

### Refactor Progress Report, 2026-05-24

The first two refactor milestones are complete for the safety level that was
intended: Motoko now has focused internal modules and live-subsystem boundary
objects, while the root `motoko` executable remains the compatibility facade
for orchestration that still coordinates realm-local state, terminal behavior,
model requests, cancellation, and background work.

Internal refactor roadmap status:

- Architecture baseline: complete. The subsystem boundaries, invariants, and
  validation path are recorded in this document.
- Pure utilities: complete. Text, terminal, styling, wrapping, and report/TUI
  formatting helpers have moved into `motoko_core`.
- State, paths, and JSON I/O: complete for the foundation. Generic
  realm-local paths, atomic JSON writes, JSON loading, and JSONL helpers live
  in `motoko_core.state`; domain-specific mutations are still split across
  their owning services and the root facade.
- Model boundary: complete for this phase. `model_io`, `model_routes`,
  `model_services`, and `model_manager` isolate transport, route catalog
  parsing, approved `motoko-model` helper interaction, and content-free
  diagnostics. The root facade still decides when to make live model calls.
- Corpus selection and freshness: complete. `.motokoignore`, allowlist,
  skip-rule, fingerprint, source metadata, and freshness helpers live in
  `motoko_core.corpus_selection`.
- Retrieval layers: mostly complete as pure helpers. Lexical scoring,
  evidence spans, vector primitives, rerank response parsing, source reports,
  preview/debug formatting, context-plan accounting, and retrieval eval helpers
  are importable. Live hybrid orchestration over actual indexes, evidence
  stores, vector stores, rerank routes, and source readers still mostly lives
  in the root facade.
- Memory and conversation services: mostly complete. Conversation persistence,
  conversation cleanup helpers, memory ranking/rendering, maintenance
  checkpoints, feedback fixtures, and dossier/profile rendering helpers are
  importable. The root facade still coordinates full lifecycle actions that
  touch several artifact families at once.
- TUI refactor: substantially complete for pure behavior. Input editing,
  overlay pages, message formatting, bottom status composition, and live-answer
  display helpers are importable. The root facade still owns terminal mode,
  event draining, and actual writes.
- Command dispatch: complete for shared semantics. Typed command requests and
  shared dispatch helpers cover report, mutation, context attachment, memory,
  vector/evidence/index, repo, title/rename, blocking foreground work, and
  feedback commands. Session/control commands remain explicit at the UI
  boundary because their behavior is intentionally TUI or line-mode specific.

Live subsystem extraction status:

- Characterization coverage: complete enough for the completed milestone.
  Tests cover the new runtime context, typed command metadata, job snapshots,
  model-route manager, retrieval-service wrapper, artifact lifecycle decisions,
  observability scrubbing, TUI rendering helpers, and input editing helpers.
- Runtime context: complete. `motoko_core.runtime` exposes
  `runtime-context-v1`, and `/status` reports it.
- Command boundary: complete. `CommandRequest` records classify command work
  before the UI decides how to execute it.
- Job supervisor: complete for in-process jobs. `motoko_core.jobs` tracks
  job identity, lane/kind metadata, stop/pause flags, progress, checkpoint
  metadata, and report formatting. Deeper durable job ownership remains a
  future improvement.
- Model route manager: complete. The route manager uses only the approved
  `motoko-model` helper path and content-free status data.
- Retrieval service: in progress and now live. `motoko_core.retrieval_service`
  owns live index retrieval, lexical/path/task/evidence/vector candidate
  fusion, deterministic temporal Org evidence selection, and hybrid rerank
  control through injected callbacks. Context packing, report formatting, and
  some source-record construction still remain in the root facade.
- Artifact lifecycle service: partial. Lifecycle decision records exist, stale
  superseded index cleanup uses them, and index health now reports source
  lifecycle decisions for changed, deleted, or newly ignored indexed files.
  Source lifecycle plans now count dependent vector stores, evidence stores,
  dossiers, retrieval debug/eval files, and feedback evals, and `index-storage`
  surfaces that as rebuild-first work. There is still not one service that
  applies cleanup/rebuild work across all of those artifact families.
- TUI event loop through job/event paths: mostly complete. Worker creation now
  goes through the job supervisor and terminal writes remain single-owned.
  `/stop` and `Ctrl+C` share the active-answer cancellation path, while
  foreground blocking commands can still improve after more APIs narrow.
- Content-free observability: complete for this phase. `/status`,
  `/last-call`, model reports, and job/progress reports avoid request and
  response bodies.
- Soak/eval gate: complete for the committed milestone. Automated validation
  passed before commit, and deployment smoke checks confirmed the live runtime
  schema, fresh index quality, hybrid retrieval, vector/evidence freshness, and
  `/sources` output.

The most important remaining architectural debt is that the root `motoko`
facade is still large and still owns live orchestration. That is acceptable for
the completed milestone, but future work should shrink it by moving complete
live subsystems behind tested service APIs rather than continuing to add more
top-level orchestration.

### Next Long Refactor Stretch: Retrieval Ownership

The next long autonomous work stretch should make retrieval the first live
subsystem with real ownership rather than only pure helper extraction. This is
the best next target because retrieval is where Motoko's intelligence,
source-grounding, vector/rerank work, deterministic Org/date truth, feedback
evals, and future reflection audits meet.

Goal: `motoko_core.retrieval_service` should own the live hybrid retrieval
pipeline through explicit injected stores, route callers, and source readers,
while the root `motoko` facade keeps only CLI/TUI plumbing, state-root
selection, and backward-compatible wrappers.

Planned steps:

1. Baseline and characterization. Map the current live retrieval call graph in
   the root facade and add narrow tests around the exact behaviors that must
   not regress: query term handling, path mentions, evidence-store priority,
   vector/rerank fusion, source record shape, stale warnings, and `/sources`
   provenance.
2. Service input model. Define small stdlib dataclasses for retrieval requests,
   retrieval environment, store handles, source readers, route callers,
   retrieval budgets, and output records. Keep prompts, source excerpts, and
   filenames inside user-owned Motoko state and in returned in-memory records,
   not in content-free observability reports.
3. Move live index/source selection behind the service. Let the service accept
   attached indexes and source readers, decide freshness/staleness warnings,
   apply `.motokoignore`/deleted-source signals supplied by corpus selection,
   and return structured diagnostics.
4. Move hybrid candidate generation into the service. The service should fuse
   lexical/path/task candidates, deterministic structured signals, evidence
   rows, vector recall, and reranker scores in one place. Lexical and
   deterministic truth must remain first-class; vector recall is an additional
   candidate lane, not a replacement.
5. Move evidence/subspan selection into the service. Bounded subspans, Org day
   and heading spans, date evidence, query windows, embedding/rerank subspan
   preparation, and parent provenance should become service-owned behavior.
6. Add deterministic temporal selection for dated Org/logbook questions. When
   a query asks for "last", "latest", "yesterday", "today", or "last two
   days" in a dated Org file, deterministic date ranking should provide
   high-priority evidence before normal semantic ranking. This addresses the
   current failure mode where retrieval is grounded but not strictly
   chronological.
7. Move context packing and source-record construction into the service. The
   service should own which snippets become prompt context, what appears in
   `/sources`, and how source audit records distinguish strong evidence,
   summary-only context, stale evidence, and missing evidence.
8. Move retrieval reports into the service. `/retrieval-preview`,
   `/retrieval-debug`, `/vector-query` integration notes, source audit
   summaries, and retrieval-eval inputs should come from the same structured
   result object instead of parallel report paths.
9. Wire feedback fixtures into retrieval evaluation. User `/up` and `/down`
   rows should be usable as private per-realm retrieval eval fixtures, so
   future ranking changes can be tested against real failures without letting
   feedback directly mutate ranking behavior.
10. Tighten artifact lifecycle after retrieval is service-owned. Create a
    higher-level lifecycle service that can decide cleanup/rebuild work across
    indexes, evidence stores, vector stores, topic dossiers, memory dossiers,
    feedback evals, profile state, and conversation-derived artifacts when
    files are edited, deleted, ignored, or reprocessed.
11. Improve interruption and foreground responsiveness. After retrieval and
    lifecycle work have narrower APIs, route answer preparation, report work,
    foreground study/index/vector operations, `/stop`, queued prompts, and
    progress events through the job supervisor with clearer cancellation
    checkpoints and less TUI blocking.
12. Keep observability content-free. Extend `observability-v1` only with
    counts, durations, route names, job ids, schema versions, and status
    states. Do not expose prompts, responses, snippets, private filenames,
    memories, or summaries in admin-owned logs or service output.
13. Update docs and migration notes as APIs settle. Keep `docs/motoko.md`,
    `docs/project-context.md`, and `CHANGELOG.md` aligned with any new command
    behavior, source-selection behavior, lifecycle decisions, or user-visible
    retrieval diagnostics.
14. Validate and commit in narrow chunks. Prefer several local commits:
    characterization tests, service input model, candidate fusion move,
    evidence/context packing move, temporal selector, lifecycle expansion,
    interruption improvements, and docs. Run syntax/regression/TTY/eval checks
    for code changes and `nix flake check` before the final commit in the
    stretch.

Current progress on this stretch:

- Complete: characterization coverage for live retrieval service boundaries.
- Complete: service request/result/environment types for injected stores,
  vector/rerank callbacks, source readers, and retrieval budgets.
- Complete: live hybrid index retrieval and candidate fusion moved behind the
  retrieval service.
- Complete: hybrid rerank control moved behind the retrieval service.
- Complete: deterministic temporal Org/logbook selection for recent/latest
  dated questions.
- Complete: attached index context now renders through the retrieval service
  instead of a generic root-facade callback.
- Complete: `retrieval-debug` now includes production selected-source summaries
  from the retrieval-service result, tying diagnostics to the context chat
  would actually receive.
- Complete: feedback rows can be replayed as private retrieval-eval fixtures.
- Complete: index health reports source lifecycle decisions for changed,
  deleted, and ignored indexed files.
- Complete: source lifecycle plans count dependent derived artifacts and
  surface rebuild-first work in `index-storage`.
- Progress: prompt-level lane packing and context-plan source accounting now
  use a service-returned `context-package-v1` record. Remaining context work is
  narrower: final prompt wording, excerpt/snippet choice across non-index
  lanes, and some `/sources` source-record construction still live in the root
  facade.
- Progress: `retrieval-debug` now reads its production selected-source summary
  and content-free diagnostics from the same retrieval-service result object
  used for chat context. Remaining report work is to turn preview/debug/vector
  displays into thin renderers over one richer result shape. `/retrieval-preview`
  now also reads attached context directly from the structured context package
  instead of parsing it back out of the rendered prompt.
- Progress: artifact lifecycle now owns the stale-superseded index cleanup
  decision/apply loop through injected callbacks, so the root facade supplies
  filesystem authority while lifecycle owns report shape and blocking logic.
  Remaining lifecycle work is broader source-level apply support for vectors,
  evidence stores, dossiers, memories, feedback fixtures, profiles, and
  conversation-derived artifacts after rebuilds materialize replacement state.
- Complete: `Ctrl+C` now takes the same safe stop path as `/stop` while an
  answer is active, preserving the idle `Ctrl+C` exit behavior.
- Progress: foreground blocking commands now register with the content-free job
  supervisor while they run. Remaining foreground work is finer cooperative
  cancellation checkpoints for study/index/vector operations after those APIs
  narrow further.

Completion criteria for this next stretch:

- The root facade no longer owns the core hybrid retrieval algorithm; it calls
  the retrieval service with explicit environment objects and renders the
  returned result.
- `/sources`, `/retrieval-preview`, `/retrieval-debug`, chat context packing,
  and retrieval evals use the same underlying retrieval result shape.
- Dated Org/logbook "latest days" questions use deterministic temporal
  evidence before semantic ranking.
- Feedback rows can become private retrieval eval fixtures without changing
  production ranking directly.
- Artifact cleanup/rebuild decisions are centralized enough that deleted or
  ignored sources have one clear lifecycle path across indexes, vectors,
  evidence, dossiers, and feedback-derived artifacts.
- `/stop` and queued prompt behavior are no worse than before, and any
  foreground-job changes include direct tests or a clear manual soak checklist.
- All changes remain stdlib-only, realm-local, and compatible with the stable
  `motoko` command.

Remaining follow-up items from this stretch:

- Finish moving context/source construction out of the root facade where it
  still owns final prompt wording, non-index lane excerpt choices, and some
  `/sources` source-record assembly.
- Reduce retrieval preview/debug/vector reports into thin renderers over one
  richer retrieval result shape, so diagnostics, chat context, and `/sources`
  cannot drift into parallel interpretations of the same query.
- Add broader source-level lifecycle apply support after rebuilds materialize
  replacement state: vectors, evidence stores, dossiers, memories, feedback
  fixtures, profiles, and conversation-derived artifacts should have one clear
  cleanup/rebuild path for changed, deleted, ignored, or reprocessed source
  files.
- Add finer cooperative cancellation checkpoints for foreground study, index,
  vector, and dossier work. Foreground work is now tracked by the job
  supervisor, but long-running functions still need narrower pause/stop
  boundaries before cancellation can feel as responsive as chat answering.

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

## Periodic External-Agent Reviews

Every three months, review Nous Research's Hermes Agent
(`github.com/NousResearch/hermes-agent`) and a small set of comparable local or
self-hosted assistant/agent systems for ideas that could make Motoko more
intelligent, competent, inspectable, or carefully crafted. Treat this as a
research and design input, not as a mandate to copy architecture.

The first Hermes Agent review should deeply understand its goals, skills,
tools, looping behavior, memory model, self-improvement mechanisms, scheduling,
subagent/fanout patterns, sandboxing, and evaluation story. Candidate ideas may
include skills, tool registries, explicit goals, durable loops, self-improving
artifacts, and user-feedback workflows. Import code only when the license,
dependency, security, privacy, and maintenance tradeoffs are reviewed and the
result still fits Motoko's account boundaries, stdlib-first bias, provenance
requirements, and NixOS-owned service boundary.

Initial Hermes Agent study on 2026-05-24 reviewed
`github.com/NousResearch/hermes-agent` through commit `bc3f1f4`. The main idea
worth adapting now is a smaller, stricter procedural skill spine: user- or
agent-authored instructions stored as durable files, listed by metadata, loaded
by progressive disclosure, and selected only when relevant. Motoko's version
must stay realm-local, dependency-free, and inspectable. It should not import a
broad tool runtime, YAML dependency, cross-realm skill store, or autonomous
curator until the safety and evaluation design is reviewed.

Motoko skills should crystallize actionable knowledge into explicit effects:

- `Skill`: durable procedural package with triggers, kind, handler,
  allowed effects, provenance, and optional support files in later versions;
- `Planner`: deterministic or bounded model-assisted decision about whether a
  skill applies before the relevant subsystem runs;
- `Handler`: built-in Motoko code first, and only later tightly constrained
  scripts when the security boundary is clear;
- `LLM`: ambiguous judgment and final synthesis, not hidden ownership of
  source selection or filesystem authority.

The first shipped instance is `org-temporal-retrieval`. It now declares a
retrieval handler and participates in a pre-retrieval `retrieval_plan_v1`, so
queries such as "last three days present in logbook.org" activate a skill plan
before context packing. The deterministic handler still owns source scoping,
Org date parsing, and evidence extraction. This is the intended pattern for
future Motoko skills: skills preserve procedure and trigger metadata; handlers
perform bounded, inspectable effects; `/sources` and diagnostics show what was
activated.

Motoko should also learn when a conversation contains skill-worthy procedural
knowledge. Adapt Hermes' prompt-driven review pattern in a Motoko-shaped way:
user corrections, workflow changes, non-trivial debugging paths, repeatable
techniques, and stale or incomplete loaded skills are signals for a possible
skill update. Hermes prefers updating loaded or umbrella skills before creating
new ones, and can add support files via `skill_manage`. Motoko should follow
that shape through a narrower internal action model: `create`, `patch`,
`write_file`, and `remove_file` suggestions are pending realm-local proposals,
not direct writes. Accepting a suggestion applies it through Motoko validators.
Support files may live under `references/`, `templates/`, or `scripts/`, but
scripts require adjacent `*.tool.json` metadata and a fingerprinted approval
before they can even be considered for execution. Motoko should expose support
files and tool metadata through explicit listing/view commands, validate typed
action records before execution, run only approved low-risk stdlib Python tools
through the narrow runner, and include bounded matching support-file excerpts
as `skill-support` sources when a selected skill needs them. The
background reviewer should not rely only on a fixed message interval: explicit
recent phrases such as "reusable procedure" or "make this a skill" can trigger
an early review, and recently loaded skills should be passed into the review
prompt so Motoko prefers patching the skill that was actually in play. The
local Motoko review heuristic is whether the action would save tokens, reduce
errors, improve reliability, or encode project-specific craft; do not present
that sentence as an upstream Hermes quote.

## Agentic Capability Design Gate

Detailed design review lives in `docs/agentic-capability-design.md`.

Motoko now has the first tightly scoped tool and skill-script execution path,
but broader execution remains a reviewed architecture change, not a background
refactor. The goal is to gain the useful parts of agent harnesses such as
Hermes Agent and modern Codex-style goal loops while keeping Motoko smaller,
stricter, realm-local, dependency-light, and inspectable.

The accepted review checklist for script execution and a general tool runner:

- Authority model: which effects exist, which are prompt-only, which are
  built-in handlers, which are script-backed, and which require explicit user
  confirmation every time.
- Skill package format: script assets under `scripts/` need metadata declaring
  interpreter, allowed arguments, allowed effects, input/output schemas, source
  fingerprint, provenance, and whether the script is executable or inert text.
- Planner boundary: the model may propose or select actions, but execution must
  go through typed Motoko action records validated by code. No free-form shell
  command should be executed directly from model text.
- Filesystem and realm boundaries: scripts must stay inside the current user's
  Motoko realm, respect document allowlists and `.motokoignore`, avoid
  `/home/personal` from `mares`, avoid copied cross-account state, and never
  get sudo or system-service authority.
- Environment and sandboxing: strip secrets from environment variables, set a
  controlled working directory, bound runtime and output size, decide whether
  network is forbidden by default, and prefer NixOS-declared wrappers if OS
  sandboxing becomes necessary.
- User experience: provide dry-run/preview, concise explanation of the planned
  effect, confirmation for mutating actions, visible progress, `/stop` and
  pause behavior, and an inspectable result in `/sources` or a tool ledger.
- Observability and privacy: job status, telemetry, and admin-visible service
  logs must remain content-free. Prompts, retrieved excerpts, filenames,
  summaries, script inputs/outputs, and tool results stay in the user's Motoko
  state only.
- Provenance and artifact lifecycle: every tool-produced artifact needs schema,
  builder, skill/tool id, input hashes, source spans where applicable,
  created-at, quality status, and a migration or source-reprocess path when
  schemas change.
- Evaluation gate: add synthetic fixtures and private feedback-derived evals
  before a runner affects production behavior. Evals should cover refusal of
  unsafe actions, argument validation, output parsing, interruption, stale
  artifact handling, and source-grounding quality.
  `motoko action-eval` is the first deterministic command surface for these
  safety fixtures.
- NixOS boundary: if a tool requires system packages, sandboxes, helper users,
  service control, model files, or network policy, NixOS declares that surface;
  Motoko consumes approved interfaces and does not call `sudo` or `systemctl`.

Goal loops should be added after the planner/handler/tool boundary is solid.
The intended shape is a durable, user-approved loop record with objective,
scope, allowed skills/tools, context sources, budgets, stop conditions,
checkpoint ledger, and final audit. A loop should run explicit phases: plan,
retrieve, act through approved handlers/tools, observe, reflect/audit, persist
artifacts or feedback, and either continue or stop. Loops must be pauseable,
resumable, visible in job status, and conservative by default: read-only loops
first, then user-confirmed local mutations, and only later any broader
automation after separate review.

## NixOS-Facing Model Boundary

Motoko has repo-local support for named model routes, deterministic
model-output caching, and a chat context governor. NixOS owns approved model
files, worker users, sockets, VRAM residency, service hardening, and llama.cpp
flags. Motoko owns route selection, provenance, quality gates, private
output-cache hits, and graceful user-visible handling of queued/loading/missing
model states. The chat context governor estimates prompt size and selects among
NixOS-declared chat route profiles: `selection.default == true` for ordinary
turns, `route_profile == "quality"` only when explicitly requested,
`route_profile == "deep"` for long-context work, and `route_profile == "max"`
only for maximum-context prompts or explicit overrides. Use
`MOTOKO_CHAT_CONTEXT_MODE=quality|deep|max` for explicit selection. Do not infer
KV placement from route names; use catalog `kv_offload` and
`kv_cache.location`. Do not fake server-side KV caching inside Motoko;
prompt-prefix/KV reuse belongs in the deployed local model service if
measurement shows it is worthwhile.

The main chat route may use llama.cpp per-request reasoning controls. Motoko
sets `reasoning_format="deepseek"`,
`chat_template_kwargs.enable_thinking`, and `thinking_budget_tokens` only for
logical chat requests. The current presets are `MOTOKO_REASONING=off|low|default|high|max`;
the default is enabled with a 4096-token thinking budget. Worker routes for
indexing, titles, memory maintenance, profiles, and audits must not inherit
chat thinking settings just because they share the transport helper. Streaming
`reasoning_content` may be shown live under a distinct `Thinking` phase in the
TUI active-answer row, but it must not be stored in content-free telemetry,
logs, shared state, or prompt history.

Model-call telemetry must remain content-free. `last-model-call.json`,
`/last-call`, and `motoko context-bench` may record route names, route profiles,
model ids, configured context size, declared KV placement, reasoning preset and
budget, estimated prompt/completion token counts, source counts, timing, and
estimated token rates. They must not record prompt text, response text,
reasoning text, filenames, excerpts, summaries, private memory text, or
corpus-derived content.

When NixOS declares route cache fields such as `route.cache.prompt`,
`reuseMinTokens`, `cacheRamMiB`, `slotPromptSimilarity`, `metrics`, and
`metrics_endpoint`, Motoko should treat them as declared service capabilities
for display and measurement. Motoko must not call `/slots`, use persistent slot
files, log request/response content, or write corpus-derived data outside the
current user's Motoko state.
