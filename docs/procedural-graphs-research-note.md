# Procedural Graphs: Self-Evolving Execution Structures for Motoko

Date: 2026-09-10
Status: research note; high relevance to Motoko, not an implementation decision

This note records findings from Lu, Chen, Wu, and Arık (2026), *Procedural
Graphs: Self-Evolving Execution Structures for LLM Agents*
(arXiv:2609.09153), and evaluates what Motoko should borrow from the design.

This paper is especially relevant after the Recuris review in
`docs/recuris-experiential-working-memory-research-note.md`. Recuris argues that
long-horizon competence depends strongly on verified working state, reusable
experience, routing, and checkers. Procedural Graphs (PG) adds a complementary
claim: procedural memory can itself have explicit topology. Rather than storing
only independent skills, guidelines, or past trajectories, the system stores
which procedures can follow which other procedures, under what conditions, with
what guidance and pitfalls.

For Motoko, the strongest synthesis is therefore not "replace skills with a
graph." It is:

```text
verified working state
    -> localize current procedural state
    -> retrieve a small connected neighborhood of relevant procedures
    -> give the model compact situational guidance
    -> execute through normal typed tools/handlers
    -> verify results through trusted validators/receipts
    -> learn from failures through review-first, eval-gated updates
```

This is a plausible future extension of Motoko's current skill/retrieval/goal
architecture, especially for repository work and other long-horizon tasks with
repeated procedures. It is less directly applicable to open-ended personal
conversation, where facts, interpretations, and relationships often do not form
a clean executable state machine.

Related Motoko documents:

- `docs/recuris-experiential-working-memory-research-note.md`
- `docs/retrieval-pipeline-directions.md`
- `docs/agentic-capability-design.md`
- `docs/motoko-self-improvement-playbook.md`
- `docs/deferred-projects.md`
- `docs/project-context.md`

## What a Procedural Graph is

The paper distinguishes procedural memory from semantic and episodic memory.
A knowledge graph organizes factual relations for "what is true?" questions.
A Procedural Graph organizes action/procedure relations for "what should I do
next?" questions.

Formally, the graph contains directed attributed edges:

```text
(procedure_u, relation, procedure_v)
```

A node may represent:

- a tool action;
- a reusable skill;
- an internal reasoning/procedure step;
- a task status.

Each transition edge can carry task-specific attributes. The paper's
implementation uses three textual fields:

```text
condition   -- when this transition is appropriate
guidance    -- how to perform or reason about the transition
pitfalls    -- mistakes or invalid behavior to avoid
```

This is more expressive than an unordered skill bank. A skill bank can tell an
agent that both `validate_configuration` and `apply_change` exist; a procedural
graph can encode that validation should occur after a candidate change, before
some higher-risk transition, and that a failed validation should lead to a
repair path rather than completion.

The graph is intended to remain outside model weights. It is inspectable,
editable, retrievable, and can evolve from execution feedback without
fine-tuning the solver.

## Online inference: localize, extract, generate

At every decision step, PG performs three conceptual operations.

### 1. Localize the current procedure

The paper identifies the graph node corresponding to the agent's most recent
procedure. In its implementation this is based on exact matching of the latest
procedure/action to a node name.

This turns the recent trajectory into a procedural position rather than asking
the solver to reconstruct the entire plan from a flat transcript.

### 2. Extract a local connected neighborhood

Once localized, the system retrieves the outgoing graph neighborhood within a
small hop radius. The reported experiments use a two-hop neighborhood.

This is an important difference from ordinary top-k retrieval. Independent
semantic retrieval can return a relevant action without its prerequisite. The
paper gives the general failure pattern: retrieving advice about a later action
can omit the transition that establishes when that action is valid. Connected
retrieval preserves some local dependency structure.

### 3. Generate situational guidance

A guidance LLM receives:

- the task/query;
- the localized graph neighborhood;
- a short recent trajectory window (three steps in the reported experiments).

