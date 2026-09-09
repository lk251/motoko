# Deferred Project: Local-Model NixOS Engineering Agent for `nixos-configs`

Date: 2026-09-09

Status: deferred design and evaluation project. No implementation is authorized by
this document.

## Scope Boundary

This project has one narrow objective:

> Make a locally served, roughly 27B-class model as capable as practical at
> understanding, changing, validating, deploying, and diagnosing the NixOS
> systems whose declarative configuration and operating procedures live in the
> `nixos-configs` repository.

The current reference model is Qwen3.8-27B. The design should remain model-
agnostic enough to adopt future local models in the same practical hardware and
parameter class, for example a future Qwen 4 27B-class successor if and when an
appropriate model exists. Do not bake Qwen3.8-specific prompt quirks into the
architecture unless an eval demonstrates that the gain justifies the coupling.

This is **not** a project to make Motoko a general-purpose coding agent, host
administrator, personal-computer controller, web agent, or cloud automation
framework. It is specifically about `nixos-configs` and the NixOS systems that
repository describes.

This document deliberately records a possible system that is broader than
Motoko's current authority boundary. A prototype may live entirely outside
Motoko, for example on the OpenHands Software Agent SDK or OpenWorker. If the
prototype proves valuable, a later design review can decide whether any proven
pieces belong in Motoko. This document does not implicitly authorize arbitrary
shell execution, network access, service control, sudo, or deployment inside
Motoko.

Machine-specific accounts, hostnames, checkout paths, remotes, sockets,
privilege maps, and deployment commands remain owned by `nixos-configs` and
should not be copied into this public repository. The intended architecture
should reuse that repository's reviewed operational and security boundaries
rather than duplicating them here.

## Executive Conclusion

The original framing, "what retrieval pipeline should Motoko use for
`nixos-configs`?", is too narrow for the actual goal.

Retrieval is useful, but the stronger abstraction is a **specialized NixOS
engineering/operator agent with a high-quality Agent-Computer Interface (ACI)
and a closed verification loop**.

The central design question is therefore not merely:

> Which files should the model retrieve?

It is:

> What observations, deterministic semantic queries, editing abilities,
> verification procedures, and carefully bounded operational actions should a
> local model be able to request so that it can reason reliably about the
> repository and the machines it declares?

A capable end state should combine:

```text
                       local ~27B model
                              |
                      agent reasoning loop
                              |
        +---------------------+---------------------+
        |                     |                     |
        v                     v                     v
   repository            Nix semantics          live systems
   interface              interface              interface
        |                     |                     |
 files / search          option evaluation      service state
 repo map                definitions/provenance journal excerpts
 Git history             builds/derivations     boot/generation state
 pinned inputs           closure changes        hardware/network facts
 docs/runbooks           checks                 bounded diagnostics
        |                     |                     |
        +---------------------+---------------------+
                              |
                       isolated worktree
                              |
                    deterministic validation
                              |
                        human approval
                              |
                   narrow reviewed deployment
                              |
                     post-deploy verification
```

Retrieval becomes one **context-acquisition subsystem** inside this larger
architecture. It should not be the organizing principle of the whole system.

## Why This Direction Fits the Model Class

Qwen's published Qwen3.8-27B results are unusually relevant because its
software-engineering benchmarks are evaluated through interactive coding-agent
harnesses rather than by simply placing an entire repository in one prompt. The
Qwen3.8-27B model card reports strong agentic terminal and repository-level
coding results and states that SWE-bench Pro, NL2Repo-Bench, DeepSWE, and
QwenSWEBench evaluations use a Claude-Code-style harness, generally with a
256K context window. These are vendor-reported benchmark results, not direct
evidence of NixOS competence, but they strongly suggest that the model is meant
to be used through an interactive software-agent interface rather than as a
one-shot RAG chatbot.

The project should exploit that strength. A 27B local model is likely to gain
more from a crisp, low-ambiguity interface to authoritative tools than from
large amounts of vaguely relevant context.

The design should also assume that future same-class models will differ in
reasoning style and tool-use quality. The interface, deterministic tools, tests,
and eval suite should carry the durable competence; model replacement should be
comparatively cheap.

## First-Principles Model of the Problem

### 1. The repository is desired/configured state, not the whole machine

Even a complete declarative NixOS repository is only one layer of truth. A
reliable assistant must distinguish at least:

```text
configured
    -> evaluated
        -> built
            -> installed
                -> activated
                    -> booted
                        -> live-verified
```

These states must never collapse into one generic claim such as "it is done" or
"the machine has X".

Examples:

