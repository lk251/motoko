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
  boundaries before proposing code changes. For refactors, include
  root-facade or hotspot terms so `code-query` returns the largest live
  orchestration targets instead of relying on memory of the root file.
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
   cleanup conservatively, and replacement-readiness plus storage-audit source
   lifecycle rows are now service-owned. Future work should keep moving artifact
   fanout, rebuild decisions, and family-specific cleanup into tested lifecycle
   services instead of adding more root-facade special cases.
5. Add finer cancellation checkpoints for long foreground study, index, vector,
   dossier, and profile operations. The job supervisor is in place, and
   `/profile-refresh` now forwards foreground cancellation. Topic dossier
   pre-model chunk ranking is also cancellable before the first model call; the
   remaining craft work is narrowing the long functions so `/stop` and pause
   feel immediate.
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
   counting, JSON artifact deletion, superseded index snapshot deletion
   reports, index cleanup formatting, source lifecycle classification, and
   stale superseded-index candidate selection now live in the lifecycle
   service. Conversation deletion now also gets its JSON-dir, JSONL-ledger, and
   single-JSON-file cleanup families from the lifecycle service instead of
   hard-coding those policies only in the root facade. Index-storage audit
   source-lifecycle storage-plan rows are now collected by the lifecycle
   service across indexes instead of a root-facade loop.
2. Add finer cooperative cancellation checkpoints for long foreground study,
   index, vector, dossier, and report operations. The job supervisor exists;
   the remaining work is making the long functions yield durable stop/pause
   points without corrupting indexes, vectors, memories, or ledgers.
   Current progress: active chat answers, queued prompts, foreground
   index/vector/study paths, evidence build/refresh, index cleanup,
   source-lifecycle reports, and `bg-now` now pass cancel events through their
   CLI or slash-command paths. Lifecycle apply/report helpers now also accept
   injected cancellation checkpoints before materialization or deletion. Index
   artifact enrich/upgrade, quality repair, profile refresh, and model-backed
   memory maintenance now carry cancellation through CLI/background/model-call
   paths. Queued memory proposals remain retryable when interrupted.
   Retrieval/vector/evidence report queries now also receive cancel events
   through TUI and CLI paths, including `/retrieval-debug`,
   `/retrieval-preview`, `/vector-query`, `/evidence-query`, prompt context
   preparation, span embedding/rerank selection, and retrieval-service hybrid
   report construction. `index-storage` audits now also run inside a
   foreground cancel scope and check cancellation during index, partial,
   duplicate-reference, orphan-chunk, and source-lifecycle scans. Continue this
   work by adding checkpoints inside any remaining long report or non-index
   context lane operation that still lacks cooperative cancellation. Memory
   dossier ranking, recent-conversation recall ranking, prompt-time
   memory/conversation recall, and profile source-material scans now also
   receive and honor foreground cancellation before model work starts.
   Deterministic Motoko codebase context (`code-map` / `code-query`) and
   model-planned goal-loop retrieval now also carry the same cancel signal, so
   self-improvement scans can stop cleanly before expensive planning continues.
   Superseded index cleanup and source-lifecycle apply now also pass the
   cancellation token into index snapshot deletion itself; the lifecycle
   service checks inside the index/progress/partial, chunk-directory,
   derived-JSON, and single-file artifact deletion loops.
3. Improve code-intelligence precision. Extend `motoko code-map` and
   `motoko code-query` only with deterministic facts that help Motoko find the
   right implementation, test, schema, command handler, module boundary, or
   migration before proposing a change. Current progress: code intelligence
   now exposes cooperative cancellation paths, so self-improvement work can
   query which functions use foreground cancel scopes, pause checks, or
   `raise_if_work_cancelled` before editing long-running index, vector,
   dossier, memory, or report operations.
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

## Next Motoko Self-Code Session

When Motoko is next asked to improve her own repository, she should start with
this operational list:

1. Run `motoko code-map` and a focused `motoko code-query QUERY` before
   answering or editing. For architecture work, include terms for the command,
   schema, artifact family, service module, and tests.
