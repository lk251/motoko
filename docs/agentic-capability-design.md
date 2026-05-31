# Motoko Agentic Capability Design

Date: 2026-05-24

Status: approved boundary; implementation in progress.

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
- Filesystem and realm boundaries: accepted. Scripts must stay inside the current user's
  Motoko realm, respect document allowlists and `.motokoignore`, avoid
  `/home/personal` from `mares`, avoid copied cross-account state, and never
  get sudo or system-service authority.
- Environment and sandboxing: accepted. Strip secrets from environment variables, set a
  controlled working directory, bound runtime and output size, decide whether
  network is forbidden by default, and prefer NixOS-declared wrappers if OS
  sandboxing becomes necessary.
- User experience: accepted. Provide dry-run/preview, concise explanation of the planned
  effect, confirmation for mutating actions, visible progress, `/stop` and
  pause behavior, and an inspectable result in `/sources` or a tool ledger.
  Repetitive confirmed actions may be approved for the rest of the current
  session when the action type, tool, effect set, and scope do not broaden.
- Observability and privacy: accepted. Job status, telemetry, and admin-visible service
  logs must remain content-free. Prompts, retrieved excerpts, filenames,
  summaries, script inputs/outputs, and tool results stay in the user's Motoko
  state only.
- Provenance and artifact lifecycle: accepted. Every tool-produced artifact needs schema,
  builder, skill/tool id, input hashes, source spans where applicable,
  created-at, quality status, and a migration or source-reprocess path when
  schemas change.
- Evaluation gate: accepted. Add synthetic fixtures and private feedback-derived evals
  before a runner affects production behavior. Evals should cover refusal of
  unsafe actions, argument validation, output parsing, interruption, stale
  artifact handling, and source-grounding quality. This should not block the
  first implementation; ship a small eval harness now and grow it from usage.
- NixOS boundary: accepted. If a tool requires system packages, sandboxes, helper users,
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

Approval checkpoint, 2026-05-24:

- The user approved the next authority step under this exact boundary:
  project mutation is a code-owned typed action, not arbitrary script write
  authority. Script tools may propose or prepare data, but Motoko's validator
  and applier own the filesystem effect.
- `write_allowed_project` remains disabled for script-backed tools. The
  approved path is `project_file_write`, with an absolute allowlisted target,
  `.motokoignore` and VCS/cache enforcement, one exact session confirmation,
  overwrite hash checks, atomic writes, and content-safe ledger rows.
- Goal-loop execution may begin only as an explicit action-list runner. The
  loop record declares objective, budgets, allowed effects/tools, and concrete
  actions; every action still passes through the normal validator,
  confirmation, execution, and ledger path. Autonomous model-planned loops
  remain a later design step.

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
9. For project-file mutation, implement a first-class `project_file_write`
   action. It should create or overwrite only files under Motoko allowlists,
   never ignored paths, never VCS/cache directories, and never symlink targets
   or parents. Overwrites require an `expected_sha256` match. The ledger stores
   hashes and byte counts, not raw file content.

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
   `artifact_lifecycle_apply`, `project_file_write`, and later
   `goal_loop_step`.
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

## Filesystem and Realm Boundaries

Decision: accepted on 2026-05-24.

Tool and handler authority is always realm-local and scope-limited. Motoko may
read or write only what the accepted effect contract permits, only in the
current user's realm, and only under explicitly allowed roots.

Accepted rules:

- `mares` must not read `/home/personal`, copy personal Motoko state, or rely
  on Javier/admin account state.
- Skill tools may read allowlisted project/document roots only when the tool's
  effect contract includes `read_allowed_files`.
- Skill tools must obey `.motokoignore` for corpus/document operations.
- Scripts may write Motoko-owned state only with `write_motoko_state`; project
  writes require the code-owned `project_file_write` action, the
  `write_allowed_project` effect, and explicit confirmation policy. Script
  tools do not receive direct project-write authority.
