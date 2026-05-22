# Motoko Personal Assistant

Date: 2026-05-17

Motoko is the first terminal chat interface for the HB3 `personal` realm, and
is also available as a small local helper for the `mares` and `javier` realms.
It is intentionally small: a Python standard-library script that talks to the
existing local llama.cpp OpenAI-compatible endpoint for Qwen3.6.

Motoko is not Texere, not Hermes, and not an agent runtime. It is primarily a
personal chat and memory tool; when used from `javier` or `mares`, its repo
commands are fixed read-only review helpers.

For documents, Motoko uses a small dependency-free form of hierarchical
retrieval-augmented generation: it builds chunk summaries, file summaries, and a
corpus summary, then retrieves the most relevant chunks for the current question
and includes those excerpts in the prompt.

## Security Boundary

Motoko is installed for `personal`, `mares`, and `javier` on HB3. Each account
uses its own home directory, so conversations, memories, indexes, and
permissions are separate unless Javier deliberately imports or copies state.
The `personal` and `mares` accounts are non-sudo. The `personal` account has
local-model access, but does not have Hermes provider-key access.

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

Default per-user state paths:

```text
~/.local/state/motoko/conversations/
~/.local/state/motoko/indexes/
~/.local/state/motoko/topics/
~/.local/state/motoko/memories.jsonl
```

Default config path:

```text
~/.config/motoko/config.json
~/.config/motoko/allowdirs
~/.config/motoko/personality.md
```

Conversation files are JSON. Memories are append-only JSONL rows.

## Identity And Personality

Motoko separates structured identity from conversational style:

- `~/.config/motoko/config.json` says who she is in this Unix account: name,
  realm, role, and small UI defaults such as Motoko's assistant label color.
  NixOS may override only the assistant label color for a realm by setting
  `MOTOKO_ALIAS_COLOR`.
- `~/.config/motoko/personality.md` says how she should speak: tone, warmth,
  directness, enthusiasm, and style.

This keeps one codebase and one executable while allowing each account to have a
different identity and separate memories. The repo stays named `motoko`; the
instance identity is per user.

Example identity config:

```json
{
  "identity": {
    "name": "Motoko",
    "realm": "admin",
    "description": "NixOS and repository review assistant for Javier's admin account."
  },
  "ui": {
    "assistant_color": "purple"
  }
}
```

Motoko shows identity in:

```bash
motoko identity
motoko about
motoko status
```

and includes it in the system prompt and `/sources` provenance for each answer.
`motoko about` is the compact introduction screen: Motoko's name, version,
brief purpose and development values, the Mares ASCII logo in the assistant
color, identity/realm, active chat model and endpoint, background lanes, state
paths, and permissions. In the TUI, `/about` and other report-style commands
open a temporary page instead of adding report text to the chat view; close the
page with Enter or Esc. Detailed model route information lives in
`motoko model-routes` and `/model-routes` instead of `/about`.

## Permissions

Motoko has a small per-user feature gate stored in:

```text
~/.config/motoko/config.json
```

Inspect it with:

```bash
motoko permissions
motoko permissions path
```

Change it with:

```bash
motoko permissions set chat-only
motoko permissions set repo-read
motoko permissions set repo-review
```

The modes are:

- `chat-only`: chat, conversations, memories, profile, personality, and status;
  no document reads, indexes, or repo inspection.
- `repo-read`: `chat-only` plus allowlisted document reads and document
  indexes. This is the default because it preserves Motoko's original document
  workflow.
- `repo-review`: `repo-read` plus fixed read-only Git/review summaries for
  allowlisted repositories.

These permissions are Motoko feature gates, not a sandbox. The real security
boundary is still the Unix user, file permissions, SSH policy, NixOS service
policy, and explicit document allowlists. Motoko permissions do not grant sudo,
do not grant Git push access, and do not bypass `motoko allow-dir`.

Per-user index defaults can also live in `config.json`:

```json
{
  "identity": {
    "name": "Motoko",
    "realm": "admin",
    "description": "NixOS and repository review assistant for Javier's admin account."
  },
  "permissions": {
    "mode": "repo-review"
  },
  "index": {
    "max_derived_bytes": "2GiB",
    "max_files": 20000,
    "max_file_bytes": "8MiB"
  },
  "ui": {
    "assistant_color": "purple"
  }
}
```

Environment overrides are available for one-off sessions:

```bash
MOTOKO_PERMISSIONS=chat-only motoko
MOTOKO_MAX_DERIVED_INDEX_BYTES=250GiB motoko index ~/Documents
MOTOKO_INDEX_MAX_FILES=50000 motoko index ~/Documents
MOTOKO_INDEX_MAX_FILE_BYTES=20MiB motoko index ~/Documents
```

To set defaults manually for `personal` or `mares`, log into that account and
run `motoko permissions set MODE`, then edit `~/.config/motoko/config.json` if
that account needs different index limits, identity text, or assistant label
color. Valid `ui.assistant_color` values are `red`, `green`, `yellow`, `blue`,
`purple`, `pink`, `turquoise`, `magenta`, `cyan`, and `white`. State and config
remain under that account's own home directory.

