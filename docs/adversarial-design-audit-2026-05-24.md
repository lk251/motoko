# Adversarial Design Audit - 2026-05-24

This audit reviews the Hermes-inspired agentic features Motoko has added:
procedural skills, support files, script-tool metadata, approvals, typed
actions, project writes, goal loops, action evals, and the surrounding
retrieval/artifact boundaries.

The purpose is preemptive fault finding. The standard is Motoko's guiding
values: increase intelligence and competence while preserving careful,
inspectable, security-conscious craftsmanship.

## Scope

Motoko source reviewed:

- `motoko`
- `motoko_core/agentic.py`
- `motoko_core/skills.py`
- `motoko_core/goal_loops.py`
- `motoko_core/artifact_lifecycle.py`
- `motoko_core/jobs.py`
- `motoko_core/model_manager.py`
- `motoko_core/retrieval_service.py`
- `tests/motoko_regression.py`
- `tests/motoko_eval.py`
- `tests/motoko_tty.py`

Hermes Agent source reviewed:

- `NousResearch/hermes-agent` at commit
  `186bf25cb11077b8c158dbfc1f768e48bc28b0db`.
- Key files:
  - `tools/skills_tool.py`
  - `tools/skill_manager_tool.py`
  - `tools/skills_guard.py`
  - `agent/curator.py`
  - `agent/tool_guardrails.py`
  - `agent/tool_executor.py`
  - `agent/skill_commands.py`
  - `AGENTS.md`

## Method

- Compared Motoko's accepted design in
  `docs/agentic-capability-design.md` against live behavior.
- Searched for authority-changing surfaces: `subprocess`, project writes,
  deletion, stale cleanup, shell/service-control mentions, path handling,
  session confirmations, symlink handling, and cross-realm paths.
- Compared Hermes' skill model and curator model to Motoko's narrower
  authority model.
- Added regressions for high-confidence issues found during the audit.
- Extended `motoko action-eval` so the eval surface includes the new
  safeguards, not just ordinary tests.

## Core Invariants

These invariants should remain true before Motoko becomes more agentic:

- Model output is planning data, not authority.
- Executable behavior goes through typed `motoko-action-v1` records.
- Script files are inert unless they have valid adjacent tool metadata and a
  current fingerprint approval.
- Persistent tool approval grants only the tool contract. It does not grant
  arbitrary arguments, broader paths, network, service control, sudo, shell, or
  project-file writes.
- Per-session confirmation is allowed only when the action type, skill, tool,
  effect set, confirmation policy, and argument scope do not broaden.
- Read/write paths stay within explicit allowlists, avoid `/home/personal`
  from `mares`, reject traversal, and respect `.motokoignore`.
- Project mutation stays code-owned through `project_file_write` until a later
  reviewed design explicitly changes that.
- Ledgers and admin-visible route telemetry remain content-safe. Private tool
  inputs, outputs, prompts, filenames, summaries, and retrieved context stay in
  the current user's Motoko state.
- Long-running work must be visible, checkpointed, pauseable/recoverable, and
  migration-aware when artifact schemas change.

## Fixed Findings

### 1. Relative tool path arguments bypassed allowlist checks

Severity: high.

`action_path_checker` only checked absolute paths. A script tool with a
`read_allowed_files` or `write_allowed_project` path-like argument could pass a
relative path through validation without resolving it against the current
working directory and the Motoko allowlist.

Fix:

- Relative action path arguments are now resolved against `Path.cwd()` before
  validation.
- Read paths go through `require_allowed`.
- Write paths go through `require_project_write_allowed`.
- Regression added:
  `test_skill_tool_relative_path_arguments_require_allowed_cwd`.

### 2. Session-repeat confirmation was not argument-scoped

Severity: high.

`session_approval_key()` included action kind, skill, tool, effects, network,
and project-write flags, but not action arguments. A same-session confirmation
for one approved tool invocation could therefore apply to a second invocation
of the same tool with different arguments. That violated the accepted rule that
repetition is allowed only when scope does not broaden.

