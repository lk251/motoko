You are working as a senior terminal-performance engineer on a real user-visible
bug in Motoko.

Repository:
  the Motoko repository root

GitHub issue:
  lk251/motoko#1
  "Eliminate idle TUI typing latency with a measurable PTY responsiveness budget"

The user observes that typing in Motoko's default raw Linux TUI visibly lags even
when CPU/GPU load is low, while other shells in the same terminal are responsive.

This is a diagnosis-first task. Do not jump to a plausible-looking optimization.

FIRST, BEFORE EDITING:

1. Read all of:
   - AGENTS.md
   - README.md
   - docs/project-context.md
   - CHANGELOG.md
   - tests/motoko_tty.py
   - motoko_core/tui_render.py
   - motoko_core/terminal.py
   - the MotokoTui input, event-loop, render and write paths in `motoko`

2. Inspect:
   - git status --short --branch
   - git log --oneline -10
   - git remote -v

3. Do not discard, reset, overwrite or incorporate unrelated working-tree
   changes.

4. If the current checkout is clean, create:
     bounty/issue-1-tui-input-latency

   If it is dirty, leave it untouched and create a separate worktree and branch
   from the current HEAD for this task.

5. Record the baseline commit SHA.

6. Retrieve issue #1 with `gh issue view 1 --repo lk251/motoko` if GitHub CLI
   access is available. The requirements below remain authoritative if it is not.

CONSTRAINTS:

- Linux only for reproduction and validation.
- Python standard-library-only runtime.
- No new runtime dependency.
- No sudo.
- No NixOS deployment or service changes.
- No provider credentials.
- Do not inspect personal Motoko state or private personal corpora.
- Use isolated temporary state/config in tests.
- Do not push, merge, deploy, or mutate the master branch.
- Leave local commits and a draft PR description for review.
- Preserve the line-mode fallback.
- Preserve append-only terminal scrollback.
- Preserve slash suggestions, resize handling, cursor movement, history,
  Emacs-style editing keys, kill/yank, deletion, paste, Unicode input,
  cancellation, and typing during streamed answers.

OBJECTIVE:

Diagnose and eliminate the ordinary-keypress latency in the raw TUI and prove
the improvement with repeatable PTY instrumentation.

PHASE 1 — BUILD A BASELINE

Add a focused stdlib-only pseudo-terminal responsiveness harness. It must not
need a live model endpoint or real Motoko user state.

Measure and report:

- input write/key injection to corresponding visible composer output;
- p50, p95 and maximum latency;
- output bytes per ordinary printable character;
- terminal write/render count per character;
- short transcript versus deliberately long transcript;
- short one-line input versus wrapped multi-line input;
- a fast ASCII burst;
- representative multibyte Unicode input;
- no dropped, duplicated, reordered or corrupted input.

Avoid brittle CI timing tests. Combine tolerant wall-clock guards with strong
deterministic invariants. In particular, ordinary end-of-buffer input must not:

- perform work proportional to transcript length;
- invoke subprocesses;
- read route/config files repeatedly;
- contact model endpoints or network services;
- redraw unrelated transcript content.

Make the harness capable of demonstrating a deliberately reintroduced version
of the diagnosed regression.

PHASE 2 — DIAGNOSE

Instrument and inspect the complete synchronous path:

- MotokoTui.run
- select/read scheduling
- read_key and queued-input handling
- handle_key
- render
- bottom_area_frame
- draw_bottom_area
- fixed_prompt_input_display
- status_display and model-badge computation
- transcript-tail restoration
- terminal clear/redraw sequences
- blocking os.write behavior

Explicitly test, rather than assume, these possible causes:

1. Only one ordinary byte is handled before an expensive render.
2. Queued bytes are not drained efficiently.
3. Full bottom-frame clearing and rewriting occurs for every character.
4. Status/model route/config work occurs synchronously per key.
5. Transcript formatting occurs on the normal input path.
6. Input wrapping scales unnecessarily with accumulated input.
7. Excessive ANSI output causes terminal backpressure.
8. Event-loop ordering introduces an avoidable delay.

Do not claim the select timeout itself is the cause merely because it is 0.12
seconds while idle: select should wake for readable input. Demonstrate the real
cause.

Use stdlib profiling/instrumentation. Existing system tools may be used if
already installed, but do not add a dependency to Motoko.

PHASE 3 — FIX

Implement the smallest robust change supported by the measurements.

Valid classes of solution may include, depending on evidence:

- draining a bounded batch of pending printable input before rendering;
- separating composer-only incremental writes from full frame changes;
- caching immutable or slowly changing status data;
- preventing transcript work on ordinary composer updates;
- reducing write amplification;
- making rendering cost independent of conversation length.

These are hypotheses, not instructions to force a specific implementation.

Do not "fix" the issue through:

- dropping or coalescing user characters;
- delaying visible echo with debounce;
- removing useful status information;
- weakening Unicode or editing behavior;
- disabling the TUI;
- changing the default to line mode;
- adding an arbitrary sleep;
- hiding the benchmark failure.

PHASE 4 — VERIFY

Run at minimum:

  nix develop --command python3 -m py_compile motoko
  nix develop --command python3 tests/motoko_regression.py
  nix develop --command python3 tests/motoko_eval.py
  nix develop --command python3 tests/motoko_tty.py
  nix flake check
  git diff --check

The affected-machine product target is p95 input-to-visible-character latency
of 30 ms or less while idle. The automated guard may be more tolerant to avoid
flaky CI, but it must detect a deliberate reintroduction of the diagnosed
regression.

Verify:

- fresh and long conversations;
- slash dropdown open and closed;
- one-line and wrapped input;
- rapid ASCII input;
- multibyte Unicode;
- backspace/delete;
- arrows, Home/End and Emacs editing keys;
- history navigation;
- resize;
- typing during answer streaming;
- line mode;
- no transcript-scrollback regression.

PHASE 5 — ADVERSARIAL REVIEW

After the implementation passes, perform a separate critical review of your own
change. Look specifically for:

- character loss under bursts;
- partial UTF-8 reads;
- stale cursor placement;
- terminal output races;
- resize races;
- unbounded batching;
- starvation of background events or streamed tokens;
- performance improvement achieved by silently reducing functionality;
- flaky timing assertions;
- accidental access to real user state.

Correct all confirmed findings and rerun the full suite.

DELIVERABLES:

1. Focused local commits on the dedicated branch.
2. The benchmark/regression harness.
3. The smallest justified implementation fix.
4. CHANGELOG.md update.
5. A draft PR description containing:
   - environment;
   - exact demonstrated root cause;
   - alternatives tested and ruled out;
   - baseline p50/p95/max;
   - final p50/p95/max;
   - bytes and writes per key before/after;
   - short versus long transcript comparison;
   - test results;
   - remaining limitations.
6. A concise final report to the user.

Stop before push, merge or deployment.