2. Activate existing umbrella skills first:
   `motoko-codebase-maintainer`, `motoko-refactor-craft`,
   `motoko-retrieval-maintainer`, or `motoko-agentic-boundary-review`. Patch
   those skills or add support files when the procedure generalizes.
3. Check `motoko skill curator` and `motoko skill scan` before trusting new
   skill/script material. Prefer support-file notes, consolidation proposals,
   or pending `skill_manage` suggestions over immediate autonomous mutation.
4. Treat feedback and real failures as eval seeds. A good improvement leaves a
   regression, retrieval fixture, `self-eval`, `action-eval`, or documented
   soak check that would catch the same class of problem later.
5. Favor the current highest-value craftsmanship targets: artifact lifecycle
   fanout, cancellation/job supervision, code-query precision, skill curator
   quality, feedback-to-eval flow, and goal-loop review behavior.
6. Keep the authority boundary explicit. Model reasoning may propose; Motoko
   code validates, records provenance, asks for confirmation when required,
   and applies changes only through typed actions.

## Motoko Repo Improvement Backlog

Use this backlog when Motoko is asked to improve herself after a normal period
of usage. It is ordered by likely value to intelligence, competence, and craft:

1. Finish artifact lifecycle ownership. Keep moving stale-source detection,
   rebuild decisions, vector/evidence/dossier invalidation, and conservative
   cleanup into `motoko_core.artifact_lifecycle` instead of adding more
   root-facade branches.
2. Finish cooperative cancellation and durable interruption. Model-backed
   memory maintenance now cooperatively cancels and leaves queued proposals
   retryable. Retrieval/debug/vector/evidence report queries now carry cancel
   events through the service/model-call path, and `index-storage` audits now
   accept the same foreground cancel token while scanning stored indexes and
   derived artifacts. The next target is any remaining topic, memory-dossier,
   profile/report, or non-index context operation that can still block `/stop`,
   `/pause`, or clean shutdown.
3. Improve always-fresh context behavior. When background refresh finishes while
   a TUI session is open, the session should notice fresh indexes, evidence
   stores, vectors, memories, and dossiers without needing a restart.
4. Improve incremental vector and evidence refresh diagnostics. Status should
   say whether a refresh is full, resumed, schema-forced, route-forced, or
   source-change-only, with concise rows/ETA/progress rather than opaque
   `vectorizing`.
5. Tighten conversation persistence. Queued prompts, resumed empty chats,
   feedback targeting, and deleted-chat artifact cleanup should have focused
   regression coverage because they directly affect trust in daily use.
6. Strengthen code intelligence only with deterministic facts that help
   Motoko edit the right code: command-to-handler-to-test traces, schema
   constants, artifact-family ownership, route/cancellation call paths, and
   root-facade hotspots.
7. Convert feedback into eval seeds. Positive and negative feedback should
   propose private retrieval fixtures, prompt-packing fixtures, skill patches,
   or regression tests; it must not silently mutate prompts, ranking, or skills.
8. Improve Hermes-inspired skill lifecycle craft without importing broad
   Hermes authority. Useful pieces are progressive disclosure, usage/view/patch
   counts, pinned skills, recoverable archives, curator reports, support-file
   organization, and "patch existing skill before creating a new one".
9. Add a narrow Motoko self-maintenance skill bundle only if skill selection
   gets noisy in practice. A bundle could load codebase, refactor, retrieval,
   and agentic-boundary procedures together for Motoko repo work, but it should
   stay opt-in so normal chats do not pay extra prompt cost.
10. Use goal loops as review loops first. Good early loops inspect code,
    retrieve context, run diagnostics, propose typed actions, and stop for
    review. Mutating autonomous loops remain out of scope until the review loop
    is boringly reliable.

Current progress on this backlog:

- Always-fresh context behavior now refreshes attached index references at
  prompt/retrieval time and after background study completion. Attached index
  records now also carry the corpus glob, can recover to the latest same
  root/name/glob index if an old snapshot was cleaned up, and refresh stored
  index/topic/dossier summaries from current artifact files before prompt
  construction. Prompt-time catalog text is now rebuilt from current
  user-owned state instead of trusting an older persisted catalog file, and
  current evidence/vector store ids, row counts, freshness, and vector refresh
  metadata are surfaced alongside each index. Catalog memory/profile summaries
  also expose current latest-memory and profile source-count metadata so
  prompt-time private context inventory reflects newly materialized memory and
  profile state without a restart. Prompt-context lane ordering and source
  bookkeeping now live in `motoko_core.retrieval_service` too, so chat,
  previews, and `/sources` keep using one tested context-package shape while
  root owns live retrieval and state reads. `/status` now also builds its
  context-catalog line from current state instead of trusting an older
  persisted catalog file. Current-directory corpus learning now attaches the
  newly built index, saves the conversation, and refreshes the catalog from the
  TUI event handler when the job completes. `/sources` fallback for attached
  index context now reports current evidence/vector artifact ids, row counts,
  freshness, and vector refresh labels from live state. It also resyncs
  attached index records before rendering when no answer sources have been
  recorded yet, so a newly materialized same-family index can appear in source
  inspection without needing a chat prompt path or TUI restart. The next
  improvement is checking any remaining TUI-only cached surfaces after real
  usage exposes them.
- Vector refresh diagnostics now expose content-free mode/cause labels such as
  `full missing`, `resumed checkpoint`, `incremental source-change`, and
  `rebuild schema`, plus reuse/new row counts, durable elapsed time, and ETA.
  Resumed vector refreshes measure visible elapsed time from the original
  vector-progress checkpoint instead of resetting to the current TUI session.
  Evidence refresh reports now expose the same style of mode/cause diagnostics
  for missing, forced, schema, stale, and source-change rebuilds.
- Artifact lifecycle policy has moved another step into
  `motoko_core.artifact_lifecycle`: delete-derived families, manual-review
  families, single-file durable state families, and derived delete-report labels
  now live in one service-owned declaration. Source lifecycle cleanup now
  distinguishes deleted/ignored detached sources from changed sources that have
  already been reprocessed into a fresh replacement index, so old derived
  artifacts can be cleaned after reprocessing instead of staying permanently
  blocked. Index-storage audit cleanup sections for safe candidates vs
  blocked/repair-first work are now built by the lifecycle service too.
  Conversation deletion cleanup has also moved another step into the lifecycle
  service: the service now owns the derived-family fanout, single-state-file
  actions, slot-cache counters, report shape, and path-key spec normalization,
  while root code still resolves realm-local paths and performs filesystem
  mutation through explicit callbacks. Context-catalog invalidation for deleted
  index snapshots is now also declared by the lifecycle service as a
  derived single-file artifact, so cache cleanup follows the same service-owned
  policy path as vectors, evidence, progress, and other derived state.
- Source-lifecycle report orchestration has moved another step inward. The
  lifecycle service now sequences summary collection, affected-source path
  derivation, replacement readiness, artifact-record lookup, cancellation
  checkpoints, and final report/apply delegation through injected callbacks.
  The root facade supplies current-state and filesystem authority, but no longer
  owns the report-input fanout itself. Index-storage audit source-lifecycle rows
  now use the same service-owned orchestration path, including multi-index
  collection and cancellation checkpoints, instead of rebuilding a parallel
  plan loop in the root facade.
- Index-storage audit ownership has moved another pure slice inward:
  `motoko_core.index_storage` now owns duplicate-reference target analysis and
  final audit dictionary assembly. It now also owns the full storage-audit
  orchestration across complete indexes, partial indexes, duplicate-reference
  checks, orphan chunk-file discovery, cleanup section construction, and final
  report assembly. The root facade still owns realm-local state discovery,
  filesystem path resolution, source lifecycle callbacks, and cleanup
  materialization authority.
- Index-storage scan-row semantics have also moved into
  `motoko_core.index_storage`: inline chunks, stored chunk paths, duplicate
  references, missing content, digest accounting, and warning rows are now
  service-owned with injected path/size callbacks. The root facade still
  supplies realm-local path resolution, filesystem reads, and cancellation
  checkpoints.
