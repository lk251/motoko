# Draft PR: Eliminate TUI Typing Latency

## Summary

Fixes `lk251/motoko#1` by removing measured synchronous work from ordinary raw
TUI input, then fixing the reopened real-background-study latency path.

The TUI now:

- drains already-readable input in a bounded batch before rendering;
- skips transcript synchronization unless transcript rows changed;
- caches display-only model badge and assistant color values briefly, so
  ordinary keys do not reread config/route state;
- bounds/coalesces pending render events so background progress cannot
  monopolize the input loop;
- runs deterministic evidence-store refresh from background study in a
  supervised subprocess, keeping CPU-heavy parsing and JSON construction out of
  the TUI process and away from the TUI GIL.

## Environment

- Host: `Linux hb3 6.18.35 #1-NixOS SMP PREEMPT_DYNAMIC Tue Jun 9 10:28:53 UTC 2026 x86_64 GNU/Linux`
- Python: `Python 3.12.13`
- Worktree: `/home/mares/repos/motoko-issue-1-tui-input-latency`
- Branch: `bounty/issue-1-tui-input-latency`
- Baseline commit: `f4ebe1073d6fe7b9a1e2036e2a6e923ea0a68116`
- Harness: `MOTOKO_TUI_LATENCY_REPORT=1 nix develop --command python3 tests/motoko_tty.py`

## Bounty Verification Command

Acceptance command:

```bash
nix develop --command python3 tests/bounty_issue_1.py
```

This command is stdlib-only, uses isolated temporary Motoko state/config,
requires no live model endpoint, exercises the real TUI through a PTY with
ASCII, accented Latin, and non-Latin input, and prints one compact JSON object.
It exits 0 only when accepted.

Result:

```json
{"accepted":true,"background_study":{"background_completed":true,"input_integrity":true,"longest_stall_ms":1085.797,"max_ms":0.545,"p50_ms":0.528,"p95_ms":0.538,"phase":"study: evidence-store","samples":53,"visible_before_phase_end":true},"failure_reasons":[],"input_integrity":true,"issue":1,"long_transcript":{"max_ms":3.074,"p50_ms":2.404,"p95_ms":3.005,"samples":100},"schema":"motoko-bounty-verification-v1","short_transcript":{"max_ms":2.977,"p50_ms":2.534,"p95_ms":2.897,"samples":100},"unicode_integrity":true}
```

Repeated-run stability:

- 5/5 repeated runs accepted.
- Short-transcript p95 range: 2.897 to 7.217 ms.
- Long-transcript p95 range: 1.379 to 3.074 ms.
- Background-study p95 range: 0.538 to 0.566 ms.
- Background-study max range: 0.545 to 0.576 ms.
- Background-study visible-progress stall range: 1085.179 to 1085.797 ms.

## Root Cause

The original measured root cause was not the idle `select()` timeout. `select()` wakes
when input is readable.

The ordinary input path handled exactly one decoded key, then rendered the full
bottom frame before checking the fd again. Each render also called status
display helpers that recomputed model badge/config state, and each render
walked the transcript list looking for unsynchronized rows even when no
transcript content changed.

Baseline evidence:

- fast ASCII burst: 62 chars -> 62 renders, 62 bottom writes, 62 model-badge
  calls, 7,341 bytes written;
- long transcript, 7 chars: 9,800 transcript-list iterations during ordinary
  input;
- deliberately long transcript did not need new transcript formatting, but the
  per-render synchronization scan was still proportional to transcript length.

The reopened background-study defect had a separate root cause: deterministic
evidence-store construction ran as CPU-heavy Python work inside the same Motoko
process as the TUI. While `study: evidence-store` was active, that worker could
hold the GIL long enough that typed input was accepted only after the background
phase completed.

Corrected background verifier evidence before process isolation:

- real PTY child process, real TUI, real synthetic evidence-store background
  phase;
- background p50/p95/max: 1832.596 / 1832.605 / 1832.612 ms;
- longest visible-progress stall: 1832.613 ms;
- input integrity and artifact completion were true, proving the failure was
  foreground scheduling rather than lost data.

## Alternatives Tested

- `select()` timeout: ruled out as the root cause because readable input wakes
  the loop; latency tracked render/write amplification, not the 0.12s idle
  timeout.
- Full composer-only incremental rendering: not needed for this fix. Bounded
  input draining plus transcript/status caching removes the measured idle burst
  lag while preserving the existing bottom-frame architecture.