- A file can define an option without that module being part of a host.
- A host can evaluate successfully but fail to build.
- A closure can build but never be installed.
- A generation can be installed but not active.
- The active generation can differ from the booted generation.
- Declarative intent can be correct while a service is failing at runtime.

A source-retrieval system alone cannot resolve those distinctions.

### 2. NixOS source text is not the same thing as NixOS semantics

NixOS configuration is a module evaluation system, not merely a collection of
configuration files. Modules recursively import other modules, declare options,
define values, and merge those definitions according to option types and module
semantics. `lib.mkIf`, `mkMerge`, defaults, priorities, overrides, submodules,
Home Manager composition, flake outputs, and other mechanisms mean that the
model should not be asked to mentally emulate the module system whenever Nix
itself can answer the question.

The official Nix module-system documentation describes `lib.evalModules` as
returning the evaluated `options` and `config` trees, and the NixOS module
documentation describes evaluation as recursively collecting modules,
collecting option declarations, and merging each option's definitions according
to its type.

Therefore one of the highest-value capabilities is a safe semantic interface to
**evaluated Nix**, not a better embedding model.

### 3. Runtime diagnosis requires runtime evidence

A question such as "why is SSH not working?" may require all of the following:

- source definitions;
- the host's effective evaluated option value;
- which definitions contributed that value;
- whether the intended generation built;
- whether it is installed and active;
- service state;
- recent journal evidence;
- listeners/interfaces/firewall facts;
- relevant Git changes.

The assistant therefore needs controlled live observation in addition to source
inspection.

### 4. Let deterministic systems prove what they can prove

The model should reason, form hypotheses, choose investigations, propose edits,
and interpret evidence. Deterministic tools should answer questions that have a
more authoritative computational answer:

- Git should answer history and diff questions.
- Nix should answer evaluation/build questions.
- systemd should answer unit-state questions.
- the kernel and proc/sys interfaces should answer live system facts.
- validation scripts should enforce repository-specific invariants.

Do not spend model intelligence pretending to be these systems.

### 5. Verification is part of reasoning, not an afterthought

The system should be organized around:

```text
inspect -> hypothesize -> change -> evaluate -> build/test -> observe -> revise
```

rather than:

```text
retrieve -> answer
```

If a proposed edit fails evaluation or a build, that observation should return
to the same reasoning loop so the model can diagnose and iterate.

### 6. Git worktrees are a natural transaction/isolation boundary

Give the model broad freedom in an isolated worktree rather than narrow freedom
in the canonical checkout. A failed or destructive code edit then damages only
the disposable task workspace. Human-reviewed Git artifacts become the handoff
boundary.

The canonical branch remains human-controlled and deployable according to the
rules in `nixos-configs`.

### 7. Context quality matters more than context volume

A large context window is useful, but it is not a reason to dump the entire
repository, full journals, large diffs, or every transitive dependency into the
prompt.

The model should receive progressively disclosed, bounded observations and ask
for more detail as its hypothesis develops. This is especially important for
~27B local models, where irrelevant context can consume attention that would be
better spent on the few facts that decide the task.

## Agent-Computer Interface as the North Star

SWE-agent's core research result is directly applicable: language-model agents
benefit from interfaces designed for the model as an end user. Its ACI work
shows that tool and observation design materially changes software-agent
performance. Practical lessons included concise repository search output,
bounded file views, automatic syntax checking after edits, and explicit success
messages when commands produce no output.

For this project, the relevant ACI is not merely "terminal + editor". It should
be a **NixOS-specific engineering interface**.

A target tool surface might eventually include the following families.

### Repository tools

```text
repo_map()
repo_search(query)
repo_read(path, range)
repo_status()
repo_diff()
repo_history(path_or_query)
repo_blame(path, range)
repo_show(commit)
```

The implementation may often use ordinary mature command-line tools such as
`rg`, `git`, and a bounded file reader. The important requirement is to return
compact, unambiguous observations to the model.

### Nix semantic tools

Conceptual API:

```text
nix_hosts()
nix_host_eval(host, attr)
nix_option(host, option)
nix_option_definitions(host, option)
nix_option_declaration(host, option)
nix_flake_check()
nix_build_host(host)
nix_derivation(...)
nix_closure_diff(before, after)
```

These names are illustrative, not an implementation commitment.

The strongest tools should expose both value and provenance where Nix makes
that available. For an option question, an ideal observation is closer to:

```text
host: <host>
option: services.example.enable
value: true

definitions:
  path/to/module-a.nix:<line>
  hosts/<host>/configuration.nix:<line>

declarations:
  <pinned-nixpkgs>/nixos/modules/...:<line>

evaluation_status: success
```