It converts static edge attributes into guidance for the current situation.
That guidance is appended to the solver prompt. The solver is still free to
reason and choose an action; the graph steers rather than mechanically executes
the workflow.

This "soft procedural prior" is attractive for Motoko because it avoids two
bad extremes:

- unconstrained generation from a long transcript, where the procedure is
  implicit and easy to lose;
- a rigid workflow engine that cannot adapt when the task requires judgment.

The correct Motoko boundary would be **soft guidance, hard invariants**:
procedural memory may steer the model, while permissions, validators, security
boundaries, and externally verifiable completion remain code-owned.

## Offline self-evolution

The graph is not static. The paper defines an offline loop that improves it from
execution traces.

Each round:

1. executes the current graph on a training batch;
2. gives trajectories and scores to an LLM refiner;
3. lets the refiner propose graph edits;
4. applies structural checks to a candidate copy;
5. evaluates the candidate on an independent validation set;
6. accepts the candidate only if validation performance is at least as high as
   the retained graph;
7. records rejected candidates and their evidence in rejection memory so the
   refiner is less likely to repeat failed edits.

Allowed edits include adding/deleting nodes, adding/deleting edges, and revising
edge attributes. In the implementation, revising an edge attribute is modeled
as deleting and re-adding the edge with updated values.

The candidate graph is structurally checked before expensive validation. Among
the paper's checks are valid endpoints and the existence of a path from every
node to some terminal node. Depending on configuration, cycles may be repaired
or allowed.

This is conceptually close to Motoko's review-first skill curation and to the
Recuris lesson that a model may propose an improvement but should not be the
sole authority deciding whether its own patch was successful.

## Main empirical results

The paper evaluates seven task families overall and gives its main comparison
on six benchmarks across four LLM families. All methods share the same ReAct
solver and differ in how procedural experience is stored and reused.

The compared memory/procedure baselines include MemoryBank, RAP, ExpeL,
AutoGuide, Agent Workflow Memory (AWM), and KnowAgent.

Across 24 model-benchmark settings, Procedural Graph ranks first or joint first
in 21. Against the strongest competing baseline in each setting, the paper
reports 19 wins, two ties, and three losses; excluding ties, the one-sided exact
binomial sign test is reported as `p = 4.3e-4`.

Some of the largest reported margins over the strongest baseline are:

- BFCL v3 with Gemini 3.5 Flash: `67.0%` versus `58.0%` (`+9.0` points);
- GDPval with Gemini 3.1 Pro: `78.78` versus `71.37` (`+7.41` points);
- tau-bench with Gemini 3.1 Pro: `80.0%` versus `73.04%` (`+6.96` points).

The breadth matters more for Motoko than any single number: the same
representation idea is tested across multi-hop search, multi-turn instruction
retention, professional work, embodied action ordering, customer-service tool
use, and multi-turn function calling.

These are paper-reported benchmark results and should not be treated as a
guarantee that a procedural graph will improve Motoko. The relevant question is
whether Motoko has repeated failure classes caused by missing procedural
structure rather than by missing facts or insufficient model capability.

## Construction results: evolution can outperform a human prior

One especially interesting part of the paper compares how the graph is built.
It tests hand-crafted expert graphs, one-time updates, iterative evolution from
an expert graph, and evolution from a minimal skeleton.

On HotpotQA, scratch + iterative evolution reaches `78.79` answer F1 and `66.30`
exact match, gains of `+7.58` F1 and `+7.50` EM over the unguided baseline in
that construction experiment.

On MultiChallenge, a hand-crafted expert graph is actively harmful: success
falls from an `87.50%` unguided baseline to `58.93%`. A single static update
falls further to `53.57%`. Iterative evolution with validation gating repairs
the bad prior and reaches `92.86%`.

