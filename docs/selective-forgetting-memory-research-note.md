# Selective Forgetting and Graph-Based Long-Term Memory

Date: 2026-09-07
Status: research note; not an implementation decision

This note records findings from Rusu, Khanzadeh, and Alalfi (2026),
*Selective Forgetting: A Graph-Based Memory Framework for Long-Term LLM
Agents* (arXiv:2608.28978), and evaluates what is worth borrowing for Motoko's
current and deferred memory/retrieval architecture.

The paper is especially useful because its most important result is partly
negative: converting conversational turns into a knowledge graph did **not**
beat a flat vector baseline at a matched top-5 retrieval-root budget. The more
promising result is the explicit retention/forgetting mechanism. For Motoko,
the paper therefore argues more strongly for careful lifecycle management and
preservation of raw evidence than for replacing hybrid retrieval with GraphRAG.

Related Motoko documents:

- `docs/retrieval-pipeline-directions.md`
- `docs/deferred-projects.md`
- `docs/project-context.md`
- `docs/motoko.md`

## Paper summary

The framework has three stages:

1. **Update:** each conversational turn is passed through an LLM extractor that
   produces typed nodes and attributed edges. Node descriptors are embedded,
   de-duplicated by normalized title and embedding similarity, and then written
   or merged into a persistent graph.
2. **Retrieval:** entities referenced by the question are extracted and
   embedded; the top five matching nodes above a similarity threshold are used
   as roots, then expanded to a two-hop subgraph capped at 15 nodes. The
   resulting subgraph is serialized as answer context.
3. **Retention:** nodes receive an importance score combining recency, access
   frequency, graph degree centrality, and age in conversational turns. Nodes
   below a threshold are removed with their incident edges.

The paper's concrete scoring rule is:

```text
score = 0.35 * recency
      + 0.25 * frequency
      + 0.20 * centrality
      + 0.20 * turn_age_decay
```

The reported configuration uses a 90-day recency half-life, a 1,000-turn age
half-life, a pruning threshold of 0.10, and a nominal forgetting interval of
400 turns. These values were fixed a priori rather than tuned, so they should be
viewed as one experimental operating point rather than generally validated
retention constants.

## Main empirical results

The authors evaluate on 500 LongMemEval questions.

### Graph representation versus raw-turn vector retrieval

At a matched candidate-generation budget of five retrieval roots:

| System | Token F1 | LLM-judge correctness |
| --- | ---: | ---: |
| Graph RAG | 0.417 | 0.454 |
| Flat vector RAG | 0.468 | 0.536 |

The paired bootstrap difference in token F1 is -0.050 with a 95% confidence
interval of [-0.085, -0.016]. The graph representation therefore loses
measurable accuracy in this implementation rather than merely tying the flat
baseline.

The largest failure is particularly relevant to Motoko: questions that require
recalling a specific prior assistant turn have judged correctness of 0.607 with
the graph versus 0.911 with raw-turn vector retrieval. The paper attributes
this to extraction loss: decomposing a turn into entities and relations can lose
which recommendation, wording, qualification, or statement was actually
emphasized in the source turn.

Graph retrieval's only improvement on the paper's LLM-judge metric is for
`temporal-reasoning` questions (0.293 versus 0.278). This is weak evidence that
relational/temporal structure can help selected query classes, not evidence that
a graph should become the canonical memory representation.

The graph also underperforms on knowledge-update questions. The authors identify
conflict handling as one cause: an older attribute may survive when the memory
system should prefer the newer value. This is directly relevant to any Motoko
memory representation that consolidates evolving facts.

### Selective forgetting

The forgetting experiment starts from a persistent graph containing 27,021
nodes and 46,538 edges. Applying the forgetting module removes:

- 9.8% of nodes;
- 5.5% of edges;
- 9.5% of stored bytes (440.6 MB to 398.6 MB).

Token F1 changes from 0.292 to 0.293. LLM-judge correctness changes from 0.300
to 0.284. In the paired bootstrap, none of the four reported retrieval/answer
metrics show a statistically significant difference; for F1 the delta is
+0.001 with 95% CI [-0.015, +0.016], and for judged correctness it is -0.016
with 95% CI [-0.038, +0.006].