Suggested realm identities:

```json
{
  "identity": {
    "name": "Motoko",
    "realm": "mares",
    "description": "Mares Engineering work assistant for Texere, RaceFocus, Motoko, and source-repo analysis. Keep work context separate from Javier's personal memories and from admin-only host-apply authority."
  },
  "permissions": {
    "mode": "repo-review"
  },
  "ui": {
    "assistant_color": "pink"
  }
}
```

```json
{
  "identity": {
    "name": "Motoko",
    "realm": "admin",
    "description": "Admin-side NixOS and repository review assistant for Javier. Help inspect diffs, explain system policy, and prepare safe changes, but do not imply sudo, switching, pushing, or live mutation authority."
  },
  "permissions": {
    "mode": "repo-review"
  },
  "ui": {
    "assistant_color": "turquoise"
  }
}
```

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

When Motoko starts in an allowlisted directory without an attached matching
index, she treats that directory tree as a **corpus**: a distinct body of source
material plus Motoko-owned derived artifacts such as indexes, summaries, chunks,
topic dossiers, memory dossiers, freshness metadata, and study state. If a
matching corpus index already exists for the current directory root, Motoko
attaches it automatically and freshness checks decide whether later background
refresh is useful. A fresh automatic attachment stays quiet at startup and is
visible through `/status` or `/sources`; stale or otherwise actionable index
state is still shown. If no matching index exists, the TUI asks whether to
learn the directory tree. Saying `yes` starts a heavy local-model indexing pass over
all readable text files under that root and stores a separate corpus index for
that directory. Saying `no` records a short decline cooldown so she does not ask
again immediately. Binary files and common cache/vendor directories are skipped
because they are not useful model context; source documents themselves remain
read-only.

This first corpus pass is real HRAG preprocessing, not a cheap filename scan:
Motoko stores source chunks, asks the local model for chunk summaries, file
summaries, and a corpus summary, and records fingerprints for freshness checks.
Index plans and first-run learning prompts include estimated chunks and HRAG
model calls so long jobs are easier to anticipate. Multi-round file and corpus
summaries can still make early estimates rough, so Motoko updates the model-call
plan as larger reductions are discovered and bases ETA on completed model-call
timing rather than only on raw file count. While the TUI is learning a corpus,
the top status reports file/chunk/model-call progress, elapsed time, current
model-call time, and ETA; `/indexes` and `/status` also show active durable
index jobs from Motoko state. The same progress display is used later if an
attached stale index needs a heavy background refresh.

Long corpus passes checkpoint after each completed file. If Motoko is paused,
times out, crashes, or the machine loses power, completed file work remains in
private partial-index state and `/indexes` shows a `partial` row with a resume
command. On restart in the same directory, Motoko offers to resume the partial
corpus index before starting a fresh one. Resume rescans the current directory
tree: already indexed files are reused if their content is still fresh, newly
discovered readable files are added, and changed already-indexed files stop the
resume so the user can choose a clean rebuild.

`/pause` and `motoko pause` are cooperative. They ask active work to stop at the
next durable checkpoint: corpus indexing saves a partial index, chat answering
saves the streamed partial answer, and background memory/study work records a
paused state at its next phase boundary. A local model request that is already
in flight may need to return or time out before Motoko reaches that checkpoint.

`/indexes` reports a corpus health percentage computed from current readable
files under the indexed root, newly discovered files, missing old files, and
stale source fingerprints. This is the cheap CPU-side signal Motoko uses before
deciding whether heavier model reprocessing is useful.

For Org-mode files, Motoko also extracts deterministic structured signals:
headings, TODO states, priorities, deadlines, and schedules. These signals are
stored alongside HRAG summaries and boost retrieval for task-planning questions
such as "what are the highest priority tasks for tomorrow?" They are derived
metadata under Motoko state; source Org files remain untouched. For task and
priority questions, Motoko also gives the model a ranked task-candidate list
using TODO state, priority cookies, and Org dates before asking it to answer.
Use `/tasks [QUERY]` to inspect that ranked task-candidate list directly.

Motoko also builds a **corpus profile** for each completed index. The profile is
a deterministic derived artifact that maps file roles, task/date signals, tags,
and high-value planning cues. It is injected into retrieval context and can be
inspected with `/corpus-profile [INDEX_ID]` or `motoko corpus-profile INDEX_ID`.
Older completed indexes that predate the current artifact schemas can be
upgraded with `motoko index-upgrade INDEX_ID` or `motoko index-upgrade --all`.
`motoko index-enrich` remains as a compatibility alias. These upgrades are
CPU-only: they read existing stored chunks, update index metadata, and do not
rerun model summaries. The light background study loop also upgrades a small
number of old completed indexes automatically when idle; it refuses to touch an
index that still has an active progress job.