This is highly relevant to Motoko's philosophy. Human-written procedures and
AGENTS/skill guidance should not be assumed correct merely because they were
written deliberately. A procedural prior can make the model worse. What matters
is whether it survives measured use and regression evaluation.

The lesson is:

```text
expert prior != trusted prior
trusted prior = inspectable prior + evidence + validation + rollback
```

## Long-horizon result

The paper also studies ten rounds of self-evolution on EnterpriseArena, a
long-horizon financial simulator where delayed capital delivery makes timing
and procedure important.

In the reported smaller self-evolution experiment, the baseline has `0%`
full-horizon validation survival. Early evolution discovers a sequence that
audits cash, forecasts runway, and then makes financing decisions. A subsequent
round adds note recall. Later rounds prune and restructure the graph.

The returned graph reaches `85%` test survival versus `0%` for the baseline.
The authors explicitly distinguish this from the best intermediate round, which
reached `95%`: they report the returned checkpoint rather than selecting the
best test result after the fact.

This result is striking but should be interpreted cautiously. The
self-evolution study uses only 20 episodes per train/validation/test split, and
the paper notes that individual accept/reject decisions can turn on one or two
episodes. For Motoko, this argues for conservative gates, larger or repeated
fixtures where possible, and explicit uncertainty around small eval sets.

## Efficiency result: localization matters, but guidance is not free

A particularly useful ablation compares:

- no procedural graph;
- raw full-graph injection;
- full-graph generative guidance;
- localized-subgraph generative guidance.

The localized two-hop subgraph with generative guidance performs best on all
three tested tasks in this ablation. Relative to full-graph generative guidance,
localization reduces total token use by about:

- `70.9%` on ALFWorld;
- `18.1%` on GDPval;
- `14.8%` on MultiChallenge.

However, the extra guidance model call still makes the system more expensive
than the no-graph baseline. On GDPval and ALFWorld, localized guidance reduces
solver steps but total token use remains `33.4%` and `55.4%` above baseline,
respectively.

This is a crucial constraint for Motoko, especially with local models. The paper
supports **localized procedural retrieval**, but does not establish that a
second full LLM call at every step is the right cost/latency trade-off for
Motoko.

A Motoko prototype should therefore separate two hypotheses:

1. connected local procedural retrieval improves action selection;
2. an additional LLM guidance call is necessary to realize that improvement.

The first could be valuable even if the second is too expensive.

## How this maps onto Motoko

### Procedural Graph is not another document RAG index

Motoko should not mix this directly into semantic fact retrieval.

The objects answer different questions:

```text
semantic / episodic retrieval:
    What facts, source spans, or past events are relevant?

procedural retrieval:
    Given the verified current state, what actions or skills are admissible or
    useful next, and what prerequisites/pitfalls connect them?
```

A single user turn may require both. For example, a repository task may first
retrieve factual evidence about the codebase and then use procedural memory to
choose whether the next step is inspect, edit, validate, review diff, or stop.

### Motoko already has graph-worthy procedural objects

Current Motoko has several pieces that could eventually participate in such a
graph:

- skills and support files;
- skill trigger metadata;
- deterministic handlers and allowed effects;
- typed action/tool contracts;
- goal-loop phases and stop conditions;
- validators/checkers;
- retrieval procedures;
- common failure/repair patterns learned from feedback.

What it does not yet need is one graph that becomes the source of truth for all
of these. Their authority differs. A prompt-only learned skill and a security
validator must not become equally mutable graph nodes.

The safer architecture is a **derived procedural side-index** over stable IDs:

```text
canonical skill / handler / action / validator definitions
                    |
                    v
          procedural graph projection
        (relations + conditions + pitfalls)
                    |
          current verified working state
                    |
                    v
         localized procedural context
                    |
                    v
                  model
```

The graph may describe and connect trusted primitives, but should not own their
permissions or implementation.

## Strongest ideas to borrow

### 1. Make procedural memory relational

