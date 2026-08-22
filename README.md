# Motoko

Motoko is Javier's small terminal personal assistant for the HB3 `personal`
realm. She is a local-first chat, memory, retrieval, and project-assistance
tool over NixOS-declared llama.cpp endpoints. Motoko is intentionally not
Texere, Hermes, a provider gateway, or a general-purpose autonomous agent
runtime.

Motoko does include a deliberately narrow agentic substrate: review-first
skills, code-owned retrieval handlers, typed action records, approved
standard-library tools, confirmed project-file writes, and explicit durable
goal loops. Those capabilities remain bounded by realm-local state, allowlists,
validators, visible ledgers, budgets, and user confirmation. Arbitrary shell,
network, service-control, privileged, and hidden autonomous execution remain
outside the product boundary.

## Current Status

As of 2026-08-22, Motoko is a substantial working local assistant rather than
the original single-purpose chat script:

- Interactive chat uses conversation-scoped named models such as
  `qwen38-default`, `qwen38-long`, `qwen38-longest`, and `muse-glimmer` from the
  NixOS route catalog. `/reasoning` exposes model-native effort controls, and
  context pressure causes compaction and fresh retrieval rather than a silent
  model or quant change.
- The raw TUI has a dedicated input/render owner, append-only terminal
  scrollback, durable queued prompts, first-keystroke background preemption,
  and PTY regression probes for latency under background-event pressure.
- Retrieval is hybrid and inspectable: lexical/path matching, deterministic Org
  structure, hierarchical evidence, embeddings, reranking, span selection,
  `/sources`, `/retrieval-preview`, and `/retrieval-debug` share the same
  provenance-preserving service boundary.
- Index, evidence, vector, dossier, memory, feedback, and skill artifacts have
  explicit schemas, provenance, quality checks, refresh/rebuild paths, and
  durable background progress. Incremental vector refresh reuses compatible
  rows and rebuilds incompatible stores from source indexes.
- Skills remain review-first. Typed actions and goal loops can inspect,
  propose, and apply narrowly validated project changes, including managed Git
  worktrees, but they cannot turn model text into unrestricted host authority.
- The implementation remains Python-standard-library-only. The root `motoko`
  executable is still the main composition facade while focused services are
  being extracted into `motoko_core/`; continuing that separation is
  craftsmanship work, not a framework rewrite.

The project is usable, but not architecturally finished. Current priorities are
reliability and competence: keep the TUI responsive, complete artifact
lifecycle ownership and cooperative cancellation, improve retrieval and code
intelligence with inspectable evals, harden reviewed action/goal-loop paths,
and improve memory and dossier quality through real use.

## Guiding Constraints

- Python standard library only.
- No provider API keys.
- No Hermes or Texere dependency.
- No LangChain or LangGraph.
- No database server.
- Explicit document allowlists.
- Inspectable memories, sources, and index freshness.
- Explicit profile dossier built from memories and conversations.
- Query-focused memory dossiers built from saved memories and prior
  conversations.
- Explicit `/study QUERY` and `motoko study QUERY` passes that reuse existing
  dossiers before building new derived context.
- A low-intensity idle background study loop that refreshes the private context
  catalog without silently crawling new directories or competing with chat.
- Bounded heavy background index refresh for attached stale indexes or meaningful
  batches of new files, visible in the TUI bottom status line.
- Heavy corpus indexing records durable progress under Motoko state and reports
  file/chunk/model-call progress with elapsed time and ETA in the TUI.
- Heavy corpus indexing checkpoints completed files, can pause at durable
  boundaries, and can resume unfinished work while rescanning the source tree
  for new files.
- A durable study-job ledger under Motoko state so interrupted background study
  passes are visible and the next pass can safely recompute/resume planning.
- Context planning lanes and `/sources` explanations for why each memory,
  conversation, dossier, index, or chunk was included.
- Quick `/status` and `motoko status` checks for model, memory, and context
  state.
- A Codex-style TUI transcript: chat output is append-only so normal terminal
  scrollback works, while the composer and status line redraw at the bottom.
- TUI model badge showing the conversation's named chat model and reasoning
  effort, such as `qwen38-default:xhigh` or `muse-glimmer:high`.