- Absolute paths, path traversal, symlinks escaping the allowed root, hidden
  cross-account state, and broad home-directory access are denied.
- `service_control` and `privileged` remain forbidden effects.

Implementation recipe:

1. Centralize path checks for skill tools and actions: resolve paths, reject
   path traversal, reject cross-realm roots, and require an allowed base.
2. Reuse existing allowlist and `.motokoignore` logic for document/project
   reads instead of creating a separate runner-specific policy.
3. Add tests for allowed relative paths, denied absolute paths outside scope,
   denied `..`, denied symlink escape, ignored files, and `/home/personal`
   denial from `mares`.

## Environment and Sandboxing

Decision: accepted on 2026-05-24.

Motoko should start with a strict process environment and stdlib-only runner.
If stronger OS sandboxing becomes necessary, NixOS should declare reviewed
wrappers; Motoko should consume those wrappers rather than inventing host
authority.

Accepted rules:

- Script tools run with a scrubbed environment, fixed working directory,
  bounded runtime, bounded stdout/stderr, and no inherited secrets.
- Network is off by default at the Motoko policy layer. Network-capable tools
  require an explicit `network` effect and a later reviewed NixOS policy.
- Supported interpreters start narrow. The first implementation should support
  only repo-reviewed `python3` scripts through a declared wrapper name; no
  shell interpreter, no arbitrary executable path, and no `PATH` guessing for
  authority.
- Tools must receive structured JSON arguments, not shell-expanded strings.

Implementation recipe:

1. Define a safe default tool environment with only content-free variables
   needed for stable execution.
2. Define timeout and output-limit enforcement in the runner layer.
3. Require script metadata to name an approved wrapper/interpreter pair.
4. Leave stronger wrappers, helper users, seccomp/bubblewrap, or network
   policy as NixOS-owned extensions.

## User Experience

Decision: accepted on 2026-05-24.

Tool use should feel clear and interruptible. Motoko should explain the exact
planned effect before risky work, then make results inspectable without
dumping private data into ordinary chat.

Accepted rules:

- Mutating or higher-risk actions get dry-run/preview first.
- Confirmation records can be one-shot, persistent approval-contract records,
  or session-repeat approvals. Session-repeat approval applies only while the
  current Motoko session is alive and only for the same action kind, skill,
  tool, effects, confirmation policy, and non-broader scope.
- `/stop` must interrupt active foreground tool work where possible and mark
  the ledger entry as interrupted.
- Rejected, previewed, confirmed, running, completed, failed, and interrupted
  states should be visible from an inspection command.

Implementation recipe:

1. Add session-local approval records in memory, separate from persistent tool
   approvals under Motoko state.
2. Add a dry-run/preview path that validates and describes an action without
   executing it.
3. Add result inspection through the action/tool ledger before wiring results
   into `/sources`.
4. Add cancellation checks around long-running tool work.

## Observability and Privacy

Decision: accepted on 2026-05-24.

Motoko needs enough telemetry to debug behavior without leaking private
content to admin-visible logs or service journals.

Accepted rules:

- Job status, route status, and admin-visible logs remain content-free.
- Private prompts, retrieved excerpts, filenames, summaries, memories, script
  inputs/outputs, and tool results stay in the current user's Motoko state.
- Ledgers may store content hashes, schema ids, tool ids, effect tiers,
  statuses, durations, byte counts, and paths only when the ledger is
  user-owned. Content-free public summaries should avoid filenames when they
  may reveal private corpora.

Implementation recipe:

1. Add a realm-local action/tool ledger under Motoko state.
2. Split ledger metadata into content-safe fields and private detail fields.
3. Keep terminal reports user-local; do not write request/response bodies to
   journald or admin-owned logs.

## Provenance and Artifact Lifecycle

Decision: accepted on 2026-05-24.

