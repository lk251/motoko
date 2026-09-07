# Recuris: Experiential-Working Memory Evolution for Long-Horizon Agents

Date: 2026-09-07
Status: research note; high relevance to Motoko, not an implementation decision

This note records findings from Yu et al. (2026), *Recursive
Experiential-Working Memory Evolution for Long-Horizon Agent Harnesses*
(arXiv:2608.24876), together with its open-source implementation, and evaluates
what Motoko should borrow from the design.

Of the recent memory/retrieval systems reviewed for Motoko, Recuris is unusually
close to Motoko's existing architecture. It does not require changing model
weights. Instead, it treats the external harness -- working state, reusable
skills, skill invocation, and correctness checks -- as the surface that can
improve over time. That maps directly onto Motoko's existing goals, skills,
retrieval plans, validators, source provenance, and review-first
self-improvement mechanisms.

The strongest lesson is not simply "store more experience." Recuris shows that
long-horizon performance depends heavily on maintaining a compact,
evidence-grounded representation of what is still unresolved and using that
state to decide *when* a reusable skill is relevant. Its ablations suggest that
verified working state does more work than an ever-growing library of memories
by itself.

Related Motoko documents:

- `docs/retrieval-pipeline-directions.md`
- `docs/deferred-projects.md`
- `docs/motoko-self-improvement-playbook.md`
- `docs/agentic-capability-design.md`
- `docs/project-context.md`

## Recuris architecture

Recuris keeps the downstream model frozen and defines a Skill Memory:

```text
M = (E, W, rho, C)
```

where:

- `E` -- **Experiential Memory**: reusable knowledge/procedure/action-result
  cards distilled from prior failures;
- `W` -- **Working Memory**: a compact structured ledger of the current task
  state and unresolved obligations;
- `rho` -- **Invocation Policy**: the routing/delivery rule that determines
  which experiential memory is shown and when;
- `C` -- **Checkers**: assertions or validators that determine whether a
  claimed state transition is actually supported.

This decomposition is important because the components have different failure
modes. If a useful skill does not exist, that is a knowledge failure. If the
skill exists but is never invoked, that is a routing failure. If the agent
believes an operation succeeded but the environment says otherwise, that is a
working-state/grounding failure. A downstream score alone cannot reliably tell
these cases apart.

### Within-task loop: verified state drives memory use

The open-source runtime is intentionally structured around a verified state
transition loop. In outline it:

1. classifies the incoming event;
2. updates the working-memory ledger under explicit write permissions;
3. lets the invocation policy select relevant experiential memory;
4. drafts the next action/response;
5. runs checkers, with a bounded redraft when needed;
6. grounds claimed progress against real tool/environment receipts;
7. commits the verified state transition.

A particularly valuable invariant is that the model cannot simply mark its own
work `DONE`. Completion is harness-owned and requires actual evidence. The
implementation documentation describes an earlier failure where allowing the
model's belief that it had finished to enter the ledger disabled several safety
and termination mechanisms at once.

This is an important design distinction for Motoko:

```text
model belief about state != verified working state
```

For tool/action tasks, progress should be updated from validator-owned results,
not from natural-language confidence or a self-authored summary.

### Across-task loop: localize, patch, validate, recurse

Recuris then turns the structured execution trace into evidence for harness
improvement. A fixed Meta-Agent diagnoses a failure and proposes local edits to
only the implicated memory components. The proposal is not trusted merely
because the Meta-Agent produced it.

The candidate package passes code-owned checks and a fixed validation gate. The
released implementation describes the gate as paired held-out evaluation with a
bootstrap confidence interval and a regression cap. It also performs leakage
checks and an activation/fingerprint check so an apparent score improvement is
not credited to a mechanism that never actually fired.

The overall loop is approximately:

```text
memory
  -> behavior
  -> structured execution evidence
  -> component-level failure localization
  -> targeted candidate patch
  -> deterministic/held-out validation
  -> accepted memory
  -> new behavior and new evidence
```

Only the proposed patch is generative. Admission is controlled by ordinary
artifacts and arithmetic rather than a model voting on its own work. The
repository also persists the campaign state as files -- reviews, lessons,
changelog, regression suspects, and evaluation records -- rather than relying
on hidden model context to carry the improvement process across rounds.

## Empirical results worth noting

Across four long-horizon benchmarks and ten models, the authors report improved
task success in 35 of 37 completed model/benchmark pairs.

Examples reported by the paper/repository include:

- GPT-5.6 Sol on tau2-Retail: `58.3 -> 76.1` (`+17.8` points);
- Claude Opus 5 on tau2-Retail: `72.4 -> 87.9` (`+15.6` points);
- Qwen3.6-27B on SkillFlow: `42.2 -> 58.7` (`+16.6` points);
- Qwen3.6-35B on SkillFlow: `35.3 -> 48.8` (`+13.5` points).

The reported advantage grows with interaction horizon, reaching `+32.2` points
on the longest task bucket, while common long-horizon failure modes fall by up
to 80%.

These are benchmark results rather than guarantees for Motoko. However, the
breadth across model sizes and families is interesting because the improvement
lives outside the frozen model and the evolved memory packages can transfer
between models.

## The ablations are more important than the headline result

The tau2-Retail ablation is particularly relevant to Motoko. A secondary
analysis of the paper reports the following matched results:

| Variant | Task success |
| --- | ---: |
| Base | 58.1 |
| Experiential Memory only | 60.1 |
| Working Memory only | 82.0 |
| Model-controlled skill invocation | 65.6 |
| Experiential + Working Memory (Recuris) | 83.6 |

The main implication is that merely having reusable experience in context is
not enough. The largest gain comes from maintaining the right current state.
Experiential memory adds more value when verified state controls its invocation.

The same analysis reports required-write recall of 55.7% for the base agent,
61.1% for model-controlled skill injection, 80.9% for Working Memory only, and
82.4% for full Recuris. This supports a useful interpretation:

> A good skill that is available at the wrong time is often not useful memory.
> Long-horizon competence depends on the coupling between state and retrieval.

The paper also reports much better failure attribution from structured traces:
roughly 64.8% macro attribution from the structured Recuris trace, versus 37.0%
from the raw trajectory and 13.0% from the final outcome alone. This is directly
relevant to Motoko's self-improvement loop because coarse thumbs-up/down or task
success signals cannot tell whether the failure was caused by recall, routing,
state tracking, an incorrect procedure, a checker, or final synthesis.

## Mapping Recuris onto current Motoko

A useful conceptual mapping is:

| Recuris | Closest Motoko concept |
| --- | --- |
| `E` Experiential Memory | learned/reviewed skills, support files, durable repair lessons, selected memories/dossiers |
| `W` Working Memory | goal-loop state, conversation working state, unresolved actions/obligations, future typed long-horizon working state |
| `rho` Invocation Policy | skill triggers, retrieval planners, handler activation, candidate fusion/routing |
| `C` Checkers | action validators, typed contracts, grounding checks, deterministic handlers, eval assertions |

This is not an instruction to merge those Motoko subsystems into one data
structure. Their security and lifecycle properties differ. The mapping is useful
because it gives Motoko a diagnostic language for asking *which control surface
failed*.

### Current strength: Motoko already has much of E, rho, and C

Motoko's skill architecture is already review-first, records trigger hints and
allowed effects, and can activate code-owned deterministic handlers before a
subsystem runs. The curator can turn repeated repairs or feedback into pending
skill suggestions rather than silently rewriting production behavior.

Motoko also already treats important effects as typed and validator-owned,
preserves source provenance, and keeps retrieval diagnostics visible. These are
compatible with Recuris rather than requiring a wholesale replacement of the
current architecture.

### Largest likely gap: first-class verified working state

The Recuris ablation suggests Motoko should pay special attention to `W`.
Motoko's goal loops already preserve explicit phase/action progress, and the
long-horizon memory roadmap proposes a typed working-state/notes layer across
context rollover. Recuris provides evidence that this should not be treated as
mere summarization.

For action-oriented work, a future Motoko working-state object should distinguish
at least:

```text
requested / inferred goal
pending obligation
attempted action
verified result
blocked / failed result
resolved obligation
open question
```

Where an objective external receipt exists, the harness should own the
transition from pending to resolved. Natural-language summaries may describe the
state, but should not be authoritative over it.

For personal conversation, the analogy must be used more carefully. Human
intentions, feelings, relationships, hypotheses, and uncertain life events often
have no deterministic checker. There, Motoko should preserve provenance and
uncertainty rather than pretending subjective state can be machine-verified.
Recuris is most directly applicable to project work, tool use, goals, coding,
research workflows, and other tasks with observable state transitions.

## Ideas Motoko should borrow

### 1. State-conditioned skill and retrieval activation

Do not decide skill relevance solely from the latest user message or semantic
similarity to a growing transcript. Let explicit current state participate in
routing.

For example, when a goal-loop state says a required validation step remains
pending, that state should be a high-authority trigger for the relevant
procedure/checker even if the recent conversation has drifted elsewhere.