This is encouraging, but the point estimate still includes a 1.6-point judge
accuracy drop, and the confidence interval permits a somewhat larger loss. More
importantly, Experiment 2 applies the forgetting module once after ingestion is
complete. It does not demonstrate repeated destructive pruning over years of a
live personal corpus. Motoko should therefore treat the result as evidence that
a low-utility tail may be compressible, not as evidence that permanent
conversation deletion is safe.

## Implications for Motoko

### 1. Preserve raw conversational evidence as canonical

This paper strengthens an existing Motoko design direction: derived memories,
graph objects, dossiers, summaries, and working-state notes must not become the
only surviving representation of personal history.

Motoko's deferred long-horizon design explicitly keeps raw episodic history
searchable and distinguishes raw evidence from model-authored summaries and
interpretations. The paper provides direct empirical support for that choice:
structured extraction can discard exactly the surface form required for precise
recall.

If Motoko later adds a person/event/relationship graph, the graph should be a
**secondary retrieval index** whose nodes link back to source message IDs or
source spans. It should improve navigation, temporal reasoning, and multi-hop
candidate generation while raw turns remain available for final evidence.

Recommended invariant:

```text
raw source turn/span = authoritative evidence
structured node/edge = derived index with provenance
summary/dossier      = derived interpretation with provenance
```

No graph merge should silently erase the source material from which it was
derived.

### 2. Borrow selective retention, but initially as tiering rather than deletion

Motoko already ranks saved memories using lexical relevance, thread relevance,
manual importance, recency, pinning, and a `seen_count`-like signal. The paper
suggests a useful extension: lifecycle decisions can use *access history* and
possibly structural importance in addition to query-time relevance.

The safest Motoko interpretation is not "delete low-score memories." It is a
hot/warm/cold evidence hierarchy:

- **Hot:** actively indexed and cheap to retrieve; recently relevant, pinned,
  frequently accessed, or high importance.
- **Warm:** retained and searchable but excluded from the smallest/default
  candidate structures unless the query explicitly reaches it.
- **Cold:** raw source remains stored and recoverable, while disposable derived
  indexes/embeddings/summaries may be dropped and rebuilt on demand.

This can bound active-index size without turning an imperfect importance score
into irreversible information loss.

For personal conversations, explicit user deletion remains a separate lifecycle
operation and must not be conflated with automatic low-utility pruning.

### 3. Treat importance as a measured policy, not a copied formula

The paper's recency/frequency/centrality/age score is a useful design template,
but Motoko should not copy its weights or half-lives directly. The authors did
not sweep the retention parameters, and different kinds of personal memory have
very different utility curves.

Examples:

- a rarely referenced medical, legal, financial, relationship, or family fact
  may remain important after years;
- a frequently retrieved but now-superseded fact may deserve demotion;
- a highly connected graph node may be central because of extraction artifacts,
  not because it is semantically important;
- a pinned or explicitly user-authored memory should normally outrank automatic
  decay policy.

Any Motoko retention score should therefore include hard policy overrides and
be trained/tuned through Motoko-specific evals rather than intuition alone.

Candidate signals to evaluate include:

- user-assigned importance and pinning;
- provenance type (`user_statement`, raw turn, model inference, summary, etc.);
- last successful retrieval timestamp;
- successful retrieval count, not merely candidate-generation count;
- explicit contradiction/supersession state;
- source freshness and validity interval;
- relationship/graph centrality only if a graph layer exists;
- age by wall clock and by conversation turns;
- whether the item is reconstructible from retained raw evidence.

### 4. Separate "forgetting" of derived artifacts from forgetting of evidence

Motoko's artifact architecture already supports rebuildable indexes, vector
stores, evidence stores, dossiers, and other derived state. These are ideal
places to apply selective forgetting first.

A low-utility vector row, graph edge, cached summary, or topic projection can be
removed from the hot derived store when the original conversation/document
source remains available and the artifact can be deterministically rebuilt.
This gives many of the storage and retrieval-noise benefits of forgetting with
far less epistemic risk.

For derived artifacts, a retention policy should record why an artifact was
retired and which source/rebuild path can recover it. For raw evidence, the
default should be preservation until the user or an explicit retention policy
requires deletion.

### 5. Use graph structure selectively for query classes that justify it

The result argues against replacing Motoko's existing hybrid retrieval with a
single graph representation. A better future architecture is:

```text
raw turn/span retrieval
+ lexical/exact retrieval
+ dense semantic retrieval
+ deterministic temporal/task/entity signals
+ optional graph/relationship side-index
+ query-class-aware candidate fusion
+ reranking
+ source-span recovery
```