- Automatic ranked memory selection and quiet after-answer memory maintenance,
  with visible phases, resumable state, and `/sources` provenance.
- Adaptive document retrieval, topic dossiers, and deeper `/deepen` dossiers
  for sustained attention on a subject.
- Current-directory corpus learning: when started inside an allowlisted
  directory without an attached index, Motoko can ask once whether to learn that
  directory tree and then stores separate corpus artifacts per directory root.
  Completed TUI learning attaches the new index to the conversation and
  refreshes the context catalog immediately.
- Repo-local `.motokoignore` files let a corpus deterministically exclude
  archival or irrelevant paths from automatic indexing and derived evidence /
  vector work without changing the document allowlist security boundary.
- Org-mode corpus artifacts include deterministic heading, TODO, priority,
  deadline, and schedule signals so task-planning questions can retrieve the
  right source chunks even when model summaries are too generic.
- Corpus Profile v1 maps each index's file roles, task/date signals, tags, and
  high-value planning cues into an inspectable derived artifact.
- Existing completed indexes can be upgraded with current structured signals
  and corpus profiles without rerunning model summaries; idle background study
  performs bounded CPU-only upgrades when it is safe to do so.
- Fresh indexes with failed quality gates can be repaired with targeted
  `index-repair` passes that regenerate bad chunk/file/corpus summaries instead
  of rebuilding the whole corpus.
- Background model work is routed by named worker role, so chunk/file summaries,
  labels/classification, corpus synthesis, memory/profile work, titles, audits,
  and chat can use different NixOS-declared local endpoints.
- Model-derived artifacts record provenance, schema, route, model, prompt
  version, source fingerprint, and quality status; deterministic summary routes
  use a private output cache for repeatable background work.
- `/sources` includes an answer-grounding audit, and `motoko retrieval-eval`
  checks synthetic corpus fixtures before generation so retrieval quality is
  measurable without reading private documents.
- `motoko retrieval-debug QUERY` explains deterministic file/chunk retrieval
  scores, boosts, freshness, vector/rerank state, and diagnosis notes.
- `motoko retrieval-preview QUERY` shows the source context Motoko would send
  for a question without calling a model, so retrieval failures can be separated
  from final synthesis failures.
- `motoko index-storage` audits derived index storage, duplicate chunk
  references, missing duplicate targets, orphan chunk files, and safe cleanup
  opportunities without deleting anything.
- `motoko evidence-build`, `motoko evidence-refresh`, and
  `motoko evidence-query` build and inspect a deterministic hierarchical
  evidence store for indexed corpora. Evidence rows include Org days, Org
  tasks, headings, paragraphs, and bounded source windows with parent
  file/chunk provenance.
- `motoko vector-plan` reports the vector/reranker storage contract,
  realm-local privacy boundary, invalidation keys, sizing estimate, route
  discovery, and readiness gates before vector retrieval is trusted.
- `motoko vector-build` and `motoko vector-query` build and inspect a
  realm-local vector store. The default `auto` method uses a NixOS-declared
  `/v1/embeddings` route when the local catalog exposes one, and falls back to
  the deterministic `lexical-hash-v1` baseline otherwise.
- `motoko vector-refresh` builds missing or stale embedding stores for current
  indexes. The background study loop may run one bounded refresh pass at a time
  when routes are available, so indexes gradually acquire semantic recall
  without mutating source files. Embedding refresh uses the NixOS-declared
  route parallelism for batch requests, so bg-heavy vectorization can use more
  of the approved worker route while staying inside the per-realm service
  boundary. It adapts embedding batch size to produce enough requests for the
  route's parallel slots, instead of leaving small corpora with only a handful
  of large batches. Completed embedding batches are checkpointed under Motoko
  state so an interrupted refresh can resume without redoing finished rows.
  Long source chunks are split into bounded, source-linked embedding subrows
  instead of being squeezed into one oversized or heavily truncated request;
  each subrow still maps back to the original file/chunk for provenance and
  hybrid retrieval deduplication.
  Progress messages report whether the refresh is full, resumed, incremental,
  reuse-only, or a schema/route rebuild, and include an ETA once completed rows
  provide enough throughput data. If the route cannot sustain the requested
  parallelism, Motoko saves completed rows and retries remaining batches at
  lower parallelism. Dense vectors are rebuilt from the saved source index when
  the vector schema, embedding input schema/split policy, source fingerprint,
  embedding route, model, or dimensions change; Motoko does not pretend old
  embedding coordinates can be migrated across incompatible embedding models.