- Orphan chunk-file detection for index-storage audits is now service-owned as
  well, with the root facade only supplying the allowed chunk directories,
  path-size callback, and cancellation hook.
- Index-storage row orchestration across complete indexes and partial indexes
  now lives in the same service too: latest-family flags, resumable/superseded
  partial flags, shared digest maps, duplicate-reference rows, and referenced
  path sets are built under one tested helper.
- Duplicate-reference target reporting now carries its own cancellation
  checkpoints inside `motoko_core.index_storage`, so root no longer wraps that
  service-owned report with a separate loop.
- `motoko-refactor-craft` now records the service-loop extraction lesson from
  this pass: once a service owns a per-record decision, the collection loop
  should usually move there too, while root keeps realm-local state and
  filesystem authority behind callbacks.
- Skill curator review can now use saved private `feedback-eval` fixtures, not
  only raw response-feedback rows. Matching fixtures create review-first,
  content-safe support-file suggestions for existing learned skills, hiding raw
  query/note/source text until the user explicitly inspects the private eval
  artifact. Pure curator candidate construction now lives in
  `motoko_core.skill_curator`, and the curator report itself is now formatted
  by that same service. The root facade keeps realm-local state access and
  suggestion writes. `motoko self-eval` now checks that the code-query path can
  find this curator/eval implementation and its regression coverage.
- Worker model-eval fixtures now live in `motoko_core.evals` with the worker
  eval prompt/scoring helpers. Live route selection, model calls, and private
  report persistence remain at the root facade edge.
- Vector planning row math and readiness-gate shaping now live in
  `motoko_core.vector_store`. The root facade still supplies current indexes,
  memories, conversations, routes, eval reports, and realm-local store paths.
- Vector query row scoring and same-chunk deduplication now live in
  `motoko_core.vector_store`. The root facade still owns query embedding,
  reranker model calls, freshness checks, and cancellation wording.
- Embedding vector row construction and reusable-row validation now live in
  `motoko_core.vector_store`, so checkpoint and previous-store reuse share the
  same evidence/provenance rules. The root facade still owns batching,
  progress, route calls, and atomic persistence.
- Embedding vector progress identity, compatibility checks, and progress-record
  assembly now live in `motoko_core.vector_store`. The root facade still owns
  progress-file paths, elapsed/ETA callbacks, pause/resume writes, and model
  batch orchestration, but the schema/route/source/input rules and checkpoint
  dictionary shape are now pure and regression-tested.
- Embedding vector store record assembly now also lives in
  `motoko_core.vector_store`. The root facade still owns model route calls,
  progress callbacks, atomic persistence, and cancellation, but the final
  vector-store provenance/reuse/source/route dictionary shape is pure and
  regression-tested.
- Embedding vector refresh batching, pending-batch selection, reusable-row
  collection, vector-dimension inference, and refresh-mode labeling now live in
  `motoko_core.vector_store`. The root facade still owns reading source text,
  calling the embedding route, and deciding when to checkpoint or pause.
- Embedding vector checkpoint row parsing and previous-store row indexing now
  live in `motoko_core.vector_store`, keeping resume filtering and reusable-row
  lookup rules together with the rest of the vector checkpoint contract.
- Embedding vector route identity normalization and input-candidate collection
  now live in `motoko_core.vector_store` too. The root facade still owns source
  text reads, model route calls, progress persistence, and cancellation
  wording, but the pure route/candidate contract is tested outside the live
  orchestration path.
- Embedding vector checkpoint/previous-store reuse accounting now also lives in
  `motoko_core.vector_store`, including checkpoint precedence, reused-row
  counts, superseded-row counts, initial completed rows, pending rows, and
  dimension inference.
- Embedding vector progress-line formatting is now core-owned too, so
  content-free refresh mode, reuse/new row counts, elapsed time, ETA, and
  finalizing status are tested with the vector refresh contract rather than
  hidden in the root facade.
