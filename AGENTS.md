# Codex Instructions for Motoko

Motoko is Javier's small terminal personal assistant for the HB3 `personal`
realm. It talks to a local llama.cpp OpenAI-compatible endpoint and is designed
to stay simple, inspectable, and dependency-light.

## Working Rules

- Keep Motoko dependency-free unless Javier explicitly approves a new runtime
  dependency. The current implementation uses only Python's standard library.
- Do not add provider API keys, cloud accounts, database servers, LangChain,
  LangGraph, browser/web UI machinery, or autonomous tool execution without a
  reviewed design change.
- Treat personal-memory and document-index behavior as security-sensitive:
  preserve explicit allowlists, provenance, and source visibility.
- Prefer small, testable improvements that make the assistant more trustworthy
  before making it more agentic.
- Do not store secrets in this repository.
- Read `docs/project-context.md` before making architectural, security-boundary,
  or terminal-interface changes.

## Mares Account Handoff

When running as the non-admin `mares` account, or when changing Motoko workflow,
packaging, NixOS integration, account boundaries, memory/document behavior, or
handoff process, read `docs/mares-motoko-handoff.md` before editing. That file
is the repo-local context bridge from Javier's admin session to
`/home/mares/repos/motoko`; do not rely on raw Codex session history or copied
account state.

## Validation

Before committing code changes, run:

```bash
nix flake check
```

For quick syntax-only validation:

```bash
nix develop --command python3 -m py_compile motoko
```
