# Mares Motoko Handoff

Date: 2026-05-18

This is the repo-local handoff for future Codex sessions running as the
non-admin `mares` account in:

```text
/home/mares/repos/motoko
```

It distills current repo docs, NixOS integration facts, and safe Codex memory
summaries. It does not copy raw Codex session logs and must not contain secrets,
tokens, API keys, private keys, browser/session data, or unrelated personal
material.

## Why This File Exists

Conversation history from Javier's admin Codex session will not be available to
Codex running as `mares`. Future `mares` Codex sessions should therefore treat
this document, plus `AGENTS.md`, `README.md`, and the rest of `docs/`, as the
durable context for Motoko work.

The delivery path is:

1. Javier edits and commits this file in `/home/javier/repos/motoko`.
2. Javier pushes the Motoko repo to `mbp111`.
3. The `mares` clone pulls the commit into `/home/mares/repos/motoko`.
4. Codex running as `mares` reads this file from the repo.

Do not replace this with copied raw `.codex` sessions. Repo-local summaries are
the intended handoff mechanism.

## Purpose

Motoko is Javier's small terminal personal assistant. She is a local chat,
memory, and document-context tool over an existing llama.cpp
OpenAI-compatible endpoint.

Motoko is intentionally not:

- Texere;
- Hermes;
- a provider gateway;
- an autonomous host-admin agent;
- a LangChain or LangGraph app;
- a browser or web UI;
- a service manager or NixOS apply tool.

The near-term goal is a dependable, inspectable, dependency-light terminal
assistant. New capability should first improve trust, provenance, memory
quality, document retrieval quality, and TTY ergonomics.

## Repository Locations

Expected working checkouts:

```text
/home/javier/repos/motoko
/home/mares/repos/motoko
```

Current repo convention:

```text
origin  mbp111:/home/javier/git/motoko.git
github  named remote, if configured
codeberg named remote, if configured
```

Verify live remotes before pushing:

```bash
cd /home/mares/repos/motoko
git remote -v
```

Do not assume GitHub or Codeberg authorization exists for `mares`. Push only
when Javier explicitly asks and only after verifying the intended remote. Do not
broaden credentials, copy Javier's SSH keys, or add new account authorization to
make a push work.

## Current Architecture

Motoko is deliberately simple:

- `motoko`: one Python standard-library script and CLI/TUI implementation.
- `flake.nix`: packages the script with `python312` using
  `writeShellScriptBin`.
- `README.md`: high-level user and design summary.
- `AGENTS.md`: repo rules for Codex.
- `docs/motoko.md`: main operating manual.
- `docs/project-context.md`: architecture, security, interface, and product
  direction.
- `tests/motoko_regression.py`: stdlib regression tests for memory, TUI helpers,
  model-call shims, explicit memories, and indexing plans.
- `tests/motoko_eval.py`: small evaluation harness for study, context planning,
  and background-study behavior.
- `tests/motoko_tty.py`: pseudo-terminal render checks for TTY/tmux-like
  behavior.
- `CHANGELOG.md`: concise user-facing change summaries.

Motoko uses only Python's standard library. Do not add runtime dependencies
unless Javier explicitly approves the concrete tradeoff.

Important environment variables:

```text
MOTOKO_ENDPOINT
MOTOKO_MODEL
MOTOKO_STATE_HOME
MOTOKO_CONFIG_HOME
MOTOKO_TUI
MOTOKO_SPINNER
MOTOKO_BACKGROUND_STUDY
MOTOKO_BACKGROUND_PROFILE
MOTOKO_MAX_DERIVED_INDEX_BYTES
```

The defaults target HB3's local Qwen endpoint and normal per-user XDG paths.
Tests should override state/config paths so they never touch real user memory.

## NixOS Integration

The active NixOS integration lives in:

```text
/home/javier/repos/nixos-configs
```

In `nixos-configs`, Motoko is consumed as a flake input:

```nix
motoko = {
  url = "git+ssh://mbp111/home/javier/git/motoko.git";
  inputs.nixpkgs.follows = "nixpkgs";
};
```

The NixOS flake passes:

```nix
motokoPackages = motoko.packages.${system};
```

HB3 then installs `motokoPackages.default` for the non-admin `mares` and
`personal` accounts. A normal Motoko source change is not deployed to the NixOS
system package until Javier updates the `motoko` flake input in
`nixos-configs`, reviews the resulting diff, and rebuilds from the admin path.

`mares` has normal development authority for Motoko source work in this
repository. NixOS deployment is separate: `mares` should not update the deployed
`nixos-configs` flake lock or rebuild HB3 unless Javier explicitly asks for
that deployment phase.