- `motoko vector-eval` runs the synthetic retrieval fixtures through the
  lexical baseline by default, with `--method embedding-v1` available for
  measuring the approved embedding route.
- `motoko vector-query --rerank QUERY` inspects how the NixOS-declared
  `/v1/rerank` route reorders the top vector candidates.
- Normal corpus retrieval uses true hybrid candidate generation: lexical/path
  matches, deterministic Org/task signals, evidence rows, and fresh embedding
  rows are unioned and deduplicated, then reranked together when a
  `/v1/rerank` route is available. Exact and structured signals remain visible
  in `/retrieval-debug` and `/sources`, and rerank failures fall back to the
  non-reranked hybrid set.
- For chronological Org files, exact-date queries and phrases such as "last
  two days" or "latest entries" select the matching dated sections as
  mandatory evidence inside a large chunk before preview/chat/rerank use the
  source text. This keeps `logbook.org`-style `** do` and `** log`
  subsections visible even when the file was indexed as one broad chunk.
- More generally, Motoko now performs evidence-span selection inside retrieved
  chunks. She scores dated Org sections, Org/Markdown headings, query-term
  windows, and overlapping text windows. Long candidate spans are split into
  bounded worker-sized subspans with parent provenance, scored through the
  approved embedding and reranker routes, then reassembled into source evidence
  under the chat-context budget. The selected span metadata is visible in
  `/sources`; set
  `MOTOKO_SPAN_EMBEDDING=0`, `MOTOKO_SPAN_RERANK=0`, or
  `MOTOKO_SPAN_MODEL_MAX_CHUNKS=N` for diagnosis. Set
  `MOTOKO_SPAN_MODEL_INPUT_CHARS=N` or
  `MOTOKO_SPAN_MODEL_MAX_SUBSPANS_PER_PARENT=N` only when diagnosing worker
  context limits.
- `/feedback up|down|ok [TEXT]` records private per-realm answer feedback
  under Motoko state so retrieval, rerank, prompt, and answer-quality work can
  improve from real use without writing feedback into the conversation.
- `motoko feedback-eval` converts that private answer feedback into
  inspectable per-realm eval fixtures for future retrieval/rerank/prompt
  improvement work; it does not directly change ranking behavior.
- `motoko model-eval` runs synthetic source-grounded checks against configured
  worker routes before small models are trusted for production indexing.
- `motoko models` shows content-free local model service state from the
  approved `motoko-model` helper, and `motoko model-stop ROUTE` explicitly
  releases a worker without giving Motoko direct systemd control.
- Source documents are read-only; reusable indexes store derived chunks under
  Motoko state, not in the repo and not by editing source files.
- Duplicate-aware indexing reuses exact chunks already present in Motoko state
  instead of writing the same source text repeatedly.
- Reusable indexes default to a 200 GiB derived-text budget and fail closed
  before writing beyond it.
- User-owned personality/style guidance in
  `~/.config/motoko/personality.md`.

These constraints are the design, not temporary omissions. Motoko should gain
intelligence through better evidence, memory, procedures, evaluation, and
carefully bounded action—not by accumulating opaque infrastructure or ambient
authority.

See [docs/motoko.md](docs/motoko.md) for usage and operating notes.
See [docs/project-context.md](docs/project-context.md) for the HB3/NixOS,
security, and interface context that should guide future changes.
See [CHANGELOG.md](CHANGELOG.md) for concise user-facing change summaries.

## Nix

Run from this repository:

```bash
nix run
```

Build the package:

```bash
nix build
```

Validate:

```bash
nix flake check
```

Run only the stdlib evaluation harness:

```bash
nix build .#checks.x86_64-linux.evaluation
```

Run only the pseudo-terminal render checks:

```bash
nix build .#checks.x86_64-linux.tty
```
