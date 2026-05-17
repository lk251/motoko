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
- Quick `/status` and `motoko status` checks for model, memory, and context
  state.
- Automatic ranked memory selection and quiet after-answer memory maintenance,
  with `/sources` provenance.
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