## HB3 Realm Model

HB3 currently has three relevant Unix accounts:

- `javier`: administrator account. This is the sudo and NixOS apply path.
- `mares`: Mares Engineering work realm. No sudo. Normal Codex development,
  analysis, and Motoko source work can happen here.
- `personal`: personal assistant realm. No sudo. Private Motoko memory and
  personal document context belong here.

`mares` and `personal` are intentionally separate. They may both have Motoko
installed and both may reach the local model endpoint, but their state and data
must remain separate under each account's home directory.

Do not copy Javier's admin SSH keys, GitHub tokens, browser profiles, shell
history, Codex auth, raw Codex sessions, provider keys, or personal data into
`mares` or `personal`.

## Local Model Endpoint

Motoko's default endpoint is:

```text
http://127.0.0.1:8083/v1/chat/completions
```

The default model string in the Motoko source is:

```text
qwen3.6-27b-mtp-ud-q5-k-xl
```

On HB3 headless, NixOS starts the Qwen3.6 27B MTP UD-Q5 llama.cpp service at
boot. The service is intended to be a dumb local inference endpoint, not a tool
owner, memory owner, credential holder, or host-mutation authority.

`mares` and `personal` should be able to use the endpoint. They should not be
able to start, stop, restart, or reconfigure model services. That remains
Javier/admin responsibility.

If the endpoint changes later, update Motoko defaults, docs, tests, and the
NixOS integration deliberately. Do not silently route Motoko through Hermes,
provider API keys, or a cloud service.

## State And Config Layout

Motoko uses the same directory shape for every Unix account:

```text
~/.local/state/motoko/conversations/
~/.local/state/motoko/indexes/
~/.local/state/motoko/topics/
~/.local/state/motoko/dossiers/
~/.local/state/motoko/memories.jsonl
~/.local/state/motoko/maintenance.json
~/.local/state/motoko/profile.json
~/.local/state/motoko/context-catalog.json
~/.local/state/motoko/study-state.json
~/.local/state/motoko/study-jobs.jsonl
~/.local/state/motoko/heavy-study.json
~/.config/motoko/allowdirs
~/.config/motoko/personality.md
```

For `mares`, these paths resolve under `/home/mares`. For `personal`, they
resolve under `/home/personal`.

Never merge `personal` Motoko state into `mares`. `personal` memories, dossiers,
indexes, and allowed documents may contain private material. Future Codex work
from `mares` should improve Motoko through code review, synthetic fixtures,
test cases, and user-visible behavior, not by reading `/home/personal`.

Document reads are allowlist-only. Motoko should not broadly crawl a home
directory. Add document access deliberately:

```bash
motoko allow-dir ~/Documents
```

Document indexes and dossiers are derived private state and may duplicate
source text under Motoko's state directory. Treat them as private account data.

## Normal Use

Start a new chat:

```bash
motoko
motoko new
```

Inspect the runtime:

```bash
motoko about
motoko status
```

List and resume conversations:

```bash
motoko list
motoko resume
motoko resume CONVERSATION_ID
```

Manage memories:

```bash
motoko memories
motoko memory review
motoko memory search "query"
motoko remember "short durable memory"
```

Use documents:

```bash
motoko allow-dir ~/Documents
motoko index ~/Documents --plan
motoko index ~/Documents
motoko chat --index INDEX_ID
```

Inside the TUI, `/help` opens a categorized help view. Press `q` or `Esc` to
return to the conversation.

## Development Commands

From the Motoko repo:

```bash
cd /home/mares/repos/motoko
```

Inspect state:

```bash
git status --short --branch
git log --oneline -5
```

Quick syntax check:

```bash
nix develop --command python3 -m py_compile motoko
```

Regression and evaluation checks:

```bash
nix develop --command python3 tests/motoko_regression.py
nix develop --command python3 tests/motoko_eval.py
nix develop --command python3 tests/motoko_tty.py
```

Full flake check:

```bash
nix flake check
```

Build or run the packaged app:

```bash
nix build
nix run
```

Whitespace check before committing:

```bash
git diff --check
```

Because this is a Git flake, untracked files may be invisible to Nix flake
checks. If a new source, doc, or test file should be part of the package or
checks, `git add` it before relying on `nix flake check`.

## Mares Motoko Workflow