than to a pile of grep matches.

The tool implementation should use fixed, code-owned evaluation shapes. The
model should choose safe parameters such as host and option name; it should not
receive an unrestricted privileged Nix-expression execution capability merely
because an `nix eval` tool exists.

### Validation tools

```text
validate_repo()
validate_host(host)
build_host(host)
compare_host_closure(host, base_ref, candidate_ref)
run_relevant_tests(scope)
```

The harness should know the repository's reviewed validation commands and
produce structured summaries rather than requiring the model to rediscover the
same workflow every session.

### Live read-only host tools

Later phases may expose deliberately bounded observations such as:

```text
host_system_state(host)
host_generations(host)
host_failed_units(host)
host_service_status(host, unit)
host_journal(host, unit, since, limit)
host_boot_state(host)
host_kernel(host)
host_mounts(host)
host_network_interfaces(host)
host_network_listeners(host)
host_disk_state(host)
host_hardware_summary(host)
host_gpu_state(host)
```

These should return structured, capped results. For example, do not feed an
entire boot journal to the model by default. Summarize counts and relevant
units, retain enough exact text for diagnosis, and allow follow-up reads.

### Privileged action tools

Only after read-only competence is demonstrated should the project consider
operations such as:

```text
deploy_build(host)
deploy_test(host)
deploy_switch(host)
deploy_rollback(host)
host_reboot(host)
```

These must map to reviewed, code-owned procedures in `nixos-configs`, remain
host-scoped, show the exact intended effect, and require the level of explicit
human authorization defined by that repository. Never make "arbitrary model
shell with sudo" the privileged interface.

## Worktree and Shell Model

A useful capability/security split is:

```text
arbitrary model shell
    -> unprivileged
    -> isolated task worktree
    -> repository/build/evaluation/test tools

privileged machine operations
    -> typed code-owned actions only
    -> reviewed implementation
    -> explicit authorization
```

The model should normally be allowed to run ordinary unprivileged tools in its
own worktree because adaptive investigation is one of the main advantages of an
agent harness. Useful commands include repository search, Git inspection, Nix
evaluation/build commands, `jq`, and other explicitly available local developer
tools.

The model should not be allowed to turn a shell command into arbitrary root
access or arbitrary cross-host execution.

## The Repository World Model

The model benefits from a compact persistent map of `nixos-configs` before it
begins a task. This map should be deterministic where practical and should not
attempt to summarize every line of code.

Useful entities include:

- declared flake outputs;
- active hosts versus build-only artifacts;
- `hosts/<host>/` roots;
- shared `modules/`;
- Home Manager modules and imports;
- overlays and local packages;
- installer/bootstrap paths;
- operational/security runbooks;
- relevant checks and helper scripts;
- important ownership boundaries from repository documentation.

For Nix-specific structure, record relationships such as:

- flake output -> host module tree;
- module -> imported modules;
- host -> shared modules;
- Home Manager user -> imported user modules;
- option declaration -> defining module;
- option -> definitions by host;
- local package/overlay -> referring configurations;
- runbook -> host/workflow scope.

Aider's repository-map design is a useful precedent: send the model a concise
map of important repository definitions and relationships, then let it request
source detail when needed. RepoGraph and AutoCodeRover provide research evidence
that repository-level structure can improve navigation and issue resolution.

For Nix, the graph should reflect Nix concepts rather than mechanically copying
a Python call graph.

## Nix-Aware Parsing and Indexing

If a persistent index is built, `.nix` should not be chunked primarily by a
fixed token count.

Prefer meaningful units such as:

- complete option definitions;
- option declarations;
- `imports` blocks;
- `home-manager.users.<name>.imports` blocks;
- `lib.mkIf` / `mkMerge` expressions when they form coherent policy units;
- meaningful `let` bindings or helper functions;
- flake output definitions;
- package/overlay definitions;
- Markdown sections and runbook steps;
- shell functions or coherent script regions.

A Nix parser such as a tree-sitter grammar may be useful, but parser choice
should be eval-driven and should not become a prerequisite for the first
prototype. Simple exact search plus actual Nix evaluation may outperform a
large indexing project for many tasks.

Distinguish Nix language `import` from the NixOS module-system `imports`
mechanism. They have different semantics and graph edges should not conflate
them.

## Evaluated Nix as a First-Class Knowledge Source

This is the most important Nix-specific capability in the proposed system.

For each declared host, the agent should be able to ask for values and source
provenance from the evaluated configuration rather than infer them only from
text.

Relevant underlying information includes the evaluated
`nixosConfigurations.<host>.config` and `.options` trees. The Nix module system
retains declaration and definition information for options; the exact supported
query mechanism should be implemented and tested against the pinned Nixpkgs
version rather than assumed from memory.

