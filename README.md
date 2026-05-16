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

