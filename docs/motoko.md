# Motoko Personal Assistant

Date: 2026-05-17

Motoko is the first terminal chat interface for the HB3 `personal` realm. It is
intentionally small: a Python standard-library script that talks to the existing
local llama.cpp OpenAI-compatible endpoint for Qwen3.6.

Motoko is not Texere, not Hermes, and not an agent runtime. It is a personal
chat and memory tool for the `personal` account.

For documents, Motoko uses a small dependency-free form of hierarchical
retrieval-augmented generation: it builds chunk summaries, file summaries, and a
corpus summary, then retrieves the most relevant chunks for the current question
and includes those excerpts in the prompt.

## Security Boundary

Motoko is installed only for `users.users.personal` on HB3. The `personal`
account is non-sudo and has local-model access, but does not have Hermes
provider-key access.

Motoko does not use:

- provider API keys;
- Hermes;
- Texere;
- LangChain or LangGraph;
- pip packages;
- npm packages;
- a database server;
- service-control authority.

Motoko uses:

- `/nix/store/.../python3` from the NixOS system closure;
- the Python standard library only;
- the existing loopback MTP model endpoint at `127.0.0.1:8083`;
- files in the `personal` account's own home directory.

On `.#hb3-headless`, the default Qwen3.6 service starts at boot. The
`personal` account cannot start, stop, or restart the llama.cpp model services.

## Storage

Default state paths:

```text
~/.local/state/motoko/conversations/
~/.local/state/motoko/indexes/
~/.local/state/motoko/topics/
~/.local/state/motoko/memories.jsonl
```

Default config path:

```text
~/.config/motoko/allowdirs
~/.config/motoko/personality.md
```

Conversation files are JSON. Memories are append-only JSONL rows.

## Personality And Style

Motoko loads conversation style guidance from:

```text
~/.config/motoko/personality.md
```

If the file does not exist, Motoko uses a small built-in default: warm,
attentive, calm, direct, honest, privacy-preserving, and grounded. Create the
editable file with:

```bash
motoko personality init
```

Inspect it with:

```bash
motoko personality
motoko personality path
```

The file is free-form Markdown. Prose is preferred over numeric sliders because
it gives the model richer behavioral guidance. This file shapes tone and style;
it does not override factual accuracy, source-grounding, privacy boundaries, or
explicit safety constraints.

## Document Access

Document reads are allowlist-only. Before Motoko can attach a file or directory,
the directory must be added explicitly:

```bash
motoko allow-dir ~/Documents
```

After that, files under the allowed directory can be attached directly with
`/read PATH` or `motoko chat --file PATH`. Larger directories should be indexed
with `motoko index DIR`, `motoko chat --dir DIR`, or `/index DIR`.

Motoko does not claim live filesystem access to the model. Attached documents
are read by the CLI, clipped to a bounded size, and included in the prompt.
Motoko never edits, rewrites, annotates, truncates, moves, or deletes source
documents. It writes only its own config and state files under the Motoko config
and state directories. Reusable document indexes are derived Motoko state, not
source-document edits.

## Commands

Start a new chat:

```bash
motoko
motoko new
motoko help
motoko chat --line
```

When stdin and stdout are terminals, `motoko` starts in a small stdlib-only TUI:
the conversation stays above, the composer stays pinned to the bottom, `/`
opens command suggestions, arrow keys move through suggestions, Enter accepts a
selection, and typed text remains available while Motoko streams an answer.
Use `/stop` to stop the current streamed answer.
If the raw terminal UI is not available or you want the older behavior, use
`motoko chat --line` or set `MOTOKO_TUI=0`.