Every durable tool output must be traceable and upgradable or explicitly
rebuildable from source.

Accepted rules:

- Tool-produced artifacts need schema, builder, skill id, tool id, action id,
  input hashes, source spans where applicable, created-at, quality status, and
  source realm/security context.
- Schema changes need deterministic migrations when possible. If a new schema
  needs information missing from the old artifact, mark the artifact for
  resumable source reprocessing.
- Artifact cleanup follows existing lifecycle planning: changed/deleted/ignored
  sources should make dependent artifacts stale before deletion.

Implementation recipe:

1. Reuse existing artifact lifecycle paths where possible instead of creating a
   separate tool-artifact cleanup system.
2. Add tool/action provenance fields to new tool artifacts and ledgers.
3. Add migration hooks for action/tool schemas before production use.

## Evaluation Gate

Decision: accepted on 2026-05-24.

Evals should guide implementation without becoming a reason to stall the first
safe version. The first runner can ship with focused synthetic tests and an
explicit path for feedback-derived eval rows.

Accepted rules:

- Add synthetic tests now for validation, refusal, previews, ledgers, and
  interruption semantics.
- Add a command/report surface for agentic eval fixtures as soon as production
  tool behavior exists.
- Private feedback from real use can become per-realm eval rows, but feedback
  does not directly mutate production policy.

Implementation recipe:

1. Start with deterministic unit/regression tests for the runner substrate.
2. Add feedback-derived eval storage later under the current user's Motoko
   state, following the existing retrieval feedback pattern.
3. Keep model-judged evals optional; deterministic safety evals are required.

## NixOS Boundary

Decision: accepted on 2026-05-24.

NixOS owns system capability. Motoko owns realm-local planning, validation, and
use of approved interfaces.

Accepted rules:

- Motoko does not call `sudo`, direct `systemctl`, or arbitrary service-control
  commands.
- If a tool needs a package, sandbox, helper user, service endpoint, model
  file, network policy, or wrapper, NixOS declares it.
- Motoko discovers and uses approved local model/service surfaces through
  existing catalog and helper interfaces such as `motoko-model`, not through
  direct service mutation.

Implementation recipe:

1. Keep tool metadata wrapper names declarative and inspectable.
2. Deny tools that require undeclared system capability.
3. Document any future NixOS-side requirement before implementation.

## Implementation Work Plan

Status: implementation complete to the accepted boundary; future gates remain
active.

This plan implements the accepted design without widening authority beyond the
reviewed boundary:

1. Keep admin/reasoning-stream changes only if validation stays green.
2. Add the accepted design sections and recipes to this document.
3. Implement an effect registry and strict tool metadata validator.
4. Implement realm-local persistent approvals and session-repeat approvals.
5. Implement typed action records, action validation, preview formatting, and
   content-safe ledgers.
6. Expose inspection commands for skill tools and action previews.
7. Add focused deterministic tests for safe and unsafe paths.
8. Run repository validation and commit locally.

Implementation checkpoint, 2026-05-24:

- Added the validation/preview substrate: effect registry, strict
  `scripts/*.tool.json` validation, script and metadata fingerprinting,
  persistent tool approvals, typed action validation, session-repeat approval
  keys, and a realm-local content-safe action ledger.
- Added inspection surfaces: `motoko skill tools NAME`,
  `motoko skill approve-tool NAME TOOL --yes`, `motoko action preview FILE`,
  `/skill tools NAME`, `/skill approve-tool NAME TOOL --yes`, and
  `/action preview FILE`.
- Script execution remains deliberately disabled. The current implementation
  lets Motoko inspect, approve, and preview tool contracts before any future
  runner executes them.

Runner checkpoint, 2026-05-24:

- Added the first executable runner for `skill_tool_run` actions. It runs only
  approved `python3` tools using the declared `motoko-tool-python-stdlib`
  wrapper, sends structured JSON on stdin, uses a scrubbed environment, sets a
  fixed skill-package working directory, enforces per-tool timeout and
  stdout/stderr byte limits, validates JSON object output, and writes private
  inputs/results under the current user's Motoko state.
