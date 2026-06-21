# Next Codex Prompt — Finish Motoko Issue #1 Under Real Background Work

Use this in a fresh Codex CLI session on Linux.

```text
The previous Motoko issue #1 candidate improved idle/burst composer rendering, but the real defect remains during background study. This is a correction task, not a new feature.

Repository/worktree:
  /home/mares/repos/motoko-issue-1-tui-input-latency

Branch:
  bounty/issue-1-tui-input-latency

Existing candidate commits:
  69dad1c6d8ae05ad2f266d344020b0e8a17f193f
  fdf54095b5cb8aca81984993bcd38176ccadad32

Read first:
  AGENTS.md
  README.md
  docs/project-context.md
  docs/mares-motoko-handoff.md
  docs/draft-pr-issue-1-tui-input-latency.md
  tests/bounty_issue_1.py
  tests/motoko_tty.py
  GitHub issue #1 and its newest comment

Inspect git status, branch, remotes, and recent log. Preserve unrelated changes. Do not push, merge, deploy, use sudo, access personal state, or add runtime dependencies.

## Corrected user observation

On the affected Linux machine:

- During `study: evidence-store`, typed characters can remain completely invisible.
- After several characters, no further characters appear.
- When the phase changes to `bg-light: catalog(cpu)`, the accumulated text suddenly appears.
- During catalog CPU work, input sometimes appears only after delays measured in seconds.
- Similar lag is reproducible during evidence-store work.

The previous bounty verifier is insufficient because it explicitly disables background study and stubs the study loop. It proved only that idle input batching and transcript scanning improved.

## Objective

Make the raw TUI remain continuously responsive while the real background-study pipeline performs CPU/state work. Preserve the previous idle improvements and preserve completion/correctness of background work.

## Critical test-architecture correction

Do not drive the TUI and the key injector as threads in the same Python process for the new acceptance scenario. That can hide or distort whole-process GIL starvation: if a background thread holds the GIL, both the UI thread and the in-process driver stop together.

Build the background responsiveness verifier as:

  parent verifier process
    -> real PTY
    -> separate Motoko child process
         -> real TUI main loop
         -> real background study worker path

The parent timestamps key injection independently from the Motoko process and observes when each complete composer prefix appears on the PTY.

## Phase 1 — Reproduce before changing production code

Create isolated synthetic Motoko state containing enough deterministic index/artifact data to exercise actual CPU-only background phases without a model endpoint or private documents.

Run the real Motoko executable as a child through a PTY with background study enabled and vector/model-heavy work disabled where necessary. Use short test-only intervals/idle grace through existing environment configuration.

The reproducer must:

1. Observe the real status phase `study: evidence-store` and, if feasible, `study: catalog` / `bg-light: catalog(cpu)`.
2. Inject a representative ASCII/Unicode sequence from the parent while the target phase is still active.
3. Require characters to become visible before the phase transition, not merely after work completes.
4. Measure p50, p95, max, and longest no-visible-progress stall.
5. Verify exact final composer contents.
6. Record child-process heartbeat/event-loop responsiveness separately from total background-job duration.
7. Fail reliably on the current candidate before the production fix.

If the real phase is too brief for a reliable test, increase the synthetic fixture deterministically. Do not replace the real background pipeline with a sleep-only fake. A narrow test seam/barrier is acceptable only if the actual evidence-store/catalog code still executes and the seam merely keeps the phase observable.

## Phase 2 — Diagnose the demonstrated cause

Instrument before optimizing. Distinguish among at least:

- CPU/GIL starvation from Python loops or large JSON encoding/decoding;
- a C operation retaining the GIL for too long;
- unbounded `drain_events()` processing while progress events are produced;
- progress/event flooding;
- a shared lock or state-file lock used by the UI path;
- synchronous filesystem/config/status work in the main TUI thread;
- terminal write/backpressure;
- another demonstrated cause.

Useful evidence may include:

- event-loop heartbeat gaps measured by the parent process;
- queue depth and events drained per main-loop iteration;
- phase-specific stack snapshots or timing spans;
- time spent in evidence-store construction, JSON serialization, catalog construction, atomic writes, and status rendering;
- comparison with progress callbacks suppressed;
- comparison with background work moved to a process or cooperatively chunked, as a temporary experiment only.

Do not assume the prior idle root cause explains this one.

## Phase 3 — Implement the smallest architectural fix

Choose the fix based on measurements. Plausible classes include, but are not mandates:

- bound the number/time budget of background events drained per TUI iteration;
- coalesce replaceable progress/phase events instead of queueing all of them;
- make CPU-heavy background work cooperatively yield at bounded intervals;
- stream/chunk large serialization instead of one long GIL-holding operation;
- move genuinely heavy CPU serialization/transformation to a separate process;
- remove a shared lock or synchronous state read from the input/render path.

Requirements:

- Background evidence/catalog work must still complete and produce equivalent artifacts.
- Do not disable background study, delay it indefinitely, or silently skip evidence/catalog work.
- Do not merely hide the status phase.
- Do not lower data quality or remove provenance.
- Do not add arbitrary sleeps as the product fix.
- Preserve standard-library-only runtime, append-only scrollback, Unicode/editing behavior, streaming input, cancellation, and line mode.
- Keep main-loop scheduling fair among input, render, model/background events, resize, and cancellation.

## Phase 4 — Simplified final bounty verifier

Extend:

  nix develop --command python3 tests/bounty_issue_1.py

It must still emit one compact JSON object and exit nonzero on rejection. Add a `background_study` section such as:

  {
    "phase": "study: evidence-store",
    "samples": 60,
    "p50_ms": 0.0,
    "p95_ms": 0.0,
    "max_ms": 0.0,
    "longest_stall_ms": 0.0,
    "visible_before_phase_end": true,
    "input_integrity": true,
    "background_completed": true
  }

Acceptance conditions:

- Existing short idle p95 <= 30 ms.
- Existing long-transcript idle p95 <= 40 ms.
- Background-study p95 <= 50 ms on the verification host.
- No individual multi-second stall; set a generous deterministic ceiling appropriate to repeated measurements, initially max <= 250 ms.
- Exact ASCII/Unicode input integrity.
- At least one complete prefix is visibly emitted while the target background phase is still active; the test must fail if all text is withheld until phase transition.
- Background work completes and its expected artifact exists/passes its deterministic integrity check.
- The test runs from isolated synthetic state and needs no live model endpoint.

Run the command at least five times and report ranges.

## Phase 5 — Regression and adversarial checks

Add focused tests proving that the verifier fails when the diagnosed starvation is deliberately reintroduced. Do not commit the deliberate regression.

Check at minimum:

- large evidence-store fixture;
- catalog CPU phase if reproducible;
- rapid ASCII and Unicode input;
- input while background progress events are active;
- Ctrl+C/stop responsiveness;
- SIGWINCH/resize responsiveness;
- background completion and artifact correctness;
- no event loss if event draining is bounded/coalesced;
- no process leak or orphan worker after test completion.

Then run:

  nix develop --command python3 -m py_compile motoko
  nix develop --command python3 tests/bounty_issue_1.py
  nix develop --command python3 tests/motoko_tty.py
  nix develop --command python3 tests/motoko_regression.py
  nix develop --command python3 tests/motoko_eval.py
  nix flake check
  git diff --check

Update:

  docs/draft-pr-issue-1-tui-input-latency.md
  CHANGELOG.md

Correct the document so it no longer claims the original issue was fully fixed by idle batching alone. State the two distinct root causes and their measured contributions.

Create one or more focused follow-up commits on the current branch. Do not push.

Final response must include:

- commit SHA(s);
- exact demonstrated background root cause;
- failing pre-fix background metrics;
- passing post-fix metrics from five runs;
- final one-command verifier JSON;
- background artifact integrity result;
- full validation result;
- remaining limitations, if any.
```