- Removing status/model information: rejected. The status row remains; display
  values are cached for a short interval instead of recomputed per key.
- Delaying echo/debounce: rejected. The loop still renders immediately after
  the currently available bounded batch; it does not sleep to coalesce input.
- Transcript redraw removal: preserved append-only transcript behavior. The
  fix only skips transcript synchronization when no transcript rows are dirty.
- Background evidence refresh in a thread: rejected for the reopened issue.
  Cooperative checkpoints improved cancellation points but did not reliably
  prevent GIL starvation under the real TUI child-process verifier. A
  supervised subprocess preserves the deterministic worker path while isolating
  CPU work from the render/input loop.

## Metrics

All latency numbers are input write/key injection to corresponding visible
composer output, in milliseconds, from the stdlib PTY harness.

| Scenario | Baseline p50/p95/max | Final p50/p95/max |
| --- | ---: | ---: |
| short one-line input | 1.200 / 2.187 / 2.187 | 0.877 / 1.323 / 1.323 |
| long transcript input | 1.600 / 1.817 / 1.817 | 0.957 / 1.027 / 1.027 |
| wrapped multi-line input | 0.181 / 1.167 / 1.311 | 0.419 / 1.263 / 1.318 |
| fast ASCII burst | 28.595 / 34.845 / 34.868 | 2.256 / 2.350 / 2.391 |
| multibyte Unicode burst | 6.676 / 11.060 / 11.060 | 1.556 / 1.640 / 1.640 |
| typing during streaming | 12.495 / 20.612 / 21.152 | 1.455 / 1.518 / 1.559 |
| typing during background study | rejected / rejected / rejected | 0.531 / 0.541 / 0.549 |

Write/render amplification:

| Scenario | Baseline bytes/key | Final bytes/key | Baseline writes/key | Final writes/key | Baseline renders/key | Final renders/key |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| short one-line input | 90.143 | 90.143 | 1.000 | 1.000 | 1.000 | 1.000 |
| long transcript input | 89.143 | 89.143 | 1.000 | 1.000 | 1.000 | 1.000 |
| fast ASCII burst | 118.403 | 2.403 | 1.000 | 0.016 | 1.000 | 0.016 |
| multibyte Unicode burst | 94.000 | 12.750 | 1.000 | 0.125 | 1.000 | 0.125 |
| typing during streaming | 130.227 | 6.409 | 1.000 | 0.045 | 1.091 | 0.136 |

Short versus long transcript:

- baseline transcript iterations: short 28, long 9,800;
- final transcript iterations: short 0, long 0 for ordinary input.

Regression-demonstration mode:

- `MOTOKO_TUI_INPUT_BATCH_LIMIT=1` deliberately reintroduces the one-key-per-render
  burst behavior in the harness;
- final regression probe: 62 chars -> 62 renders, 62 writes, 7,651 bytes,
  p50/p95/max 7.207 / 20.813 / 22.449 ms;
- transcript iterations remain 0, proving the harness separates the fixed
  transcript scan from the deliberately reintroduced batching regression.

## Test Results

- `nix develop --command python3 -m py_compile motoko`: pass
- `nix develop --command python3 tests/bounty_issue_1.py`: pass, accepted JSON with idle and background-study sections
- `nix develop --command python3 tests/motoko_regression.py`: pass, 293 tests
- `nix develop --command python3 tests/motoko_eval.py`: pass, 15 checks
- `nix develop --command python3 tests/motoko_tty.py`: pass, 4 TTY render/input checks
- `nix flake check`: pass
- `git diff --check`: pass

## Remaining Limitations

- The automated latency guard is intentionally tolerant (`p95 <= 250 ms`) to
  avoid flaky CI timing failures; the bounty verifier enforces stricter idle
  budgets and a `p95 <= 50 ms` background-study budget.
- The affected-product target is p95 <= 30 ms while idle. The HB3 PTY harness
  now measures below that for the covered idle/burst scenarios, but real Linux
  virtual terminals may still need manual soak after deployment.
- Background-study verification uses synthetic realm-local state and disables
  model/vector-heavy work. It exercises the real TUI process, real background
  study loop, real evidence refresh command, and real evidence-store artifact
  writing, but it does not cover every background lane.
- Very large paste bursts render once per bounded batch of 64 decoded keys, not
  once for the entire paste.
- Slash suggestion shrinkage may still restore exposed transcript tail rows;
  that is intentional to preserve the append-only scrollback visual contract.