When an index is source-fresh and schema-current but still fails quality checks,
use `motoko index-repair INDEX_ID` or `/index-repair [INDEX_ID]`. Repair is
different from an upgrade: it targets bad model-derived artifacts, such as empty
chunk summaries, then refreshes only the affected file summary and corpus
summary. The idle background loop can run a bounded repair pass automatically
with `MOTOKO_BACKGROUND_INDEX_REPAIR=1` and
`MOTOKO_BACKGROUND_INDEX_REPAIR_LIMIT=N`. Stale source content still needs a
source refresh or reindex; repair is for quality convergence on a current
index.

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
There is no fixed separator between the chat body and the composer. The TUI
does not print routine startup tips into the conversation body; `/help`,
`/status`, and `/sources` are the inspectable places for that state.
Use `/stop` to stop the current streamed answer.
If the raw terminal UI is not available or you want the older behavior, use
`motoko chat --line` or set `MOTOKO_TUI=0`.

The TUI uses a compact `>` input prompt. Chat body roles use compact glyph
markers: assistant and system rows render as `›` in their role color, and the
active answer status row renders as `● Preparing (...)` or `● Answering (...)`
with the elapsed phase time dimmed. After an answer finishes, the TUI adds a
dim `Worked for ...` separator line across the chat width. Motoko's assistant
marker uses per-user `ui.assistant_color` from `~/.config/motoko/config.json`
with `purple` as the default. If `MOTOKO_ALIAS_COLOR` is set to a valid Motoko
color, it takes precedence; if it is invalid, Motoko falls back to `purple`.
Report-like output such as `/sources`, `/status`, `/model-routes`,
`/identity`, `/permissions`, and `/retrieval-debug` highlights labels and
warnings only at render time. Saved conversation and artifact text stays plain.
Prose in the chat body and prompt wraps on word boundaries when possible;
code/preformatted blocks keep character wrapping so copied snippets remain
literal.
Supporting UI such as titles and command text uses turquoise where terminal
color support is available. The slash-command dropdown scrolls with the active
selection so entries past the first visible page remain visible.
The TUI does not render a spinner or duplicate chat activity in the top status
line; the in-chat active answer row carries `Preparing` and `Answering` state.
The top status line starts with the conversation title rather than the
assistant name. It includes the model badge, for example
`qwen3.6-27b-mtp:8083`, and reports active memory and background-study phases
such as
`mem: proposing(model)`, `bg-light: catalog(cpu)`, or
`bg-heavy: summarizing chunk file 6/54 chunk 10/100 9% eta 3h12m`.

Emacs-style editing keys in the TUI:

```text
Ctrl+A  beginning of line
Ctrl+E  end of line
Ctrl+B  backward char
Ctrl+F  forward char
Alt+B   backward word
Alt+F   forward word
Alt+Backspace  delete previous word
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
motoko delete CONVERSATION_ID --yes
motoko show
motoko show CONVERSATION_ID
motoko status
motoko model-routes
motoko models
motoko models qwen36-chat
motoko model-stop qwen36-chat
motoko model-eval
motoko index-enrich INDEX_ID
motoko index-enrich --all
motoko index-upgrade INDEX_ID
motoko index-upgrade --all
motoko index-repair INDEX_ID
motoko index-repair --all
motoko index-storage
motoko index-cleanup
motoko index-cleanup --yes
motoko corpus-profile INDEX_ID
motoko tasks "priority tasks tomorrow"
motoko permissions
```

When an ID is omitted in an interactive terminal, Motoko opens a numbered
picker. This avoids typing long conversation IDs for normal use.
`motoko list` displays compact `created`, `updated`, `branch`, and
`conversation` columns. Full timestamps remain stored in the conversation JSON.
`/rename TEXT` and `/title TEXT` both set the current conversation title.
`/delete` asks for confirmation before deleting the current conversation; it
also removes Motoko-owned derived artifacts that explicitly reference that
conversation, such as memories, feedback rows, memory dossiers, owned topic
dossiers, profile/context cache state, and resumable maintenance state.
Document indexes are corpus artifacts rather than chat artifacts, so deleting a
conversation does not delete indexed source-derived data unless that artifact
declares the deleted conversation as its owner.

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
/pause
/new [TITLE]
/rename TEXT
/delete
/resume [CONVERSATION_ID]
/read PATH
/index-plan PATH
/index PATH
/index-resume INDEX_ID
/resume-work [INDEX_ID]
/attach-index [INDEX_ID]
/corpus-profile [INDEX_ID]
/index-repair [INDEX_ID]
/topic [INDEX_ID] QUERY
/deepen [INDEX_ID] QUERY
/attach-topic [TOPIC_ID]
/dossier QUERY
/attach-dossier [DOSSIER_ID]
/indexes
/tasks [QUERY]
/topics
/topic-show [TOPIC_ID]
/dossiers
/dossier-show [DOSSIER_ID]
/study QUERY [--focus recent]
/compact
/sources
/feedback up|down|ok [TEXT]
/up [TEXT]
/down [TEXT]
/status
/model-routes
/models [ROUTE]
/model-status [ROUTE]
/model-stop ROUTE
/retrieval-eval
/retrieval-debug QUERY
/retrieval-preview QUERY
/index-storage
/vector-plan [INDEX_ID]
/vector-build [INDEX_ID]
/vector-refresh [INDEX_ID]
/vector-query [--rerank] QUERY
/vector-eval
/identity
/permissions
/permissions set MODE
/repo status [PATH]
/repo diff [PATH]
/repo log [PATH]
/repo review [PATH]
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

