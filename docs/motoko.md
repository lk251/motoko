# Motoko Personal Assistant

Date: 2026-08-22

Motoko is a terminal personal assistant and bounded local project/repository
helper. It remains Python-standard-library-only and talks to operator-approved
local llama.cpp routes. The root `motoko` executable owns CLI
and composition while focused runtime, retrieval, memory, artifact, skill,
action, goal-loop, model, and terminal services live under `motoko_core/`.

Motoko is not a provider gateway or a general-purpose autonomous agent runtime.
She is primarily a personal chat, memory, and
retrieval assistant. Repository use starts from fixed read-only inspection and
may cross into project mutation only through typed, validator-owned,
user-confirmed action records and explicit goal-loop/worktree workflows.

For documents and allowlisted repositories, Motoko uses dependency-free hybrid
retrieval: lexical/path matching, deterministic Org structure, hierarchical
evidence, optional local embeddings and reranking, source-span selection, and
deliberate context packing. `/sources`, `/retrieval-preview`, and
`/retrieval-debug` expose what was selected and why.

## Current Implementation Status

As of 2026-08-22:

- `/model` selects a conversation-scoped named chat model from the NixOS
  catalog; `/reasoning` selects model-native effort. Context size belongs to
  the selected model, and Motoko compacts/retrieves before overflow rather than
  silently changing model or quant.
- The TUI uses a dedicated input/render owner and input-first event scheduling.
  Background catalog, audit, repair, indexing, and vector work is lane-aware,
  bounded, visible, checkpointed where needed, and expected to yield to active
  conversation work.
- Retrieval, evidence, vector queries, preview, debug, and chat context are
  converging on shared typed service results with source provenance and
  content-free diagnostics.
- Realm-local skills are review-first. Code-owned handlers may affect retrieval;
  approved stdlib tools run only through fingerprinted contracts and typed
  actions. Arbitrary executables, shell, network, service control, and
  privileged effects are not enabled.
- Explicit and model-planned goal loops are durable and budgeted. Read-only
  loops stop with proposals; mutating loops stop for confirmation and apply
  only through the normal validators and ledgers. Managed Git worktrees keep
  larger project changes isolated.
- The main remaining work is hardening and craftsmanship: shrink the root
  facade behind tested service boundaries, finish artifact lifecycle and
  cooperative cancellation coverage, improve code retrieval and dossier
  quality, and exercise reviewed action/goal-loop paths through real use and
  evals.

## Security Boundary

Each installation uses the current account's home directory, so conversations,
memories, indexes, configuration, and permissions stay separate unless the
operator deliberately imports or copies state. Motoko should run without sudo,
provider credentials, or direct service-control authority.

Motoko does not use:

- provider API keys;
- a provider gateway;
- LangChain or LangGraph;
- pip packages;
- npm packages;
- a database server;
- service-control authority.

Motoko uses:

- `/nix/store/.../python3` from the NixOS system closure;
- the Python standard library only;
- approved per-realm local model routes from
  `~/.config/motoko/local-models.json`;
- files deliberately allowlisted by the current user.