This enables questions such as:

- What is the effective value of this option on this host?
- Which modules contributed definitions?
- Is this host-specific definition being overridden?
- Which hosts are affected by changing this shared module?
- Does this conditional module actually participate in this host role?

The model should use source retrieval to understand *why* the relevant code is
written the way it is, while Nix evaluation establishes what the declarative
system actually computes.

## Exact Pinned Upstream Source Is Part of the Environment

The assistant should not rely primarily on pretrained knowledge of NixOS or
Home Manager because that knowledge may refer to a different version.

`flake.lock` identifies the exact source revisions the repository uses. Give the
agent searchable/readable access, subject to the local security boundary, to
the pinned source trees for:

- Nixpkgs;
- Home Manager;
- relevant third-party flakes;
- other exact source inputs needed to understand the evaluated configuration.

Then questions such as "what does this option do?" or "where is this service
implemented?" can be answered from the actual version in use.

This is often more valuable than retrieving another chunk from the user's own
repository.

## Git as Authoritative Engineering Memory

Do not build an elaborate AI memory system to solve questions Git already
answers.

Git provides inspectable history for:

- why a workaround appeared;
- which change introduced a regression;
- whether an odd line is intentional;
- how a module evolved;
- what differed between a working and failing revision;
- what the model changed in the current task.

The agent should have excellent `log`, `show`, `diff`, `blame`, and history
search tools. Repository docs and dated reports should remain the higher-level
operational memory where the repository already uses them.

Model-authored long-term memory should be considered only for information that
is genuinely not represented in source, Git, runbooks, reports, or live state.

## Retrieval: Useful, but Demoted from the Center

The project should initially use four context-acquisition modes.

### 1. Exact and lexical search

Use path/file search, `rg`-style string search, option-path search, package
names, commands, error strings, and Git search. These signals are particularly
strong in configuration repositories because names and option paths are often
precise identifiers.

Sourcegraph's Cody documentation is useful evidence against assuming embeddings
are mandatory: Sourcegraph removed embeddings from its Enterprise context path
and states that its mature search mechanisms gave equal or better quality for
that use case. This is not proof that embeddings are useless, but it reinforces
that code search quality should be measured rather than assumed.

### 2. Deterministic repository map / graph

Use host/module/output/import/runbook relationships to guide navigation and to
expand a strong initial match into the small surrounding dependency context.

### 3. Interactive model-directed reading

Let the model inspect source as its hypothesis develops. Do not require one
retrieval pass to predict every file that will matter later in the trajectory.
RepoCoder's iterative retrieval/generation results and AutoCodeRover's iterative
program-structure search support this general principle.

### 4. Optional semantic search

Dense embeddings are useful for fuzzy questions, especially prose and
conceptual documentation, for example:

- Where is the unusual GPU wake issue documented?
- Which files discuss remote-build security?
- Where did we document the rationale for this operational constraint?

Use semantic retrieval as an additional recall lane, not as an authority layer.
Exact identifiers, graph relationships, Nix evaluation, Git, and live evidence
should be allowed to outrank a semantically similar chunk.

If hybrid retrieval is later justified, a sensible candidate stack is:

```text
exact/BM25
+ path/name/rare-term boosts
+ dense semantic search
+ Nix structural graph candidates
+ Git recency/history candidates when relevant
+ explicit host/option scope
-> candidate fusion
-> bounded graph expansion
-> rerank
-> compact evidence packing
```

Do not build this entire stack before demonstrating that simpler interactive
search is a bottleneck.

## Progressive Disclosure for ~27B Models

The ACI should optimize observation density.

Bad default:

```text
journalctl -b     -> thousands of lines in context
```

Better:

```text
boot log lines: 4,238
errors: 14
warnings: 81
failed/relevant units:
  example.service: 4 errors
  first relevant line: ...
  last relevant line: ...

request more with host_journal(unit=..., limit=...)
```

Bad default:

```text
grep recursively -> hundreds of matching source lines
```

Better:

```text
7 files matched
ranked paths: ...
open a file/range for detail
```

SWE-agent's ACI work found concise search results and bounded file views more
useful than flooding the model with surrounding text. Treat this as a design
hypothesis to reproduce in the private Nix eval suite rather than as a universal
constant.

## Optional Fresh-Context Read-Only Explorer

OpenWorker contains a particularly useful idea for local-model context economy:
its `explore` tool spawns a read-only child agent with a fresh context window,
allows it to search/read Git and source, and returns only the final report to the
main agent. Intermediate reads never enter the parent's active context.

