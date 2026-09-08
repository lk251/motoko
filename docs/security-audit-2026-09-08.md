# Motoko security audit — 2026-09-08

Audited application revision: `3fe714edd75c57b2f346cf930a2a12003022d4cc`.

Implementation follow-up: the first three repair priorities (S01/S16, S02,
and S03) have been implemented in this revision. See the remediation
section below for scope, compatibility changes, and verification status.
The findings and reproductions below describe the original audited code.

During the initial audit and its extended follow-up, HEAD advanced through
`4194832` to `bbdd0069fbb60eeb43160f70ae4549761727ac42`. The intervening changes
affect only `docs/deferred-projects.md`, `docs/project-context.md`, and
`motoko.org`. Those changes were checked; application code and the pinned
runtime are unchanged. The follow-up reran all synthetic probes and
`nix flake check` against that unchanged application code.

This expanded report contains 15 findings and one explicitly identified trust
limitation (S15). It distinguishes executable reproductions, source-level
observations, and untested deployment assumptions. It is a repository-wide
security review with targeted adversarial testing, not an exhaustive proof of
every line, schedule, input, or branch.

This is a source audit of a personal, local harness. The relevant assets are
private documents and conversations, the accuracy of remembered information,
project files, and the user's control over execution. An approved local model
and a trusted OS account are part of the deployment assumptions. Motoko is not
being assessed as a public network service or a multi-tenant platform.

There are concrete implementation gaps worth fixing. The strongest are
document reads escaping the allowlist through symlinks, executable repository
content running during a read-only review, and script approvals failing to
cover imported local code. Exploitation of the execution findings requires
untrusted or subsequently modified repository/skill content. These findings
do not establish that the user's installation has been compromised.

The initial audit did not change application code, configuration, allowlists,
deployment, or Git refs; this report was its only added repository file.
The subsequent authorized remediation changes application code and tests as
described below. It does not deploy the application or alter live user state.

## Scope and validation

- Inventoried all 62 tracked files and parsed all Python sources. Reviewed
  security-relevant filesystem, subprocess, model-I/O, persistence, and
  rendering paths, including the facade and its callers.
- Refreshed the tracked-tree and reachable-history scan at `bbdd006`: 1,896
  unique blobs across 491 commits, or 473,874,755 bytes of historical blob
  content. The initial scan had covered 1,859 blobs across 484 commits.
- No matches were found for the tested private-key, GitHub, AWS, Slack,
  OpenAI, Stripe-live, credential-assignment, or credential-bearing URL
  patterns. This is a signature scan, not proof that arbitrary encoded or
  unusual secrets are absent. Deleted deployment documentation remains in
  reachable history; a clean current tree does not erase older metadata.
- No non-standard-library Python imports were found in the tracked Python
  sources. Packaging uses a locked Nix input and a Python interpreter from
  that input.
- `nix flake check` passed on x86_64-linux: syntax, 332 regression tests,
  15 evaluation checks, and 6 TTY checks. Other platforms were not tested.
- Synthetic probes used isolated temporary repositories, configuration and
  state. Model summaries were replaced with recording functions. Network
  behavior was tested with an in-memory HTTP connection; no private corpus
  or live model endpoint was used. Existing tests pass while the behaviors
  below remain reproducible.
- The follow-up completed 14 additional probes, including negative controls;
  all 14 original probes were also rerun successfully. Completion here means
  that the probe produced its observation, not that the vulnerable behavior
  passed a security requirement. The follow-up inspected goal scope and
  accounting, next-prompt memory invalidation, source-policy revocation,
  automatic code context, script authority, descendant cleanup, HTTP response
  cancellation, and existing rejection/deletion controls.
- The original probe's incomplete HTTP mock was repaired before its final
  run. Follow-up fixture details were also corrected before its final clean
  run. No audit step in the follow-up was blocked by a content notice. The
  earlier platform notice's suppressed content cannot be inspected, so this
  report makes no claim about what that notice withheld.

Coverage included:

| Area | Files reviewed for security boundaries |
| --- | --- |
| Execution and approval | `motoko`, `agentic.py`, `goal_loops.py`, skill management/registry/curator/scanner |
| Document ingestion and retrieval | `corpus_selection.py`, `index_storage.py`, retrieval/planner/service, vector store, sources, dossiers, code intelligence |
| Private state and lifecycle | `state.py`, conversations, memory, profile, feedback, artifact lifecycle, maintenance, jobs, runtime, observability |
| Model boundary | model I/O, routes, services, manager, slot cache, facade request helpers |
| Terminal and commands | terminal, TUI rendering, input editing, text, commands, facade CLI/TUI dispatch |
| Packaging and validation | Nix files, all test files, eval/self-eval code, repository guidance and security/design documentation |