Likewise, in long personal conversations, an explicit unresolved question or
working hypothesis may be a better retrieval cue than the entire recent chat.
The evidence retrieved in response must still preserve normal provenance rules.

### 2. Distinguish missing knowledge from failed invocation

Motoko should not interpret "the agent did not use the right skill" as evidence
that the skill is missing.

Evals and diagnostics should distinguish at least:

```text
needed procedure absent
procedure present but not retrieved
procedure retrieved but not activated
procedure activated but ignored/misapplied
working state incorrect/stale
checker/validator insufficient
correct evidence selected but final synthesis failed
```

This extends Motoko's existing retrieval failure taxonomy rather than replacing
it.

An activation probe analogous to Recuris is especially attractive: before
changing a skill because an eval failed, test whether the current trigger and
handler are capable of firing on the failing fixture.

### 3. Record structured execution evidence for self-improvement

A self-improvement system should not learn only from a scalar outcome.

For appropriate Motoko workflows, preserve a compact content-safe trace such as:

```text
working-state snapshot
candidate skills/procedures
selected skill + reason
handler/effect activated
retrieval/source IDs used
action proposal
action validator result
tool/environment receipt
post-action verified state
final outcome / user feedback
```

This can make future curator suggestions much more targeted and can reveal that
a failure attributed to "bad memory" was actually a state, routing, or checker
problem.

Private raw content should remain governed by the normal realm-local privacy
rules; diagnostic records should be content-free where possible.

### 4. Patch the smallest responsible component

When a failure is localized, prefer a narrow repair:

- skill content failure -> patch the skill/support file;
- routing failure -> patch trigger/planner metadata;
- state-model failure -> patch the typed state transition or parser;
- checker failure -> patch the validator/checker;
- retrieval failure -> patch candidate generation/reranking;
- final synthesis failure -> patch prompting/model selection only if the
  evidence pipeline was correct.

This is substantially safer and more interpretable than rewriting one large
system prompt or memory summary after each failure.

### 5. Never let the proposing model be the sole admission authority

This is one of the strongest Recuris ideas for Motoko.

A model can propose a skill or harness change. It should not be able to declare
that its own proposal is correct merely by reviewing it again. Candidate changes
should pass independent checks appropriate to their risk:

- schema/lint validation;
- activation tests;
- leakage checks;
- synthetic regression fixtures;
- held-out evaluation cases;
- deterministic policy/security checks;
- explicit human review for behavior-changing or security-sensitive artifacts.

For low-risk prompt-only learned skills, Motoko may eventually allow more
aggressive eval-gated automation. Working-state schemas, code-owned handlers,
action validators, security boundaries, and executable tool contracts should
remain much more protected.

### 6. Make improvement campaigns reproducible artifacts

Recuris keeps each improvement round reproducible from files rather than relying
on the Meta-Agent's hidden context. Motoko should preserve this principle in any
future automated self-improvement campaign.

A campaign should have an inspectable ledger containing:

- failure fixtures;
- attribution;
- proposed patch;
- expected mechanism;
- activation evidence;
- evaluation before/after;
- regressions;
- accept/reject decision;
- final artifact fingerprint.

This matches Motoko's existing preference for inspectable state, typed actions,
and review-first mutation.

### 7. Keep skill memory model-agnostic where possible

Recuris reports that evolved memory transfers across models. Even if Motoko does
not reproduce that result, model-agnostic skills are strategically useful.

Avoid encoding unnecessary model-specific prompt quirks into durable skills.
Where possible, define the procedure, trigger, provenance, expected effect, and
validation independently of the current chat model. Then evaluate the same skill
against more than one approved route when practical.

This should make Motoko's learned competence more durable as local model routes
change over time.

## Security and epistemic boundaries

Recuris is a research harness for benchmark/task agents. Motoko has stronger
requirements around personal memory, privacy, user control, and reviewable
mutation. The architecture should therefore be borrowed selectively.

### Protect the checker layer

`C` is effectively part of the trust boundary. If a self-improving model can
freely weaken the checker that judges its actions, it can make itself appear
more successful without becoming more correct.

For Motoko, code-owned validators, permission checks, source-boundary rules, and
security-sensitive deterministic handlers should not be autonomously rewritten
by the same loop they supervise. Proposed modifications should require explicit
review and separate tests.

### Working state is not durable truth

A working-state ledger describes what the system currently believes is pending,
resolved, or relevant to the active task. It must not silently become the
canonical personal-memory store.