Fix:

- `session_approval_key()` now includes a stable hash of the action arguments.
- Regression added:
  `test_skill_tool_session_confirmation_is_argument_scoped`.
- `motoko action-eval` fixture added:
  `session_confirmation_scopes_arguments`.

### 3. Script-tool read paths did not enforce `.motokoignore`

Severity: medium-high.

Project writes already respected `.motokoignore`, and corpus selection did too,
but read-oriented skill-tool path validation only checked the allowlist. That
made it possible to pass an ignored archival file path to an approved read
tool, despite the design saying skill tools must respect `.motokoignore` for
document/corpus operations.

Fix:

- Read paths now resolve the allowed root, parse `.motokoignore`, and reject
  ignored file or directory paths before execution.
- Regression added:
  `test_skill_tool_read_paths_respect_motokoignore`.
- `motoko action-eval` fixture added:
  `motokoignore_skill_read_denied`.

### 4. New agentic regressions must be registered in the custom runner

Severity: process-low.

`tests/motoko_regression.py` uses an explicit test list. New tests can exist in
the file but not run unless added to that list. The new agentic path tests are
now registered in the list.

Fix:

- Registered the relative-path, `.motokoignore` read, and session-scope tests.
- Full regression count increased accordingly.

## Confirmed Strong Points

Motoko is already stricter than Hermes in the places that matter for this
repo's security boundary:

- Hermes skills may refer to broad native tools such as terminal/code
  execution. Motoko skill scripts require adjacent JSON contracts,
  fingerprint approval, typed action records, and a narrow stdlib Python
  runner.
- Hermes has a powerful `skill_manage` tool and curator. Motoko borrows the
  procedural-memory shape but keeps mutation review-first and schema-bound.
- Hermes has trust-level scanning for hub/community skills. Motoko currently
  avoids a broad external skill marketplace and treats scripts as inert until
  approved.
- Hermes curator can archive and consolidate agent-created skills. Motoko has
  started the safer version: prompted suggestions, support files, and typed
  skill-management actions without hidden broad execution.
- Motoko's code-owned `project_file_write` has the right shape: allowlist,
  `.motokoignore`, VCS/cache denial, symlink denial, expected hash on
  overwrite, atomic write, exact confirmation, and content-safe ledger.
- Model route control stays behind `motoko-model`; Motoko does not call
  `systemctl` or mutate live system services directly.

## Remaining Risks

These are not regressions in the current feature set, but they are the places
most likely to produce future errors if Motoko becomes more agentic.

### A. Script tools are policy-confined, not OS-confined

Current script tools run as the current user with a scrubbed environment and
fixed working directory, but there is no OS-level sandbox preventing a malicious
approved script from opening arbitrary user-readable paths by ignoring its
arguments. The current safety model is therefore: only approve scripts whose
source and metadata are trusted.

Before external/community scripts, network tools, or broad terminal-like tools:

- Add a static skill/script scanner inspired by Hermes' `skills_guard.py`.
- Prefer a NixOS-owned sandbox wrapper or helper user.
- Keep no ambient secrets in the runner environment.
- Keep network disabled by default.

### B. Foreground script cancellation needs a real kill path

The runner enforces timeouts, but `/stop` should eventually interrupt active
foreground script work and mark the ledger as interrupted. This is most
important before longer-running script tools or goal loops depend on scripts.

Recommended next work:

- Add an interrupt signal into the action runner.
- Terminate the subprocess on stop.
- Persist an `interrupted` ledger/result state.
- Add action-eval coverage for interrupted tool work.

### C. Skill lifecycle is safer than Hermes but less mature

Hermes has usage telemetry, curator state, archives, pinned skills, structured
curator reports, and consolidation/pruning distinction. Motoko has review-first
suggestions and support files, but not a full curator.

Recommended Motoko-shaped path:

- Track usage/selection/patch counts for learned skills.
- Add pin/archive/restore before any automatic cleanup.
- Keep automatic curator passes report-first until trust is earned.
- Prefer umbrella skill consolidation and support files over many narrow
  session-specific skills.

### D. Goal loops are durable but not yet autonomous

The explicit action-list runner is a good foundation. Autonomous model-planned
loops are not enabled, by design.

Before enabling them:

- Start with read-only plan/retrieve/inspect/audit loops.
- Require budgets, stop conditions, allowed skills/tools, and visible
  checkpoints.
- Require final audit and user review before mutation.
- Only then consider user-confirmed mutating loops.

### E. Artifact lifecycle remains incomplete across all derived families

Index cleanup and source lifecycle decisions exist, but a single lifecycle
service does not yet apply cleanup/rebuild across vectors, evidence stores,
topic dossiers, memory dossiers, feedback fixtures, profile dossiers, and
conversation-derived artifacts.

Recommended next work:

- Make source lifecycle events fan out to all dependent artifact families.
- Keep cleanup conservative: stale first, delete only after replacement or
  explicit review.
- Add evals for edited, deleted, ignored, and reprocessed source files.

### F. Root orchestration remains large

The root `motoko` script still owns live orchestration for retrieval, TUI,
index jobs, foreground jobs, and action dispatch. The refactor plan remains
valid: keep extracting live subsystem ownership without weakening cancellation,
progress, or privacy.

Recommended next work:

- Continue extracting retrieval context/source construction.
- Continue extracting action/job lifecycle surfaces.
- Keep the root facade as a coordinator, not the owner of every invariant.

## Hermes Lessons to Keep

Valuable ideas to adapt:

- Progressive disclosure for skills: list metadata first, load full
  instructions/support files only when needed.
- Skills as procedural memory: save reusable craft knowledge, not isolated
  chat anecdotes.
- Support files for references/templates/scripts so procedures are not bloated
  into one prompt.
- Curator-style review: periodic or signal-triggered review that prefers
  patching/consolidating existing umbrella skills before creating new ones.
- Usage telemetry and pin/archive/restore instead of irreversible deletion.
- Tool-call loop guardrails: detect repeated failures and no-progress loops.

Ideas not to copy directly:

- Broad terminal/code-execution authority as the default execution substrate.
- Hidden autonomous mutation.
- Cross-profile or shared skill stores that blur realm boundaries.
- Trust in prose instructions as executable authority.
- Persistent or admin-visible logs containing private corpus/tool content.

## Immediate Backlog

1. Add action interruption for active script tools and durable interrupted
   ledger states.
2. Add a Motoko-shaped skill usage/lifecycle layer: usage counts, pinned,
   archived, restored, and report-first curator suggestions.
3. Add script-assisted project mutation through structured proposals, not raw
   script writes.

The first four items are now implemented. Script-assisted mutation is enabled
only as `propose_project_changes` plus typed `project_file_write` proposals;
Motoko still owns validation, confirmation, atomic writes, and ledgers.
Read-only model-planned goal loops are enabled as explicit
`planner: model_readonly` records that retrieve, plan, audit, and propose
without mutating files.
User-confirmed model-planned goal loops are now enabled as explicit
`planner: model_confirmed` records that retrieve and propose typed actions,
then stop for `motoko goal apply RUN_ID --yes`. Managed Git worktree
create/commit/fast-forward-merge/remove actions are typed and confirmed; they
do not grant arbitrary shell authority.

Remaining:

1. Extend artifact lifecycle application across vectors, evidence, dossiers,
   memories, feedback, profiles, and conversation-derived artifacts.
2. Add static script/skill scanning before any external skill import path.

## Validation Added By This Audit

- `test_skill_tool_relative_path_arguments_require_allowed_cwd`
- `test_skill_tool_read_paths_respect_motokoignore`
- `test_skill_tool_session_confirmation_is_argument_scoped`
- `motoko action-eval` fixture `motokoignore_skill_read_denied`
- `motoko action-eval` fixture `session_confirmation_scopes_arguments`
