# Codex Instructions for Motoko

Motoko is a small local terminal assistant. It talks to an operator-approved
llama.cpp OpenAI-compatible endpoint and is designed to stay simple,
inspectable, and dependency-light.

## Guiding Values

1. Always try to choose the next steps that will increase her intelligence and competence
2. Bring the high craftsmanship approach of a Swiss watchmaker to making Motoko, whomever is using her has to feel that she was made with much care, attention to detail, thoughtfulness and love, to work as well as possible and be crafted as well as possible.

## Working Rules

- Keep Motoko dependency-free unless the maintainer explicitly approves a new
  runtime dependency. The current implementation uses only Python's standard
  library.
- Do not add provider API keys, cloud accounts, database servers, LangChain,
  LangGraph, browser/web UI machinery, or autonomous tool execution without a
  reviewed design change.
- Treat personal-memory and document-index behavior as security-sensitive:
  preserve explicit allowlists, provenance, and source visibility.
- When changing index, memory, dossier, cache, or other derived-artifact
  schemas, include an inspectable upgrade/migration path for old artifacts, or
  explicitly document why source reprocessing is required. Wire deterministic
  migrations into the bounded light CPU background lane, and wire model-based
  reprocessing into resumable visible heavy work so corpora can gradually
  converge instead of depending on manual one-off commands.
- Design background work as lane-aware, durable, and efficient. Use bounded
  light CPU work for cheap gradual maintenance, visible `bg-heavy` work for
  urgent/model/GPU-heavy jobs, and safe parallelism up to the approved local
  route or workload limit when the job benefits from it. Long-running jobs
  should expose progress, pause or recover at durable checkpoints, avoid losing
  completed work after interruption or power loss, and include the
  upgrade/rebuild path needed when their artifact pipeline changes.
- Prefer small, testable improvements that make the assistant more trustworthy
  before making it more agentic.
- Do not store secrets in this repository.
- Read `docs/project-context.md` before making architectural, security-boundary,
  or terminal-interface changes.

## Deployment Context

Public architecture, security boundaries, and product decisions belong in
`docs/project-context.md`. Machine-specific accounts, paths, remotes, hosts,
ports, sockets, hardware, privilege boundaries, and deployment commands belong
in the operating-system configuration repository, currently `nixos-configs`,
not here. Credentials must remain in its reviewed secret-management path. Keep
Motoko's public development workflow complete without deployment-specific
context.

## Validation

Before committing code changes, run:

```bash
nix flake check
```

For quick syntax-only validation:

```bash
nix develop --command python3 -m py_compile motoko
```