Raw user statements, correspondence, documents, and tool receipts remain
separate evidence classes with their own provenance. Derived working state
should point back to those sources where possible and be disposable/rebuildable
when appropriate.

### Avoid benchmark-style leakage in learned skills

Recuris explicitly forbids storing held-out task answers in skill cards. Motoko
needs an analogous rule for eval-driven learning: a skill should encode a
procedure or generalizable lesson, not memorize the answer to an evaluation
fixture. Any future automatic skill campaign should run leakage checks before
claiming an improvement.

## Recommended Motoko experiment

Recuris is worth an eval-driven prototype, but the first step should be
instrumentation and diagnosis rather than an autonomous self-modification loop.

### Phase A: structured trace instrumentation

On selected existing goal-loop, retrieval, and skill fixtures, record a bounded
trace containing:

- typed working state;
- relevant skill candidates;
- selected/activated skills;
- retrieval evidence IDs;
- handler/checker outcomes;
- action receipts;
- final result.

Do not change production behavior yet.

### Phase B: component-level failure attribution

Build an offline evaluator that classifies failures into a Motoko-shaped version
of the Recuris decomposition:

```text
E: missing/wrong procedure or durable knowledge
W: stale/wrong/unverified working state
rho: routing/invocation failure
C: validator/checker failure
R: underlying evidence-retrieval failure
S: final synthesis/model-use failure
```

Compare classification quality using:

1. final task result only;
2. raw transcript/trajectory;
3. structured trace.

This directly tests whether Recuris's diagnostic advantage transfers to Motoko.

### Phase C: review-first targeted patch proposals

Allow the curator/meta-agent to propose one narrow patch against the attributed
component. Initially restrict automated proposals to existing low-risk surfaces
such as prompt-only skill content, support files, and trigger metadata.

Every proposal remains pending and user-reviewable.

### Phase D: independent validation gate

Evaluate proposed patches on frozen fixtures that were not supplied as direct
answers to the proposer. Require:

- the target failure to improve;
- activation/fingerprint evidence that the intended mechanism fired;
- no security/schema violations;
- no leakage;
- bounded regression on unrelated fixtures.

Record the full decision as an artifact. Human approval can remain the final
admission step even when the deterministic gate passes.

### Phase E: bounded multi-round evolution

Only after the previous phases demonstrate reliable attribution and validation,
run a small campaign over a narrow skill family. Cap rounds and budgets, keep
snapshots of every accepted version, and measure whether improvements transfer
to held-out tasks and more than one approved model route.

The goal is not "Motoko rewrites herself." The goal is:

> Motoko can turn repeated, well-diagnosed failures into small reusable
> improvements without allowing one noisy outcome, one model's self-judgment, or
> one bad patch to mutate the whole harness.

## Current recommendation

Keep Recuris near the top of Motoko's memory/self-improvement research
references. It is more directly actionable for the current architecture than
model-internal memory mechanisms such as delta-mem and more immediately relevant
than deferred visual retrieval.

The highest-value ideas to carry forward are:

1. make verified working state a first-class control surface for long-horizon
   tasks;
2. let working state drive skill/retrieval invocation rather than relying only
   on the growing transcript;
3. diagnose failures from structured execution evidence and distinguish memory
   content from routing, state, checker, retrieval, and synthesis failures;
4. patch the smallest responsible component;
5. require an independent validation gate before learned harness changes are
   admitted;
6. preserve every improvement round as inspectable, reproducible artifacts;
7. keep durable skills as model-agnostic and provenance-rich as possible.

The ablations suggest a useful priority order for Motoko: **state correctness
first, state-conditioned retrieval/invocation second, experiential skill growth
third**. A larger memory library is not automatically a better long-horizon
agent if the harness cannot reliably tell what remains unresolved and deliver
the right procedure at the moment it becomes relevant.

## References

- Yu, Z., Wu, Y., Yin, Z., Chen, K., Zhao, Z., Wang, M., Yan, S., and Yang, L.
  (2026). *Recursive Experiential-Working Memory Evolution for Long-Horizon
  Agent Harnesses*. arXiv:2608.24876:
  <https://arxiv.org/abs/2608.24876>
- Official Recuris implementation:
  <https://github.com/Gen-Verse/Recuris>
- Recuris architecture documentation:
  <https://github.com/Gen-Verse/Recuris/blob/main/docs/architecture.md>
- Recuris Skill Memory format:
  <https://github.com/Gen-Verse/Recuris/blob/main/docs/skill-memory-format.md>
- Jiqizhixin post that prompted this research note:
  <https://x.com/jiqizhixin/status/2096809181722411383>