Repo commands are available in `repo-review` mode:

```bash
motoko repo status ~/repos/nixos-configs
motoko repo diff ~/repos/nixos-configs
motoko repo log ~/repos/nixos-configs
motoko repo review ~/repos/nixos-configs
```

Inside a chat:

```text
/repo status ~/repos/nixos-configs
/repo diff ~/repos/nixos-configs
/repo log ~/repos/nixos-configs
/repo review ~/repos/nixos-configs
```

The report is attached to the conversation as bounded context so Motoko can
discuss it in the next answer. These commands use fixed Git invocations:
`status --short --branch`, diff summaries, recent log, and
`scripts/nixos-review-gate` when that executable exists. They do not run an
arbitrary shell, do not call sudo, do not push, do not switch NixOS, and do not
print full patch contents by default. The repo path must still be under an
allowlisted directory.

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
If no answer has been generated yet, `/sources` falls back to the currently
attached indexes, topic dossiers, and dossier evidence so study results are
visible immediately after `/study`.

Motoko also runs quiet after-answer maintenance. Periodically, after enough
messages have accumulated, she proposes high-confidence durable memories to
herself and saves them automatically with provenance `auto-model-proposed`.
For model compatibility, memory proposal sends recent turns as a quoted
conversation transcript inside a user request instead of replaying raw
assistant turns as chat history; this avoids assistant-prefill behavior on
thinking-mode local worker routes while preserving source text for extraction.
Duplicate detection reinforces existing similar memories by updating their
`seen_count`, tags, and last-seen metadata instead of creating many copies of
the same fact. Stored memories remain inspectable with `motoko memory review`,
searchable with `motoko memory search`, and removable with `motoko forget`.
The top bar reports the active maintenance phase, such as `memory: checking`,
`memory: proposing`, `memory: saving`, or `memory: compacting`. Interrupted
maintenance writes a small resumable state file and is retried conservatively
when the same conversation is opened again. The TUI also shows how long the
current maintenance phase has been active. Automatic memory proposal work runs
in a bounded helper process so a stuck local model request is terminated and
reported as a maintenance failure instead of leaving `memory: proposing`
visible forever.
When Javier explicitly asks Motoko to remember something with natural wording
such as `remember that ...`, Motoko saves that memory deterministically before
answering instead of waiting for the model proposal pass.
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
attached files, file summaries, document chunks, index freshness state, and
context planning lanes used for the last answer. It also prints a short `why:`
line for each source. It ends with an answer-grounding audit that reports
whether the answer had excerpt-level evidence, only summary/memory context,
stale context, or no usable grounding for a source-shaped question. This is
meant to make answers inspectable: Motoko should be able to say which stored
context influenced a response instead of sounding like she has unbounded hidden
knowledge.

`/status` prints the current model endpoint, state paths, memory/index/topic
counts, and the amount of context attached to the active conversation.

While the TUI is open, Motoko also runs a low-intensity background study loop
only when she is idle. The loop refreshes a private context catalog, checks
index freshness, upgrades a bounded number of old CPU-only index artifacts, and
records study suggestions. By default it avoids heavy model calls so it does not
compete with chat; set `MOTOKO_BACKGROUND_PROFILE=1` to allow idle
profile-dossier refreshes. It does not silently crawl new directories or create
large document indexes; document access still starts from explicit allowlists
and `/index`. Use `/study QUERY` for a deliberate bounded study pass that either
reuses an existing dossier, builds a topic dossier from an attached or relevant
index, or builds a memory/conversation dossier. `/study QUERY --focus recent`
is a real parsed focus hint for recent/today/yesterday retrieval; it is not
sent through as literal query text.
When a query names a file such as `logbook.org`, retrieval gives that path a
strong deterministic boost before model synthesis so explicit file requests do
not lose to broad task-signal matches elsewhere in the corpus.
For document corpora already attached to the active conversation, Motoko may
also run a heavier background index refresh when an attached index becomes stale
or when enough new files appear under the indexed root. This work uses the local
model endpoint for summaries, is shown in the top status bar as
`bg-heavy: indexing(model)`, and queues new prompts until the refresh finishes
so the chat does not compete with the indexing pass. It is deliberately bounded:
it only considers already attached indexes, waits for normal idle time, refreshes
at most one index per pass, and uses a cooldown plus new-file thresholds so tiny
repo edits do not immediately trigger a large rebuild.
Background study writes `study-state.json` and appends events to
`study-jobs.jsonl` under Motoko state. If Motoko exits during the cheap
catalog/planning pass, the next pass records the interrupted job and recomputes
from current state; no personal documents are lost or rewritten.

Motoko separates background work into three lanes:

- `cpu`: deterministic parsing, fingerprints, corpus health, artifact upgrades,
  lexical retrieval, and Org task/date extraction;
- `small-model`: repetitive summarization/classification work such as chunk
  summaries, file summaries, short labels, and file-purpose maps;
- `large-model`: chat answers, corpus synthesis, dossiers, memory/profile
  reflection, audits, and hard ambiguous reasoning.