1. Inspect, edit, and test in `/home/mares/repos/motoko`.

   ```bash
   cd /home/mares/repos/motoko
   git status --short --branch
   # edit files
   nix develop --command python3 -m py_compile motoko
   nix develop --command python3 tests/motoko_regression.py
   nix develop --command python3 tests/motoko_eval.py
   nix develop --command python3 tests/motoko_tty.py
   git diff --check
   ```

   Work directly on `master` for small, approved changes. Create feature
   branches only when they are technically useful, such as for larger or
   interruptible work.

2. Commit accepted Motoko changes locally.

   ```bash
   git status --short
   git diff --stat
   git add FILES
   git commit -m "Clear Motoko change message"
   ```

3. Push only when Javier explicitly asks.

   ```bash
   git remote -v
   git push origin master
   ```

   Do not add credentials, copy Javier's SSH keys, or push to a remote that has
   not been confirmed for `mares`.

4. Update `nixos-configs` only from the Javier/admin path when a deployed
   Motoko package change is accepted.

   ```bash
   cd /home/javier/repos/motoko
   git push origin master

   cd /home/javier/repos/nixos-configs
   nix flake lock --update-input motoko
   nix build --dry-run .#nixosConfigurations.hb3-headless.config.system.build.toplevel
   ```

   Javier owns the final `nixos-configs` commit, review, and `hb3-headless`
   rebuild/switch. `mares` does not run sudo and does not mutate the live
   system.

## Security Boundaries

Motoko development from `mares` should preserve these boundaries:

- no sudo;
- no `nixos-rebuild switch`;
- no service restarts;
- no provider API keys;
- no Hermes provider-key access;
- no admin SSH keys;
- no copied Javier Codex auth or raw session history;
- no browser/session data;
- no broad reads of `/home/javier` or `/home/personal`;
- no broad document crawling without an explicit Motoko allowlist;
- no Docker socket, cloud credentials, or package-manager secrets;
- no pip/npm runtime dependency installation;
- no LangChain, LangGraph, vector database, web UI, or database server without a
  reviewed design change.

If Motoko needs to learn from personal documents, the code should run as
`personal` and use that account's allowlists and state. Codex running as
`mares` should work from synthetic tests, interface reports, and code review,
not from private personal corpora.

## Javier/Admin Responsibilities

Javier remains responsible for:

- deploying accepted Motoko package revisions through `nixos-configs`;
- pushing deployment or admin-owned remotes when required;
- updating the `motoko` flake input in `nixos-configs`;
- running NixOS review/dry-build/switch workflows;
- starting, stopping, or debugging systemd model services;
- managing secrets and provider credentials;
- granting or revoking SSH/Git credentials;
- deciding whether Motoko's personal state needs a stronger boundary such as a
  NixOS container or KVM VM.

## Known Pitfalls

- `codex /resume` in `mares` may be empty. That is expected because Codex
  sessions are account-local and raw session logs are not copied.
- Do not copy `/home/javier/.codex` wholesale. Only safe memory/skill/rule
  context should be bootstrapped by reviewed scripts.
- Do not treat Motoko state as repo data. Conversations, memories, indexes,
  dossiers, and personality files live under each user's home directory.
- Do not merge `personal` and `mares` Motoko state just because the directory
  shape is the same.
- Do not reintroduce LiteLLM, LangChain, LangGraph, provider gateways, web UIs,
  or database services into Motoko to solve a local assistant problem.
- Do not make the local model endpoint responsible for tools, repo access,
  memory, RAG state, credentials, or host mutation.
- Do not assume a live Qwen endpoint is required for all tests. The regression
  suite includes a small fake OpenAI-compatible server and isolated state paths.
- For flakes, remember that untracked files are easy to miss. Add new files
  before trusting `nix flake check`.
- If terminal rendering breaks, test through `tests/motoko_tty.py` and prefer
  TTY/tmux-safe behavior over GUI-terminal-only polish.

## Deferred Work

Current high-value future work:

- improve profile and topic dossier quality using synthetic fixtures and
  user-visible reports;
- improve document-derived dossier quality after real documents are added by
  `personal`, without Codex reading those documents directly;
- add better memory review/edit/delete workflows when daily use shows the exact
  friction;
- keep background study inspectable and bounded;
- consider a NixOS container or KVM VM for personal assistant state only if the
  current account split is not enough;
- revisit the local model endpoint if the Qwen3.6 MTP service changes.

Do not reintroduce:

- provider API key handling;
- hidden autonomous tool execution;
- broad filesystem crawling;
- web UI machinery;
- database servers;
- pip/npm dependency sprawl;
- LangChain or LangGraph.

Motoko should stay small, inspectable, and useful before becoming more agentic.
