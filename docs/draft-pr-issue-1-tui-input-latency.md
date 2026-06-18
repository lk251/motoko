# Draft PR: Eliminate Idle TUI Typing Latency

## Summary

Fixes `lk251/motoko#1` by removing measured synchronous work from ordinary raw
TUI input and adding repeatable PTY responsiveness instrumentation.

The TUI now:

- drains already-readable input in a bounded batch before rendering;
- skips transcript synchronization unless transcript rows changed;
- caches display-only model badge and assistant color values briefly, so
  ordinary keys do not reread config/route state.

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
{"accepted":true,"failure_reasons":[],"input_integrity":true,"issue":1,"long_transcript":{"max_ms":2.723,"p50_ms":2.024,"p95_ms":2.669,"samples":100},"schema":"motoko-bounty-verification-v1","short_transcript":{"max_ms":2.806,"p50_ms":2.224,"p95_ms":2.753,"samples":100},"unicode_integrity":true}
```

Repeated-run stability:

- 5/5 repeated runs accepted.
- Short-transcript p95 range: 2.561 to 4.328 ms.
- Long-transcript p95 range: 2.610 to 3.582 ms.

## Root Cause

The measured root cause was not the idle `select()` timeout. `select()` wakes
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
- `nix develop --command python3 tests/motoko_regression.py`: pass, 291 tests
- `nix develop --command python3 tests/motoko_eval.py`: pass, 15 checks
- `nix develop --command python3 tests/motoko_tty.py`: pass, 4 TTY render/input checks
- `nix flake check`: pass
- `git diff --check`: pass

## Remaining Limitations

- The automated latency guard is intentionally tolerant (`p95 <= 250 ms`) to
  avoid flaky CI timing failures; deterministic invariants catch the regression.
- The affected-product target is p95 <= 30 ms while idle. The HB3 PTY harness
  now measures below that for the covered idle/burst scenarios, but real Linux
  virtual terminals may still need manual soak after deployment.
- Very large paste bursts render once per bounded batch of 64 decoded keys, not
  once for the entire paste.
- Slash suggestion shrinkage may still restore exposed transcript tail rows;
  that is intentional to preserve the append-only scrollback visual contract.