The TUI uses a compact `>` input prompt. Motoko's assistant label is purple and
shown as `Motoko`, without a `>` suffix. System/status lines use compact `sys`.
Supporting UI such as titles and command text uses turquoise where terminal
color support is available. The slash-command dropdown scrolls with the active
selection so entries past the first visible page remain visible.
The default spinner is the plain ASCII `-/|\` cycle so Linux TTYs with Terminus
do not show square fallback glyphs. Set `MOTOKO_SPINNER=braille` only in a
terminal/font combination known to render braille cells correctly. The top
status line includes the model badge, for example `qwen3.6-27b-mtp:8083`, so
the local MTP endpoint is visible while chatting.

Emacs-style editing keys in the TUI:

```text
Ctrl+A  beginning of line
Ctrl+E  end of line
Ctrl+B  backward char
Ctrl+F  forward char
Alt+B   backward word
Alt+F   forward word
Ctrl+K  kill to end of line
Ctrl+Y  yank killed text
Ctrl+P  previous dropdown item or history entry
Ctrl+N  next dropdown item or history entry
```

List and resume conversations:

```bash
motoko list
motoko resume
motoko resume CONVERSATION_ID
motoko show
motoko show CONVERSATION_ID
motoko status
```

When an ID is omitted in an interactive terminal, Motoko opens a numbered
picker. This avoids typing long conversation IDs for normal use.
`motoko list` displays compact `created`, `updated`, `branch`, and
`conversation` columns. Full timestamps remain stored in the conversation JSON.

Manage memories:

```bash
motoko memories
motoko memory search "query"
motoko memory review
motoko remember "short durable memory"
motoko memory edit MEM_ID "corrected memory text"
motoko memory importance MEM_ID 1-5
motoko memory pin MEM_ID
motoko memory unpin MEM_ID
motoko forget MEM_ID
```

Useful in-chat commands:

```text
/help
/
/stop
/new [TITLE]
/resume [CONVERSATION_ID]
/read PATH
/index-plan PATH
/index PATH
/attach-index [INDEX_ID]
/topic [INDEX_ID] QUERY
/deepen [INDEX_ID] QUERY
/attach-topic [TOPIC_ID]
/dossier QUERY
/attach-dossier [DOSSIER_ID]
/indexes
/topics
/topic-show [TOPIC_ID]
/dossiers
/dossier-show [DOSSIER_ID]
/study QUERY
/compact
/sources
/status
/personality
/profile
/profile-refresh
/remember TEXT
/memory search TEXT
/memory review
/memory edit ID TEXT
/memory importance ID 1-5
/memory pin ID
/memory unpin ID
/forget ID
/memorize
/memories
/title TEXT
/exit
```

Commands with optional IDs open a picker when the ID is omitted. If Python
`readline` is available, Motoko also enables Tab completion in chat; type `/`
then Tab to list slash commands, or start `/resume`, `/attach-index`,
`/attach-topic`, `/topic-show`, `/attach-dossier`, `/dossier-show`, `/topic`,
or `/deepen` and press Tab to complete stored IDs. This is a small stdlib line
editor fallback. In the default TUI, these same commands use an inline dropdown
above the bottom composer.

The TUI is implemented with Python standard-library terminal primitives only.
It does not add prompt-toolkit, rich, textual, urwid, curses UI dependencies,
or any package outside the Python standard library. It intentionally keeps a
line-mode fallback because raw terminal control varies across TTYs and SSH
clients.

`/memorize` asks the local model to propose durable memories from the current
conversation. Motoko prints the proposal and appends it only after an explicit
`yes`.

New memories receive stable IDs and provenance fields. Manual memories record
whether they came from a shell command or a conversation. Model-proposed
memories record the source conversation and that they were created by
`/memorize`. Use `motoko memory review` or `/memory review` to inspect that
provenance before trusting a memory.

Each turn receives an automatic ranked subset of cross-conversation memories
plus a bounded set of recent saved conversation capsules. Recent conversation
recall uses two lanes: a tiny recency lane for the newest useful conversations
and a relevance lane scored against the current prompt and thread. Durable
memory ranking remains separate and uses the current prompt, the conversation
title, recent user turns, the compacted summary, memory importance, pinned
status, repeated sightings, thread relevance, and recency. Use `/sources` after
an answer to see which memories and recent conversations were selected and why.

Motoko also runs quiet after-answer maintenance. Periodically, after enough
messages have accumulated, she proposes high-confidence durable memories to
herself and saves them automatically with provenance `auto-model-proposed`.
Duplicate detection reinforces existing similar memories by updating their
`seen_count`, tags, and last-seen metadata instead of creating many copies of
the same fact. Stored memories remain inspectable with `motoko memory review`,
searchable with `motoko memory search`, and removable with `motoko forget`.
The top bar reports the active maintenance phase, such as `memory: checking`,
`memory: proposing`, `memory: saving`, or `memory: compacting`. Interrupted
maintenance writes a small resumable state file and is retried conservatively
when the same conversation is opened again. The TUI also shows how long the
current maintenance phase has been active; memory proposal work is bounded by a
wall-clock timeout so a stuck proposal returns control to the chat.
After the first few messages, maintenance may also ask the local model for a
short conversation title. First-message titles are provisional unless Javier
set a title manually with `/title` or `motoko new --title`.

Memories default to importance `3`. `motoko memory importance ID 1-5` changes
that priority. `motoko memory pin ID` makes a memory eligible for inclusion even
when lexical matching is weak; use this for stable identity, style, or life
context that should travel across conversations.

`/compact` summarizes older conversation turns into a compact conversation
summary, keeps the most recent turns verbatim, and saves both into the
conversation JSON. Motoko may also perform this compaction automatically after
long chats so context remains usable without forcing every old turn into the
model prompt.

`/sources` prints the memories, recent conversation capsules, compacted summary,
attached files, file summaries, document chunks, and index freshness state used
for the last answer. This is meant to make answers inspectable: Motoko should
be able to say which stored context influenced a response instead of sounding
like she has unbounded hidden knowledge.

`/status` prints the current model endpoint, state paths, memory/index/topic
counts, and the amount of context attached to the active conversation.

While the TUI is open, Motoko also runs a low-intensity background study loop
only when she is idle. The loop refreshes a private context catalog, checks
index freshness, and records study suggestions. By default it avoids heavy
model calls so it does not compete with chat; set `MOTOKO_BACKGROUND_PROFILE=1`
to allow idle profile-dossier refreshes. It does not silently crawl new
directories or create large document indexes; document access still starts from
explicit allowlists and `/index`. Use `/study QUERY` for a deliberate bounded
study pass that either reuses an existing dossier, builds a topic dossier from
an attached or relevant index, or builds a memory/conversation dossier.

`/profile-refresh` or `motoko profile refresh` builds a compact profile dossier
from durable memories and recent conversation material. This is an explicit
hierarchical retrieval-augmented memory layer for Javier's stable preferences,
goals, projects, working style, personal context, constraints, sensitivities,
and open questions. `/profile` or `motoko profile` displays it. The dossier is
included in future prompts with `/sources` provenance.

`/dossier QUERY` or `motoko dossier QUERY` builds a query-focused memory
dossier from the profile dossier, ranked durable memories, and relevant/recent
conversation capsules. This is Motoko's conversation-history HRAG layer: it is
for deliberately studying one subject from her stored memory before continuing
the chat. It writes derived private state under:

```text
~/.local/state/motoko/dossiers/
```

Use `/attach-dossier`, `/dossiers`, `/dossier-show`, `motoko dossiers`,
`motoko dossier-show`, or `motoko chat --dossier DOSSIER_ID` to reuse a dossier.
Memory dossiers may duplicate sensitive personal snippets from memories and
conversation history, so treat them as private Motoko state.

## Document Indexes

Build a reusable mixed-file index from an allowed directory:

```bash
motoko allow-dir ~/Documents
motoko index ~/Documents --name personal-notes
```

Preview what would be indexed without writing derived text:

```bash
motoko index ~/Documents --plan
```

The default indexing mode is `auto`: Motoko recursively indexes every file that
looks like readable UTF-8-ish text, including Org, Markdown, plain text, source
files, config files, logs, JSON/YAML/TOML, and extensionless text. It skips
common cache/vendor directories and files that look binary. The goal is one
corpus index per source tree, not separate indexes by file extension.

By default, a new reusable index may store up to 200 GiB of derived chunk text
under Motoko state. Override this for a reviewed one-off index with:

```bash
motoko index ~/Documents --max-derived-bytes 250GiB
```

or set:

```bash
MOTOKO_MAX_DERIVED_INDEX_BYTES=250GiB motoko index ~/Documents
```

Start a chat while indexing a directory:

```bash
motoko chat --dir ~/Documents
```

Attach an existing index:

```bash
motoko indexes
motoko chat --index INDEX_ID
```

Inside a chat:

```text
/index-plan ~/Documents
/index ~/Documents
/attach-index
/attach-index INDEX_ID
```

Indexes live under:

```text
~/.local/state/motoko/indexes/
```

Each index stores:

- a corpus-level summary;
- one summary per file;
- one summary per chunk;
- raw chunk text for later retrieval, stored as Motoko-owned derived files;
- source fingerprints: file size, mtime, and SHA-256 at index time.

On each question, Motoko scores the indexed summaries and chunks with a small
local lexical retriever, then injects the corpus summary, relevant file
summaries, and top matching excerpts into the prompt. The retrieval window
uses the current prompt plus recent conversation context and adapts to the
question: broad evidence/detail/deep-analysis prompts receive a wider slice of
attached indexes than ordinary conversational prompts. This avoids sending every
file on every turn while still letting the model answer from relevant source
text.

`motoko indexes` reports whether an index appears `fresh`, `stale`,
`metadata-changed`, or `unknown`. Older indexes that predate fingerprints show
as `unknown`; rebuild them if freshness matters. When an attached index is
stale, Motoko includes a freshness warning in the prompt and `/sources` output
so the answer can be reviewed with that caveat.

Current indexing bounds favor completeness over early omission. Motoko does not
cap the number of files matched by a document-index request and does not impose
a fixed per-file byte cap during reusable indexing. It streams each source file,
splits the decoded text into summarized chunks, and stores those chunks under
`~/.local/state/motoko/indexes/INDEX_ID.chunks/`. The index JSON stores metadata,
summaries, fingerprints, and paths to those derived chunk files.

This means Motoko may duplicate indexed text inside her own private state so
that later retrieval can answer from the whole indexed corpus. The source files
themselves are not modified. To avoid needless growth, new indexes reuse exact
duplicate chunks already present in previous indexes instead of writing the same
chunk text again. If an index build fails before the index JSON is saved, or if
the derived-text budget would be exceeded, Motoko removes the partially written
chunk directory to avoid abandoned derived text.

Large directories and large files can take a long time because every indexed
chunk is summarized through the local model. Use `--glob` to narrow very broad
indexes when needed.

## Topic Dossiers

Topic dossiers are Motoko's first topic-focused HRAG layer. They are not a
separate source-document format and they do not modify the source tree. A topic
dossier starts from one or more existing document indexes, retrieves the chunks
most relevant to a specific question or subject, and writes a derived private
dossier under:

```text
~/.local/state/motoko/topics/
```

Create one from the shell:

```bash
motoko topic INDEX_ID "family memories involving Buenos Aires" --name buenos-aires
motoko deepen INDEX_ID "family memories involving Buenos Aires"
motoko topics
motoko topic-show TOPIC_ID
motoko topic-show TOPIC_ID --evidence
motoko chat --topic TOPIC_ID
motoko dossier "why does Javier care about craftsmanship?"
motoko dossiers
motoko dossier-show DOSSIER_ID
motoko dossier-show DOSSIER_ID --evidence
motoko chat --dossier DOSSIER_ID
```

Create or attach one from inside a chat:

```text
/topic family memories involving Buenos Aires
/topic INDEX_ID family memories involving Buenos Aires
/deepen family memories involving Buenos Aires
/deepen INDEX_ID family memories involving Buenos Aires
/attach-topic
/attach-topic TOPIC_ID
```

If a chat already has a document index attached, `/topic QUERY` uses that
attached index. Otherwise `/topic` opens an index picker and then asks for the
topic query. Topic dossiers store summaries and selected excerpts as Motoko
derived state, so they can duplicate sensitive personal text inside the
`personal` user's Motoko state directory. They are useful for going deeper into
a subject without reinjecting the entire corpus on every turn, but they should
be treated as private assistant memory.

`/deepen` and `motoko deepen` use the same mechanism with the larger topic
budget. Use them when a conversation has narrowed to a subject and Motoko needs
a more detailed private dossier before answering follow-up questions.

## Operational Model

Normal use from HB2 or another client:

```bash
ssh hb3-personal
motoko
```

The default endpoint is the MTP Qwen3.6 service:

```text
http://127.0.0.1:8083/v1/chat/completions
```

While waiting for the first streamed response token or while background
maintenance runs, Motoko shows a small thinking spinner. The default `auto`
mode uses a single-character braille spinner on UTF-8 terminals and falls back
to ASCII otherwise:

```bash
MOTOKO_SPINNER=auto motoko
MOTOKO_SPINNER=ascii motoko
MOTOKO_SPINNER=block motoko
MOTOKO_SPINNER=braille motoko
MOTOKO_SPINNER=off motoko
```

## Limits

Motoko is not a sandbox. The isolation comes from the HB3 account split and
from not granting `personal` sudo, provider keys, SSH/GitHub credentials, or
service-control authority.

Motoko has explicit attached documents, hierarchical document indexes,
conversation history, automatic compaction, ranked durable memories, and
topic-focused dossiers. If
personal memory/RAG becomes sensitive enough to require stronger isolation, move
the assistant state and process into a reviewed NixOS container or KVM VM while
keeping GPU inference on the HB3 host unless a later review justifies GPU
passthrough.
