# Motoko Self-Improvement Playbook

Motoko may help improve her own repository, but she should do it as a careful
local engineering assistant, not as an unconstrained autonomous agent. This
playbook turns the current craft direction into reusable procedure.

## Operating Shape

- Read `AGENTS.md`, `docs/project-context.md`, and
  `docs/agentic-capability-design.md` before architectural, security-boundary,
  skill/tool, background-job, retrieval, memory, or TUI changes.
- Use `motoko code-map` for the repository overview and `motoko code-query
  QUERY` to find command handlers, symbols, tests, modules, and ownership
  boundaries before proposing code changes.
- Prefer existing `motoko_core` modules and narrow service boundaries over
  adding more root-facade orchestration.
- Keep the runtime stdlib-only, realm-local, inspectable, and explicit about
  provenance, schemas, migrations, and source reprocessing.
- Make one coherent change at a time, validate it, and commit it locally when
  appropriate. Do not push unless the user explicitly asks.

## Skill And Tool Craft

- Prefer improving an existing built-in handler or umbrella skill before
  creating a narrow duplicate skill.
- Built-in umbrella skills now carry the core self-improvement procedures:
  `motoko-codebase-maintainer` for deterministic code lookup,
  `motoko-retrieval-maintainer` for retrieval diagnosis,
  `motoko-refactor-craft` for careful service-boundary refactors, and
  `motoko-agentic-boundary-review` for skills/tools/actions/goal-loop safety.
- Use `motoko skill plan QUERY` to inspect skill selection and deterministic
  handler activation without a model call.
- Use `motoko skill curator` for library hygiene. Stale unused skills should
  get review notes first; archive only with `motoko skill archive NAME --yes`
  after the useful procedure has been preserved or judged obsolete.
- Use `motoko skill scan [NAME]` before trusting a new script-backed or
  externally imported skill.
- Treat scripts as inert support files unless they have approved metadata,
  current fingerprints, typed action records, validators, ledgers, and explicit
  confirmation.

## Retrieval And Memory Craft

- Diagnose answer failures with `/sources`, `motoko retrieval-debug QUERY`,
  `motoko retrieval-preview QUERY`, `motoko evidence-query QUERY`, and
  `motoko vector-query --rerank QUERY` before changing prompts or ranking.
- Classify retrieval failures precisely: recall, ranking, stale data, source
  lifecycle, chunking/span selection, prompt packing, or final synthesis.
- Keep lexical, structured Org/task/date evidence, evidence rows, embeddings,
  and rerank as a hybrid pipeline. Do not replace exact/structured truth with
  dense retrieval alone.
- Use `/feedback up|down|ok NOTE` after important answers. Feedback becomes
  private eval signal and reviewable suggestions, not direct mutation.

## Improvement Queue

These are durable self-improvement targets for Motoko to keep in view during
future repo work:

- Use `motoko code-query` before architectural, refactor, command, test, or
  self-improvement answers about Motoko.
- Strengthen `motoko-retrieval-maintainer` whenever a real retrieval failure
  reveals a reusable diagnosis or repair procedure.
- Strengthen `motoko-refactor-craft` whenever a refactor teaches a better
  service-boundary, validation, migration, or deployment-soak pattern.
- Strengthen `motoko-agentic-boundary-review` whenever a skill/tool/action
  issue reveals a reusable safety check.
- Prefer support files for examples, checklists, templates, or bounded script
  designs that would bloat a skill body.
- Keep `self-eval`, `action-eval`, retrieval evals, and focused regressions
  close to the behavior they are meant to protect.
- Review Hermes Agent and comparable local assistant systems periodically, but
  adapt only ideas that preserve Motoko's realm-local, stdlib-first,
  typed-action, review-first boundary.

## Prepared Self-Improvement Worklist

When Motoko is asked to improve her own repository, start from this worklist and
use `motoko code-query`, `/sources`, and the relevant umbrella skill before
proposing code changes:

1. Strengthen retrieval quality first. Add or improve fixtures whenever a real
   answer failure shows weak recall, stale artifacts, bad span selection,
   missing structured evidence, poor context packing, or final prompt misuse.
2. Improve `motoko-retrieval-maintainer` when a retrieval repair becomes a
   reusable procedure. Prefer a support file for examples and diagnostics over a
   long skill body.
3. Improve `motoko-refactor-craft` when a refactor reveals a better boundary
   pattern, migration rule, validation sequence, or deployment soak checklist.
4. Improve `motoko-agentic-boundary-review` when tools, scripts, project writes,
   goal loops, route scheduling, or approvals reveal a reusable safety check.
5. Keep extracting live subsystems only when the new module has clear
   ownership, focused tests, and less orchestration in the root facade. Good
   future candidates are command formatting, artifact lifecycle fanout,
   foreground cancellation, model-route scheduling diagnostics, and TUI status
   surfaces.
6. Make artifact lifecycle behavior coherent across every derived family:
   indexes, repairs, evidence rows, vector stores, dossiers, retrieval/debug
   reports, feedback evals, memories, and skill-support artifacts.
7. Treat user feedback as private eval seed material. Feedback should suggest
   tests, skill patches, support files, or retrieval fixtures; it must not
   silently rewrite retrieval policy or prompts.
8. Keep Hermes-inspired features narrow and inspectable: progressive disclosure,
   support files, skill curator reports, loaded-skill patch preference, and
   typed `skill_manage` suggestions are useful; broad terminal tools,
   cross-realm skill stores, hidden agents, and dependency-heavy runtimes are
   not part of Motoko's current shape.
9. For codebase self-improvement, build or update skills only when they encode a
   repeated, actionable procedure that would save tokens, reduce errors, improve
   reliability, or preserve project-specific craft. Prefer patching an existing
   umbrella skill before creating a narrow new skill.
10. Every self-improvement change should leave a gate behind: a regression test,
    `self-eval`, `action-eval`, retrieval/vector eval, or a documented manual
    soak check that would catch the same failure next time.

## Refactor Craft

- Characterize behavior with tests before moving live orchestration.
- Extract pure helpers first, then side-effecting boundaries with fakeable
  callbacks, then live TUI/job/model behavior.
- Preserve the stable `motoko` executable as the facade until the new boundary
  is demonstrably safer and simpler.
- For derived artifacts, every schema or pipeline change needs a deterministic
  migration path or visible resumable source reprocessing.
- Keep background work lane-aware, durable, interruptible, progress-visible,
  and parallel only up to the approved local route or workload limit.

## Soak Checklist

Before trusting a self-improvement change after deployment:

- ask a grounded document question and inspect `/sources`;
- run `motoko retrieval-preview QUERY` and `motoko retrieval-debug QUERY` for a
  representative failure-prone query;
- edit or delete an indexed source and confirm stale/source-lifecycle behavior;
- run `motoko vector-refresh` or `/bg-now` when catch-up is needed;
- record feedback and run `motoko feedback-eval`;
- test `/stop` during preparing/answering and `/pause` during heavy work;
- check `/status`, `/last-call`, `/models`, `motoko self-eval`, and
  `motoko skill scan` remain content-free outside user-owned state.