- Executable script tools are treated as having the `external_process` effect
  even when older metadata omits it, so the approval contract records the real
  authority being granted. Script tools cannot declare `prompt_only`; that
  effect remains reserved for non-executable procedural guidance.
- Added `motoko action run FILE [--yes]` and `/action run FILE [--yes]`.
  `--yes` grants only one session-style confirmation for that invocation when
  the action already has a persistent fingerprint approval but still requires
  run confirmation.
- Shell commands, arbitrary executables, network tools, service control,
  privileged actions, and project-file-writing tools remain blocked. The
  runner currently enables low-risk read/Motoko-state tools first; broader
  mutation still needs a later review step with previews, cancellation, and
  stronger sandboxing if needed.
- Action ledgers remain content-safe. Private stdin/stdout/stderr and parsed
  result JSON stay in realm-local `tool-runs/` records owned by the current
  user.

Tool machinery checkpoint, 2026-05-24:

- Added a Motoko-shaped tool catalog rather than importing Hermes' broad tool
  registry. `motoko tools` and `/tools` list all declared skill tools across
  learned skills, including validation errors, approval state, effects, script
  fingerprints, and metadata fingerprints.
- Added the first deterministic planner bridge: `motoko action plan QUERY` and
  `/action plan QUERY`. This performs no model call and no execution. It ranks
  known approved-or-approvable tools by query overlap, infers only obvious
  arguments such as named file/path mentions and small integer hints, and
  prints candidate `motoko-action-v1` JSON records with validation status.
- Added result inspection: `motoko action ledger`, `/action ledger`,
  `motoko action result RUN_ID`, and `/action result RUN_ID`. Ledger reports
  are content-safe. Private stdout/stderr and parsed JSON result content are
  hidden unless the owning user explicitly passes `--private`.
- Hermes' public design uses broad toolsets and terminal/code-execution
  backends, with optional Docker/SSH/container-style containment and skill
  scanning for externally sourced skills. Motoko should not import that broad
  surface. The Motoko equivalent is a smaller catalog plus per-tool contracts,
  fingerprint approvals, realm-local ledgers, and NixOS-owned stronger
  containment if a future tool truly needs it.

Gated capabilities not completed by design:

- Script-assisted project mutation: script tools still cannot directly write
  project files. This is intentional. The current safe path is code-owned
  `project_file_write`, and the likely next step is to let approved scripts
  emit structured patch/write proposals that Motoko validates and applies
  through the same allowlist, `.motokoignore`, hash, confirmation, atomic-write,
  ledger, pause, and checkpoint machinery. Raw script filesystem write
  authority should remain a later, separately reviewed option if it is ever
  needed.
- `network`: not enabled. To enable it, require a NixOS-reviewed wrapper or
  policy, explicit destination/purpose metadata, no ambient secrets, and
  content-safe telemetry.
- Read-only model-planned goal loops: enabled only through explicit
  `planner: model_readonly` records. They may plan, retrieve, inspect, audit,
  and propose typed actions under budget, but they refuse project-write,
  network, service-control, and privileged effects and do not apply mutations.
  Mutating model-planned loops remain disabled until the read-only form has
  enough usage and eval coverage.
- Broader terminal-like tools and arbitrary executable control: not enabled.
  Shell commands, arbitrary executables, service control, and privileged
  actions remain outside Motoko's authority.
- Stronger containment: not required for the current low-risk runner, but
  needed before broad terminal-like tools, network tools, or direct project
  mutation. This should be NixOS-owned, not a hidden Python-side privilege
  expansion.

Priority assessment for future intelligence and competence:

1. Script-assisted project mutation and read-only model-planned loops now form
   the first useful agentic layer: Motoko can turn understanding into
   reviewable proposals and can run a bounded plan/retrieve/audit loop without
   granting mutation authority.
