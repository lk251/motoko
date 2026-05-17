# Motoko Personal Assistant

Date: 2026-05-16

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
- the existing loopback model endpoint at `127.0.0.1:8082`;
- files in the `personal` account's own home directory.

On `.#hb3-headless`, the default Qwen3.6 service starts at boot. The
`personal` account cannot start, stop, or restart the llama.cpp model services.

## Storage

Default state paths:

```text
~/.local/state/motoko/conversations/
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
and state directories.

## Commands

Start a new chat:

```bash
motoko
```

List and resume conversations:

```bash
motoko list
motoko resume CONVERSATION_ID
motoko show CONVERSATION_ID
```

Manage memories:

```bash
motoko memories
motoko memory review
motoko remember "short durable memory"
motoko memory edit MEM_ID "corrected memory text"
motoko forget MEM_ID
```

Useful in-chat commands:

```text
/help
/read PATH
/index PATH
/attach-index INDEX_ID
/compact
/sources
/personality
/remember TEXT
/memory review
/memory edit ID TEXT
/forget ID
/memorize
/memories
/title TEXT
/exit
```

`/memorize` asks the local model to propose durable memories from the current
conversation. Motoko prints the proposal and appends it only after an explicit
`yes`.

New memories receive stable IDs and provenance fields. Manual memories record
whether they came from a shell command or a conversation. Model-proposed
memories record the source conversation and that they were created by
`/memorize`. Use `motoko memory review` or `/memory review` to inspect that
provenance before trusting a memory.

`/compact` summarizes older conversation turns into a compact conversation
summary, keeps the most recent turns verbatim, and saves both into the
conversation JSON. This is manual compaction; Motoko does not silently rewrite
conversation history in the background.

`/sources` prints the memories, compacted summary, attached files, file
summaries, document chunks, and index freshness state used for the last answer.
This is meant to make answers inspectable: Motoko should be able to say which
stored context influenced a response instead of sounding like she has
unbounded hidden knowledge.

## Document Indexes

Build a reusable index from an allowed directory:

```bash
motoko allow-dir ~/Documents
motoko index ~/Documents --glob '*.txt' --name personal-notes
```

Start a chat while indexing a directory:

```bash
motoko chat --dir ~/Documents --glob '*.txt'
```

Attach an existing index:

```bash
motoko indexes
motoko chat --index INDEX_ID
```

Inside a chat:

```text
/index ~/Documents
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
- bounded raw chunk text for later retrieval.
- source fingerprints: file size, mtime, and SHA-256 at index time.

On each question, Motoko scores the indexed summaries and chunks with a small
local lexical retriever, then injects the corpus summary, relevant file
summaries, and top matching excerpts into the prompt. This avoids sending every
file on every turn while still letting the model answer from relevant source
text.

`motoko indexes` reports whether an index appears `fresh`, `stale`,
`metadata-changed`, or `unknown`. Older indexes that predate fingerprints show
as `unknown`; rebuild them if freshness matters. When an attached index is
stale, Motoko includes a freshness warning in the prompt and `/sources` output
so the answer can be reviewed with that caveat.

Current indexing bounds favor completeness over early omission. Motoko does not
cap the number of files matched by a document-index request. For each file, it
indexes up to 20 MiB and splits all indexed text into summarized chunks. If a
file exceeds 20 MiB, Motoko does not modify the source file; it indexes a
truncated in-memory copy, records `truncated = true`, and records how many bytes
were omitted. This non-destructive source-file rule applies to every indexed or
attached file, not only files above the size cap. Motoko should not be treated
as having read bytes beyond a recorded truncation point.

Large directories and large files can take a long time because every indexed
chunk is summarized through the local model. Use `--glob` to narrow very broad
indexes when needed.

## Operational Model

Normal use from HB2 or another client:

```bash
ssh hb3-personal
motoko
```

The default endpoint is the non-MTP Qwen3.6 service:

```text
http://127.0.0.1:8082/v1/chat/completions
```

Override only for a reviewed experiment:

```bash
MOTOKO_ENDPOINT=http://127.0.0.1:8083/v1/chat/completions motoko
```

## Limits

Motoko is not a sandbox. The isolation comes from the HB3 account split and
from not granting `personal` sudo, provider keys, SSH/GitHub credentials, or
service-control authority.

Motoko has explicit attached documents, hierarchical document indexes,
conversation history, manual compaction, and simple durable memories. If
personal memory/RAG becomes sensitive enough to require stronger isolation, move
the assistant state and process into a reviewed NixOS container or KVM VM while
keeping GPU inference on the HB3 host unless a later review justifies GPU
passthrough.