The audit does not certify the installed OS, llama.cpp server, model files,
native dependency closure, filesystem permissions of a real deployment, or
remote repository state. It also does not establish resistance to every
model-level prompt injection.

The saved implementation branches now listed in `docs/deferred-projects.md`
are separate from the audited master code. Their documented completion or
validation status is not independently certified here; this audit did not
merge, alter, or resume those deferred work items. Findings overlapping those
branches remain applicable to master until reviewed fixes are integrated.

## Findings

Severity describes potential impact when the stated prerequisite holds.
For this personal harness, the local-relevance column is especially useful.

| ID | Severity | Finding | Relevance to personal use |
| --- | --- | --- | --- |
| S01 | High | Indexing follows file symlinks outside the document allowlist | An ordinary symlink in an indexed tree can ingest unintended private files |
| S02 | High | Read-only repository review executes repository code | Matters when reviewing downloaded, shared, or modified repositories |
| S03 | High | Approved scripts can execute unapproved sibling modules | Matters when a skill package changes after approval |
| S04 | Medium | Git pathspecs bypass per-file commit checks | Wildcards can commit files excluded by `.motokoignore` |
| S05 | Medium | Ancestor symlinks bypass VCS write denial | A confirmed ordinary-looking path can write into `.git` |
| S06 | Medium | Untrusted terminal control sequences are rendered | Model output or displayed source content can manipulate the terminal |
| S07 | Medium | I/O limits do not reliably bound resource use | A broken tool, large file, or FIFO can hang work or exhaust resources |
| S08 | Low | Private overwrite content is briefly stored with broader permissions | Requires another account able to traverse the project directory |
| S09 | Medium | HTTP model requests inherit ambient proxy routing | Relevant to HTTP routes in a shell with proxy settings; Unix routes are unaffected |
| S10 | Medium | Pinned Python lacks an applicable HTTP hang fix | Requires a malfunctioning or hostile model HTTP response |
| S11 | Medium | Goal execution and apply do not enforce the declared project scope | Confirmed work in one project can affect another globally allowlisted project |
| S12 | Medium | Goal model-call accounting can be bypassed by failure and resume | A broken planner can consume more resources than the approved budget |
| S13 | Medium | Corrected or forgotten memories survive in profile context | The next prompt can still contain the obsolete or deleted fact |
| S14 | Medium, policy gap | Cached document retrieval ignores later exclusion or allowlist removal | Revoking new reads does not revoke use of previously cached evidence |
| S15 | Informational, high impact | Approved skill code executes with the user's OS authority | Effect declarations and the scanner are not a filesystem or network sandbox |
| S16 | High | Automatic code context trusts a lookalike source tree and outside symlinks | A code question can read unintended files even in chat-only mode |

### S01 — Indexing bypasses the document allowlist through file symlinks

Locations: `motoko_core/corpus_selection.py:286-355`,
`motoko:16765-16832`, `motoko:16258-16316`.

`build_document_index()` checks the root once. Candidate selection then opens
file symlinks when checking whether they contain text, and `stream_index_file()`
opens them again without validating the resolved target. Directory traversal
does not follow directory symlinks by default, but that does not protect file
symlinks.

**Reproduction:** an allowlisted temporary repository contained `linked.txt`
pointing to a synthetic private file outside every allowed root. Direct
`read_text_file(link)` correctly refused it. Indexing the repository included
the file and passed its contents to the recording model-summary function.

**Fix:** enforce resolved-source containment and regular-file checks before
sampling, hashing, planning, and ingestion. Apply the policy to every candidate
and to resumed work. Use descriptor-based checks where concurrent path changes
matter. The separate automatic code-intelligence path has now been reproduced
too; see S16 for its root-selection and permission issues.

Existing indexes need an inspectable source-boundary audit. Cheap validation
belongs in the light maintenance lane; affected summaries, vectors and dossiers
should be invalidated or rebuilt through visible resumable heavy work. A fix to
future ingestion alone cannot undo previously ingested content.

### S02 — A read-only repository review executes repository-owned code

Locations: `motoko:22386-22421`; related Git runner:
`motoko:22330-22350`, `motoko:8847-8857`.

`repo_review_report()` automatically executes `scripts/nixos-review-gate` if
that path is executable. The script has no fingerprint approval, effect
validation, environment scrubbing, or execution confirmation. Its filename
does not constrain what it does. An attacker can include it in a repository
that the user authorizes Motoko to inspect.

**Reproduction:** the review gate in a temporary allowlisted repository wrote
a marker outside that repository during `repo_review_report()`. No tool
approval was created.