- Embedding vector elapsed/ETA calculations now live with the vector refresh
  contract as pure helpers. Elapsed time can use a durable checkpoint timestamp
  while ETA remains based on rows completed in the current session.
- Embedding vector completed-row materialization now preserves candidate order
  through a core helper used by both progress checkpoints and final stores.
- Conversation persistence trust has focused coverage for empty-chat pruning,
  queued prompt durability/history seeding, report-output non-persistence,
  rename/delete helpers, and owned derived-artifact cleanup. Deleted
  conversations now fan out through newer derived artifact families such as
  vector stores, evidence stores, vector progress, retrieval debug/eval
  reports, feedback evals, action evals, model evals, skill suggestions, and
  conversation-specific slot/KV cache records. The JSON directory families for
  conversation deletion are now declared by the artifact-lifecycle service
  instead of being scattered as root-facade one-offs; conversation-linked JSONL
  ledgers such as feedback, action ledgers, memory proposals, and study jobs
  have the same service-owned declaration. Goal loops and goal runs that
  structurally reference a deleted conversation are cleaned too, while
  unrelated goals and ledgers are preserved. Conversation-linked single-file
  state cleanup for skill suggestions, profile state, maintenance state, study
  state, and the context catalog is also declared by the lifecycle service,
  with the root facade only resolving realm-local paths and performing the
  guarded user-state mutation. Memory-row cleanup for deleted conversations now
  uses a memory-core helper for normalization and conversation-reference
  filtering, leaving root to only read and rewrite the realm-local memory file.
  Profile source-material assembly now also lives in `motoko_core.profile`:
  the service selects useful conversation recall rows, formats bounded private
  source blocks, returns source ids, and honors injected cancellation while
  root only loads user-owned state and calls the profile model route. Project
  scope matching for profile dossiers is service-owned too; root supplies
  conversation-root lookup and the project-root comparison callback. Memory
  dossier source-material assembly now lives in `motoko_core.dossiers` as
  well: the service formats bounded profile, memory, and conversation source
  blocks, returns normalized source rows, and honors injected cancellation
  while root owns ranking, model calls, and realm-local persistence.
  Feedback targeting now pairs the rated
  assistant answer with the nearest prior user prompt, so `/up` or `/down`
  used while a newer prompt is preparing does not attach the wrong query to
  the private feedback fixture.

Skill work that should usually happen before new code:

- Patch `motoko-codebase-maintainer` when code-map/code-query learns a better
  way to find ownership, tests, schemas, migrations, or command handlers.
- Patch `motoko-refactor-craft` after each successful service extraction with
  the reusable recipe, risk, validation gate, and deployment soak note.
- Patch `motoko-retrieval-maintainer` after each real retrieval failure with
  the reusable diagnosis and fixture shape.
- Patch `motoko-agentic-boundary-review` after each action/tool/goal-loop
  issue with the exact authority check that would have caught it earlier.
- Create a new skill only when the procedure is repeated, actionable, and not a
  cleaner patch to one of the umbrella skills. If the durable value is examples
  or transcripts, add a support file instead of bloating `SKILL.md`.

Hermes Agent remains most useful here as a design reference for procedural
memory rather than as an authority model. Keep the parts that fit Motoko:
progressive skill loading, agent-managed skill suggestions, skill usage
metadata, curator hygiene, and recoverable archives. Keep rejecting the parts
that do not fit Motoko: broad terminal authority, cross-realm skill stores,
hidden mutation, dependency-heavy runtime assumptions, and prompt-only security.

## Bird's-Eye State, 2026-05-31

Motoko is past the fragile prototype stage. The core shape now exists:
realm-local model routes, hybrid lexical/structured/evidence/vector retrieval,
reranking, source citations, feedback records, action/goal ledgers, review-first
skills, self-code lookup, artifact lifecycle reports, resumable background work,
and a TTY-first interface. The work is not finished, but the remaining roadmap
is mostly about making the existing architecture boringly reliable and easier
for Motoko herself to inspect before editing.

The most important unfinished implementation tracks are:

1. Artifact lifecycle ownership: keep moving stale-source detection,
   rebuild/upgrade decisions, derived-family cleanup, and source reprocessing
   into service-owned code with injected filesystem callbacks.
2. Cooperative cancellation and durable interruption: finish checkpoints in any
   long topic, dossier, profile, report, memory, vector, evidence, or indexing
   path that can still make `/stop`, `/pause`, or shutdown feel delayed.
3. Always-fresh context: finish remaining cached-memory/profile surfaces so
   open sessions notice new artifacts without restart.
4. Conversation persistence trust: cover queued prompts, resumed empty chats,
   feedback targeting, rename/delete cleanup, and deleted-chat artifact cleanup
   with focused regressions.
5. Skill lifecycle craft: make learned skills useful through support files,
   curator reports, usage metadata, pinned/recoverable states, and patch-first
   suggestions, while keeping unknown scripts inert until reviewed.
6. Goal loops as review loops: use loops to retrieve, inspect, audit, and
   propose typed actions before considering broader autonomous mutation.

Prepared improvement list for Motoko's own code work:

- Build a self-code session by first querying code facts, not by guessing:
  `motoko code-map`, then `motoko code-query` for command handlers, tests,
  schemas, migration constants, artifact families, and service boundaries.
- Use or patch the umbrella skills before creating narrow skills:
  `motoko-codebase-maintainer`, `motoko-refactor-craft`,
  `motoko-retrieval-maintainer`, and `motoko-agentic-boundary-review`.
- Turn repeated successful repairs into durable procedure: if a change saves
  tokens, reduces errors, improves reliability, or preserves Motoko-specific
  craft, add a skill support file or a review-first curator suggestion.
- For retrieval failures, classify the fault first: recall, ranking, stale
  source, chunk/span selection, prompt packing, final synthesis, or lifecycle
  freshness. Then add a fixture or diagnostic that catches that class again.
- For refactors, use the Swiss-watch recipe: characterize current behavior,
  extract pure helpers, introduce a narrow service boundary, inject side
  effects, preserve migrations/reprocess paths, validate, and commit.
- For skills/tools/actions, keep Hermes-inspired procedural memory but not
  Hermes-style broad authority. Scripts stay inert until scanned, approved, and
  bound to typed action records with validators and ledgers.
- Treat `/feedback` as private eval seed material. A good feedback-driven
  improvement proposes a test, retrieval fixture, support file, or prompt
  packing check; it does not silently mutate policy.
- Leave a gate behind every improvement: a focused regression, `self-eval`,
  `action-eval`, retrieval/vector eval, or a documented manual soak check.

Self-improvement skill targets:

- Maintain the four umbrella built-in skills first. `motoko-codebase-maintainer`
  owns deterministic code lookup; `motoko-refactor-craft` owns service-boundary
  extraction; `motoko-retrieval-maintainer` owns retrieval and context failures;
  `motoko-agentic-boundary-review` owns actions, scripts, tools, and goal-loop
  safety.
- Build or patch a support file for a skill when a repeated repair produces a
  reusable recipe, fixture shape, command trace, ownership map, or audit
  checklist. Prefer support files over long `SKILL.md` bodies.
- Consider a narrow `motoko-self-maintenance` bundle only after real use shows
  that loading the four umbrella skills separately is noisy or easy to miss.
  The bundle should compose existing procedures; it should not grant new
  authority.
- Future skill candidates should come from repeated evidence, not speculation:
  an Org-mode structure/query maintainer, an artifact-lifecycle caretaker, a
  background-job supervisor, a conversation-persistence auditor, and a
  code-query precision auditor are attractive only when real failures show the
  umbrella skills need more specialized support.
- Keep the Hermes lesson narrow: prompted self-review, progressive disclosure,
  support files, usage metadata, curator hygiene, patch-before-create behavior,
  and recoverable archives are good fits. Broad host tools, hidden mutation,
  cross-realm stores, and prompt-only security are not.

## Bird's-Eye Update, 2026-06-01

