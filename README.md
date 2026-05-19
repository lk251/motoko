# Motoko

Motoko is Javier's small terminal personal assistant for the HB3 `personal`
realm. She is intentionally not Texere, not Hermes, and not an agent runtime.
She is a local chat, memory, and document-context tool over an existing
llama.cpp OpenAI-compatible endpoint.

Design constraints:

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
  batches of new files, visible in the TUI status bar.
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
- TTY-safe ASCII spinner by default, with braille as explicit opt-in.
- TUI model badge showing the active local model/endpoint, such as
  `qwen3.6-27b-mtp:8083`.
- Automatic ranked memory selection and quiet after-answer memory maintenance,
  with visible phases, resumable state, and `/sources` provenance.
- Adaptive document retrieval, topic dossiers, and deeper `/deepen` dossiers
  for sustained attention on a subject.
- Current-directory corpus learning: when started inside an allowlisted
  directory without an attached index, Motoko can ask once whether to learn that
  directory tree and then stores separate corpus artifacts per directory root.
- Org-mode corpus artifacts include deterministic heading, TODO, priority,
  deadline, and schedule signals so task-planning questions can retrieve the
  right source chunks even when model summaries are too generic.
- Corpus Profile v1 maps each index's file roles, task/date signals, tags, and
  high-value planning cues into an inspectable derived artifact.
- Existing completed indexes can be upgraded with current structured signals
  and corpus profiles without rerunning model summaries; idle background study
  performs bounded CPU-only upgrades when it is safe to do so.
- Background model work is routed by named worker role, so chunk/file summaries,
  corpus synthesis, memory/profile work, titles, audits, and chat can use
  different local endpoints once deployment provides them.
- Model-derived artifacts record provenance, schema, route, model, prompt
  version, source fingerprint, and quality status; deterministic summary routes
  use a private output cache for repeatable background work.
- Source documents are read-only; reusable indexes store derived chunks under
  Motoko state, not in the repo and not by editing source files.
- Duplicate-aware indexing reuses exact chunks already present in Motoko state
  instead of writing the same source text repeatedly.
- Reusable indexes default to a 200 GiB derived-text budget and fail closed
  before writing beyond it.
- User-owned personality/style guidance in
  `~/.config/motoko/personality.md`.

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