The lanes are implemented through named model routes. On HB3, NixOS declares
the approved local model catalog in `~/.config/motoko/local-models.json`; routes
normally point at `unix:///run/motoko-llm/<realm>/<route>.sock` and are served
by per-realm worker users such as `mares-llm` or `personal-llm`. Motoko talks to
those OpenAI-compatible Unix sockets, but does not call `systemctl` or run
llama.cpp as the current user. Use `motoko-model list/info/verify/start/stop/status`
for model-service operations.

All routes still fall back to the normal chat endpoint until config,
environment variables, or the NixOS local-model catalog override them, so the
feature is safe before smaller worker models are deployed. Inspect routes with
`/model-routes` or:

```bash
motoko model-routes
```

Inspect live local model service state with `/models` or:

```bash
motoko models
motoko models qwen36-chat
```

This uses the approved `motoko-model status ROUTE` helper and is intentionally
content-free: it reports service lifecycle fields such as socket/proxy/backend
state when NixOS exposes them, not prompts, responses, filenames, retrieved
context, summaries, or memory content. `backend=active` is service/process
state; it is not proof that the full model weights are currently resident in
VRAM.

Release a worker explicitly with `/model-stop ROUTE` or:

```bash
motoko model-stop qwen36-chat
```

This calls `motoko-model stop ROUTE`; Motoko still does not call `systemctl`
directly and does not stop models automatically when the TUI exits.

Route overrides can live in `~/.config/motoko/config.json`:

```json
{
  "model_routes": {
    "index_chunk": {
      "endpoint": "http://127.0.0.1:8091/v1/chat/completions",
      "model": "small-summary-worker"
    },
    "index_file": {
      "endpoint": "http://127.0.0.1:8091/v1/chat/completions",
      "model": "small-summary-worker"
    },
    "index_label": {
      "endpoint": "http://127.0.0.1:8092/v1/chat/completions",
      "model": "small-label-worker"
    },
    "index_corpus": {
      "endpoint": "http://127.0.0.1:8083/v1/chat/completions",
      "model": "qwen3.6-27b-mtp-ud-q5-k-xl"
    }
  }
}
```

Equivalent one-off environment overrides use
`MOTOKO_ROUTE_<ROUTE>_ENDPOINT` and `MOTOKO_ROUTE_<ROUTE>_MODEL`, for example
`MOTOKO_ROUTE_INDEX_CHUNK_MODEL=small-summary-worker`.

First requests to a Unix socket may socket-activate a model worker and block
while weights load into VRAM. Motoko uses generous Unix-socket request timeouts
and treats `503 Loading model` responses as a normal loading state to retry
instead of an immediate failure. She reports the active route/lane in visible
background status. If a declared model file is missing, run
`motoko-model verify <route>`; Motoko also includes catalog download URL/hash
details in socket connection diagnostics when they are available.

If NixOS declares a route cache policy in
`~/.config/motoko/local-models.json`, `/model-routes` and
`motoko model-routes` display those content-free capabilities, including prompt
cache enablement, reuse threshold, cache RAM, slot prompt similarity, metrics
availability, and metrics endpoint. Motoko reads those fields as service-owned
capabilities. She keeps prompts stable and explicit, but does not call `/slots`,
does not persist KV cache files, and does not fake prompt/KV caching in user
state.

When the NixOS catalog is keyed by worker service name instead of Motoko route
name, Motoko resolves routes through each catalog entry's `tasks` list. For
example, `index_chunk` can map to `qwen35-2b-worker`, `index_file` to
`qwen3-4b-instruct-worker`, `index_label` to `ministral-3b-worker`, and topic
or corpus synthesis to `qwen35-9b-worker`.

For hierarchical summaries, Motoko can fan out independent reduction batches
across smaller worker routes before the final synthesis route runs. For
example, a topic dossier may reduce retrieved chunks through `index_file` and
`index_chunk` workers in parallel, then ask the `topic` route for the final
dossier. The NixOS catalog's `maxParallel` value is respected per route, and
`MOTOKO_SUMMARY_MAX_PARALLEL` can cap total reduction workers for one process.
Set `MOTOKO_SUMMARY_PARALLEL=0` to disable this fanout for a session.

Before trusting newly installed worker models, run:

```bash
motoko retrieval-eval
motoko model-eval
motoko model-eval --route index_chunk --route index_file
motoko model-eval --write
```

`retrieval-eval` is deterministic and does not call a model. It uses synthetic
corpus fixtures to check whether the lexical retriever selects the expected
files, chunks, dates, TODOs, paths, and rare terms before generation begins.
Reports written with `--write` are stored under
`~/.local/state/motoko/retrieval-evals/`.

`retrieval-debug QUERY` is also deterministic. It explains which indexes were
chosen, the top file and chunk rows, lexical score, path boost, task-signal
boost, matched terms, summary-versus-content matches, freshness, and short
diagnosis notes. Use it after a weak answer to distinguish recall failure,
ranking failure, stale data, missing chunk text, weak summaries, or final
prompt/synthesis failure. In chat, `/retrieval-debug QUERY` uses attached
indexes first; from the shell, `motoko retrieval-debug QUERY` uses the best
matching current indexes unless `--index INDEX_ID` is supplied.