2. Mutating model-planned loops are potentially valuable, but only after the
   read-only form works well. Mutation should remain user-confirmed until
   evals and real usage prove reliability.
3. Hermes-style skill improvement should continue incrementally: prompted
   self-review, loaded-skill patching, support files, and tool contracts are
   useful; broad terminal/code-execution toolsets should not be copied.
4. Network tools are useful for research and external data, but less central to
   Motoko's local intelligence than project mutation, retrieval quality,
   memory, and durable skills.
5. Stronger containment is enabling infrastructure, not intelligence by
   itself. Add it when a concrete high-value tool needs it.

Recommended next implementation sequence:

1. Harden script-assisted project mutation, read-only model-planned loops,
   model-confirmed apply, and managed worktree workflows through real use,
   feedback-derived evals, and clearer proposal review.
2. Keep broader autonomous act/observe loops disabled until the
   review/apply path is stable. The next broadening step would be a richer
   final-audit and resume UX around model-confirmed applies, not arbitrary
   terminal execution.
3. Hermes-style skill improvement as an ongoing parallel track. Keep improving
   prompted self-review, loaded-skill patching, support-file use, and
   feedback-derived eval fixtures so Motoko's procedural memory becomes more
   useful through real use. Preserve Motoko's typed-action and approval
   boundary instead of importing a broad terminal/tool runtime.

Goal-loop preview checkpoint, 2026-05-24:

- Added preview-only goal-loop records with schema `motoko-goal-loop-v1`.
  `motoko goal plan OBJECTIVE` and `/goal plan OBJECTIVE` build a disabled
  loop draft with objective, scope, allowed tools/effects, budgets, stop
  conditions, and phases. `--save` stores the draft under the current user's
  Motoko state.
- Added `motoko goal list`, `/goal list`, `motoko goal preview FILE`, and
  `/goal preview FILE`. These validate and inspect loop records without
  execution.
- Goal-loop execution was disabled at this checkpoint. Low-risk effects could
  be previewed as `draft`; `write_allowed_project` and `network` produced
  `needs_approval`; `service_control` and `privileged` were rejected.

Project-write and goal-run checkpoint, 2026-05-24:

- Added the code-owned `project_file_write` action kind. It requires an
  absolute allowlisted target path, respects `.motokoignore`, rejects
  VCS/cache directories and symlink targets, requires one exact session
  confirmation, and writes atomically. Overwrite mode requires the current
  `expected_sha256` of the target.
- Added `motoko action apply FILE --yes` and `/action apply FILE --yes` for
  confirmed project-file writes. `motoko action run FILE [--yes]` can dispatch
  both approved script-tool actions and typed project-file writes, but
  script-owned project writing remains blocked.
- Extended `motoko-goal-loop-v1` with an optional explicit `actions` list and
  added `motoko goal run FILE --yes` / `/goal run FILE --yes`. The runner does
  not ask a model to plan; it executes only the concrete actions in the record,
  within budgets and allowed effects/tools, and each action still passes
  through the normal action validator and ledger.
- Goal loops are now executable only in this narrow explicit-action form.
  Autonomous plan/retrieve/act/observe loops remain a later reviewed step.

Action-eval checkpoint, 2026-05-24:

- Added `motoko action-eval` and `/action-eval` as the first command/report
  surface for agentic safety fixtures. The eval runs in a temporary Motoko
  state/config root, calls no model, and uses no real user corpus content.
- Current fixtures cover confirmed code-owned project writes, unconfirmed write
  blocking, `.motokoignore` denial for project writes and skill-tool document
  reads, argument-scoped session confirmation, script-owned project-write
  blocking, explicit goal action-list confirmation, and goal budget refusal.