The current architecture is usable and coherent enough for daily work. The
major systems are in place: document indexes, hierarchical evidence,
embedding/rerank hybrid retrieval, source citations, background repair/vector
jobs, realm-local model routes, conversation recall, feedback records,
review-first skills, typed actions, goal ledgers, worktree actions, code-query,
self-eval, and action-eval. The recent durability fix for parallel atomic
writes plus the vector-store helper extractions are examples of the current
preferred craft pattern: diagnose a real failure, move reusable logic into a
focused service module, add regressions, update the playbook, validate, and
commit.

What remains is not one missing feature that blocks Motoko from being useful.
It is a reliability and self-understanding stretch:

1. Finish artifact lifecycle ownership so stale-source detection, rebuild
   decisions, cleanup, and source reprocessing are declared in service-owned
   code across indexes, evidence, vectors, dossiers, conversations, feedback,
   goals, memory artifacts, and skill-support artifacts.
2. Finish cooperative cancellation and interruption by finding any remaining
   long-running report, topic, dossier, profile, memory, vector, evidence, or
   indexing path that still cannot stop at a durable checkpoint.
3. Keep always-fresh context boringly reliable so an open TUI session notices
   newly finished indexes, evidence stores, vector stores, memory proposals,
   profiles, dossiers, and catalog updates without requiring a restart.
4. Continue shrinking the root facade only where ownership becomes clearer:
   vector query scoring/deduplication, model-route scheduling diagnostics,
   foreground job state, command/report formatting, and artifact lifecycle
   fanout are good candidates.
5. Improve code-query precision with deterministic facts that help Motoko find
   the right code before editing: command traces, tests, schema constants,
   validation gates, artifact-family owners, cancellation paths,
   route/model call paths, and root hotspots.
6. Strengthen conversation persistence trust with focused regressions for
   queued prompts, resumed empty chats, feedback targeting, rename/delete
   cleanup, and derived artifact cleanup.
7. Convert feedback into eval seed material. Positive and negative feedback
   should propose private fixtures, support files, skill patches, or focused
   regressions; it should not silently mutate prompts, ranking, or skills.
8. Mature Hermes-inspired skill lifecycle craft without importing Hermes'
   broader authority: usage/view/patch metadata, pinned skills, recoverable
   archives, curator reports, support-file organization, and patch-before-create
   behavior.
9. Use goal loops as review loops first. The valuable near-term loop is
   inspect, retrieve, audit, and propose typed actions under budget, then stop
   for review. Broader autonomous mutation remains out of scope until that path
   is uneventful in real use.

Prepared skill-building direction for Motoko:

- Patch `motoko-codebase-maintainer` when code-query learns a better way to
  expose implementation ownership, tests, schemas, migrations, route paths, or
  cancellation paths.
- Patch `motoko-refactor-craft` after each successful extraction with the
  reusable recipe, risk, validation gate, and deployment soak note.
- Patch `motoko-retrieval-maintainer` after real retrieval failures with the
  exact failure taxonomy, fixture shape, and diagnostic command sequence.
- Patch `motoko-agentic-boundary-review` after action/tool/goal-loop issues
  with the authority check that would have caught the issue earlier.
- Add support files before adding new skills when the durable value is an
  example, transcript, command trace, fixture recipe, or audit checklist.
- Create a new skill only when repeated evidence shows that an umbrella skill is
  too broad. Current plausible future candidates are an artifact-lifecycle
  caretaker, background-job supervisor, conversation-persistence auditor,
  code-query precision auditor, and Org-structure/query maintainer.
- Keep every self-created or self-patched skill review-first. Motoko may
  suggest and prepare a `skill_manage` action, but code-owned validation and
  explicit user acceptance decide whether it becomes durable.

Hermes Agent remains a useful comparison point, but the lesson for Motoko is
selective. Hermes' progressive skill disclosure, skill usage metadata,
agent-created skill lifecycle, background curator reports, pinned/recoverable
states, and patch-before-create behavior are worth adapting. The security
lesson is just as important: code-level guards must protect bundled, hub,
hand-authored, and cross-realm skills from background mutation. Motoko should
keep the stricter invariant that prompts can recommend, but validators enforce.

