# Motoko Project Context

Date: 2026-05-17

Motoko was split out of `nixos-configs` into this repository so her code,
tests, and main documentation can evolve independently while NixOS keeps only
host integration policy.

## Current Role

Motoko is Javier's local terminal personal assistant for the HB3 `personal`
realm. She is meant to feel conversational and useful for private daily notes,
documents, memory, and local Qwen chat.

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
- `nixos-configs` consumes Motoko through a private GitHub flake input.
- HB3 installs Motoko only for the non-sudo `personal` user.
- `personal` has local-model access but no Hermes/provider-key group access.
- `.#hb3-headless` starts the default Qwen3.6 local model service so `personal`
  can use Motoko without first entering an admin account.
- Motoko's default endpoint is the local MTP llama.cpp endpoint:
  `http://127.0.0.1:8083/v1/chat/completions`.

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
- source documents are read-only;
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
- topic dossiers and deeper dossiers over already indexed material;
- TTY-friendly terminal ergonomics;
- no new runtime dependencies unless the benefit is reviewed and concrete.

Avoid for now:

- autonomous file editing;
- broad filesystem crawling without explicit allowlists;
- provider/API key handling;
- browser UI;
- vector database dependencies;
- role-playing multi-agent abstractions;
- hidden background state that cannot be inspected from the CLI.

## Javier's Interface Preferences

Current UI direction:

- Motoko's name in chat should be purple.
- Motoko's assistant label is `Motoko`, without a `>` suffix; color carries
  the role distinction.
- System/status lines use compact `sys`, not `System>`.
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
  - `Ctrl+K` kill to end of line;
  - `Ctrl+Y` yank killed text;
  - `Ctrl+P` previous suggestion/history;
  - `Ctrl+N` next suggestion/history.
- Conversation lists should use compact relative times while preserving full
  timestamps in JSON state.
- Resume/list columns should be readable and compact:
  `created`, `updated`, `branch`, `conversation`.
- Recent saved conversations should be available as bounded, inspectable context
  in new chats. Durable memories remain separate from this recency recall.
- Query-focused memory dossiers should be available when Javier wants Motoko to
  study a subject across saved memories and prior conversations before
  continuing the chat.
- Background memory work should report the actual phase and recover cleanly
  from interruption instead of leaving an indefinite spinner.
- Unicode braille spinners are preferred when the terminal can render them;
  Linux TTYs should use the ASCII spinner because some fonts render braille as
  square fallback glyphs.

## Near-Term Next Improvement

The highest-ROI next engineering improvement is improving the quality of
profile dossiers and document-derived dossiers after real personal documents
are added. The regression suite now includes a small fake OpenAI-compatible
test server so Motoko can test streaming, maintenance, recall, and profile
behavior without requiring Qwen or llama.cpp to be running.