A similar facility could help questions such as:

> Map how networking is structured across the repository and report only the
> important relationships with source locations.

Use this only where it measurably improves answer quality or prevents context
pollution. Do not introduce role-playing multi-agent complexity merely because
multiple agents are fashionable. A read-only explorer is attractive because it
solves a concrete context-management problem and has a sharply limited
permission boundary.

## Framework Candidates

The framework decision should be made empirically against `nixos-configs`, not
by popularity.

### OpenHands Software Agent SDK

OpenHands is currently the strongest candidate for the initial maximum-
capability prototype because the Software Agent SDK is explicitly designed for
agents that work with code. It provides agent/conversation/workspace primitives,
terminal and file-editor tools, custom tools, local or ephemeral workspaces, and
an Agent Server option. Its architecture is therefore well aligned with a
specialized engineering ACI.

The project should evaluate the **Software Agent SDK**, not assume that the
entire OpenHands product/UI stack must be adopted.

OpenHands also documents local-LLM use through OpenAI-compatible endpoints. The
current `nixos-configs` deployment already has a stronger, NixOS-owned local
inference isolation boundary. Preserve that boundary. If an OpenHands client
requires an HTTP base URL while the approved model route is a forwarded Unix
socket, use a tiny lifecycle-bound client-side loopback relay rather than
opening the inference API on the LAN. The exact topology belongs in
`nixos-configs`.

OpenHands's name may be less familiar in terminal-agent discussions than Codex
or Claude Code partly because its history is different and its clean Software
Agent SDK is a newer layer of the project. Lack of personal exposure is not a
useful quality signal; benchmark performance on the actual workload is.

### OpenWorker

OpenWorker is already integrated into the NixOS environment and should be a
serious comparison baseline, not discarded.

Its strongest ideas for this project are governance and context control:

- a permission engine that separates read-only planning, interactive approval,
  and more autonomous modes;
- path- and command-aware authorization decisions;
- hard human-only floors and an audit trail in the broader design;
- a read-only `explore` subagent with its own context window;
- existing integration with the reviewed local-model transport boundary.

OpenWorker is a broader local coworker rather than a software-engineering SDK,
so building a deeply specialized Nix engineering environment may be less
natural than with OpenHands. That is a hypothesis, not a conclusion. Compare
both using the same tasks.

### Motoko

Do not begin by expanding Motoko until the project has measured what the local
model actually lacks.

Motoko already contains useful ingredients such as source grounding, typed
review-first actions, worktrees, retrieval machinery, local model routing, and
an inspectability-first security philosophy. However, converting Motoko into a
full engineering agent would require substantial ACI, shell, execution,
workspace, and verification work and would broaden current security boundaries.

A better sequence is:

1. discover the best-performing ACI externally;
2. measure which tools and retrieval mechanisms matter;
3. decide whether the successful system should remain independent, use
   OpenHands/OpenWorker directly, or contribute a carefully bounded subset back
   into Motoko.

## OpenHands vs OpenWorker: Working Hypothesis

For this one narrow project, the current prior is:

| Requirement | OpenHands SDK | OpenWorker |
| --- | --- | --- |
| Repository/software engineering as core purpose | Strong | Supported but broader |
| Interactive shell/edit/test loop | Strong | Strong |
| Custom Nix-specific tool substrate | Strong SDK fit | Extensible tools/MCP |
| Isolated workspaces | First-class | Workspace/path governed |
| Local model | Supported via compatible endpoint | Already integrated locally |
| Existing `nixos-configs` deployment work | None | Strong |
| Fine-grained permission/governance ideas | Good | Particularly relevant |
| Fresh-context read-only explorer | Possible/custom | Already present |
| Best initial use | Capability prototype | Baseline and possible final system |

The current recommendation is to prototype with OpenHands SDK while preserving
and benchmarking OpenWorker. The result could reasonably reverse the prior.

## Security and Authority Architecture

The project should preserve the principle that inference, source access, and
host authority are separate capabilities.

### Model-serving boundary

Reuse the existing NixOS-owned model-serving isolation. The model server does
not need repository filesystem access merely because the agent using it has
repository access. Only inference request/response data should cross that
boundary.

### Workspace boundary

The engineering agent receives an unprivileged isolated task worktree. It can
inspect and modify that workspace and run approved unprivileged developer
commands.

### Secrets

Do not feed secrets to the model merely because the repository can refer to
secret-management machinery. Secret ciphertext, public identifiers, or
configuration may be source evidence when already permitted; private keys,
passwords, tokens, PINs, recovery material, and plaintext secrets must remain
outside the agent's context and logs.