Motoko's skills currently encode useful procedures and trigger information, but
some knowledge is naturally relational:

- `A` should happen before `B`;
- `B` is valid only if `A` produced condition `x`;
- failure of `B` should route to `repair_C`;
- `D` terminates the procedure;
- `E` and `F` are alternative branches under different states.

Representing all of this independently inside prose skill files forces the model
to reconstruct topology repeatedly. A small explicit relation layer could make
procedure selection more reliable and easier to inspect.

Candidate relation types might include:

```text
PRECEDES
REQUIRES
ENABLES
ALTERNATIVE_TO
ON_FAILURE
ON_SUCCESS
RETRY_WITH
VALIDATES
TERMINATES
```

These should remain a small reviewed vocabulary initially. Free-form relation
explosion would recreate an unstructured memory problem in graph form.

### 2. Retrieve connected neighborhoods, not isolated procedure snippets

Motoko's retrieval direction already favors hierarchical and source-aware
context selection. For procedural memory, topology offers another retrieval
signal.

If a state localizes to `edit_candidate`, retrieving only the semantically
nearest skill may miss `validate_candidate` or `inspect_diff`. A bounded
outgoing neighborhood can carry the immediate dependency chain without dumping
the full skill library into context.

This suggests a general retrieval principle:

```text
semantic similarity finds plausible objects
structure recovers their dependencies
reranking decides what actually enters context
```

The graph should therefore complement, not replace, lexical/dense retrieval.

### 3. Localize from verified state, not merely surface trajectory text

The paper's implementation exactly matches the most recent procedure to a graph
node and falls back to the full graph when matching fails. Motoko can do better
when a task has typed state.

Following the Recuris lesson, localization should preferentially use:

- validator-owned action results;
- tool receipts;
- explicit goal-loop phase/action state;
- deterministic handler outcomes;
- typed unresolved obligations.

Only when such state is unavailable should the model infer location from free
text.

Likewise, a mature Motoko graph should not fall back to injecting the entire
graph when localization fails. It should use bounded candidate retrieval over
node metadata and current working state, then expose uncertainty in diagnostics.

### 4. Store conditions and pitfalls on transitions

This is more useful than storing only `next` edges.

A transition should be able to explain why it is admissible and what commonly
goes wrong. In Motoko terms, a relation could eventually carry metadata such as:

```text
from
relation
to
condition
reason
guidance
pitfalls
source / learned_from
confidence / validation status
last_validated
```

Provenance is essential. A transition learned from one failure should not become
an unqualified universal rule.

### 5. Keep guidance soft; keep safety and truth checks hard

The graph should guide the solver, not grant authority.

If the local graph says an action is appropriate but a Motoko permission check,
action validator, source boundary, or security rule rejects it, the trusted code
wins. Likewise, the model should not infer that a step succeeded merely because
the graph predicts that success normally follows it.

This is the same key distinction identified in the Recuris review:

```text
procedural prior = advice
verified working state = evidence-backed state
validator/security boundary = authority
```

### 6. Let self-improvement edit topology, not only prose

Motoko's current curator can learn or patch skills. Procedural Graphs suggests a
new failure class: the individual procedures may all be correct, but their
connections may be wrong or missing.

Future failure attribution should distinguish:

```text
procedure content missing/wrong
procedure trigger/routing wrong
working state wrong
transition missing
transition condition wrong
failure branch missing
termination edge wrong
pitfall/guidance wrong
validator/checker wrong
underlying evidence retrieval wrong
final model synthesis wrong
```

A self-improvement proposal can then patch the smallest responsible layer.

### 7. Keep rejected structural edits as negative experience

The paper's rejection memory is a useful complement to ordinary success memory.
An improvement system that stores only accepted fixes can repeatedly rediscover
and retry attractive but harmful changes.

Motoko should consider preserving a compact rejection record containing:

- candidate diff/fingerprint;
- targeted failure class;
- validation delta;
- structural diagnostics;
- regression examples or categories;
- reason for rejection.

This should be bounded and deduplicated. Retaining every rejected full graph or
raw private trajectory indefinitely would create unnecessary storage and privacy
cost.

### 8. Evolve from minimal structure where possible

The paper's scratch-evolution results are a warning against over-designing the
initial procedure graph.

Motoko should begin with only high-confidence structure derived from existing
skills, typed actions, validators, and explicit goal-loop sequences. Then use
real failures and evals to justify additional relations.

A small correct graph is preferable to a comprehensive speculative graph that
quietly biases the model into bad workflows.

## Relationship to Recuris

These two systems should be treated as complementary rather than competing
references.

Recuris decomposes long-horizon agent memory into:

```text
E   experiential memory
W   verified working memory
rho invocation policy
C   checkers
```

Procedural Graphs gives a possible richer representation for part of `E` and
`rho`: not just a library of independent procedural cards, but an explicitly
connected, state-localizable structure over procedures.

A Motoko synthesis could eventually look like:

```text
W: verified current working state
        |
        v
procedural localization
        |
        v
PG: small local graph neighborhood
        |
        +----> relevant skill/support knowledge
        |
        v
rho: choose what context/procedure to activate
        |
        v
model proposes next action
        |
        v
C: trusted validator/checker/tool receipt
        |
        v
updated W
```

This gives the procedural graph a clear role without allowing it to replace the
working-state or checker layers that Recuris shows are crucial.

## What not to copy directly

### Do not add an LLM guidance call at every step by default

The paper's best-performing configuration uses an extra guidance-model call each
step. That is an important experimental result, but it has real token and
latency cost.

Motoko should first test cheaper variants:

1. directly serialize a compact local neighborhood into the solver prompt;
2. deterministically render the current node, likely next transitions,
   conditions, and pitfalls;
3. invoke a guidance model only when branching/ambiguity exceeds a threshold;
4. cache guidance while the procedural state has not changed.

Only measured gains should justify an always-on extra model call.

### Do not use full-graph fallback

The paper falls back to the full graph when node matching fails. This is
reasonable for small experimental graphs but is a poor scaling default.

Motoko should instead retrieve a bounded set of plausible nodes using typed
state, exact names, lexical matching, and embeddings; if localization remains
uncertain, report that uncertainty rather than flood the prompt.

### Do not allow graph evolution to weaken trusted boundaries

A refiner may propose procedural changes, but it must not autonomously change:

- permission policy;
- security validators;
- code-owned truth checks;
- arbitrary executable tool contracts;
- deletion/privacy boundaries.

Those remain separately reviewed authority layers.

### Do not confuse procedural structure with factual truth

A learned graph edge saying `A -> B` is evidence that a procedure often works
under some conditions. It is not evidence that the facts assumed by `B` are
true in the current task. Factual evidence must still come through Motoko's
normal source-grounded retrieval and tool results.

## Recommended Motoko experiment

This paper is strong enough to justify an eventual focused prototype, but the
right first experiment is small and derived from existing Motoko artifacts.

### Phase A: build an inspectable procedural projection

For a narrow set of existing repository/goal workflows, generate a read-only
`procedural-graph-v1` artifact over stable existing IDs.

Candidate node classes:

```text
skill
handler
action kind
validator/checker
goal phase
status
```

Candidate edge fields:

```text
from_id
relation
to_id
condition
guidance
pitfalls
source
validation_status
```

Do not let the graph define permissions or execute actions.

### Phase B: compare retrieval/invocation strategies

On existing or synthetic long-horizon fixtures, compare:

1. current Motoko behavior;
2. independent top-k procedural skill retrieval;
3. current-state localization + raw local graph neighborhood;
4. current-state localization + deterministic neighborhood rendering;
5. current-state localization + conditional LLM-generated guidance.

Measure:

- task completion;
- required-step recall;
- tool/action ordering errors;
- repeated/unproductive actions;
- premature termination;
- irrelevant skill activations;
- solver turns/steps;
- prompt tokens;
- extra model calls and latency;
- validator failures;
- source/provenance visibility.

### Phase C: test topology-specific failure attribution

Create fixtures where the same skill content is held constant but one edge is
missing, wrong, or has an incorrect condition. Verify that diagnostics can
identify a topology failure rather than proposing unnecessary edits to the
skill itself.

### Phase D: review-first topology evolution

Allow a curator/refiner to propose graph-only edits from failed and successful
traces. Every candidate should remain isolated until it passes:

- schema and structural validation;
- no-dangling-node/path checks;
- permission/security invariants;
- activation/localization tests;
- held-out task evaluation;
- regression caps;
- leakage checks;
- explicit review while the feature remains experimental.

Keep rejected candidate fingerprints and concise reasons as negative evidence.

### Phase E: determine whether procedural graphs deserve a permanent layer

Promote the graph only if it solves a repeatable class of Motoko failures better
than simpler alternatives such as richer skill metadata or goal-state routing.

The success criterion is not that a graph can represent Motoko's procedures.
Almost anything can be represented as a graph. The criterion is that explicit
transition structure measurably improves long-horizon competence, diagnostics,
and self-improvement enough to justify its complexity.

## Current recommendation

Keep this paper on the high-priority procedural-memory/self-improvement
watchlist.

The most actionable ideas for Motoko are:

1. model procedural memory as relationships between procedures, not only as
   independent skill documents;
2. localize procedure selection from verified working state whenever possible;
3. retrieve a bounded connected neighborhood so prerequisites and failure paths
   travel with the candidate action;
4. attach explicit `condition`, `guidance`, and `pitfalls` semantics to
   transitions;
5. treat topology/routing mistakes as their own diagnosable failure class;
6. let candidate topology evolve from trajectories, but only through structural
   checks, held-out evaluation, regression controls, and review;
7. retain compact rejection memory so failed structural changes are not
   repeatedly rediscovered;
8. preserve Motoko's current hard boundaries: procedural guidance may steer,
   but trusted validators and real evidence decide what is true and what is
   allowed.

Taken together with Recuris, the paper strengthens a broader design direction:
Motoko's future competence is likely to come not merely from retrieving more
text, but from combining **authoritative working state, source-grounded factual
retrieval, structured procedural memory, state-conditioned invocation, and
independently validated learning from experience**.

## References

- Lu, Y., Chen, Y., Wu, S., and Arık, S. Ö. (2026). *Procedural Graphs:
  Self-Evolving Execution Structures for LLM Agents*. arXiv:2609.09153:
  <https://arxiv.org/abs/2609.09153>
- Paper HTML:
  <https://arxiv.org/html/2609.09153v1>
- Paper PDF:
  <https://arxiv.org/pdf/2609.09153>
- Recuris: *Recursive Experiential-Working Memory Evolution for Long-Horizon
  Agent Harnesses*:
  <https://arxiv.org/abs/2608.24876>
- CoALA: *Cognitive Architectures for Language Agents*:
  <https://arxiv.org/abs/2309.02427>
- MemP: *Exploring Agent Procedural Memory*:
  <https://arxiv.org/abs/2508.06433>
- AutoGuide: *Automated Generation and Selection of Context-Aware Guidelines
  for Large Language Model Agents*:
  <https://arxiv.org/abs/2307.03493>
- Agent Workflow Memory (AWM):
  <https://arxiv.org/abs/2409.07429>
- FlowBench: workflow-guided planning for LLM agents:
  <https://arxiv.org/abs/2406.14884>

As of 2026-09-10, the arXiv paper does not link an official public code
repository. If an implementation is released later, this note should be updated
to inspect the actual graph schema, localization logic, mutation engine, and
validation gate rather than relying only on the paper description.