- `--write` stores the JSON report under the current user's Motoko state in
  `action-evals/`. These evals are deterministic safety checks; private
  feedback-derived agentic eval rows can come later after real usage reveals
  useful cases.

Adversarial audit checkpoint, 2026-05-24:

- Detailed report: `docs/adversarial-design-audit-2026-05-24.md`.
- Compared Motoko's current skill/tool/action/goal-loop machinery with
  `NousResearch/hermes-agent` commit
  `186bf25cb11077b8c158dbfc1f768e48bc28b0db`, focusing on skills,
  `skill_manage`, skill scanning, curator behavior, tool guardrails, and tool
  execution.
- Fixed three concrete boundary issues found by the audit:
  relative skill-tool path arguments now resolve through the current working
  directory and allowlist; skill-tool read paths now respect `.motokoignore`;
  and same-session confirmations now include an argument hash so approval for
  one invocation cannot silently authorize a broader one.
- Open risks remain explicit rather than hidden: current script tools are
  policy-confined but not OS-confined, active foreground script cancellation
  still needs an interrupted ledger path, a full skill lifecycle/curator layer
  is not implemented, autonomous model-planned loops remain disabled by
  design, and artifact lifecycle application still needs to cover every
  derived artifact family.

Durable goal-run checkpoint, 2026-05-24:

- Confirmed `motoko goal run FILE --yes` and `/goal run FILE --yes` now create
  `goal-run-v1` records under the current user's Motoko state before execution
  begins. The record stores the source loop id/path, objective, allowed
  effects/tools, budgets, explicit typed actions, cursor, status, and
  per-action result metadata.
- The runner updates the record after every action. Interruptions, refusals,
  and validation failures therefore leave an inspectable checkpoint rather than
  relying on terminal scrollback.
- `motoko pause` and `/pause` are checked at action boundaries. A pause request
  marks the run `paused`, preserves completed action results, clears the pause
  request, and leaves resume to continue at the next pending action.
- Added `motoko goal runs` / `/goal runs` and `motoko goal resume RUN_ID --yes`
  / `/goal resume RUN_ID --yes`. Resume starts at the first incomplete action;
  completed runs are reported without re-executing actions.
- This is still not an autonomous model-planned loop. It is the durable
  execution substrate for explicit action-list loops, preserving the reviewed
  validator, effect, budget, confirmation, and ledger boundaries.

Interruption checkpoint, 2026-05-24:

- Added foreground action/tool interruption for the current narrow runner.
  Action execution now accepts a cancellation token; script tools terminate the
  child process, write an `interrupted` private result, and append an
  `interrupted` action ledger row; project-file writes can stop before the
  atomic write; explicit goal runs mark durable `interrupted` records and keep
  cursor/checkpoint state so resume does not replay completed actions.
- Added action-eval coverage for interruption: running-to-interrupted ledger
  state, invalid actions staying rejected under cancellation, and goal
  interruption/resume without replaying completed work.

Script-assisted project proposal checkpoint, 2026-05-30:

- Added a narrow `propose_project_changes` tool effect. Approved scripts with
  this effect may return `proposed_actions` containing typed
  `project_file_write` records, but they still do not receive direct project
  filesystem write authority.
- Tool results now store content-safe proposal validation summaries alongside
  private stdout/stderr/output JSON. Proposals are validated immediately
  through the same allowlist, `.motokoignore`, expected-hash, confirmation,
  atomic-write, and ledger boundary used by normal `project_file_write`
  actions.
- Added `motoko action proposals RUN_ID` / `/action proposals RUN_ID` to
  inspect proposals and `motoko action apply-proposal RUN_ID INDEX --yes` /
  `/action apply-proposal RUN_ID INDEX --yes` to apply one proposal through
  Motoko-owned write machinery. Tool output that contains `proposed_actions`
  without declaring `propose_project_changes` fails closed.
- Added action-eval and regression coverage for successful proposal
  application, `.motokoignore` rejection, undeclared proposal effects, and the
  existing direct script project-write block.

