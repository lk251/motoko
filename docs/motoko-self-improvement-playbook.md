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
- Include schema, artifact, migration, and version terms in code queries when
  the work touches derived state such as indexes, vectors, memories, skills,
  actions, cache manifests, or corpus lifecycle. `code-query` exposes
  module-level constants so compatibility boundaries can be checked as code
  facts.
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
   reports, feedback/action/model evals, memories, action/goal ledgers, and
   skill-support artifacts.
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

## Next Self-Improvement Brief

When today's work is deployed and Motoko is asked to reason about improving the
Motoko repo itself, treat this as the current prepared queue:

1. Start every self-code session by running or retrieving `motoko code-map` and
   a focused `motoko code-query QUERY`; do not let the model infer command
   handlers, tests, or module ownership from memory alone.
2. Use the existing self-improvement umbrella skills first:
   `motoko-codebase-maintainer`, `motoko-refactor-craft`,
   `motoko-retrieval-maintainer`, and `motoko-agentic-boundary-review`. Patch
   or add support files to these before creating narrow duplicate skills.
3. Improve code intelligence before broader agency. The first version of this
   upgrade now exists: `motoko code-map` reports command-to-handler-to-test
   traces, simple resolved call edges, root-facade hotspots, and
   `motoko_core` service-boundary maps; `motoko code-query QUERY` can retrieve
   those rows for focused self-improvement context. Future work should refine
   relationship precision and add new deterministic facts only when they help
   Motoko find the right code before proposing changes.
4. Finish artifact lifecycle ownership. Source lifecycle now plans and formats
   cleanup conservatively, but future work should keep moving artifact fanout,
   rebuild decisions, and family-specific cleanup into a tested lifecycle
   service instead of adding more root-facade special cases.
5. Add finer cancellation checkpoints for long foreground study, index, vector,
   and dossier operations. The job supervisor is in place; the remaining craft
   work is narrowing the long functions so `/stop` and pause feel immediate.
6. Improve curator quality in a Hermes-inspired but Motoko-shaped way:
   usage/patch metadata, loaded-skill patch preference, support-file
   organization, consolidation review notes, and feedback-derived patch
   proposals should remain review-first and content-safe by default.
7. Use goal loops as review tools before mutation tools. Prefer
   `model_readonly` loops for "inspect, retrieve, audit, propose" work over
   any broader autonomous act/observe loop. `model_confirmed` runs should still
   stop for explicit `goal apply`.
8. Build new skills only from repeated, proven procedures. A candidate skill
   should save tokens, reduce errors, improve reliability, or preserve
   Motoko-specific craft. If the knowledge is mostly examples, put it in
   `references/`; if it is a reusable bounded operation, design an inert
   `scripts/` support file and a separate reviewed tool contract.
9. Keep borrowing only the parts of Hermes Agent that fit Motoko: progressive
   disclosure, procedural skill memory, support files, curator reports, usage
   metadata, and review-first skill management. Do not copy broad terminal
   authority, cross-profile skill stores, hidden autonomous mutation, or
   dependency-heavy runtime machinery.
10. After any self-improvement change, run the relevant gate: focused
    regression tests for code behavior, `self-eval` for self-code readiness,
    `action-eval` for authority behavior, retrieval evals for context changes,
    and `nix flake check` before committing.

## Prepared Improvement Queue, 2026-05-31

Motoko is ready for practical self-code assistance, but she should approach her
own repo as an evidence-gathering assistant rather than as an unconstrained
agent. The next high-value improvements should be selected in this order unless
fresh evidence shows a better target:

1. Finish artifact lifecycle ownership. Continue moving derived-artifact
   scanning, family-specific rebuild decisions, and cleanup/apply orchestration
   into `motoko_core.artifact_lifecycle` with injected filesystem callbacks,
   tests, and conservative manual-review handling for human-authored state.
   Current progress: source-lifecycle artifact scanning, index dependency
   counting, JSON artifact deletion, and superseded index snapshot deletion
   reports now live in the lifecycle service.
2. Add finer cooperative cancellation checkpoints for long foreground study,
   index, vector, dossier, and report operations. The job supervisor exists;
   the remaining work is making the long functions yield durable stop/pause
   points without corrupting indexes, vectors, memories, or ledgers.
3. Improve code-intelligence precision. Extend `motoko code-map` and
   `motoko code-query` only with deterministic facts that help Motoko find the
   right implementation, test, schema, command handler, module boundary, or
   migration before proposing a change.
4. Keep skill learning review-first. Patch the existing umbrella skills before
   creating narrow new skills. Use support files for examples, debugging
   transcripts, validation checklists, and reusable design recipes that would
   make a skill body too large.
5. Build Hermes-inspired skill lifecycle craft without importing Hermes'
   broad authority. Useful ideas are usage counts, view/use/patch timestamps,
   pinned skills, recoverable archive states, curator reports, support-file
   organization, and consolidation suggestions. Motoko must keep code-level
   guards: bundled or built-in skills must not be silently mutated by a model,
   and curator output should remain review-first until explicitly accepted.
6. Convert user feedback into private eval seed material. `/feedback up`,
   `/feedback down`, and diagnostic notes should propose retrieval fixtures,
   skill patches, support files, or focused regressions; they should not
   silently rewrite ranking, prompts, skills, or files.
7. Use goal loops as inspectable review tools first. Prefer
   `model_readonly` or `model_confirmed` loops that retrieve, audit, and
   propose typed actions under budget, then stop for review. Do not widen into
   broad autonomous terminal/tool authority without a separate design review.
8. Preserve the root-facade shrink discipline. Extract a subsystem only when
   the target module gains clearer ownership, focused tests, and a smaller
   public API. Do not move code just to move code.

Candidate self-improvement skill work:

- Patch `motoko-refactor-craft` with lessons from each successful service
  extraction: characterization first, injected callbacks at side-effect
  boundaries, migration or reprocess path for derived artifacts, and soak
  checks after deployment.
- Patch `motoko-retrieval-maintainer` when a real answer failure teaches a new
  reusable diagnosis across recall, ranking, stale data, chunk/span selection,
  prompt packing, or final synthesis.
- Patch `motoko-agentic-boundary-review` whenever script tools, project writes,
  goal loops, worktrees, route scheduling, or approval flows reveal a reusable
  safety check.
- Keep `motoko-codebase-maintainer` focused on deterministic code lookup:
  command-to-handler-to-test traces, module/service ownership, schemas,
  migrations, and likely validation commands.

Hermes Agent remains useful inspiration, especially its progressive skill
disclosure, agent-managed procedural memory, curator usage metadata, pinned
skills, recoverable archives, and periodic skill hygiene. The relevant lesson
for Motoko is not "copy the tool runtime"; it is "make reusable procedure
durable, inspectable, and maintained." Current public Hermes discussions also
reinforce why Motoko needs code-level guards, not only prompt instructions:
curator or background-review agents must not be able to silently alter
protected skills, bundled skills, project files, or cross-realm state.

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