`retrieval-preview QUERY` is the no-model companion to `retrieval-debug`. It
shows the source audit, source list, context plan, and the attached
document/dossier context excerpt that Motoko would send for a question, without
asking any LLM to answer. Use it when deciding whether the right evidence was
retrieved at all. In chat, `/retrieval-preview QUERY` uses the current
conversation attachments; from the shell, `motoko retrieval-preview QUERY`
auto-selects the best matching current index unless `--conversation` or
`--index INDEX_ID` is supplied.

`model-eval` uses synthetic, source-grounded fixtures for chunk summaries, file
summaries, lightweight labels/classification, and corpus synthesis. It asks
each configured route for strict JSON and scores whether the artifact preserves
names, dates, TODO states, priorities, obligations, project/file references,
source paths, avoids invented facts, and avoids `<think>` spillover. Reports
written with `--write` are stored under `~/.local/state/motoko/model-evals/`.
These fixtures are not a replacement for real use, but they are the gate before
moving bulk indexing from the main chat model to smaller workers.

Motoko also caches deterministic model outputs for repeatable summary routes
under `~/.local/state/motoko/model-cache/`. This is private Motoko state and can
be disabled for one process with `MOTOKO_MODEL_CACHE=0`. It is not server-side
KV/prompt caching; true prompt-prefix/KV reuse depends on the deployed local
model service and should be evaluated in `nixos-configs`.

Heavy index refresh can be tuned for one-off sessions:

```bash
MOTOKO_BACKGROUND_HEAVY_INDEX=0 motoko
MOTOKO_BACKGROUND_HEAVY_INDEX_COOLDOWN=3600 motoko
MOTOKO_BACKGROUND_HEAVY_INDEX_MIN_NEW_FILES=5 motoko
MOTOKO_BACKGROUND_HEAVY_INDEX_MIN_NEW_BYTES=131072 motoko
MOTOKO_CWD_LEARN=0 motoko
MOTOKO_CWD_LEARN_DECLINE_COOLDOWN=86400 motoko
```

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
under Motoko state unless the current user's `~/.config/motoko/config.json`
sets a smaller `index.max_derived_bytes`. Override this for a reviewed one-off
index with:

```bash
motoko index ~/Documents --max-derived-bytes 250GiB
```

or set:

```bash
MOTOKO_MAX_DERIVED_INDEX_BYTES=250GiB motoko index ~/Documents
```