Read-only model-planned goal-loop checkpoint, 2026-05-30:

- Added an explicit `planner: model_readonly` mode for `motoko-goal-loop-v1`.
  It is opt-in via `motoko goal plan --model-readonly "objective" --save`.
- `motoko goal run GOAL.json --yes` can now run a bounded read-only loop that
  retrieves current-project context, asks the audit route for strict JSON, and
  writes a durable `goal-run-v1` checkpoint with plan, retrieval assessment,
  observations, final audit, next steps, source records, and proposed action
  validations.
- The read-only runner refuses `write_allowed_project`, `network`,
  `service_control`, and `privileged` effects. It may store proposals under
  the user's Motoko state, but it does not apply them. `motoko goal proposals
  RUN_ID [--private]` is the review surface for those proposed action records.
- Regression coverage checks that the runner uses the audit route, stores
  proposal validations, keeps proposed project writes unapplied, hides proposal
  content by default, and rejects mutating effects.

User-confirmed model-planned and worktree checkpoint, 2026-05-30:

- Added explicit `planner: model_confirmed` records, created with
  `motoko goal plan --model-confirmed "objective" --save` or the
  `--model-write` alias. The runner retrieves context and asks the audit route
  for strict JSON action proposals, then stops in `awaiting_confirmation`.
- Added `motoko goal apply RUN_ID --yes` / `/goal apply RUN_ID --yes`.
  Applying a model-confirmed run executes the stored proposals in order,
  checkpointing after every action. The model still never receives direct file
  mutation authority; Motoko validators, confirmations, budgets, ledgers,
  allowlists, `.motokoignore`, and clean-tree checks own the effect.
- Added typed Git worktree actions: `git_worktree_create`, `git_commit`,
  `git_worktree_merge`, and `git_worktree_remove`. These are code-owned
  action kinds, not shell command strings. They require exact session
  confirmation and are available through `motoko action run ACTION.json --yes`
  or the convenience `motoko worktree create|merge|remove ... --yes`
  commands.
- New worktrees are Motoko-managed and live under the current user's Motoko
  state by default. The registry lets later `project_file_write` actions target
  those worktrees without broadening the global document allowlist. Merges are
  fast-forward-only with clean-tree checks; removal is limited to managed
  worktrees.
- Regression coverage checks that model-confirmed plans stop for review before
  mutation, `goal apply` performs the confirmed write, and managed worktrees
  can be created, written, committed, fast-forward merged to `master`, and
  removed.

Skill lifecycle checkpoint, 2026-05-30:

- Added the first Motoko-shaped skill lifecycle layer. Selection and
  patch/write events update a realm-local lifecycle store outside `SKILL.md`;
  `motoko skills` and `motoko skill show` expose state, pins, usage counts, and
  patch counts; `motoko skill curator` is report-first; and
  `pin`/`unpin`/`archive --yes`/`restore` provide reversible library hygiene.
- Archived learned skills are still inspectable, but they no longer enter
  prompt context or action planning. Built-in skills cannot be archived.
- This intentionally adapts Hermes Agent's curator direction without adopting
  automatic mutation, broad deletion, or new execution authority.
- The curator report also now flags large skills that may deserve support
  files, possible consolidation groups, stale unused learned skills that may
  deserve archive review, and recent non-positive feedback rows whose terms
  match active skills. These remain report-only hints.
- `motoko skill curator --suggest` can convert concrete curator candidates into
  pending review-first `skill_manage` suggestions. Current deterministic
  candidates come from non-positive feedback rows that match active skills,
  repeatedly selected skills that have not yet been patched, support-file
  opportunities, overlapping learned skills, and stale unused learned skills.
  Stale unused skills receive an `archive-review.md` support-file suggestion;
  the curator does not archive them. The command writes only pending
  suggestions; accepting a suggestion still goes through the existing
  validators.

Skill/handler checkpoint, 2026-05-31:

- Added `org-structural-query`, a built-in retrieval skill backed by the
  code-owned `builtin:org_structural_query` handler. It lets ordinary chat
  queries such as "show me everything tagged RaceFocus" activate deterministic
  Org evidence selection before final synthesis; users do not need a special
  `/org-query` mini-language for normal use.
- The handler parses Org headings, inherited tags, TODO state, priority,
  `DEADLINE`, `SCHEDULED`, and dated headings into evidence rows. It preserves
  source spans and records the activated skill/handler in `/sources`.
- This is the intended near-term pattern for Hermes-inspired self-improvement:
  skills describe reusable procedure and trigger metadata, planners decide
  when the procedure should affect a subsystem, code-owned handlers/tools do
  bounded deterministic work, and learned changes remain review-first.

Self-code and static scan checkpoint, 2026-05-31:

- Added `motoko-codebase-maintainer`, a built-in codebase skill backed by the
  code-owned `builtin:motoko_codebase_query` handler. It uses deterministic
  Motoko source-code maps and code queries as bounded context for ordinary
  chat questions about Motoko's own implementation, commands, tests,
  refactors, and self-improvement.
- Added `motoko code-map`, `motoko code-query QUERY`, `/code-map`, and
  `/code-query QUERY` as no-model inspection surfaces over Motoko's own
  checkout.
- Added `motoko skill scan [NAME]` and `/skill scan [NAME]` as a conservative
  static scanner for learned skills and support scripts. It is report-first
  and does not grant approval or execution authority.
- Added `motoko self-eval` and `/self-eval`, a no-model readiness gate for
  the self-code and static-scan path. It verifies that code-map/code-query
  work, the self-code skill activates, built-in skills scan cleanly, and the
  scanner catches a synthetic risky script.
- Added `docs/motoko-self-improvement-playbook.md` as the durable operating
  checklist for Motoko self-improvement. The built-in self-code skill points
  long refactor or capability-building work at that checklist instead of
  stuffing every craft rule into prompt context.

Next long stretch after skill lifecycle:

- Improve curator usefulness without auto-application: improve
  umbrella/consolidation workflows and connect richer feedback/eval rows to
  higher-quality patch proposals. The stale-unused archive-review path is now
  implemented as review-first support-file guidance, so the next curator work
  should focus on better consolidation quality and feedback-derived patches.
- Use the structured proposal lane as the only enabled path for
  script-assisted project mutation. Raw script writes, network, arbitrary
  terminal, and service control remain future reviewed gates.
- Keep support-file consolidation inspectable while improving procedural
  memory quality.

## Goal Loops

Goal loops should remain staged. The enabled forms are now an explicit
action-list runner, an opt-in read-only model planner, and an opt-in
model-confirmed planner. Explicit action-list records contain concrete typed
actions and Motoko runs them through the normal validator, confirmation,
budget, and ledger path. Read-only model-planned records retrieve context,
call the audit route for strict JSON, store an inspectable checkpoint, and stop
at proposals. Model-confirmed records also stop at proposals, then require
`motoko goal apply RUN_ID --yes` before any mutation. Each confirmed run has a
`goal-run-v1` checkpoint so completed work or completed planning is not lost
across interruption. A fully autonomous mutating form should come only after
these review/apply runners stay stable. The durable record contains:

- objective;
- scope;
- allowed skills and tools;
- context sources;
- budgets for time, model calls, tool calls, and output;
- stop conditions;
- checkpoint ledger;
- final audit.

Future mutating autonomous loops should run explicit phases: plan, retrieve,
act through approved handlers/tools, observe, reflect/audit, persist artifacts
or feedback, and either continue or stop. Loops must be pauseable, resumable,
visible in job status, and conservative by default: explicit action lists
first, then read-only model-planned loops, then user-confirmed local mutations,
and only later broader automation after separate review.
