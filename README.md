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
- Quick `/status` and `motoko status` checks for model, memory, and context
  state.
- TTY-safe ASCII spinner by default, with braille as explicit opt-in.
- TUI model badge showing the active local model/endpoint, such as
  `qwen3.6-27b-mtp:8083`.
- Automatic ranked memory selection and quiet after-answer memory maintenance,
  with visible phases, resumable state, and `/sources` provenance.
- Adaptive document retrieval, topic dossiers, and deeper `/deepen` dossiers
  for sustained attention on a subject.
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