### Live observation boundary

Read-only host observations should come through a narrow forced-command/RPC
surface or an equivalent reviewed mechanism. Avoid giving the model a generic
remote shell simply to discover whether a service is active.

### Mutation boundary

Repository edits happen in the task worktree. Privileged system changes happen
only through typed, reviewed procedures with explicit authorization.

### Evidence labeling

Every important observation should record its evidence class so the model can
reason about what it actually proves. Candidate labels include:

```text
source-code
documentation
git-state
evaluated-config
build-result
installed-state
activated-state
booted-state
live-system
derived-summary
```

A derived summary must never silently become equivalent to a live or evaluated
fact.

## Example Target Trajectory

A task such as:

> Enable a hardware/service feature on one host without changing unrelated
> machines.

should eventually look approximately like:

1. Identify the requested host and its declared role.
2. Load the compact host/module/runbook map.
3. Inspect exact host and shared-module source.
4. Search existing option definitions and related Git history.
5. Query the host's current effective evaluated options.
6. Inspect the exact pinned upstream option/module implementation if needed.
7. Determine which sibling hosts or shared roles could be affected.
8. Form a minimal proposed change.
9. Edit only the isolated worktree.
10. Evaluate the target host.
11. Evaluate other affected roles/topologies where the repository policy
    requires it.
12. Run relevant checks.
13. Build when acceptance requires a real build.
14. Inspect closure/change consequences where useful.
15. Present the diff, evidence, failures/skips, and remaining uncertainty.
16. Ask for deployment authorization if deployment is in scope.
17. Use the reviewed deployment path.
18. Run proportionate post-deploy live verification.
19. Report configured/evaluated/built/installed/activated/booted/live-verified
    states separately.
20. Produce a Git-native handoff/commit according to repository policy.

The point is not that every task needs twenty steps. The point is that the
system has access to the right evidence and verification layers when they are
necessary.

## Evaluation-First Development Plan

Do not choose the final architecture by intuition alone. Build a private,
repository-specific evaluation suite from real historical tasks.

### Task corpus

Start with roughly 20-50 tasks, growing as failures are discovered. Prefer
problems previously solved by the maintainer or a strong coding agent so there
is usable ground truth and validation evidence.

Representative categories:

1. **Locate**
   - Find where a host behavior is defined.
   - Find the relevant NixOS/Home Manager option.

2. **Explain effective configuration**
   - Explain why a host receives a package or service.
   - Identify all definitions that contribute to an option.

3. **Impact analysis**
   - Determine which hosts/roles would be affected by a shared-module edit.
   - Distinguish a host directory from a declared active flake output.

4. **Small modification**
   - Add/change one host-scoped setting without changing siblings.
   - Refactor a genuinely shared behavior into a reusable module.

5. **Evaluation/build failure**
   - Diagnose a Nix evaluation error.
   - Diagnose a build failure from bounded logs.

6. **Regression/history**
   - Identify the change that likely introduced a failure.
   - Explain why a workaround exists from Git history and documentation.

7. **Pinned-upstream reasoning**
   - Explain an option from the exact Nixpkgs/Home Manager revision in use.

8. **Live diagnosis**
   - Explain why configured intent and runtime state differ using read-only
     probes.

9. **Deployment verification**
   - Given explicit authority, perform or plan a safe deployment and distinguish
     activation from actual live verification.

### Metrics

Measure more than final answer similarity:

- task success;
- correct file/span localization;
- evaluated-option/value accuracy;
- provenance correctness;
- build/test success;
- sibling/role regression avoidance;
- unnecessary files/lines changed;
- fabricated commands/options/facts;
- unsafe or over-broad action attempts;
- context tokens consumed;
- tool calls;
- wall-clock latency;
- model inference time;
- recovery from failed hypotheses;
- quality of final evidence report.

### Required ablations

Run the same tasks through progressively stronger configurations.

Suggested sequence:

```text
A. existing OpenWorker Code baseline
B. OpenHands SDK: terminal + file editor only
C. B + compact repository map
D. C + Nix semantic/evaluated-option tools
E. D + exact pinned-upstream source access
F. E + improved Git/history tools
G. F + read-only live host probes (diagnostic tasks only)
H. G + optional semantic/hybrid retrieval
I. selected configurations + fresh-context read-only explorer
```

The precise ordering may change, but keep the principle: every additional
subsystem must earn its complexity.

Important comparisons include:

- no embeddings vs embeddings;
- raw shell `nix eval` vs typed Nix semantic tools;
- no repo map vs repo map;
- full raw logs vs bounded structured observations;
- one-context exploration vs fresh-context read-only exploration;
- OpenHands vs OpenWorker under the same model and task budget.