A graph lane is most plausible when the query asks about:

- chronology or temporal relations;
- relationships among people/projects/events;
- repeated patterns across sessions;
- multi-hop questions requiring several linked facts.

For queries that ask "what exactly did I/you say?", "what was the
recommendation?", or "what wording did we use?", raw turn/span retrieval should
be privileged.

### 6. Make update/supersession policy explicit

The paper's knowledge-update failures are a warning for Motoko's proposed typed
memory/working-state layer. "Merge similar memory" is not enough.

A future memory object should be able to express at least:

```text
current
supersedes <id>
contradicts <id>
valid_from / valid_until
uncertain / inferred / verified
```

For attributes where latest-state semantics are valid, deterministic
last-write-wins behavior may be appropriate. For ambiguous personal claims,
Motoko should retain both statements with provenance and let the reasoning model
see the conflict rather than silently choosing one.

## Recommended Motoko experiment

The paper is worth turning into an eval-driven retention experiment, but not a
production forgetting feature yet.

### Phase A: shadow retention scoring

Add a content-free or metadata-only maintenance pass over selected derived
memory artifacts. Compute candidate retention signals and record what *would*
be demoted or rebuilt, without deleting anything.

Evaluate whether low-score objects are actually irrelevant on a private/synthetic
long-horizon test suite.

### Phase B: reversible cold-tiering of derived artifacts

Allow low-value **derived** artifacts to leave the hot index while preserving:

- raw source evidence;
- artifact provenance/fingerprint;
- an inspectable reason for demotion;
- a deterministic or resumable rebuild path.

Measure active-store size, retrieval latency, recall, reranking quality, prompt
tokens, and rebuild churn.

### Phase C: optional graph side-index

Only after raw episodic retrieval is mature, test a lightweight graph of
people/events/projects/relationships as another candidate-generation lane.
Require every graph object to link to raw evidence and compare:

1. raw/hybrid retrieval only;
2. graph retrieval only;
3. hybrid retrieval + graph side-index.

Do not evaluate only aggregate F1. Break out at least:

- exact prior-turn recall;
- user fact recall;
- assistant recommendation recall;
- preference recall;
- knowledge updates/supersession;
- multi-session reasoning;
- temporal reasoning;
- contradiction handling;
- citation/source fidelity;
- low-frequency but high-importance facts.

### Phase D: repeated-retention stress test

The paper's one-shot pruning experiment is not enough for Motoko's intended
months/years horizon. A Motoko eval should simulate many retention cycles and
measure cumulative damage, including whether once-rare facts become important
again much later.

The key failure test is not merely "did average accuracy stay similar after one
prune?" It is:

> Can Motoko aggressively reduce disposable derived state while still recovering
> an old, rarely accessed but important fact from authoritative raw evidence when
> it becomes relevant again?

If the answer is yes, selective forgetting becomes a valuable *index and
artifact-lifecycle* technique without weakening long-horizon personal recall.

## Current recommendation

Do not replace Motoko's hybrid retrieval or raw conversation storage with this
paper's graph representation.

Do borrow three ideas:

1. treat retention/forgetting as a first-class memory lifecycle problem;
2. use recency, successful access frequency, importance, freshness, and possibly
   structural signals to manage the hot derived-memory working set;
3. test graph structure as an optional provenance-linked retrieval lane for
   temporal and relational questions, while preserving raw turns for exact
   recall.

The paper's negative GraphRAG result is as useful as its positive forgetting
result: it reinforces that abstraction and structure are not substitutes for
source evidence. For Motoko, the likely winning architecture is a layered
memory system that keeps raw history authoritative, derives structured indexes
for navigation, and selectively retires rebuildable low-utility artifacts rather
than irreversibly forgetting the user's past.

## References

- Rusu, T., Khanzadeh, S., and Alalfi, M. (2026). *Selective Forgetting: A
  Graph-Based Memory Framework for Long-Term LLM Agents*. arXiv:2608.28978:
  <https://arxiv.org/abs/2608.28978>
- Paper PDF:
  <https://arxiv.org/pdf/2608.28978>
- Official implementation, `Selective-Amnesia`:
  <https://github.com/skhanzad/Selective-Amnesia>
- LongMemEval:
  <https://arxiv.org/abs/2410.10813>