On managed deployments, the operating-system configuration owns the llama.cpp
worker catalog, model paths, service flags, endpoints, and route policy. Motoko can request approved
route endpoints, read content-free route status, stop a declared route through
`motoko-model stop ROUTE`, and read content-free metrics through
`motoko-model metrics ROUTE`; Motoko cannot call `systemctl`, load arbitrary
model paths, pass arbitrary llama.cpp flags, or mutate NixOS policy.

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
    "description": "Local repository review assistant for this account."
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
`motoko about` is the compact introduction screen: Motoko's name, brief
privacy/security-conscious description, development values, version, the Motoko
ASCII logo in the assistant color, identity/realm, active chat model and
endpoint, background lanes, state
paths, and permissions. The logo is rendered first and left-justified, with
the Motoko/version/values text below it so narrow terminals do not interleave
the text with the ASCII art. In the TUI, `/about` and other report-style commands
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
    "description": "Local repository review assistant for this account."
  },
  "permissions": {
    "mode": "repo-review"
  },
  "index": {
    "max_derived_bytes": "2GiB",
    "max_files": 20000,
    "max_file_bytes": "8MiB"
  },
  "conversation_recall": {
    "current_messages": 24,
    "current_max_chars": 0,
    "recent_conversations": 2,
    "relevant_conversations": 4,
    "conversation_limit": 6,
    "conversation_messages": 6,
    "matched_snippets": 2,
    "snippet_chars": 900,
    "max_chars": 12000
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

To set defaults manually, log into the target account and
run `motoko permissions set MODE`, then edit `~/.config/motoko/config.json` if
that account needs different index limits, conversation-recall budgets,
identity text, or assistant label color. Valid `ui.assistant_color` values are
`red`, `green`, `yellow`, `blue`,
`purple`, `pink`, `turquoise`, `magenta`, `cyan`, and `white`. State and config
remain under that account's own home directory.

`conversation_recall` controls how much same-realm conversation history Motoko
packs automatically. `current_messages` may be an integer or `"all"`; pair
large values with `current_max_chars` so a long chat cannot crowd out source
evidence. Saved conversations are selected by a recency lane plus a
query-relevance lane, then packed as title, summary, matched snippets, recent
turns, and provenance. If `conversation_limit` is omitted, Motoko uses at least
`recent_conversations + relevant_conversations`.

Suggested realm identities:

```json
{
  "identity": {
    "name": "Motoko",
    "realm": "work",
    "description": "Repository review assistant. Keep work context separate from private memories and host-apply authority."
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
    "description": "System-configuration and repository review assistant. Help inspect diffs and prepare safe changes without implying sudo, deployment, push, or live mutation authority."
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
the bottom status reports file/chunk/model-call progress, elapsed time, and
ETA; `/indexes` and `/status` also show active durable index jobs from Motoko
state. The same progress display is used later if an attached stale index
needs a heavy background refresh.

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

When stdin and stdout are terminals, `motoko` starts in a small stdlib-only TUI.
The conversation is an append-only transcript, so normal terminal scrollback in
TTY, Sway, Foot, or tmux shows chat history instead of old full-screen redraw
frames. The composer and status area redraw at the bottom, `/` opens command
suggestions, arrow keys move through suggestions, Enter accepts a selection,
and typed text remains available while Motoko streams an answer. Stable
completed answer lines are appended through the normal transcript/scrollback
path; the bottom frame keeps only live phase, input, suggestions, and status
controls. There is no fixed separator between the chat body and the composer.
The TUI prints a short, non-persistent startup tip block; `/tips`, `/help`,
`/status`, and `/sources` are the inspectable places for details.
Use `/stop` to stop the current answer and discard any prompts queued behind
it. Use `/clear-queue` to discard queued prompts without stopping the active
answer.
Prompts queued behind active answers, visible `bg-heavy` work, report commands,
or foreground commands such as `/bg-now` and `/index-repair` are saved on the
conversation record before they are processed. If Motoko exits or the terminal
closes first, the queued prompts are restored into input history and continue
when the conversation is resumed. Empty saved chats are omitted from
conversation lists unless they still contain queued prompts. Report commands
keep the chat/composer visible while running and open a temporary page only
when the report text is ready.
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
Report-like output such as `/sources`, `/status`, `/model`, `/model-routes`,
`/identity`, `/permissions`, and `/retrieval-debug` highlights labels and
warnings only at render time. Saved conversation and artifact text stays plain.
Prose in the chat body and prompt wraps on word boundaries when possible;
code/preformatted blocks keep character wrapping so copied snippets remain
literal.
Supporting UI such as titles and command text uses turquoise where terminal
color support is available. The slash-command dropdown scrolls with the active
selection so entries past the first visible page remain visible.
The TUI does not render a spinner or duplicate chat activity in the bottom
status line; the live answer row carries `Preparing` and `Answering` state.
The bottom status line starts with the conversation title rather than the
assistant name. It includes the selected catalog model and effort, for example
`chat-default:xhigh`, and reports active memory and background-study phases
such as `mem: proposing(worker)`, `bg-light: catalog(cpu)`, or
`bg-heavy: summarizing chunk file 6/54 chunk 10/100 9% eta 3h12m`.

## Daily Usage Tips

The normal daily loop is:

1. Start Motoko from the directory whose corpus matters, such as
   `~/Documents/notes`.
2. Ask questions naturally. If an index exists for the current directory,
   Motoko auto-attaches the best current-directory index; if she offers to learn
   the directory tree, answer `yes` only when that corpus should become part of
   her local derived knowledge. When that learning job completes in the TUI,
   the new index is attached and persisted immediately.
3. After important answers, run `/sources` to inspect the files, spans, and
   context-selection reasons used for the answer.
4. When an answer seems wrong, run `/retrieval-debug QUERY` to decide whether
   the failure is recall/indexing, ranking, stale data, chunking, summaries,
   prompt use, or final synthesis. Use `/retrieval-preview QUERY` when you want
   to see the packed context without calling a model.
5. Use `/study QUERY` for deliberate deeper analysis and `/tasks QUERY` for
   Org task planning.
6. Record concise feedback with `feedback up NOTE`,
   `/feedback up|down|ok NOTE`, or the shorthand `/up NOTE` and `/down NOTE`.
   Good notes name the missing file, date, project, stale artifact, wrong
   assumption, or behavior that worked.

Feedback stays in the current user's Motoko state, not in the conversation
transcript. It becomes useful evaluation material through `/feedback-eval` or
`motoko feedback-eval`; it does not silently retune retrieval or prompts.

Evals are health checks, not daily chat chores. Run `motoko retrieval-eval`,
`motoko vector-eval`, `motoko feedback-eval`, `motoko action-eval`, or
`motoko model-eval` after Motoko updates, model-route changes, suspicious
failures, or before trusting a new retrieval/action path. For routine use,
`/sources`, specific feedback, and targeted `/retrieval-debug` runs are usually
the higher-signal habit.

Motoko's self-improvement path is review-first: private feedback rows,
inspectable eval fixtures, skill suggestions, and approved changes. The
Hermes-style direction is to let Motoko crystallize repeated procedures into
durable skills and later tightly constrained support files/tools, while
preserving Motoko's realm-local, dependency-light, approval-first security
shape.

## Supervisory Workflow And Context Management

Motoko can act as a supervisory planner for a repository without becoming the
host's administrative control plane. Start her in the repository whose current
files should define the task. For example:

```bash
cd ~/repos/system-config
motoko index --plan --name system-config .
motoko index --name system-config .
MOTOKO_REASONING_PRESET=xhigh motoko
```

Inspect the index plan before writing derived state. Do not index `/`, `/etc`,
or `/nix/store`: a focused source repository is more current, more relevant,
and less likely to expose unrelated secrets or generated files. When discussing
a system problem, distinguish among declared repository configuration, the
built or selected closure, and live runtime state.

The intended supervisory pattern is:

1. Keep ordinary work on the catalog's highest-fidelity default chat route,
   using compaction and fresh retrieval rather than accumulating raw history.
2. Select an approved named long-context model explicitly when the task
   genuinely requires a larger assembled evidence window.
3. Delegate bounded chunk, file, label, memory, embedding, reranking, and corpus
   work to the specialist routes declared in the local catalog.
4. Bring the resulting artifacts back to the strongest suitable chat route for
   synthesis and review.

The concrete model files, quants, context sizes, and service policy belong to
NixOS. Treat `~/.config/motoko/local-models.json` and `/model-routes` as the
source of truth instead of embedding a particular quant filename in Motoko's
personality, memories, or source code.

Motoko currently combines explicit named chat-model selection with fixed
specialist task routes. She does not yet ask a large model to semantically
assign every subtask to another model. A future semantic supervisor should
return a structured plan containing only approved catalog route IDs. Motoko's
code must retain final authority over route validity, scheduling, privacy, and
service access.

A useful standing instruction is:

```text
Act as the supervisory planner for this project. Classify each part of the task,
recommend the least expensive approved route competent to handle it, reserve the
highest-fidelity route for difficult reasoning and final review, and use the
long-context route only when the assembled evidence requires it. Distinguish
source-of-truth files from summaries and distinguish declared, built, and live
system state.
```

Use `/model` to inspect the named chat models and `/model NAME` to select one
for the current conversation. `/model auto` follows the managed catalog route
marked `selection.default == true`; names, aliases, model files, quants,
context sizes, and cache placement are deployment-owned catalog data. Before a
request crosses 75 percent of the selected model's declared `context_tokens`,
Motoko compacts older turns and rebuilds query-focused retrieval context. If
the prepared prompt still does not fit, Motoko asks you to choose a
larger-context model rather than silently changing model, quant, or reasoning
effort.
`/context` is accepted only as a deprecated compatibility alias for old saved
commands and conversations.

For content-free route comparisons:

```bash
motoko model-routes
motoko context-bench --target-tokens 32000
motoko context-bench --target-tokens 64000
motoko context-bench --target-tokens 96000
```

Large raw context is not the same as durable project continuity. Approximate a
larger agent working context through fresh source retrieval, inspectable
dossiers, compact conversation state, and authoritative repository artifacts.
Do not fill a route to its declared limit: Motoko's catalog-derived prompt
budget leaves one quarter of the window for reasoning and output. Compact or
retrieve more selectively when `/last-call` reports high context pressure.

Current compaction summarizes older turns, keeps recent messages verbatim, and
saves both in the conversation. A summary can lose exact implementation detail,
so use these practices:

1. Keep one conversation per coherent project or objective and resume it.
2. Keep current files, Git commits, tests, and tracked decisions authoritative.
3. Refresh an index after material repository changes.
4. Use `/study` for broad analysis instead of manually pasting many files.
5. Use `/sources` after consequential answers to inspect grounding.
6. Use `/retrieval-debug QUERY` when Motoko misses relevant evidence.
7. Use `/compact` at a clean phase boundary after important state is recorded.
8. Use `/remember` for durable preferences and commitments, not transient code
   details that should be retrieved from the repository.

For NixOS work, `/repo review .` provides bounded read-only Git and review-gate
context. Motoko's `repo-review` permission does not grant shell, sudo, rebuild,
switch, commit, or push authority. Those operations remain separate reviewed
human or coding-agent actions.

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
motoko last-call
motoko context-bench
motoko model-routes
motoko models
motoko models ROUTE
motoko model-stop ROUTE
motoko model-metrics ROUTE
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

`motoko last-call` and `/last-call` show the most recent content-free model
call record: route, catalog route, route profile, declared KV location,
reasoning preset and actual effort, selected context tier, estimated prompt and
completion tokens, context pressure, source count, elapsed time, and estimated
generation speed. The record deliberately omits prompt text, response text,
reasoning text, filenames, excerpts, summaries, and other corpus-derived
content.

`motoko context-bench` is dry-run by default. It builds synthetic content-free
prompt sizes and shows which approved chat route the context governor would
choose. Use `--run` only when you explicitly want to send real synthetic model
requests.

`motoko model-routes`, `/model-routes`, `motoko models`, and `/models` consume
NixOS-declared route metadata such as `request_policy`, `scheduling`,
`idle_seconds`, `safety_policy`, `cache`, and `maxParallel`. Request policy can
declare sampling presets, structured-output fields, reasoning/thinking
presets, and prompt-cache measurement support. Motoko applies these policy
fields to approved local model requests and records only content-free metadata
in `/last-call`, such as route, model id, estimated tokens, selected sampling
preset, selected reasoning preset and effort, whether structured output
was requested, and timing counters.
For background and maintenance worker calls, Motoko also uses scheduling
metadata to avoid GPU residency fights: idle same-realm large chat routes may
be released through `motoko-model stop ROUTE` after their recent-chat grace
window, while workers defer when a large chat route reports active requests or
was just used. Before large foreground chat starts, Motoko also releases idle
worker routes and idle peer chat profiles so stale residency does not block the
selected chat model.
The grace window is not an eviction timer. Motoko does not proactively stop a
large chat route just because the grace window expired; it releases a route only
while preparing another conflicting model route, or when the user explicitly
requests a model stop. NixOS may still enforce its own service idle-unload
policy independently.
Deferred durable jobs are left retryable: memory proposals remain queued,
partial indexes remain resumable, and vector refreshes keep progress for a
later pass.

For prompt-cache measurement, use:

```bash
motoko model-metrics ROUTE
```

This delegates to `motoko-model metrics ROUTE` and prints bounded,
content-free service counters. Persistent slot/KV cache is available only when
the NixOS route catalog explicitly declares it for a route. Inspect it with:

```bash
motoko slot-cache [ROUTE]
motoko slot-cache gc ROUTE
motoko slot-cache clear [ROUTE] --yes
motoko slot-cache erase ROUTE
```

Motoko stores only a realm-local, content-free manifest under
`~/.local/state/motoko/slot-cache/`. The llama.cpp worker owns the actual KV
files behind its declared `--slot-save-path`. That path must be declared by the
NixOS per-realm route catalog, should be private to the route's worker user and
client realm, and should be treated as prompt-derived private state. Motoko
calls the declared `/slots/{id}?action=restore|save|erase` endpoint only when
`persistentSlotCache`, `slotsEndpoint`, and `slotSavePath` are enabled and the
route safety policy does not disable those surfaces. Cache restore/save failure
is treated as a cache miss. Motoko must remain correct with no persistent KV
cache and must not write prompts, responses, filenames, summaries, memories,
retrieved context, corpora, or reasoning text to admin-owned logs.

Slot/KV disk budget policy belongs in the NixOS route catalog. Motoko enforces
the declared route policy and supports neutral profiles: `off`, `tiny`,
`small`, `standard`, and `large`, plus explicit `slotCacheMaxBytes` or
`slotCacheMaxMiB` values. Profiles are record-count policies when the route
declares or Motoko observes the slot file size: `tiny` keeps about 1 file,
`small` 2, `standard` 4, and `large` 8. NixOS may declare exact slot-file
sizes with `slotCacheFileBytes` / `slotCacheFileMiB`; otherwise Motoko uses
observed saved-file sizes and falls back to neutral estimates until a size is
known. The application must not hard-code per-account budgets; NixOS decides
which profile or byte cap each realm receives.

If `slotSavePath` is service-owned, for example a `0700` systemd
`StateDirectory` under `/var/lib` owned by the per-realm llama.cpp worker user,
Motoko must not weaken that boundary or assume direct filesystem access. In
that mode Motoko can track the content-free manifest and use `/slots` for
restore/save/erase, but disk pruning is service-owned too. Motoko uses
`motoko-model slot-cache-status ROUTE`, `motoko-model slot-cache-gc ROUTE`, and
`motoko-model slot-cache-clear ROUTE` when those commands are available.
Motoko reports `needs-service-gc` when the manifest says the cap is exceeded
but the human realm process cannot delete the service-owned files.

Per-realm path policy also belongs in config, not source conditionals. Motoko
rejects action/tool paths that cross into another Unix home by default.
NixOS-managed `~/.config/motoko/config.json` may set
`security.allow_cross_home_paths` for a realm if that realm is explicitly
allowed to operate on another home path.

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

Manage procedural skills:

```bash
motoko skills
motoko skill show NAME
motoko skill learn NAME --description "short description" --body "procedure to follow"
motoko skill learn NAME --description "short description" --file SKILL.md --replace
motoko skill support NAME [references/file.md]
motoko skill patch NAME --old "old text" --new "new text"
motoko skill write-file NAME references/file.md --content "supporting detail"
motoko skill remove-file NAME references/file.md --yes
motoko skill tools NAME
motoko skill scan [NAME]
motoko skill approve-tool NAME TOOL --yes
motoko skill curator
motoko skill curator --suggest
motoko skill pin NAME
motoko skill unpin NAME
motoko skill archive NAME --yes
motoko skill restore NAME
motoko skill delete NAME --yes
motoko skill plan "query"
motoko tools
motoko action plan "query"
motoko action preview ACTION.json
motoko action run ACTION.json [--yes]
motoko action apply ACTION.json --yes
motoko action ledger [--limit N]
motoko action result RUN_ID [--private]
motoko action proposals RUN_ID
motoko action apply-proposal RUN_ID INDEX --yes
motoko action-eval [--write] [--json]
motoko worktree list
motoko worktree create BRANCH --yes
motoko worktree merge BRANCH --yes
motoko worktree remove PATH --yes
motoko goal plan "objective" [--model-readonly|--model-confirmed] [--save]
motoko goal list
motoko goal preview GOAL.json
motoko goal run GOAL.json --yes
motoko goal runs
motoko goal resume RUN_ID --yes
motoko goal proposals RUN_ID [--private]
motoko goal apply RUN_ID --yes
motoko skill review [CONVERSATION_ID]
motoko skill upgrade
motoko skill suggestions
motoko skill suggestion SUGGESTION_ID
motoko skill accept SUGGESTION_ID
motoko skill reject SUGGESTION_ID
motoko self-eval
```

Skills are durable procedural packages for repeatable "how to approach this
kind of task" situations. Repo-shipped built-in skills cover stable Motoko
procedures, while learned user skills are stored under the current user's
Motoko state as `SKILL.md` files. Motoko ranks skills against the current
prompt, includes only relevant ones in chat context, and lists selected skills
in `/sources`.

Skill lifecycle metadata is stored separately under the current user's Motoko
state, not inside `SKILL.md`. Motoko records when a skill is selected into chat
context, can pin a skill against archival suggestions, and can archive or
restore learned skills without deleting their files. Archived skills stay
inspectable but are not selected into prompt context or action planning. The
curator command is deliberately report-first:

```bash
motoko skill curator
motoko skill curator --suggest
motoko skill pin NAME
motoko skill unpin NAME
motoko skill archive NAME --yes
motoko skill restore NAME
```

This adapts the useful Hermes-style skill-library maintenance idea while
keeping Motoko's version reversible, realm-local, and non-autonomous. The
curator report can also point out large skills that may deserve support files,
possible consolidation groups, stale unused learned skills that may deserve
archive review, and recent feedback rows that may indicate a skill should be
patched. `motoko skill curator --suggest` turns the concrete curator candidates
into ordinary pending `skill_manage` suggestions. They are still review-first:
inspect them with `motoko skill suggestion ID`, then accept or reject them
explicitly. Curator reports hide raw feedback notes by default. Suggestion
candidates can add content-safe support-file plans for oversized skills,
consolidation review notes for overlapping learned skills, and
`archive-review.md` notes for stale unused skills; accepting those suggestions
still goes through the normal explicit skill-management path. Motoko does not
archive anything until the user explicitly runs `motoko skill archive NAME
--yes`.

Current `motoko-skill-v3` skills can declare a kind, trigger hints, handler,
allowed effects, support files, and inert script-tool metadata. Prompt-only
learned skills use `handler: prompt_only`. Built-in skills may declare
deterministic handlers that Motoko's planner can activate before a subsystem
runs. This borrows the useful progressive disclosure idea from Hermes Agent
while keeping Motoko realm-local, dependency-light, and inspectable.

The first retrieval handlers are built-in, deterministic, and selected from
natural-language queries rather than user-facing mini-languages:

- `org-temporal-retrieval` handles "last/latest N dated entries present in
  this named Org file" before context packing.
- `org-structural-query` handles Org tags, inherited tags, TODO states,
  priorities, deadlines, scheduled items, and dated headings. For example,
  "show me everything tagged RaceFocus" should activate the handler, select
  source-linked Org evidence rows, and pass those rows into the normal final
  answer with `/sources` provenance. Slash commands are inspection and
  debugging surfaces; ordinary chat should be enough for this class of query.
- `motoko-codebase-maintainer` handles Motoko self-improvement questions about
  her own source code. It activates deterministic source-code lookup over the
  Motoko checkout, mapping commands, symbols, tests, imports, and large files
  before the final model is asked to reason about refactors or implementation
  work.
- `motoko-retrieval-maintainer` is a prompt-only umbrella skill for diagnosing
  retrieval, source-grounding, span-selection, stale-data, rerank, and final
  synthesis failures before changing prompts or ranking.
- `motoko-refactor-craft` is a prompt-only umbrella skill for careful
  service-boundary refactors: characterize behavior, extract narrow modules,
  preserve migrations and pause/resume behavior, validate, document, and
  commit coherent slices.
- `motoko-agentic-boundary-review` is a prompt-only umbrella skill for
  reviewing skills, script tools, typed actions, project writes, goal loops,
  approvals, ledgers, and effect boundaries before authority is widened.

Handlers and effects are allowlisted in Motoko's code. Unknown or model-suggested
handler names degrade to `prompt_only`, and unsupported effects are discarded.
That keeps skill suggestions safe to inspect and accept without creating a
backdoor for broad shell execution.

Motoko also borrows Hermes Agent's useful `skill_manage` shape, but narrows it
to a review-first internal action model. Pending suggestions may propose
`create`, `patch`, `write_file`, or `remove_file` actions. Accepting a
suggestion applies the action through Motoko's own validators, not through a
general tool loop. Support files are confined to `references/`, `templates/`,
and `scripts/` under the selected skill package. Scripts are inert unless they
have adjacent tool metadata, current fingerprint approval, and a typed action
record accepted by Motoko validators. `motoko skill support NAME` lists support
files, and `motoko skill support NAME references/file.md` shows one file.
When a relevant skill is selected for a prompt, Motoko may include a bounded
matching support-file excerpt as additional procedural context and record it in
`/sources` as `skill-support`.

Script files under `scripts/` remain inert unless they have adjacent
`*.tool.json` metadata and a matching user approval record. `motoko skill tools
NAME` validates and displays those declarations, fingerprints, effects, and
approval status. `motoko skill approve-tool NAME TOOL --yes` approves only the
current script and metadata fingerprints. `motoko action preview ACTION.json`
validates a typed `motoko-action-v1` record and writes a private user-state
ledger row without execution. `motoko action run ACTION.json [--yes]` runs
approved typed actions. Approved `skill_tool_run` records go through the
narrow stdlib Python runner:
structured JSON on stdin, scrubbed environment, fixed skill-package working
directory, timeout and output byte limits, JSON object output validation, and
private inputs/results stored under the current user's Motoko state. `--yes`
grants only one run-local confirmation when the already approved tool contract
requires confirmation. Executable script tools are treated as having the
`external_process` effect even when old metadata omits it, so approvals show
the actual authority being granted; script tools cannot declare
`prompt_only`.

`motoko skill scan [NAME]` is the static review surface for learned skills and
support scripts. It is conservative and report-first: it flags prompt-injection
phrases, destructive shell patterns, subprocess/network/secret/path signals,
and risky Python imports or calls. Scanner findings do not approve or execute
anything; they exist so external, community, or self-created skills can be
reviewed before trust expands.

Motoko codebase intelligence is available without a model call:

```bash
motoko code-map
motoko code-query "skill planner command implementation"
motoko self-eval
```

`motoko code-map` builds a deterministic map of the current Motoko checkout:
Python files, functions, classes, argparse commands, handlers, imports, tests,
largest files, parser warnings, command-to-handler-to-test traces, resolved
call edges, root-facade hotspots, and `motoko_core` service-boundary summaries.
`motoko code-query QUERY` ranks commands, command traces, symbols, call edges,
service boundaries, tests, and files against a query. Ordinary chat questions
about Motoko's own codebase can activate the same built-in handler and include
a bounded code-query report in prompt context. Longer self-improvement work
should follow `docs/motoko-self-improvement-playbook.md`, which captures the
current craft checklist for repo understanding, skill/tool hygiene, retrieval
diagnosis, refactor boundaries, validation, and deployment soak checks.

`motoko self-eval` is a deterministic no-model readiness check for Motoko
self-improvement. It verifies that the code map parses, code-query finds
commands/symbols/tests, command traces link handlers to tests, code-map
relationships expose call edges, service boundaries, and root hotspots, the
built-in self-code skill activates for Motoko refactor questions,
self-improvement umbrella skills are present and selected for representative
queries, built-in skills scan cleanly, the scanner catches a synthetic risky
script, and the self-improvement docs are present. Use it after changes to the
skill/codebase self-improvement path or before trusting Motoko to help plan her
own refactor.

Project-file mutation uses a separate code-owned action kind,
`project_file_write`, not arbitrary script side effects. `motoko action apply
ACTION.json --yes` can create or overwrite a file only under an allowed root,
only outside `.motokoignore` exclusions and VCS/cache directories, only with
one exact session confirmation, and only through Motoko's atomic write path.
Overwrite actions require the current `expected_sha256` of the target. Action
ledgers store hashes, byte counts, effects, and statuses, not file content or
raw target paths.

Script-assisted project mutation is intentionally proposal-first. A tool may
declare the `propose_project_changes` effect and return a bounded
`proposed_actions` list containing typed `project_file_write` records. Motoko
validates those proposals immediately and stores the validation summary in the
private tool result, but the script still does not write project files.
`motoko action proposals RUN_ID` shows the content-safe proposal summary, and
`motoko action apply-proposal RUN_ID INDEX --yes` applies one proposal through
the same allowlist, `.motokoignore`, expected-hash, atomic-write, confirmation,
and ledger path as any other `project_file_write`. Tool output that contains
`proposed_actions` without declaring `propose_project_changes` fails closed.

`motoko tools` lists all declared skill tools across learned skills, including
approval state and effects. `motoko action plan "query"` is the first
deterministic planner bridge: it matches the query against known skills/tools,
infers only obvious arguments such as named file/path mentions, and prints
typed action JSON candidates without running anything or calling a model.
`motoko action ledger` shows content-safe action/tool rows. `motoko action
result RUN_ID` shows metadata for a private tool run result; add `--private`
only in the owning Unix account when you intentionally want stdout/stderr and
parsed JSON output printed.

`motoko action-eval` runs deterministic safety fixtures for the agentic action
surface without calling a model and without using real user corpora. It checks
that confirmed code-owned project writes work, unconfirmed writes block,
`.motokoignore` denials hold, script-owned project writes remain blocked,
script-produced project-change proposals can only be applied by Motoko,
explicit goal action lists run only with confirmation, and goal budgets stop
over-broad action lists. Add `--write` to save the JSON report under the
current user's Motoko state.

Git worktree operations are also typed actions, not shell access.
`git_worktree_create`, `git_commit`, `git_worktree_merge`, and
`git_worktree_remove` require explicit confirmation and use Motoko-owned
validators. `motoko worktree create BRANCH --yes` creates an isolated
branch/worktree under the current user's Motoko state and registers it as a
managed project root. Project writes may then target that worktree through the
normal `project_file_write` boundary. `motoko worktree merge BRANCH --yes`
fast-forwards the managed branch into the target branch only after clean-tree
checks; `motoko worktree remove PATH --yes` removes a managed worktree.

Goal loops are still deliberately narrow. `motoko goal plan "objective"` builds
a `motoko-goal-loop-v1` record with objective, scope, allowed tools/effects,
budgets, stop conditions, and phases. `--save` stores the draft under the
current user's Motoko state; `motoko goal list` and `motoko goal preview
GOAL.json` inspect saved or external loop records.

There are three enabled runners. The explicit runner uses an action list
already present in the loop record; each action still passes through the same
action validator, effect checks, budgets, confirmations, and ledger path. The
read-only model-planned runner is opt-in with `motoko goal plan
--model-readonly "objective" --save`. It may plan, retrieve context, inspect,
audit, and produce reviewable typed action proposals, but it refuses
`write_allowed_project`, `network`, `service_control`, and `privileged`
effects, and it does not apply mutations.

The user-confirmed model-planned runner is opt-in with `motoko goal plan
--model-confirmed "objective" --save` (alias: `--model-write`). It retrieves
context and asks the audit route for strict JSON proposals, then stops with a
`goal-run-v1` checkpoint in `awaiting_confirmation`. It may propose
`project_file_write` and the managed Git worktree action kinds above, but it
does not mutate until the user reviews the proposal summary and runs
`motoko goal apply RUN_ID --yes`. The apply phase executes proposals in order,
checkpointing after each action, and still uses the same confirmations,
allowlists, `.motokoignore`, clean-tree checks, and ledgers as ordinary typed
actions.

Use `motoko goal proposals RUN_ID` to inspect the content-safe proposal
summary; add `--private` only in the owning Unix account when intentionally
printing the proposed action JSON.

Confirmed runs create `goal-run-v1` checkpoints under the current user's Motoko
state. `motoko goal runs` lists those checkpoints, and `motoko goal resume
RUN_ID --yes` resumes from the next incomplete action or reports an already
completed run. Explicit action-list runs honor `motoko pause` and `/pause`
between actions, so a paused goal run keeps completed action results and
resumes at the next pending action or proposal apply step. Fully autonomous
model-planned mutation remains disabled: the enabled mutating path is
model-planned, user-reviewed, and user-confirmed.
`network` loops require future approval; `service_control` and `privileged`
are rejected.

The built-in `org-temporal-retrieval` skill handles queries such as "last three
days present in sample-journal.org". It declares the
`builtin:org_temporal_latest_entries` handler. For matching queries, Motoko
builds a pre-retrieval `retrieval_plan_v1`, activates that skill, scopes
retrieval to the named Org source, parses dated headings, and selects the
newest dates actually present. The deterministic retrieval layer still owns
source scoping, Org date parsing, and evidence extraction; the skill records
why and when that handler should run.

Motoko does not execute arbitrary skill scripts, shell snippets, network tools,
service-control actions, privileged actions, or script-owned project-file
writes. Skill scripts remain limited to approved stdlib Python tools with
low-risk effects such as allowlisted reads and Motoko-state writes. Project
mutation is available only through the typed, code-owned `project_file_write`
action described above. The accepted design for that runner lives in
`docs/agentic-capability-design.md`.

Skill schema changes include a deterministic upgrade path. Run
`motoko skill upgrade` to rewrite learned `SKILL.md` files to the current
schema; after-answer maintenance also runs this cheap upgrade pass so old
realm-local skills converge without one-off manual repair.

Use `motoko skill plan "query"` or `/skill plan QUERY` to inspect which
prompt skills and pre-retrieval handlers would be selected for a query without
calling a model. This is the main debugging surface for the planner/handler
boundary.

After-answer maintenance may also suggest skill actions when a conversation
contains repeatable procedural knowledge: user corrections, workflow changes,
non-trivial debugging paths, reusable techniques, or evidence that a loaded
skill is stale. These suggestions are review-first. Motoko stores pending
realm-local suggestions and prints a short note; she does not silently create,
patch, or execute learned skills. The local review heuristic is whether a
proposed action would save tokens, reduce errors, improve reliability, or
encode project-specific craft; that wording is Motoko policy, not a claimed
Hermes Agent quotation. You can also run a manual review on the current or
selected conversation when you believe a reusable procedure just emerged.
The background reviewer normally runs on a bounded interval, but it can run
earlier when recent turns explicitly mention reusable procedures or when the
last answer used a skill that may need to be patched. In those cases the
review prompt receives the recently loaded skill list and prefers patching that
skill before creating a new one.
Review suggestions with:

```bash
motoko skill review [CONVERSATION_ID]
motoko skill suggestions
motoko skill suggestion SUGGESTION_ID
motoko skill accept SUGGESTION_ID
motoko skill reject SUGGESTION_ID
```

Useful in-chat commands:

```text
/help
/
/tips
/stop
/clear-queue
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
/bg-now
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
/diagnose
/status
/model [NAME|auto]
/reasoning [off|low|medium|xhigh|auto]
/model-routes
/models [ROUTE]
/model-status [ROUTE]
/model-stop ROUTE
/model-metrics ROUTE
/retrieval-eval
/retrieval-debug QUERY
/retrieval-preview QUERY
/index-storage
/vector-plan [INDEX_ID]
/vector-build [INDEX_ID]
/vector-refresh [INDEX_ID]
/vector-doctor [INDEX_ID]
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
/skills
/skill show NAME
/skill learn NAME --description DESC --body TEXT
/skill support NAME [references/file.md]
/skill patch NAME --old OLD --new NEW [--file SKILL.md|references/file.md]
/skill write-file NAME references/file.md --content TEXT
/skill remove-file NAME references/file.md --yes
/skill delete NAME
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
recall uses two lanes: a configurable recency lane for the newest useful
conversations and a configurable relevance lane scored against the current
prompt and thread. Each selected saved conversation is packed with title,
summary, strongest lexical snippets for the current query, recent turns, and
provenance. Durable memory ranking remains separate and uses the current
prompt, the conversation title, recent user turns, the compacted summary,
memory importance, pinned status, repeated sightings, thread relevance, and
recency. Use `/sources` after an answer to see which memories and recent
conversations were selected and why.
If no answer has been generated yet, `/sources` falls back to the currently
attached indexes, topic dossiers, and dossier evidence so study results are
visible immediately after `/study`.

Motoko can already select from attached indexes, evidence stores, vectors,
memories, recent conversations, and deterministic skill handlers before an
answer. The bounded sufficiency planner can now run one deterministic extra
retrieval pass when a grounded question has no excerpt-level evidence in the
initial context window and a project-scoped stored context item is available.
This pass does not attach or mutate the conversation and does not make a
generative synthesis call; it may still use configured embedding/rerank
retrieval workers when the normal hybrid retrieval path uses them. It appears
in `/sources` as `retrieval-sufficiency`. Evidence strength is quality-aware:
a fallback chunk with no lexical, structured, evidence, vector, rerank, or
span signal no longer counts as strong grounding merely because its source
kind is `chunk`. Stale or unavailable source evidence also triggers one
bounded recovery pass when a fresh project-scoped candidate exists. Future work
may make this planner richer, but it should remain code-owned, source-visible,
and limited rather than a hidden autonomous loop.

Motoko also runs quiet after-answer maintenance. Periodically, after enough
messages have accumulated, she proposes high-confidence durable memories to
herself and saves them automatically with provenance `auto-model-proposed`.
When a conversation reaches a memory-proposal interval, Motoko first writes a
realm-local durable queue row under her own state and only clears that row after
the proposal pass finishes. If Motoko exits, loses power, or the local worker is
not ready, the queued proposal is retried by later maintenance instead of being
forgotten.
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
visible forever. For per-realm Unix-socket model routes, the helper wall
timeout is aligned with socket-activation timeouts so model loading is not
mistaken for a failed memory proposal.
When the user explicitly asks Motoko to remember something with natural wording
such as `remember that ...`, Motoko saves that memory deterministically before
answering instead of waiting for the model proposal pass.
After the first few messages, maintenance may also ask the local model for a
short conversation title. First-message titles are provisional unless the user
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
context planning lanes used for the last answer. When it falls back to attached
index context before an answer has sources, it also reports the current
evidence/vector artifact ids, row counts, and freshness for that index. It
prints a short `why:` line for each source. It ends with an answer-grounding
audit that reports
whether the answer had excerpt-level evidence, only summary/memory context,
stale context, or no usable grounding for a source-shaped question. This is
meant to make answers inspectable: Motoko should be able to say which stored
context influenced a response instead of sounding like she has unbounded hidden
knowledge.

`/status` prints the current model endpoint, state paths, memory/index/topic
counts, and the amount of context attached to the active conversation. Its
context-catalog line is generated from current user-owned state instead of
trusting an older persisted catalog file, so newly materialized indexes,
vectors, evidence stores, memories, and profile metadata can show up without a
restart.
`/diagnose` and `motoko diagnose --safe` are the privacy-preserving companion
for job trouble: they show content-free lane/job state, row/batch counters,
elapsed/ETA, stale/finalizing classifications, and route service state without
printing paths, filenames, prompts, excerpts, summaries, memories, or corpus
names.

While the TUI is open, Motoko also runs a low-intensity background study loop
only when she is idle. The loop refreshes a private context catalog, checks
index freshness, upgrades a bounded number of old CPU-only index artifacts, and
records study suggestions. The first keystroke cancels the current automatic
step so the composer remains responsive even if maintenance was already in
progress. Catalog metadata checks avoid content hashing, and source audits read
small artifact sidecars instead of loading large vector/evidence stores; legacy
large stores without sidecars are left for explicit refresh or rebuild. By
default the loop avoids heavy model calls so it does not compete with chat; set
`MOTOKO_BACKGROUND_PROFILE=1` to allow idle
profile-dossier refreshes. It does not silently crawl new directories or create
large document indexes; document access still starts from explicit allowlists
and `/index`. Use `/study QUERY` for a deliberate bounded study pass that either
reuses an existing dossier, builds a topic dossier from an attached or relevant
index, or builds a memory/conversation dossier. `/study QUERY --focus recent`
is a real parsed focus hint for recent/today/yesterday retrieval; it is not
sent through as literal query text.
When a query names a file such as `sample-journal.org`, retrieval gives that path a
strong deterministic boost before model synthesis so explicit file requests do
not lose to broad task-signal matches elsewhere in the corpus.
For document corpora already attached to the active conversation, Motoko may
also run a heavier background index refresh when an attached index becomes stale
or when enough new files appear under the indexed root. This work uses the local
model endpoint for summaries, is shown in the bottom status line as
`bg-heavy: indexing(model)`, and queues new prompts until the refresh finishes
so the chat does not compete with the indexing pass. It is deliberately bounded:
it only considers already attached indexes, waits for normal idle time, refreshes
at most one index per pass, and uses a cooldown plus new-file thresholds so tiny
repo edits do not immediately trigger a large rebuild.
Use `/bg-now` or `motoko bg-now` when you explicitly want Motoko to run this
same background catch-up path immediately. Manual bg-now runs refresh the
catalog, deterministic index upgrades, attached-index freshness checks, cleanup,
evidence stores, repairs, and vector stores through the existing bounded
background machinery. They bypass the ordinary heavy-index cooldown because the
user asked for work now, but they still respect allowlists, model-route
scheduling, durable checkpoints, pause requests, and configured per-pass limits.
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

The lanes are implemented through named model routes. A managed deployment
declares the approved local model catalog in
`~/.config/motoko/local-models.json`; routes may point at OpenAI-compatible
Unix sockets owned by isolated worker users. Motoko talks to those endpoints,
but does not call `systemctl` or run
llama.cpp as the current user. Use `motoko-model list/info/verify/start/stop/status`
for model-service operations.

Main chat reasoning is controlled per request independently of the selected
named model. For Qwen, Motoko sends:

```text
reasoning_format = deepseek
chat_template_kwargs.enable_thinking = true|false
reasoning_effort = low|medium|xhigh
```

Use `/reasoning off|low|medium|xhigh` inside Motoko to set the current
conversation. `/reasoning auto` returns to the selected model's
catalog-declared default. The catalog's request policy determines which native
request fields and effort values a model supports; old saved
`default|high|max` values remain accepted as compatibility aliases. For a
process-wide default, use
`MOTOKO_REASONING_PRESET=off|low|medium|xhigh`. Streaming reasoning switches the
active TUI answer row to `Thinking`, shows the latest reasoning text dimmed and
truncated for fit, and returns to `Answering` when normal answer tokens stream.
Reasoning text is not inserted into the conversation transcript, prompt
history, `/last-call`, logs, or shared state.

Routes require an endpoint declared by the managed local-model catalog,
environment variables, or user configuration; Motoko has no compiled-in host
or port fallback. Inspect routes with `/model-routes` or:

```bash
motoko model-routes
```

Inspect live local model service state with `/models` or:

```bash
motoko models
motoko models ROUTE
```

This uses the approved `motoko-model status ROUTE` helper and is intentionally
content-free: it reports service lifecycle fields such as socket/proxy/backend
state when NixOS exposes them, not prompts, responses, filenames, retrieved
context, summaries, or memory content. `backend=active` is service/process
state; it is not proof that the full model weights are currently resident in
VRAM.

Release a worker explicitly with `/model-stop ROUTE` or:

```bash
motoko model-stop ROUTE
```

This calls `motoko-model stop ROUTE`; Motoko still does not call `systemctl`
directly and does not stop models automatically when the TUI exits.

Route overrides can live in `~/.config/motoko/config.json`:

```json
{
  "model_routes": {
    "index_chunk": {
      "endpoint": "unix:///run/local-models/summary.sock",
      "model": "small-summary-worker"
    },
    "index_file": {
      "endpoint": "unix:///run/local-models/summary.sock",
      "model": "small-summary-worker"
    },
    "index_label": {
      "endpoint": "unix:///run/local-models/label.sock",
      "model": "small-label-worker"
    },
    "index_corpus": {
      "endpoint": "unix:///run/local-models/synthesis.sock",
      "model": "synthesis-worker"
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
capabilities. She keeps prompts stable and explicit, and she uses persistent
slot/KV cache only through the reviewed route capability gates described above.
She does not fake prompt/KV caching in user state: the user state contains only
the manifest, while llama.cpp saves and restores the actual slot cache file.
The manifest uses route/model/context/slot fingerprints so old cache records do
not carry across route or model changes. It also includes Motoko's chat slot
cache namespace, which must be bumped when the chat prompt, context packing, or
template assumptions change enough that old slot files should not be reused.
`/last-call` may show content-free slot-cache status such as
`restore=miss|restored|failed` and `save=saved|failed`; it must not contain
prompt or response text.

When the managed catalog is keyed by worker service name instead of Motoko
route name, Motoko resolves logical roles such as `index_chunk`, `index_file`,
`index_label`, and `index_corpus` through each catalog entry's `tasks` list.
Physical service names and their model assignments remain deployment-owned.

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
The source audit distinguishes quality-aware strong evidence from nominal
strong source kinds, so fallback chunks with no retrieval signal are visible
instead of being silently counted as grounded excerpts.

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

For a deliberate catch-up pass without waiting for the idle loop or the
heavy-index cooldown:

```bash
motoko bg-now
```

`/profile-refresh` or `motoko profile refresh` builds a compact profile dossier
from durable memories and recent conversation material. This is an explicit
hierarchical retrieval-augmented memory layer for the user's stable preferences,
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

To keep irrelevant or archival material out of a corpus while leaving it in the
source tree, put a `.motokoignore` file at the root being indexed. This is a
deterministic corpus-selection rule for automatic indexing and derived
evidence/vector work, not a security boundary: explicit allowlists still
control file access, and explicit reads remain separate user actions. Motoko
supports a small `.gitignore`-like subset: blank lines, `#` comments, file
globs such as `*.bak`, root-anchored paths such as `/legacy.org`, and directory
exclusions such as `archive/`. Negation patterns such as `!keep.org`
intentionally fail closed for now instead of pretending to work. `motoko index
--plan PATH` reports ignored paths and stores a source-selection fingerprint so
changing `.motokoignore` makes old indexes stale and eligible for normal
refresh/rebuild work.

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
files, cleanup opportunities, and source-lifecycle work with derived-vs-manual
review artifact counts. `motoko index-cleanup` is a dry-run; add `--yes` to
apply it. `/index-cleanup` is also a dry-run, and
`/index-cleanup yes` applies one bounded cleanup pass. Cleanup is
conservative: it deletes only stale superseded index snapshots after a newer
fresh index exists for the same corpus family, and it first materializes any
duplicate chunk references in that newer index so the replacement remains
self-contained. The light background loop can run the same bounded cleanup
automatically after a successful refresh.

Use `motoko source-lifecycle [INDEX_ID]` or `/source-lifecycle [ID]` when an
index reports changed, deleted, or newly ignored source files. This is the
source-aware cleanup report: it shows which source paths changed, which derived
artifacts reference the old index or source paths, whether a newer replacement
index is ready, and which artifacts need manual review. The only automatic
apply path is intentionally narrow: `motoko source-lifecycle INDEX_ID --apply
--yes` deletes a stale superseded index snapshot and its derived vector,
evidence, vector-progress, dossier, retrieval-debug, retrieval-eval,
feedback-eval, action-eval, and model-eval artifacts after a fresh replacement
index exists. The delete-derived versus manual-review family policy is declared
in the artifact lifecycle service; the root executable only resolves those
families to realm-local state paths and filesystem callbacks. Motoko does
not automatically delete durable conversations, memories, profile dossiers, raw
feedback, action ledgers, or goal-loop records just because they mention a
removed source; those remain review signals.

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
source fingerprint changes. Evidence refresh reports include content-free
mode/cause diagnostics such as `full missing`, `forced-rebuild forced`, or
`rebuild source-change` so the user can tell why deterministic evidence work is
running.

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
When a refresh resumes from a checkpoint, the visible elapsed time is measured
from the original vector-progress record rather than from the new Motoko
session, so interrupted work does not misleadingly appear to have started from
zero.
Before the first model batch starts, Motoko reports the safe refresh shape it
has already determined: `full`, `resumed`, `incremental`, `reuse-only`, or
`rebuild`, plus a content-free cause such as `missing`, `source-change`,
`schema`, `route`, `forced`, or `checkpoint`. For example, a one-file edit
should look like `incremental source-change reuse N new M ...`; an interrupted
refresh should look like `resumed checkpoint reuse N new M ...`; and a first
store should look like `full missing new N ...`. Vector status labels are
intentionally content-free. They show refresh mode/cause, batch, row,
parallelism, ETA, and finalizing/stalled state, but not corpus names or source
paths. If no vector progress update arrives for several minutes, the TUI marks
the work as possibly stalled instead of letting an old row count look active.
Use `motoko vector-doctor [INDEX_ID]` or `/vector-doctor [INDEX_ID]` when
vectorizing appears to underuse the GPU. The report is content-free: it shows
the embedding route, declared parallelism, candidate row counts, batch size,
planned requests, latest store statistics, and an interpretation of whether
Motoko is filling the declared route slots. Low VRAM and low watts can be
normal for the Qwen3 0.6B Q8 embedding worker; row/batch progress is a better
health signal than resident VRAM size.
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
those saved rows. When a newer same-family source index changes only some
files or sections, `vector-refresh` now looks for the latest compatible
embedding store, reuses rows whose stable row id and embedding input hash still
match, omits rows for removed or ignored sources, and embeds only new or
changed rows before writing a compact fresh manifest for the new index. The
refresh report includes refresh mode/cause plus reused, embedded, and
superseded row counts. Live status is also content-free but should show the
same mode/cause and `reuse N new M` once the reusable rows have been
identified. Embedding stores still require source
re-vectorization when the vector schema, vector row-id schema, embedding input
schema/split policy, embedding route, model, or dimensions change. Dense vector
coordinates are not migrated across
incompatible embedding models; source re-vectorization is the correct upgrade
path in that case. A fresh embedding store participates in true hybrid
retrieval: lexical/path candidates, deterministic Org/task candidates,
deterministic evidence rows, and fresh embedding candidates are unioned and
deduplicated before final context selection. When a catalog-discovered
`/v1/rerank` route is available, Motoko reranks that combined candidate set;
if reranking is missing or fails, she falls back to the non-reranked hybrid
set. Lexical scores, path boosts, Org/task signals, vector rows, rerank state,
evidence rows, and source excerpts remain visible in `/retrieval-debug` and
`/sources`. `/retrieval-debug` gets its displayed file/chunk rows,
evidence rows, vector rows, selected sources, and content-free diagnostics from
the same retrieval-service result used for chat context, so it is a diagnosis
of the production retrieval pass rather than a separate side search. Set
`MOTOKO_EVIDENCE_RETRIEVAL=0` to disable evidence-store
retrieval during diagnosis. Set `MOTOKO_VECTOR_RETRIEVAL=0` to disable
semantic retrieval during diagnosis. Set `MOTOKO_VECTOR_RERANK=0` to disable
reranking during diagnosis.

Retrieval excerpts are query-aware after a chunk is selected. If the query
mentions exact dates, or asks for the last/latest/recent dated entries, Motoko
looks inside Org chunks for dated headings and extracts the matching sections
as mandatory evidence before generic heading/window competition. Those sections
are then used for `/retrieval-preview`, chat context, topic evidence, or rerank
documents. This is specifically important for chronological files such as
`sample-journal.org`, where the relevant `** do` and `** log` subsections may live
near the end of a large chunk rather than near the beginning.

This is implemented as evidence-span selection, not as a `sample-journal.org`
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

Use `feedback up [TEXT]` or `/feedback up|down|ok [TEXT]` after an answer to
record whether it helped and what was wrong or right. The shorthand commands
`/up [TEXT]` and `/down [TEXT]` do the same thing. Feedback is written to the
current user's Motoko state as `response-feedback.jsonl`; it is not appended
to the conversation transcript. This is intended as a future
training/evaluation signal for retrieval, rerank, prompt, and answer-quality
improvements, not as an immediate unreviewed self-tuning mechanism.
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
motoko topic INDEX_ID "history of the sample project" --name sample-project
motoko deepen INDEX_ID "history of the sample project"
motoko topics
motoko topic-show TOPIC_ID
motoko topic-show TOPIC_ID --evidence
motoko chat --topic TOPIC_ID
motoko dossier "why does the user care about craftsmanship?"
motoko dossiers
motoko dossier-show DOSSIER_ID
motoko dossier-show DOSSIER_ID --evidence
motoko chat --dossier DOSSIER_ID
```

Create or attach one from inside a chat:

```text
/topic history of the sample project
/topic INDEX_ID history of the sample project
/deepen history of the sample project
/deepen INDEX_ID history of the sample project
/attach-topic
/attach-topic TOPIC_ID
```

If a chat already has a document index attached, `/topic QUERY` uses that
attached index. Otherwise `/topic` opens an index picker and then asks for the
topic query. Topic dossiers store summaries and selected excerpts as Motoko
derived state, so they can duplicate sensitive personal text inside the
current user's Motoko state directory. They are useful for going deeper into a
subject without reinjecting the entire corpus on every turn, but they should be
treated as private assistant memory.

`/deepen` and `motoko deepen` use the same mechanism with the larger topic
budget. Use them when a conversation has narrowed to a subject and Motoko needs
a more detailed private dossier before answering follow-up questions.

## Operational Model

Normal local use:

```bash
motoko
```

The default model endpoint comes from `~/.config/motoko/local-models.json` when
a managed installation provides that catalog. Endpoint addresses and service
layout are deployment details owned by `nixos-configs`, not this repository.
For an unmanaged installation, set `MOTOKO_ENDPOINT` and optionally
`MOTOKO_MODEL`, or declare routes in `~/.config/motoko/config.json`. Motoko
fails clearly when no endpoint is configured rather than assuming a host or
port.

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

Motoko is not a sandbox. Isolation comes from the OS-user boundary, file
permissions, allowlists, and not granting the process sudo, provider keys,
repository credentials, or direct service-control authority.

Motoko has explicit attached documents, hierarchical document indexes,
conversation history, automatic compaction, ranked durable memories, and
topic-focused dossiers. If
private memory or retrieval state requires stronger isolation, move the
assistant state and process into a reviewed process, container, or VM boundary.