Operational packet for future Motoko self-improvement sessions:

1. Inspect first: run `motoko code-map`, then focused `motoko code-query`
   searches for the command, handler, schema, service module, tests, migration
   constants, artifact family, and cancellation path involved in the requested
   change.
2. Load the narrowest existing procedure: prefer
   `motoko-codebase-maintainer`, `motoko-refactor-craft`,
   `motoko-retrieval-maintainer`, or `motoko-agentic-boundary-review` before
   creating a new skill.
3. Patch skills only when the lesson is reusable. If the durable value is an
   example, transcript, checklist, or validation recipe, write a support file
   instead of expanding `SKILL.md`.
4. Keep Hermes-inspired ideas in Motoko shape: progressive disclosure,
   usage/view/patch metadata, curator review, pinned/recoverable archive states,
   skill-support organization, and patch-first suggestions are valuable. Broad
   terminal authority, cross-realm skill stores, hidden mutation, and
   prompt-only security are not.
5. For every code change, preserve the derived-artifact contract: old artifacts
   need a deterministic migration, visible source reprocessing, or an explicit
   documented reason why reuse is unsafe.
6. For every behavior change, leave a gate: focused regression, deterministic
   eval, action-eval, self-eval, retrieval/vector eval, or a documented soak
   check tied to the exact failure class.

## Self-Improvement Improvement Packet

When Motoko is asked to improve her own repository after this point, she should
prepare the work as a reviewed engineering packet rather than as a vague agentic
wish list:

1. Start from code facts. Run `motoko code-map`, then use `motoko code-query`
   to find the relevant command handlers, service modules, schemas, tests,
   migration constants, cancellation paths, route/model paths, and root-facade
   hotspots.
2. Choose the existing umbrella skill before creating a new one:
   `motoko-codebase-maintainer`, `motoko-refactor-craft`,
   `motoko-retrieval-maintainer`, or `motoko-agentic-boundary-review`. Patch
   the selected skill or add a support file when the lesson generalizes.
3. Treat the most valuable near-term improvements as:
   artifact-lifecycle ownership, cooperative cancellation, always-fresh
   context, conversation persistence, feedback-to-eval conversion, code-query
   precision, skill lifecycle hygiene, and review-oriented goal loops.
4. Convert repeated successful repairs into procedural memory only when they
   save tokens, reduce errors, improve reliability, or preserve Motoko-specific
   craft. Examples, command traces, checklists, and fixture recipes should
   become support files before they become long `SKILL.md` bodies.
5. Keep Hermes-inspired skill maintenance Motoko-shaped: track usage/view/patch
   metadata; prefer patching or consolidating existing skills before creating
   narrow duplicates; support pinned and recoverable archived skills; produce
   curator reports before mutation; and make any rollback/snapshot behavior
   content-safe and realm-local.
6. Consider a future `motoko-self-maintenance` bundle only if real use shows
   that loading the four umbrella skills separately is noisy. A bundle may
   compose procedures; it must not grant authority.
7. Keep self-created skill changes review-first. Motoko may suggest a
   `skill_manage` action, support-file addition, or tool contract, but code
   validators and explicit user acceptance decide whether it becomes durable.
8. Avoid the Hermes parts that do not fit Motoko's boundary: broad terminal
   authority, prompt-only security, cross-realm skill stores, hidden mutation,
   network tools without NixOS policy, and dependency-heavy runtimes.
9. End every improvement with a gate: focused regression, `self-eval`,
   `action-eval`, retrieval/vector eval, or a manual soak check that would catch
   the same failure class later.

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
- Treat shared progress/state writes as concurrency-sensitive infrastructure.
  Parallel background lanes must not reuse one fixed temporary path for the
  same destination; use a unique same-directory temp file before atomic replace
  and leave a regression that exercises concurrent writers.
- When a background crash is fixed, patch `motoko-refactor-craft` or the
  relevant umbrella skill with the reusable lesson so future self-improvement
  sessions look for the same class of durability bug.

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
