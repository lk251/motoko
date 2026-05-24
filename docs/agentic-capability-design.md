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
- Skill package format: accepted. Script assets under `scripts/` need metadata declaring
  interpreter, allowed arguments, allowed effects, input/output schemas, source
  fingerprint, provenance, and whether the script is executable or inert text.
- Planner boundary: accepted. The model may propose or select actions, but execution must
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
- While an item is still under review, record the current proposed solution in
  the item's section so later discussion has a concrete target. When the user
  accepts or revises it, update that same section rather than leaving the
  decision in chat.
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

## Skill Package Format

Decision: accepted on 2026-05-24.

Hermes Agent reference:

- Hermes stores skills as directories with a required `SKILL.md` and optional
  supporting directories such as `references/`, `templates/`, `scripts/`, and
  `assets/`.
- `SKILL.md` uses YAML frontmatter for metadata such as `name`,
  `description`, `version`, `platforms`, `metadata.hermes.tags`,
  `requires_toolsets`, `requires_tools`, non-secret config settings, and
  required environment variables.
- Hermes treats helper scripts as files in `scripts/` that the skill
  instructions can ask the agent to run through existing tools such as terminal
  or code execution. Skills are suitable when the capability can be expressed
  as instructions plus shell commands or existing tools; Hermes recommends a
  Tool when the capability needs custom Python integration, auth flows, binary
  data, streaming, or precise custom processing.
- Hermes exposes skill discovery through progressive disclosure:
  a compact skill list first, full `SKILL.md` only when needed, and linked
  reference files only on demand.
- Hermes lets the agent maintain procedural memory through a `skill_manage`
  tool that can create, patch, edit, delete, and add supporting files to skills
  after useful workflows are discovered.
- Hermes has Skills Hub trust levels and security scanning for hub-installed
  skills, including checks for data exfiltration, prompt injection, destructive
  commands, and shell injection. It can also declare required secrets and
  config values in skill metadata.
- Hermes can render template variables such as the skill directory into
  `SKILL.md`, so the model can run a bundled helper script without path
  arithmetic. Hermes also supports inline shell snippets in skills, but that
  feature is disabled by default because it runs host commands when a skill is
  loaded.
- Hermes' public skill format does not appear to require a separate
  per-script typed execution contract. For Motoko, that is the key place to be
  stricter.

Sources reviewed on 2026-05-24:

- https://hermes-agent.nousresearch.com/docs/developer-guide/creating-skills
- https://hermes-agent.nousresearch.com/docs/guides/work-with-skills/
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md
- https://raw.githubusercontent.com/NousResearch/hermes-agent/main/tools/skills_tool.py
- https://raw.githubusercontent.com/NousResearch/hermes-agent/main/tools/skill_manager_tool.py
- https://raw.githubusercontent.com/NousResearch/hermes-agent/main/tools/skills_guard.py

Accepted Motoko decision:

- Keep `SKILL.md` as the human-readable skill package manifest and procedural
  guide. It remains the primary progressive-disclosure file that Motoko can
  show to a model or user.
- Continue supporting confined support directories:
  `references/`, `templates/`, `scripts/`, and later `assets/` if needed.
- Treat files under `scripts/` as inert text by default. A script becomes
  executable only if it has an adjacent metadata file and a matching user
  approval record.
- Require adjacent JSON metadata for every executable script. JSON is preferred
  over prose frontmatter for the execution contract because Motoko can validate
  it with the Python standard library and fail closed on unknown fields.
- Suggested naming: `scripts/name.py` has metadata in
  `scripts/name.tool.json`. Other script types use the same pattern.
- `SKILL.md` may declare high-level tools for readability, but executable
  authority comes from the adjacent tool JSON plus the approval record, not
  from prose alone.

Accepted `SKILL.md` additions:

```yaml
---
schema: motoko-skill-v3
name: example-skill
description: Short skill description.
kind: workflow
triggers:
  - example trigger phrase
handler: prompt_only
allowed_effects:
  - prompt_only
tools:
  - scripts/example.tool.json
---
```

Accepted `scripts/*.tool.json` shape:

```json
{
  "schema": "motoko-tool-v1",
  "name": "example",
  "description": "Short executable tool description.",
  "script": "example.py",
  "interpreter": "python3",
  "wrapper": "motoko-tool-python-stdlib",
  "allowed_effects": ["read_allowed_files", "write_motoko_state"],
  "argument_schema": {
    "type": "object",
    "properties": {
      "path": {"type": "string"}
    },
    "required": ["path"],
    "additionalProperties": false
  },
  "input_schema": {"type": "object"},
  "output_schema": {"type": "object"},
  "timeout_seconds": 30,
  "max_stdout_bytes": 65536,
  "max_stderr_bytes": 16384,
  "network": false,
  "writes_project_files": false,
  "requires_confirmation": false
}
```

Implementation recipe:

1. Extend skill schema to `motoko-skill-v3` while keeping deterministic
   upgrades from older skill files.
2. Add a stdlib JSON loader for `scripts/*.tool.json` with strict validation:
   reject unknown schemas, unknown effects, paths outside the skill package,
   absolute script paths, path traversal, unsupported interpreters, and
   ambiguous argument schemas.
3. Compute `script_sha256` and `metadata_sha256` from the executable script and
   adjacent tool JSON. These hashes feed the approval record from the accepted
   authority model.
4. Keep `SKILL.md` tool declarations advisory for display and discovery; the
   adjacent JSON metadata is the execution contract.
5. Add `motoko skill tools NAME` and `/skill tools NAME` to inspect declared
   tools, their status, hashes, effects, and whether approval is current.
6. Add validation tests with synthetic skill packages: valid prompt-only skill,
   valid inert script, valid executable script metadata, rejected path
   traversal, rejected unknown effect, rejected unsupported interpreter,
   rejected missing metadata, and approval invalidation after script or metadata
   changes.
7. Do not execute any scripts in this step. First implement discovery,
   validation, display, fingerprinting, and approval-status reporting.

## Planner Boundary

Decision: accepted on 2026-05-24.

The model may propose intentions, select skills, and request tools, but it must
not directly emit executable shell, filesystem, network, or service operations
that Motoko runs. Execution flows through typed Motoko action records. Motoko
code validates those records against the accepted authority model, skill
package metadata, approval store, realm boundary, `.motokoignore`, and
confirmation policy before anything happens.

The model is useful as planner; Motoko remains the authority boundary.

Accepted action record shape:

```json
{
  "schema": "motoko-action-v1",
  "kind": "skill_tool_run",
  "skill": "org-temporal-retrieval",
  "tool": "latest_entries",
  "arguments": {
    "path": "logbook.org",
    "count": 3
  },
  "reason": "Need latest dated entries from a specific Org source."
}
```

Accepted planner rules:

- Planner output is data, not authority. Natural-language instructions,
  markdown, or shell-looking text are never executable by themselves.
- Unknown action schemas, unknown action kinds, unknown skills, unknown tools,
  unknown effects, malformed arguments, or missing approvals fail closed.
- Built-in handlers and approved script tools share the same action-record
  envelope, but validation dispatches them through different registries.
- Free-form shell commands are not a supported action kind. If Motoko later
  needs command execution, it must be represented as an approved script-backed
  tool with a narrow argument schema and effect contract.
- Planning can happen before retrieval, after retrieval, or inside an approved
  goal loop, but every phase uses the same validator and ledger boundary.
- The validator may rewrite safe defaults, narrow scope, or require user
  confirmation, but it must not silently broaden the requested authority.
- Rejected action records should produce a concise, inspectable explanation for
  the user and, where useful, a safer preview-only alternative.

Implementation recipe:

1. Define `motoko-action-v1` as a small family of typed action records:
   `skill_handler_run`, `skill_tool_run`, `artifact_lifecycle_plan`,
   `artifact_lifecycle_apply`, and later `goal_loop_step`.
2. Add an action parser that accepts JSON-like data from internal planners, not
   executable text. It should reject multiple actions unless the caller is an
   approved goal loop with a declared budget.
3. Add an action validator that checks schema, kind, realm, skill id, tool id,
   handler/tool registry membership, arguments, effects, approval status,
   confirmation policy, and security boundaries.
4. Add a dispatcher that only receives validated action objects. The dispatcher
   should not parse model text or infer new authority.
5. Record accepted, rejected, previewed, interrupted, and completed actions in
   the realm-local ledger with content-safe metadata and private details kept
   in the user's Motoko state.
6. Expose an inspection command such as `motoko action validate FILE` or
   `/action preview` before enabling model-generated actions in production.
7. Add tests for valid action records, unknown kinds, unknown skills/tools,
   malformed arguments, direct shell attempts, missing approvals, stale
   fingerprints, `.motokoignore` denial, and confirmation-required actions.

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
