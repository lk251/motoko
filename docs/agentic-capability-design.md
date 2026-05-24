# Motoko Agentic Capability Design

Date: 2026-05-24

Status: design review in progress.

This document tracks the reviewed path for adding skill-script execution,
general tool running, and goal loops to Motoko. The target is not to turn
Motoko into a broad autonomous agent runtime. The target is a small,
inspectable, realm-local harness where procedural skills can trigger bounded
built-in handlers or approved script-backed tools when that makes Motoko more
competent and reliable.

The guiding constraint is that Motoko may become more capable only by making
authority explicit. A model may propose plans, select skills, and explain
intent, but code-owned validators decide what can run.

## Review Checklist

Before enabling script execution or a general tool runner, settle these design
points:

- Authority model: which effects exist, which are prompt-only, which are
  built-in handlers, which are script-backed, and which require explicit user
  confirmation every time.
- Skill package format: script assets under `scripts/` need metadata declaring
  interpreter, allowed arguments, allowed effects, input/output schemas, source
  fingerprint, provenance, and whether the script is executable or inert text.
- Planner boundary: the model may propose or select actions, but execution must
  go through typed Motoko action records validated by code. No free-form shell
  command should be executed directly from model text.
- Filesystem and realm boundaries: scripts must stay inside the current user's
  Motoko realm, respect document allowlists and `.motokoignore`, avoid
  `/home/personal` from `mares`, avoid copied cross-account state, and never
  get sudo or system-service authority.
- Environment and sandboxing: strip secrets from environment variables, set a
  controlled working directory, bound runtime and output size, decide whether
  network is forbidden by default, and prefer NixOS-declared wrappers if OS
  sandboxing becomes necessary.
- User experience: provide dry-run/preview, concise explanation of the planned
  effect, confirmation for mutating actions, visible progress, `/stop` and
  pause behavior, and an inspectable result in `/sources` or a tool ledger.
- Observability and privacy: job status, telemetry, and admin-visible service
  logs must remain content-free. Prompts, retrieved excerpts, filenames,
  summaries, script inputs/outputs, and tool results stay in the user's Motoko
  state only.
- Provenance and artifact lifecycle: every tool-produced artifact needs schema,
  builder, skill/tool id, input hashes, source spans where applicable,
  created-at, quality status, and a migration or source-reprocess path when
  schemas change.
- Evaluation gate: add synthetic fixtures and private feedback-derived evals
  before a runner affects production behavior. Evals should cover refusal of
  unsafe actions, argument validation, output parsing, interruption, stale
  artifact handling, and source-grounding quality.
- NixOS boundary: if a tool requires system packages, sandboxes, helper users,
  service control, model files, or network policy, NixOS declares that surface;
  Motoko consumes approved interfaces and does not call `sudo` or `systemctl`.

## Authority Model

Initial recommendation:

- Keep prompt-only skills as the default for new learned skills.
- Keep built-in handlers as code-owned capabilities. A skill may request a
  built-in handler by name, but Motoko only activates handlers present in a
  hard-coded registry. This is the safest path for high-value operations such
  as deterministic Org temporal retrieval, artifact lifecycle actions, or
  other behavior where correctness matters.
- Add script-backed tools only behind a per-script approval record. Every new
  script starts inert. A user must approve the script, its declared effects,
  its allowed argument schema, and its security profile before Motoko may run
  it automatically.
- After approval, the same script may run again without repeated confirmation
  only when the request fits the previously approved contract exactly: same
  script content fingerprint, same declared effects, same interpreter/wrapper,
  same allowed argument schema, same realm, and no broader filesystem, network,
  or mutation authority than originally approved.
- Any material change invalidates approval and returns the script to review:
  script body change, metadata change, interpreter change, effect expansion,
  network enablement, new path roots, new mutating behavior, or a schema change
  that allows broader inputs.
- Mutating or higher-risk executions can still require per-run confirmation
  even after script approval. Approval means "this tool is allowed to exist and
  be considered"; it does not have to mean "run any mutating action silently."

Recommended effect tiers:

- `prompt_only`: no execution authority. The skill only contributes procedural
  guidance to prompts.
- `read_context`: read Motoko-owned metadata or already attached context, but
  not arbitrary files.
- `read_allowed_files`: read files under explicit Motoko allowlists and not
  ignored by `.motokoignore`.
- `write_motoko_state`: write Motoko-owned derived artifacts, ledgers,
  suggestions, eval fixtures, or caches under the current user's state.
- `write_allowed_project`: write to an allowlisted project directory. This
  should require per-run confirmation at first.
- `network`: make network requests. Default should be denied unless a specific
  NixOS-reviewed wrapper and purpose exists.
- `external_process`: run an approved interpreter or executable. This should
  always be paired with a declared wrapper, timeout, output limit, and argument
  schema.
- `service_control`: forbidden to Motoko under the current boundary.
- `privileged`: forbidden; no sudo, no setuid helpers, no direct systemd
  control.

Recommended approval record:

```json
{
  "schema": "motoko-tool-approval-v1",
  "realm": "mares",
  "skill": "example-skill",
  "tool": "scripts/example.py",
  "script_sha256": "...",
  "metadata_sha256": "...",
  "interpreter": "python3",
  "wrapper": "motoko-tool-python-stdlib",
  "allowed_effects": ["read_allowed_files", "write_motoko_state"],
  "argument_schema": {"type": "object"},
  "network": false,
  "approved_at": "2026-05-24T00:00:00+00:00",
  "approved_by": "user",
  "requires_confirmation": false
}
```

The approval store should live in the current user's Motoko state, not in the
repository and not in another account. Repo-shipped built-in handlers are code
reviewed through Git; learned script approvals are user-state decisions.

My bias is to make the first script runner read-only or Motoko-state-only.
That gives Motoko useful deterministic tools without immediately granting
project-file mutation. Project-file writes can follow after the runner has
good previews, confirmations, evals, and interruption behavior.

## Goal Loops

Goal loops should come after the planner/handler/tool boundary is solid. The
intended shape is a durable, user-approved loop record with:

- objective;
- scope;
- allowed skills and tools;
- context sources;
- budgets for time, model calls, tool calls, and output;
- stop conditions;
- checkpoint ledger;
- final audit.

A loop should run explicit phases: plan, retrieve, act through approved
handlers/tools, observe, reflect/audit, persist artifacts or feedback, and
either continue or stop. Loops must be pauseable, resumable, visible in job
status, and conservative by default: read-only loops first, then
user-confirmed local mutations, and only later broader automation after
separate review.