Per-user `index.max_files` and `index.max_file_bytes` limits are fail-closed:
Motoko stops before writing a new index if the source tree exceeds those
configured bounds. That is useful for source-code/admin accounts where an
unexpected generated file or huge tree should be reviewed before ingestion.
Personal document accounts can leave those limits unset or set them higher.

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
/index-resume INDEX_ID
/resume-work [INDEX_ID]
/attach-index
/attach-index INDEX_ID
```

Indexes live under:

```text
~/.local/state/motoko/indexes/
```

Each index stores:

- a corpus-level summary;
- a corpus profile that maps file roles, task/date signals, tags, and planning
  cues for retrieval;
- one summary per file;
- one summary per chunk;
- raw chunk text for later retrieval, stored as Motoko-owned derived files;
- optional structured signals for formats Motoko understands, currently
  Org-mode headings, TODO state, priorities, deadlines, and schedules;
- source fingerprints: file size, mtime, and SHA-256 at index time.

Model-derived summaries also store artifact provenance: artifact kind/schema,
Motoko builder version, route, endpoint, model, prompt version, source
fingerprint, creation time, and quality status. Use:

```bash
motoko index-quality INDEX_ID
```

or `/index-quality [INDEX_ID]` to inspect whether a completed index has current
summary provenance, current structured signals, a current corpus profile, and
preserved Org task/date evidence. Older indexes can gain missing provenance and
new deterministic artifacts with `motoko index-upgrade INDEX_ID` without
discarding old summaries.
If the source is fresh but the quality gate still fails, use
`motoko index-repair INDEX_ID` to regenerate only failed model-derived
artifacts, such as empty chunk summaries, and then refresh the affected
higher-level summaries.

On each question, Motoko scores the indexed summaries and chunks with a small
local lexical retriever, then injects the corpus summary, relevant file
summaries, and top matching excerpts into the prompt. The retrieval window
uses the current prompt plus recent conversation context and adapts to the
question: broad evidence/detail/deep-analysis prompts receive a wider slice of
attached indexes than ordinary conversational prompts. This avoids sending every
file on every turn while still letting the model answer from relevant source
text.
For document, file, task, priority, date, or "according to this corpus"
questions, the system prompt tells Motoko to answer from retrieved excerpts,
structured task signals, or attached source material, and to say when context is
thin instead of inventing details from summaries.

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
chunk text again. During a long build, Motoko also writes
`INDEX_ID.partial.json` checkpoints beside the chunk directory. These are
private derived state, not source-document edits. If a model request fails or
work is paused, the partial checkpoint remains resumable with:

```bash
motoko indexes
motoko pause
motoko index-resume INDEX_ID
motoko resume-work INDEX_ID
```

Use `motoko index-storage` or `/index-storage` to audit the derived index store
before cleanup or vector-store work. The report shows complete and partial
indexes, duplicate reference chunks, unique stored chunk bodies, logical corpus
bytes versus physical stored bytes, missing duplicate targets, orphan chunk
files, and cleanup opportunities. `motoko index-cleanup` is a dry-run; add
`--yes` to apply it. `/index-cleanup` is also a dry-run, and
`/index-cleanup yes` applies one bounded cleanup pass. Cleanup is
conservative: it deletes only stale superseded index snapshots after a newer
fresh index exists for the same corpus family, and it first materializes any
duplicate chunk references in that newer index so the replacement remains
self-contained. The light background loop can run the same bounded cleanup
automatically after a successful refresh.

Use `motoko evidence-build [INDEX_ID]` or `/evidence-build [INDEX_ID]` to build
a deterministic hierarchical evidence store for an index. Evidence stores live
under `~/.local/state/motoko/evidence-stores/` and contain source-linked rows
for Org dated days, Org tasks, Org/Markdown headings, paragraphs, and bounded
text windows. Each row keeps the source index id, file path, chunk id, content
hash, source span offsets, row kind, title/date/TODO/priority metadata when
present, and compact source text. `motoko evidence-query QUERY` or
`/evidence-query QUERY` inspects those rows without calling a model.
`motoko evidence-refresh [INDEX_ID]` builds missing or stale evidence stores;
the background study loop also performs one bounded CPU-lane evidence refresh
when `MOTOKO_BACKGROUND_EVIDENCE_REFRESH` is enabled. Evidence stores are
rebuilt from the saved source index when the evidence schema/input policy or
source fingerprint changes.

Use `motoko vector-plan` or `/vector-plan [INDEX_ID]` before trusting embedding
or reranker storage. The report is also read-only: it sizes planned
realm-local vector stores for raw chunk text, hierarchical evidence rows, chunk
summaries, file summaries, labels, memories, conversations, and dossiers;
lists provenance and invalidation fields; checks retrieval-eval and
storage-audit gates; and reports whether the local model catalog advertises
embedding or reranker routes by `kind`, `tasks`, and `endpoint_paths`. This is
a contract and readiness report, not an automatic trust decision.

Use `motoko vector-build [INDEX_ID]` to build a realm-local vector store for an
index, and `motoko vector-query QUERY` to inspect its ranked rows. This writes
only Motoko-owned derived state under `~/.local/state/motoko/vector-stores/`.
The default `--method auto` uses a NixOS-declared `/v1/embeddings` route when
one is present in `~/.config/motoko/local-models.json`; otherwise it falls back
to the deterministic `lexical-hash-v1` store. Use
`motoko vector-build --method lexical-hash-v1 [INDEX_ID]` when you want the
no-model control path, or `motoko vector-build --method embedding-v1 [INDEX_ID]`
when you want to require the approved embedding route. Use
`motoko vector-eval` for the lexical synthetic fixtures, and
`motoko vector-eval --method embedding-v1` to measure the configured embedding
route without writing a store. Use `motoko vector-query --rerank QUERY` to
inspect how the configured `/v1/rerank` route reorders the top vector
candidates.

Use `motoko vector-refresh [INDEX_ID]` to build a missing or stale embedding
store for an index. Without an index argument it considers the latest index for
each corpus family and builds at most one store by default. The background
study loop also performs one bounded embedding refresh pass when
`MOTOKO_BACKGROUND_VECTOR_REFRESH` is enabled. It skips stale source indexes
and indexes above `MOTOKO_BACKGROUND_VECTOR_REFRESH_MAX_CHUNKS` unless you run
the explicit command with a larger `--max-chunks` value. Embedding refresh
uses the route's NixOS-declared `maxParallel` for concurrent batch requests by
default, capped by the number of batches. Set `MOTOKO_EMBEDDING_PARALLEL=N` to
override this for diagnosis, and `MOTOKO_EMBEDDING_BATCH_SIZE=N` to adjust
batch size. When batch size is not explicitly set, bg-heavy vector refresh
chooses a smaller adaptive batch size so small corpora still create enough
requests to fill the route's parallel slots; tune
`MOTOKO_EMBEDDING_BATCHES_PER_WORKER=N` when diagnosing throughput. The
route/configured parallelism is capped at 32. If the embedding
route fails under the requested concurrency, Motoko checkpoints completed rows
and retries the remaining work at half the parallelism until it reaches one
request at a time or the work succeeds. Progress messages include a row-based
ETA once the current run has enough completed rows to estimate throughput.
Embedding inputs are bounded before they are sent to the route. Long source
chunks are split into several source-linked subchunk rows rather than being
compressed into one lossy truncated embedding; each row keeps the original
file path, chunk id, content hash, input schema, input hash, and part count so
retrieval can map the vector hit back to the real source chunk. Tune
`MOTOKO_EMBEDDING_INPUT_CHARS=N` only for diagnosis or after route limits are
verified, and `MOTOKO_EMBEDDING_MAX_PARTS_PER_CHUNK=N` when testing the
recall/storage tradeoff for unusually long chunks.
Embedding and reranker routes fail fast when their declared local model files
are missing, and the diagnostic includes the `motoko-model verify ROUTE`
command plus the catalog download URL/hash when available.
Completed embedding batches are checkpointed under
`~/.local/state/motoko/vector-progress/`, and a later `vector-refresh` for the
same source fingerprint plus embedding route/model/dimensions resumes from
those saved rows. Embedding stores are considered stale and rebuilt from the
saved source index when the vector schema, embedding input schema/split
policy, source fingerprint, embedding route, model, or dimensions change.
Dense vector coordinates are not migrated across incompatible embedding
models; source re-vectorization is the correct upgrade path. A fresh embedding
store participates in true hybrid retrieval: lexical/path candidates,
deterministic Org/task candidates, deterministic evidence rows, and fresh
embedding candidates are unioned and deduplicated before final context
selection. When a catalog-discovered
`/v1/rerank` route is available, Motoko reranks that combined candidate set;
if reranking is missing or fails, she falls back to the non-reranked hybrid
set. Lexical scores, path boosts, Org/task signals, vector rows, rerank state,
evidence rows, and source excerpts remain visible in `/retrieval-debug` and
`/sources`. Set `MOTOKO_EVIDENCE_RETRIEVAL=0` to disable evidence-store
retrieval during diagnosis. Set `MOTOKO_VECTOR_RETRIEVAL=0` to disable
semantic retrieval during diagnosis. Set `MOTOKO_VECTOR_RERANK=0` to disable
reranking during diagnosis.

Retrieval excerpts are query-aware after a chunk is selected. If the query
mentions exact dates, or asks for the last/latest/recent dated entries, Motoko
looks inside Org chunks for dated headings and extracts the matching sections
as mandatory evidence before generic heading/window competition. Those sections
are then used for `/retrieval-preview`, chat context, topic evidence, or rerank
documents. This is specifically important for chronological files such as
`logbook.org`, where the relevant `** do` and `** log` subsections may live
near the end of a large chunk rather than near the beginning.

This is implemented as evidence-span selection, not as a `logbook.org`
special case. Motoko builds candidate spans from dated Org sections, Org and
Markdown headings, query-term windows, and overlapping text windows. She scores
those spans deterministically first. For a bounded number of large top-ranked
chunks, long candidate spans are split into bounded worker-sized subspans with
parent provenance, scored through the configured embedding and reranker routes,
then reassembled into the best source evidence before passing text to the
final chat model. The chosen span method, labels, and subspan offsets are shown
in `/sources`. Set
`MOTOKO_SPAN_EMBEDDING=0`, `MOTOKO_SPAN_RERANK=0`, or
`MOTOKO_SPAN_MODEL_MAX_CHUNKS=N` when diagnosing latency or routing behavior.
Set `MOTOKO_SPAN_MODEL_INPUT_CHARS=N` or
`MOTOKO_SPAN_MODEL_MAX_SUBSPANS_PER_PARENT=N` only when diagnosing worker
context limits.

Use `/feedback up|down|ok [TEXT]` after an answer to record whether it helped
and what was wrong or right. The shorthand commands `/up [TEXT]` and
`/down [TEXT]` do the same thing. Feedback is written to the current user's
Motoko state as `response-feedback.jsonl`; it is not appended to the
conversation transcript. This is intended as a future training/evaluation
signal for retrieval, rerank, prompt, and answer-quality improvements, not as
an immediate unreviewed self-tuning mechanism.
Use `motoko feedback-eval` or `/feedback-eval` to turn those private rows into
inspectable eval fixtures. Downvotes become `needs-review` fixtures with focus
tags such as recall, ranking, evidence, staleness, prompt use, or synthesis
derived from the note and prompt. The report remains under the current user's
Motoko state and is not shared across realms.

Large directories and large files can take a long time because every indexed
chunk is summarized through the local model. Use `--glob` to narrow very broad
indexes when needed. If only derived metadata such as structured signals or a
corpus profile needs to be added to an old completed index, prefer
`motoko index-upgrade INDEX_ID`; it is a metadata upgrade and should be much
faster than rebuilding the HRAG summaries. Use `motoko corpus-profile INDEX_ID`
or `/corpus-profile [INDEX_ID]` to inspect the profile that retrieval will show
the model.

Route smaller worker models only after the evaluation harness passes. The
quality bar is preservation of names, dates, priorities, TODO states,
obligations, project/file references, source paths, and task-priority answers
on synthetic fixtures. Use `motoko model-eval` for live configured routes; the
regression/evaluation tests cover the scoring logic without using private
personal documents.

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

On HB3, the default model endpoint comes from
`~/.config/motoko/local-models.json` when NixOS provides that catalog. It is
normally a per-realm Unix socket such as:

```text
unix:///run/motoko-llm/mares/chat.sock
```

Older or ad-hoc environments can still use the loopback MTP Qwen3.6 service:

```text
http://127.0.0.1:8083/v1/chat/completions
```

Line mode can still use the legacy thinking spinner when `MOTOKO_SPINNER` is
set. The default is off. ASCII and braille remain opt-in:

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