## Phased Implementation

### Phase 0 - Build the benchmark before the architecture

- Select historical `nixos-configs` tasks.
- Record expected source/evidence, relevant validation, and unacceptable
  changes/actions.
- Establish repeatable model settings and inference route.
- Preserve trajectories so failure classes can be inspected.

Exit criterion: enough tasks to make architecture comparisons meaningful.

### Phase 1 - Minimal interactive engineering agent

Prototype Qwen3.8-27B with an established software-agent harness, preferably
OpenHands SDK as the first candidate, in an isolated `nixos-configs` worktree.
Provide only:

- terminal;
- file editor/viewer;
- Git;
- existing repository instructions.

No embeddings, graph database, generalized Motoko integration, or live machine
access.

Compare directly with the existing OpenWorker Code path.

Exit criterion: a trustworthy baseline and a list of concrete failure modes.

### Phase 2 - Nix semantic interface

Add the highest-value typed queries:

- host discovery;
- evaluated attribute/option values;
- option definition/declaration provenance;
- bounded host evaluation/checks;
- host build result where appropriate.

Prioritize correctness and evidence location over a broad number of tools.

Exit criterion: measurable improvement on Nix-specific reasoning and fewer
model mistakes about effective configuration.

### Phase 3 - Repository map and exact pinned source

Add:

- compact deterministic Nix repository map;
- host/module/import relationships;
- exact pinned dependency source browsing;
- improved Git-history tools.

Only add semantic retrieval if benchmark failures show that exact search and
interactive browsing still miss conceptually relevant material.

### Phase 4 - Read-only live system observation

Add narrow, structured host probes for diagnosis. Keep live access read-only.
Test output caps, timeouts, disconnected hosts, permission failures, and stale
observations.

Exit criterion: the agent can correctly distinguish source/evaluated state from
live state and solve representative diagnostic tasks without generic remote
shell authority.

### Phase 5 - Controlled operational actions

Only after the agent demonstrates strong read-only competence:

- expose reviewed deployment/test/rollback operations;
- require explicit human authorization according to risk;
- automatically perform post-action verification;
- preserve complete action/evidence logs without storing secrets.

### Phase 6 - Decide the product boundary

Use measured results to choose among:

- keep the Nix agent as a dedicated OpenHands-based tool;
- keep/use OpenWorker if it performs better or provides the best governance
  trade-off;
- retain a small dedicated harness of our own;
- integrate selected proven pieces into Motoko after a separate security and
  product-boundary review.

Do not assume Motoko integration is the definition of success.

## What Not to Build First

Avoid premature investment in:

- a vector database;
- GraphRAG-style generated knowledge graphs;
- repository-wide model summaries;
- unrestricted remote shell access;
- unrestricted sudo;
- a custom full coding-agent framework inside Motoko;
- autonomous multi-agent role hierarchies;
- general personal memory for repository facts already in Git/docs;
- giant prompts containing the repository or full logs;
- deployment autonomy before read-only diagnosis is excellent.

Each may become justified later, but none is the first-principles core.

## Research and Industry Lessons to Preserve

### SWE-agent / Agent-Computer Interface

SWE-agent argues and experimentally demonstrates that the interface presented to
a model can materially affect software-engineering performance. Its practical
ACI findings favor bounded file views, succinct search output, and immediate
validation feedback.

Project lesson: optimize the **interaction protocol and observations**, not just
the prompt or retriever.

### AutoCodeRover

AutoCodeRover represents repositories as programs and uses structure-aware,
iterative search rather than treating a project as a flat bag of files.

Project lesson: Nix-specific structure should guide navigation, but the
structure should reflect the Nix module/host world rather than generic AST
fashion.

### RepoGraph

RepoGraph reports improvements from adding repository-level graph/navigation
information to multiple software-engineering systems.

Project lesson: a compact host/module/option graph is worth testing as an
additional navigation signal.

### RepoCoder

RepoCoder finds iterative retrieval/generation better than a one-shot vanilla
retrieval baseline for repository-level code completion.

Project lesson: permit retrieval and investigation to evolve as the model learns
from intermediate evidence.

### Agentless

Agentless shows that relatively simple localization -> repair -> validation can
compete strongly with complex autonomous-agent systems.

Project lesson: do not confuse agent complexity with capability. Prefer the
simplest workflow that wins the private Nix benchmark.

### Aider repository maps

Aider maintains a token-budgeted map of important repository symbols to help the
model understand the codebase beyond currently opened files.

Project lesson: a compact persistent map is a useful bootstrap, especially for a
smaller local model.

