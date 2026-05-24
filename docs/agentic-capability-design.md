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

- Authority model: accepted. Defines which effects exist, which are prompt-only, which are
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

Design review process:

- Resolve one item at a time.
- For each item, record the accepted decision and the implementation recipe in
  this document.
- Treat unresolved items as blockers for executable script-backed tools.
- Once all items are resolved, use this document as the implementation plan.
- If implementation reveals a conflict, update the relevant item here before
  widening the runner's authority.

## Authority Model

Decision: accepted on 2026-05-24.

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

Implementation recipe:

1. Add an effect registry with the effect tiers above. Unknown effects must
   fail closed.
2. Keep a hard-coded built-in handler registry. Skills may request handlers by
   name, but Motoko only activates handlers present in code and allowed by the
   handler's declared effects.
3. Add a realm-local tool approval store under the current user's Motoko state.
   Do not store approvals in the repository or in another account.
4. For script-backed tools, compute script and metadata fingerprints before
   every run. If either fingerprint differs from the approval record, block the
   run and ask for review again.
5. Validate every proposed run against the approval contract: realm, skill id,
   tool path, script hash, metadata hash, wrapper/interpreter, argument schema,
   allowed effects, network flag, and confirmation policy.
6. Allow repeated automatic runs only for low-risk approved contracts such as
   read-only or `write_motoko_state` tools. Keep project-file writes,
   networking, and other higher-risk effects behind per-run confirmation until
   the runner has strong previews, ledgers, evals, and interruption behavior.
7. Record each run in a realm-local tool ledger with content-safe metadata,
   provenance, status, timestamps, effect tier, approval id, and output hashes.
   Tool inputs/outputs that may contain private content stay in user-owned
   Motoko state, not in admin-visible logs.
8. Keep `service_control` and `privileged` effects forbidden. Motoko must not
   use sudo, setuid helpers, or direct systemd control.

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