Git itself is another execution surface: the runners inherit repository and
environment configuration. A second probe configured `core.fsmonitor` in a
temporary repository; `repo_status_report()` executed that configured hook.
This second case requires control of Git configuration, which an ordinary
clone does not obtain merely from tracked files. Git documents these behaviors
in its [configuration reference](https://git-scm.com/docs/git-config).

**Fix:** move review-gate execution behind a separately approved script/tool
contract. Centralize Git invocation and explicitly control hooks, fsmonitor,
external diff/text conversion, filters and inherited Git variables as applicable
to each operation. If an operation intentionally needs repository hooks or
filters, present that execution authority for review. Removing the direct gate
alone does not constrain all Git subprocess behavior.

### S03 — Script fingerprint approval does not cover imported local code

Locations: `motoko_core/agentic.py:590-608`, `:1328-1352`, `:1382-1389`;
support-file management: `motoko_core/skills.py:839-856`.

Approval covers the main script and its metadata. The interpreter starts with
the script directory on Python's import search path. Newly added sibling
modules can therefore run under an unchanged approval. They need no adjacent
tool metadata or approval of their own.

**Reproduction:** approved a script containing `import json` and a JSON print.
After approval, added a sibling `scripts/json.py` that wrote a marker. The
approved script and metadata were unchanged. Validation still reported
`approval=persistent`, and the unapproved module executed successfully.

**Fix:** for a stdlib-only contract, isolate the interpreter's import path
and disable unneeded site initialization. If skill-local imports are supported,
approve and fingerprint the complete executable dependency set and run a
verified snapshot. Editing executable support content must invalidate the
relevant approval.

This finding concerns the approval boundary. The already documented absence
of an OS sandbox is a separate design assumption: a deliberately malicious
approved script runs with the user's OS authority. An OS sandbox would require
the separate deployment design contemplated by the existing documentation.

### S04 — Git interprets approved filenames as pathspecs

Locations: `motoko:8991-9032`; validation:
`motoko_core/agentic.py:744-764`.

`commit_action_paths()` validates strings as filesystem paths, then passes
them to `git add` and `git commit`. `--` ends command options but preserves
Git wildcard/pathspec interpretation. Validation does not inspect every file
the pathspec actually selects.

**Reproduction:** with `secret.txt` excluded by `.motokoignore`, confirmed a
commit action with `paths=["*.txt"]`. The action reported one approved path
and completed, committing `secret.txt` too. No real secret or remote push was
involved.

**Fix:** use literal pathspec semantics, require explicit file targets, and
verify the staged/committed file set against those targets. If wildcard input
is desirable, expand it first, validate each result, and obtain confirmation
for that concrete set. Git provides
[`--literal-pathspecs`](https://git-scm.com/docs/git#Documentation/git.txt---literal-pathspecs).

### S05 — A symlink ancestor can hide a forbidden VCS destination

Locations: `motoko:8682-8721`; write implementation:
`motoko_core/agentic.py:1029-1039`.

The write policy checks forbidden component names on the supplied path and
rejects a symlink target or immediate parent. It subsequently resolves the
parent for allowlist checking, but does not repeat the VCS/cache component
denial on the canonical destination. A more distant symlink ancestor survives.

**Reproduction:** `alias -> .git` inside an allowlisted temporary repository.
A confirmed create action for `alias/info/audit.txt` completed and wrote
`.git/info/audit.txt`. This required no race.

**Fix:** apply forbidden-destination rules to canonical paths and validate
every traversed component according to an explicit symlink policy. Use the
validated destination consistently at execution. Add separate tests for
ancestor aliases and for path swaps between validation and writing.

### S06 — Terminal output preserves untrusted control sequences

Locations: `motoko_core/tui_render.py:196-253`,
`motoko_core/terminal.py:131-132`, `motoko:20610-20631`.

The render helpers preserve input escape sequences. `strip_ansi()` handles a
limited CSI pattern for formatting/measurement; it is not an output sanitizer.
Line-mode streaming prints model chunks directly.

**Reproduction:** synthetic OSC 52 clipboard-write and CSI clear-screen bytes
survived both TUI message rendering and streaming output. Bytes were captured
in memory, not sent to a real terminal. Actual clipboard behavior depends on
the terminal's settings; screen manipulation and misleading output remain
relevant to a personal terminal application.

**Fix:** sanitize untrusted text before adding Motoko-owned styling. Handle
OSC, DCS, CSI and other control characters explicitly, and preserve parser
state across streamed chunks. Cover source names, reports, errors, titles,
reasoning and saved-message replay as well as answer text.

### S07 — Resource limits are enforced too late or bypassed during I/O

Locations: `motoko_core/agentic.py:1375-1426`,
`motoko_core/corpus_selection.py:109-114`, `motoko:10142-10148`;
similar full-read behavior at `motoko_core/code_intel.py:232-236`.

Related availability problems were reproduced:

- With a one-second tool timeout, a script that slept for 2.5 seconds without
  reading stdin and received a 256 KiB argument completed after approximately
  2.52 seconds. The blocking stdin write occurs before the deadline/cancel
  polling loop, so a sufficiently large input bypasses those controls.
- A tool declaring a 1 KiB output limit wrote 256 KiB to its temporary output
  file before Motoko noticed and reported failure. The limit bounds retained
  output, not disk spooling while the process runs.
- Corpus selection blocked opening a FIFO until the probe process was killed
  by an external timeout. Separately, a 96 KiB context limit still read and
  allocated all 192 KiB of a synthetic file before truncating it. Large files
  amplify the allocation problem.
- The runner terminated a timed-out parent but left its child running. The
  child wrote a synthetic marker after the runner had returned `timeout`, then
  exited itself. The fixture was bounded; no persistent process was installed.
  `_stop_tool_process()` at `agentic.py:1303-1314` targets only the direct child.
- `close_active_model_request()` at `motoko:22819-22833` calls `resp.close()`
  synchronously, before connection close. `stop_active_answer()` calls it on
  the stop path (`:22852-22862`). With a real Python `HTTPResponse` reading
  from a synthetic pipe, response close remained blocked until the fixture
  released the pending buffered read. Thus setting the cancellation event is
  not enough to make that stop path return promptly. This exercises the actual
  close helper and HTTP buffering, not a deployed endpoint or a full PTY stop.

**Fix:** bound arguments before serialization; supervise stdin, output,
cancellation and deadlines together; stop on live output-budget exhaustion;
reject non-regular corpus files without blocking; and read bounded excerpts
with `read(limit + 1)`. Whole-file indexing should remain streaming. Review
process-tree termination as part of runner hardening. Transport cancellation
must unblock pending I/O with bounded cleanup off the terminal owner. The
deferred cancellation branch may contain relevant work; its saved status is
not a claim that master contains the fix.

### S08 — Project overwrite temporaries expose private content briefly

Location: `motoko_core/agentic.py:1000-1005`.

`_atomic_project_write()` writes its temporary file before applying the
destination permissions. With umask `022`, overwriting a `0600` file first
creates a `0644` temporary containing the replacement text.

**Reproduction:** observed the temporary immediately after its write and
before chmod: `0644`; final destination: `0600`. No second user's access was
attempted. Exposure requires that another account can traverse the project
directory. Motoko's private `0700` state directory does not have that same
exposure, so this is lower priority for a single-user private checkout.

**Fix:** create the temporary exclusively with mode `0600`, write through
that descriptor, then apply the intended final permissions and rename.
The existing private-state writer already uses `NamedTemporaryFile`.

### S09 — Ambient proxies can receive an HTTP local-model prompt

Locations: `motoko_core/model_io.py:429-435`, `:483-491`.

The HTTP path uses the default `urllib` opener, which inherits proxy settings.
An operator-approved endpoint URL therefore does not by itself ensure a direct
connection to that endpoint. A proxy configured for other shell work can receive
an HTTP model request when the target is not excluded by `no_proxy`.

**Reproduction:** an in-memory connection recorder, with an HTTP proxy setting
and empty bypass list, observed the synthetic loopback model request being
addressed to the proxy with the full prompt body. No network connection was
made. Unix-domain-socket model requests use their separate connection path
and are unaffected.

**Fix:** disable automatic proxies for model traffic by default, or make them
an explicit route policy. Also constrain redirects to approved destinations;
the default opener follows some redirects, although forwarding a POST body
across a redirect was not demonstrated here. Python documents both defaults
in the [`urllib.request` reference](https://docs.python.org/3.12/library/urllib.request.html).

### S10 — The locked runtime predates an applicable HTTP security fix

Locations: `flake.lock:5-11`, `flake.nix:31`,
`motoko_core/model_io.py:14-24`, `:374-388`, `:435`.

The locked development runtime was Python `3.12.13`. A bounded in-memory
response containing 101 consecutive `100 Continue` replies was accepted by
that runtime's `HTTPResponse.begin()`.

Python 3.12.14, released August 12, 2026, limits interim responses and chunked
trailers to address clients hanging on endless responses despite socket
timeouts. This is applicable because Motoko uses Python's HTTP response
parser, including over Unix sockets. A healthy trusted local server makes
this a maintenance issue rather than an exposed public-service emergency.
See the official [Python 3.12.14 security release notes](https://www.python.org/downloads/release/python-31214/)
and its entry for `gh-150743` / `GHSA-w4q2-g22w-6fr4`.

**Fix:** update the locked runtime to include the relevant fix, then rerun the
existing validation suite. Do not assume every advisory for Python or its
native dependencies is reachable through Motoko; a full native-closure CVE
assessment was outside this source audit.

### S11 — Goal scope is not enforced during execution or proposal apply

Locations: `motoko:7146-7183`, `:7357-7527`, `:7626-7755`;
record validation: `motoko_core/goal_loops.py:170-179`, `:240-281`.

Goal validation checks scope entries themselves, and retrieval uses a project
scope. Execution, however, validates action paths against global permissions
without intersecting them with the goal's scope. Proposed worktree paths have
their own provisional checker, also without that intersection.

**Reproduction:** two separate temporary projects were globally allowlisted.
A goal naming only project A contained a create action in project B. Running
without confirmation was refused and wrote nothing. Running with `--yes`
completed the write in B. A separate `model_confirmed` run accepted an
out-of-scope write proposal as `needs_confirmation`; explicit apply completed
that write too. No model was needed to demonstrate the validator behavior.

This does not bypass the global allowlist or eliminate confirmation. It makes
the goal's narrower declaration ineffective as an execution boundary, so a
mistaken or hostile plan can affect another project despite that declaration.

**Fix:** intersect canonical goal scope, current global permissions, allowed
effects/tools and confirmation at preview, execution, apply and resume.
Managed worktrees need explicit ownership relationships to the scoped parent
repository. Do not accept a proposed worktree merely because its destination
is under a generic managed-worktree directory.

### S12 — Goal budgets do not bound failed or resumed model calls

Locations: `motoko:7196-7220`, `:7240-7311`, `:7357-7527`;
budget normalization: `motoko_core/goal_loops.py:131-148`.

The model runner checks whether the configured allowance is at least one. It
does not subtract already consumed calls before starting another call. It
increments `model_calls` only after a successful response parse and proposal
validation. Failed calls therefore consume resources without being counted.

**Reproduction:** a goal allowed one model call. A fake planner returned
invalid JSON; the run stopped. Loading that persisted run and retrying made a
second call while persisted consumption remained zero. Separately, a resumed
run already recording one consumed call under a one-call budget made another
call and completed with `model_calls=2`.

`max_minutes` is also normalized and displayed but is not enforced as an
execution deadline in these runners. That is a source-level observation;
the audit did not spend a real minute waiting to exceed the limit. The
explicit action count and effect checks do exist and should be preserved.

**Fix:** reserve and durably record spending before starting each call, count
failures and interruptions, and check remaining cumulative budgets on resume.
Define and enforce elapsed-time accounting, including whether pauses consume
time. Apply the same accounting to retrieval-triggered model calls and
proposal application so a nominal top-level count is not misleading.

### S13 — Correcting or forgetting a memory leaves obsolete profile context

Locations: `motoko:5906-5914`, `:5952-5957`, `:10063-10128`,
`:18277-18295`, `:19188-19192`, `:19357-19358`;
renderer: `motoko_core/profile.py:10-20`.

Editing or forgetting rewrites the memory rows but does not invalidate a
profile already derived from those rows. Prompt construction loads that
profile without checking current source revisions. Automatic refresh checks
new source IDs, so edits and removals are not reliable refresh triggers.

**Reproduction:** created a synthetic memory and built its profile through the
normal profile persistence path using a deterministic fake summarizer. After
editing the memory, a newly built system prompt retained the original fact.
After forgetting it, the source row was gone but another newly built prompt
still retained that fact through the profile. Refresh was not due in either
case. No independent source document or old conversation was needed.

This is both a privacy and an answer-integrity issue: successful forgetting
does not currently mean derived context has stopped using the fact. Memory
dossiers similarly contain copied excerpts and summaries; their dependency
handling should be covered in the same repair, including transitive reuse.
The executable next-prompt reproduction specifically verifies the profile.

**Fix:** persist source revisions/dependencies, suppress affected derived
context immediately, and make invalidation transitive. Upgrade legacy
artifacts conservatively in the bounded light lane; rebuild model-derived
content through durable visible heavy jobs. Preserve unrelated artifacts and
do not silently delete independent original evidence. This overlaps the
deferred memory-lifecycle work item.

### S14 — Source-policy changes do not suppress cached document evidence

Locations: `motoko:10300-10330`, `:12818-12833`, `:18860-18903`;
`motoko_core/retrieval_service.py:1694-1758`;
`motoko_core/corpus_selection.py:364-402`.

The allowlist controls new document reads and ingestion. Retrieval from a
stored index loads its cached chunks without rechecking current source
authorization. A changed `.motokoignore` marks the index stale but does not
exclude that source's existing cached evidence from the retrieval result.

**Reproduction:** built an index over a synthetic document, then excluded that
file in `.motokoignore`. Attached-index retrieval still returned its cached
marker. After temporarily emptying the fixture's allowlist, a direct read was
correctly refused, but attached-index retrieval still returned the marker.
The index was visibly stale; the problem is continued use, not absence of all
freshness diagnostics.

**Scope qualification:** retaining already imported evidence can be an
intentional product policy. This is a revocation-policy gap, not proof that
editing the allowlist was documented to erase historical conversations.
Users need a clear distinction between stopping new reads and revoking future
use of stored copies. S01 and S16 separately demonstrate unauthorized new
reads; this case concerns previously authorized cached material.

**Fix:** define those revocation semantics explicitly. Where exclusion means
no further use, gate retrieval and prompt packing on current authorization,
invalidate summaries/vectors/topics that depend on the revoked source, and
offer inspectable cleanup. If stored copies intentionally remain usable,
make that retention and the separate revocation action visible to the user.

### S15 — Approved script code has the user's OS authority

Classification: verified trust limitation, not an approval bypass.

Locations: `motoko_core/agentic.py:474-490`, `:1187-1198`, `:1328-1390`;
`motoko_core/skill_scanner.py:17-46`, `:87-145`.

The runner validates declarations, fingerprints and selected path arguments,
scrubs the child environment, and launches Python directly. The named
`motoko-tool-python-stdlib` wrapper is a metadata value; this code does not
invoke a separately confining wrapper. Script-local filesystem operations
are not mediated by Motoko's validators. Import isolation and effect
declarations do not provide OS containment.

**Reproduction:** approved a small tool declaring only `read_context`,
`network=false`, and `writes_project_files=false`. It read a synthetic file
outside every allowlisted root and copied it to another temporary file. The
runner reported `completed`. The static scanner returned no findings for
that simple `pathlib` code. Both paths and the data belonged to the isolated
audit fixture; no private user file was accessed.

The existing design already defers stronger containment and assumes reviewed
code. Accordingly, this is not counted as a new vulnerability in a promised
OS sandbox. It verifies the practical consequence: approval must mean trust
in the code's full same-user authority. Statements that raw script writes or
networking are "blocked" must be understood as declaration checks, not runtime
containment. Actual network access was not exercised in this probe.

**Action:** make that trust assumption explicit in tool approval and security
documentation. Do not treat scanner success or low-risk metadata as a safety
proof. Supporting untrusted tools with enforceable effects requires the
separate reviewed containment design owned by deployment configuration.

### S16 — Automatic code context can read outside a lookalike source tree

Locations: `motoko_core/code_intel.py:188-214`, `:232-236`, `:914-941`;
`motoko:20984-21023`, `:19194`, `:19366`.

Source discovery prefers a current-directory ancestor containing `motoko`,
`motoko_core/`, and `AGENTS.md` over the installed source location. Those names
are not an authorization check. Enumeration resolves discovered `.py` paths
without constraining their resolved targets to the chosen root. Automatic
code-context rendering does not enforce `file-read` permission or the
document allowlist before reading that tree.

**Reproduction:** made an isolated lookalike tree with those three names and
a `.py` symlink to a synthetic private Python file outside it. With the current
directory inside the lookalike tree, an empty document allowlist, and
`MOTOKO_PERMISSIONS=chat-only`, asking about Motoko code caused
`build_system_prompt_and_sources()` to include the outside file's synthetic
constant value. Provenance identified the lookalike root. No explicit
attachment, index build, source-directory approval or model call was needed.

The owner of a repository being inspected can influence its file layout and
symlinks. Successful disclosure of useful values depends on the target's
syntax and the code query's selection; the probe establishes Python constant
disclosure, not arbitrary full-file export. This path is independent of S01's
indexing code and therefore needs its own boundary fix.

**Fix:** bind automatic self-code context to an explicitly trusted source
root. Additional checkouts need an explicit authorization policy. Enforce
permission, resolved-root containment and regular-file checks before every
read, with bounded I/O and appropriate protection against path changes.

## Other observations

- Typed project writes require confirmation and overwrite hashes. Model
  proposals are not directly evaluated as shell commands. Unknown skill
  handlers are normalized through a code-owned registry. These controls are
  useful and should remain central to remediation.
- Retrieved documents, memories and summaries are interpolated into the
  system-message text (`motoko:19291-19400`). Source instructions should be
  explicitly treated as untrusted evidence. Automatic memory formation can
  persist model-derived claims, so provenance and private adversarial evals
  matter. This audit did not demonstrate a live-model prompt-injection attack.
- The earlier scope/budget observations were followed through to executable
  reproductions and are now S11 and S12.
- Private-state JSON writes use private temporaries and atomic replacement.
  Atomic replacement alone does not provide power-loss durability without
  file/directory `fsync`, or prevent every concurrent read/modify/write lost
  update. Those are integrity hardening tasks, not evidence of data theft.
- Persisted artifact IDs, nested JSON shapes and diagnostic free-text fields
  are not uniformly validated. Under the current OS-user trust model, editing
  the user's private state is already powerful. Harden these before adding
  external artifact import or exporting supposedly content-free diagnostics.
- The code-intelligence parser uses `ast.parse` and `ast.literal_eval`, not
  execution of imported source. No use of pickle, archive extraction, or
  dynamic execution of model text was found in the production source scan.
  This does not address resource exhaustion from oversized parser inputs.
- The Python security-release review was checked against the actual import
  and call inventory. Unused webbrowser, archive, FTP, HTML/XML and CSV APIs
  were not turned into Motoko findings merely because they appear in the
  interpreter's release notes. Native-library and approved-tool reachability
  require separate deployment or package-specific analysis.
- De-duplication uses token overlap and stores one owning conversation ID
  (`motoko:5809-5829`, `motoko_core/memory.py:75-100`). Very similar facts from
  different conversations can therefore collapse into one source record.
  A deletion-control fixture initially hit this behavior; it was corrected
  to use distinct facts before testing preservation. Multi-source provenance
  and corrections deserve explicit evaluation in the deferred memory work;
  this audit does not claim that all independent corroborating evidence is
  preserved by the current single-owner representation.

## Follow-up evidence and rejection controls

The evidence files below contain synthetic fixtures and observations only.
They are temporary local audit artifacts, not committed regression tests.
The commands are reproducible while those scripts remain in the local
temporary directory:

```bash
nix develop --command python3 /tmp/motoko_security_audit.py .
nix develop --command python3 /tmp/motoko_security_audit_followup.py .
nix develop --command python3 /tmp/motoko_security_inventory.py .
nix flake check
```

Each probe script creates a new temporary state/configuration root. The
follow-up replaces model calls with recording/deterministic functions or
rejects unexpected model calls. The HTTP close probe uses a pipe, and the
proxy probe uses a recording connection. Terminal control bytes are captured
as strings. A deliberately self-terminating child verifies descendant
cleanup; bounded external timeouts contain the FIFO probe. These are local
reproductions, not tests against another user's data or service.

Final clean-run observations:

| Follow-up probe | Result | Finding/control |
| --- | --- | --- |
| Explicit goal scoped to A, action in B | Confirmation required; confirmed out-of-scope write completed | S11 |
| Model-confirmed proposal scoped to A, action in B | Proposal accepted for confirmation; apply wrote in B | S11 |
| Invalid planner JSON followed by persisted resume | Two calls under a one-call budget; recorded consumption zero | S12 |
| Resume with allowance already consumed | Another call ran; recorded consumption became two | S12 |
| Edit then forget memory used by profile | Original fact appeared in both subsequent system prompts | S13 |
| Ignore then revoke indexed source | New read denied; cached marker still retrieved | S14 |
| Approved read-context-only tool | Read outside allowlist and wrote an undeclared file; scanner returned zero findings | S15 |
| Tool parent timeout | Child wrote its marker after the runner returned timeout, then exited | S07 |
| Close a response with a pending buffered read | Close blocked until fixture released the read | S07 |
| Slot-cache outside paths and HTTP capability | Traversal, absolute escape and symlink escape rejected; HTTP persistent slots refused | Rejection control |
| Automatic code context in lookalike checkout | Outside constant reached the prompt with chat-only permission and no allowlist | S16 |
| Overwrite after another edit changed target hash | Write failed and concurrent edit was preserved | Rejection control |
| Changed main script or different approval realm | Both approvals rejected | Rejection control; distinguishes S03 |
| Delete conversation with distinct dependent/unrelated memories | Owned memory/profile removed; unrelated conversation and memory preserved | Deletion control; distinguishes S13 |

Final results were saved at
`/tmp/motoko-security-fixtures-jt82ar11/results.json` and
`/tmp/motoko-security-followup-12f5kabx/results.json`.
The refreshed inventory is `/tmp/motoko-security-inventory.json`.
All 28 probes completed. A result field such as `status=failed` or
`status=timeout` describes Motoko's observed tool/action outcome; it is not an
uncaught failure of the audit script. Final probe processes exited zero.

Coverage limits that remain:

- Source enumeration and AST/sink review covered the tracked Python tree;
  manual review concentrated on security-sensitive call chains. This is not a
  claim of exhaustive line-by-line review of the approximately 70,000 lines
  of application, tests and the two main context documents inventoried in the
  initial follow-up.
- The review mapped subprocess, transport, write/deletion and source-ingestion
  families and followed their main authorization and persistence boundaries.
  Not every wrapper, argument permutation, interleaving, model output or
  recovery path was dynamically exercised.
- Full live-model prompt-injection resistance, real TCP/Unix deployment
  isolation, service-owned cache erasure, hostile native dependencies,
  cross-user permission enforcement and non-Linux execution remain untested.
- Local reachable history was pattern-scanned; newly fetched public refs,
  unreachable Git objects, encoded secrets and all branch implementations
  were not exhaustively audited. The native dependency closure was not given
  a complete CVE assessment.
- Findings and containment observations apply to the audited master
  implementation. Unmerged branch fixes, deployment activation and actual
  compromise are separate questions.

## Suggested repair order

This orders the audit findings by repair priority; it does not supersede the
maintainer's deferred work queue in `docs/deferred-projects.md`. That queue
already includes stalled I/O, goal scope/budgets, memory invalidation, durable
history and stronger evaluations. Preserve the saved branch snapshots and
coordinate overlapping fixes there when implementation is resumed.

1. Fix ingestion and automatic code-context containment, Git literal paths
   and canonical write checks.
   These protect the user's own document/project boundaries even without a
   network attacker. Add focused rejection regressions and an existing-index
   audit/rebuild path.
2. Separate repository inspection from executable review hooks, and bind skill
   approvals to the code that can actually run.
3. Make memory correction/forgetting and document-source revocation reliable
   at prompt construction. Enforce goal scope and cumulative spending at each
   execution boundary.
4. Sanitize terminal output and make input/output/deadline limits effective
   during I/O, including descendants and transport stop. Repair temporary-file
   permissions alongside the write helper.
5. Refresh the pinned Python runtime. For HTTP routes, make proxy and redirect
   behavior explicit. Preserve the existing Unix-socket deployment boundary.

Most application-side repairs can use the standard library. Enforceable
containment of untrusted approved scripts is a separate deployment design,
not something a Python scanner can guarantee. This audit does not require
turning the personal harness into a hosted platform or adding a framework.

## Remediation of the first three priorities

The requested repairs are implemented and verified in this revision.
`nix flake check` passed on x86_64-linux: syntax, 341 regression tests,
15 evaluation checks, and 6 TTY checks. Other platforms remain untested.
The final regression build includes all nine new security tests and the
existing cancellation controls. No content notice blocked this remediation.

| Priority | Findings | Implemented repair |
| --- | --- | --- |
| 1 | S01, S16 | Descriptor-based regular-file reads enforce resolved containment during sampling, hashing, ingestion, resume and code inspection. File and ancestor swaps cannot redirect an authorized open through a symlink. Code excerpts use bounded reads. Automatic self-code context uses installed source and requires file-read permission; other checkouts require explicit directory approval. |
| 2 | S02 | Repository review reports the review script without executing it. A shared fixed-argument Git inspection profile disables fsmonitor, hooks, filter/diff/textconv helpers, signature verification, automatic fetching and inherited Git control variables. |
| 3 | S03 | Python runs a private snapshot of the exact approved script with isolated imports and no site initialization. Parsed metadata and its fingerprint use the same bytes. The execution-policy version is part of approval identity and private run receipts. |

The source-boundary repair includes older artifacts. Legacy indexes are withheld
from prompt retrieval and catalogs immediately. Dependent topic/dossier context
and vector/evidence queries are also withheld, including missing source-index
provenance. The light artifact-upgrade lane records a `source-boundary-audit-v1`
assessment without relabeling old summaries as verified. Existing saved contents
remain inspectable. The visible heavy lane gradually rebuilds eligible families
under current permissions and allowlists, recording replacement partial-index
IDs so interrupted work resumes completed files. Unattached corpus rebuilds do
not silently attach those corpora to a conversation.

Older tool approvals remain inspectable but require explicit reapproval using
`motoko skill approve-tool NAME TOOL --yes`. Tools relying on local imports need
reviewed self-contained code. S15 remains an explicit trust limitation: these
changes do not create an OS sandbox. A deliberately malicious approved script
still has the user's OS authority. Git inspection likewise assumes that the
trusted OS account does not concurrently replace Git configuration/executables;
explicit confirmed Git mutations retain their separate authority contract.

Nine security regression tests cover the original execution/read boundaries,
positive controls, source swaps, FIFO rejection, safe internal links, resumed
indexing, chat-only/default-root behavior, explicit alternate-root approval,
legacy next-prompt withholding, transitive dependencies, orphaned artifacts,
bounded light audit behavior, interrupted heavy rebuild recovery, and old-tool
reapproval. Git tests use real temporary repositories and configured helpers;
the regression check now includes Git as a test dependency. Existing retrieval
and evaluation fixtures explicitly identify their synthetic post-ingestion
records; separate legacy fixtures exercise rejection and reprocessing.

This repair does not erase independent original conversations or memories,
recover missing historical provenance, or undo past disclosure. The other audit
findings remain open, apart from the bounded source-read/FIFO portions of S07
addressed as part of containment. No live private corpus was inspected or rebuilt
during implementation. No live model endpoint or deployment was used.
Publication and deployment are separate steps from this source revision.