### Sourcegraph search over mandatory embeddings

Sourcegraph states that its Enterprise Cody context path moved away from
embeddings toward its established search mechanisms with equal or better
quality in its environment.

Project lesson: embeddings are an optional tool, not a prerequisite for serious
code intelligence.

### OpenWorker permissions and explorer

OpenWorker treats governance as architecture and includes a fresh-context,
read-only code explorer.

Project lesson: separate model reasoning from code-owned authority, and consider
fresh-context exploration as a targeted solution to context pollution.

### OpenHands Software Agent SDK

OpenHands provides a modern software-agent substrate with workspaces, terminal,
editor, custom tools, agent/conversation primitives, and local-model support.

Project lesson: use an existing engineering substrate to discover what works
before recreating it inside Motoko.

## Research Caveats

- Public software-agent benchmarks are not NixOS benchmarks.
- Vendor model-card numbers may not reproduce under local quantization, local
  inference settings, different context lengths, or a different tool harness.
- A technique that improves SWE-bench localization may not improve a compact,
  carefully documented Nix configuration repository.
- More retrieval is not monotonically better; irrelevant but plausible context
  can distract the model.
- A framework's popularity or the maintainer's familiarity with its brand is
  weak evidence compared with performance on the private task suite.

The private `nixos-configs` eval is the final arbiter.

## Success Criteria

This project succeeds when a locally served ~27B-class model can reliably act as
a high-quality assistant for `nixos-configs` and can, within its granted scope:

- locate and explain relevant configuration;
- determine effective evaluated host state from Nix rather than guess;
- inspect the exact upstream source revisions in use;
- understand host/shared-module impact;
- make minimal changes in isolation;
- run the right evaluation/build/test loop;
- diagnose failures from concise authoritative evidence;
- use Git history as engineering memory;
- distinguish configured/evaluated/built/installed/activated/booted/live state;
- inspect live systems through safe read-only tools when needed;
- request privileged actions only through reviewed typed interfaces;
- provide a clear evidence-backed handoff to the human operator;
- achieve these results without depending on a cloud model or cloud memory
  backend.

The desired end state is not that the local model "knows the whole repo" in its
prompt. It is that the model can efficiently discover what it needs, ask the
right deterministic systems for authoritative answers, make a controlled
change, verify the result, and know which claims remain unproven.

## References

Primary/current implementation sources should be preferred when revisiting this
project because agent frameworks and model serving change quickly.

- Qwen, `Qwen3.8-27B` model card:
  https://huggingface.co/Qwen/Qwen3.8-27B
- Qwen3.8 repository:
  https://github.com/QwenLM/Qwen3.8
- Yang et al., *SWE-agent: Agent-Computer Interfaces Enable Automated Software
  Engineering*:
  https://arxiv.org/abs/2405.15793
- SWE-agent ACI notes:
  https://github.com/SWE-agent/SWE-agent/blob/main/docs/background/aci.md
- OpenHands Software Agent SDK:
  https://github.com/OpenHands/software-agent-sdk
- OpenHands local-LLM documentation:
  https://github.com/OpenHands/docs/blob/main/openhands/usage/llms/local-llms.mdx
- OpenHands SDK introduction/custom-tool examples:
  https://www.openhands.dev/blog/introducing-the-openhands-software-agent-sdk
- OpenWorker:
  https://github.com/andrewyng/openworker
- OpenWorker permission engine:
  https://github.com/andrewyng/openworker/blob/main/coworker/permissions.py
- OpenWorker read-only explorer:
  https://github.com/andrewyng/openworker/blob/main/coworker/tools/subagent.py
- Nixpkgs module-system documentation:
  https://github.com/NixOS/nixpkgs/blob/master/doc/module-system/module-system.chapter.md
- NixOS module overview:
  https://wiki.nixos.org/wiki/Module
- Aider repository maps:
  https://aider.chat/docs/repomap.html
- Sourcegraph Cody FAQ on context/search and embeddings:
  https://sourcegraph.com/docs/cody/faq
- Zhang et al., *RepoCoder: Repository-Level Code Completion Through Iterative
  Retrieval and Generation*:
  https://arxiv.org/abs/2303.12570
- Zhang et al., *AutoCodeRover: Autonomous Program Improvement*:
  https://arxiv.org/abs/2404.05427
- Ouyang et al., *RepoGraph: Enhancing AI Software Engineering with
  Repository-level Code Graph*:
  https://arxiv.org/abs/2410.14684
- Xia et al., *Agentless: Demystifying LLM-based Software Engineering Agents*:
  https://arxiv.org/abs/2407.01489
