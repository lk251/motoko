# Next Codex Goal — Isolate Candidate Execution and Recover Verification Safely

Read this from a fresh Codex CLI session on Linux, then execute it as a complete goal.

```text
Work in:
  /home/mares/repos/agent-bounty-market

Remote:
  https://github.com/lk251/agent-bounty-market.git

Motoko fixture:
  /home/mares/repos/motoko-issue-1-tui-input-latency

Motoko commits:
  baseline      f4ebe1073d6fe7b9a1e2036e2a6e923ea0a68116
  intermediate fdf54095b5cb8aca81984993bcd38176ccadad32
  final        4c03e0fa02a26f1cbadbe593ae687eaa9b333d2c

## Purpose

The market core is now remote-reviewable and verifier v2 distinguishes the three Motoko candidates. Before adding real Stripe test-mode money movement, close one P0 trust gap and one recovery gap.

Current trust gap: the platform verifier owns its policy, but it imports candidate `motoko` code inside the same Python interpreter that computes the verdict. Candidate top-level code can therefore inspect or mutate verifier process state, terminate it, attempt to alter verifier files, or emit forged output. The existing test proves only that candidate-owned test files are ignored; it does not prove that malicious application code cannot interfere with the verifier.

Current recovery gap to audit: a verification run is persisted as `running` before the external verifier finishes. A crash before receipt finalization must recover safely rather than returning a replay with no receipt or leaving a bounty permanently in `verifying`.

## Read first

Read all repo source/tests/docs, especially:

- `agent_bounty/core.py`
- `agent_bounty/verification.py`
- `agent_bounty/db.py`
- `verifiers/motoko_issue_1_v2/verifier.py`
- `verifiers/motoko_issue_1_v2/contract.json`
- `tests/test_verification.py`
- `tests/test_ledger.py`
- `tests/test_motoko_integration.py`
- `docs/architecture.md`
- `docs/threat-model.md`

Inspect status, log, remotes, and current CI. Preserve legitimate work. Do not modify or merge Motoko. Do not use real Stripe credentials. Never force-push.

## Phase 1 — Reproduce the trust-boundary flaw

Create a synthetic malicious candidate used only in tests. Make safe attempts to interfere with verifier authority, such as:

- mutate globals in the verifier `__main__` module;
- replace a threshold or probe function;
- emit forged accepted JSON and exit;
- attempt to alter platform verifier files;
- attempt to read a sentinel secret present only in the trusted parent environment.

Add a regression test proving at least one attack reaches or can influence the current verifier interpreter. Do not touch real credentials or external systems.

## Phase 2 — Never import candidate code in a trusted interpreter

Refactor to this boundary:

```text
trusted market orchestrator
  -> trusted verifier parent
       -> isolated candidate execution backend
            -> untrusted candidate checkout/process
  <- parent-observed PTY/process/filesystem evidence
  -> immutable receipt
```

Requirements:

1. Candidate Python never executes in the trusted verifier interpreter.
2. Trusted parent owns fixtures, random challenge values, thresholds, timestamps, statistics, verdict logic, digests, and receipt fields.
3. Candidate work runs only in a separate process or sandbox.
4. Parent interacts through PTY I/O, exit status, and bounded artifacts in isolated state.
5. Candidate stdout is observation data, never authoritative verdict JSON.
6. Hash verifier files before and after execution and reject any change.
7. Resolve and pin the exact candidate Git SHA; trusted parent checks base ancestry.
8. Use a randomized per-run input/fixture nonce so a fixed hardcoded transcript cannot pass.

For idle probes, launch candidate Motoko as a real child process rather than constructing `MotokoTui` by importing the candidate module. Build synthetic state from platform-owned fixtures. Keep the background-study child-process approach, but make fixture creation and artifact validation platform-owned too.

## Phase 3 — Execution backend and OpenShell

Introduce an interface such as:

```text
ExecutionBackend
  LocalIsolatedProcessBackend
  OpenShellBackend
```

Local backend must support deterministic tests with:

- scrubbed environment;
- temporary HOME/state/config/work dirs;
- no Stripe, GitHub, model-provider, SSH, or user credentials;
- new process group/session;
- wall timeout and bounded output;
- kill the full process group on timeout/cancel;
- resource limits where supported: CPU, address space, file size, open files, processes;
- candidate working directory separated from verifier source;
- cleanup with no orphan child.

Document honestly that local process isolation is not a complete sandbox.

Read current official NVIDIA OpenShell/NemoClaw docs before implementing the second backend. OpenShell should enforce deny-by-default network policy and keep verifier policy and credentials unavailable to candidate code. Add the adapter, policy file, backend/policy digest recording, detection command, and tests. If OpenShell and prerequisites are available, run a real Motoko verification through it. If unavailable, report the exact blocker and skip honestly; never fake success.

## Phase 4 — Crash-recoverable verification

Audit and correct verification lifecycle:

```text
pending -> running -> accepted | rejected | error | timed_out | abandoned
```

Required behavior:

1. Replay of a completed idempotency key returns the same receipt.
2. Replay of `running` with no live lease/heartbeat resumes or creates a linked retry attempt.
3. Never return `replayed: true` with a null receipt as if complete.
4. Crash after run-row creation but before process launch is recoverable.
5. Crash after candidate completion but before receipt write is recoverable without two receipts.
6. Receipt insert, run finalization, bounty transition, and accepted-receipt binding are atomic.
7. Error/timeout never leaves the bounty stuck in `verifying`.
8. A new candidate cannot reuse an older attempt or receipt.
9. Payout requires one exact completed accepted receipt bound to candidate SHA, verifier digest, backend, and policy digest.

Use injectable fault points in tests and reopen SQLite to simulate restart.

## Phase 5 — Required adversarial tests

Automate at least:

1. Candidate cannot mutate verifier globals because it is never imported by parent.
2. Forged candidate JSON cannot accept.
3. Candidate cannot read trusted-parent sentinel env data.
4. Candidate attempts verifier-file modification; files/digest remain intact or run rejects.
5. Candidate hangs; process group dies and no orphan remains.
6. Candidate floods output; capture is bounded.
7. Randomized challenge defeats a fixed transcript.
8. Baseline Motoko rejects.
9. Intermediate Motoko rejects.
10. Final Motoko accepts under black-box verifier.
11. Fault after run creation recovers after DB restart.
12. Fault before receipt finalization produces exactly one receipt after recovery.
13. Completed replay returns same receipt.
14. Error/timeout exits `verifying` and cannot pay.
15. Receipt binds backend and verifier/policy digests.
16. Existing ledger and exactly-once payout tests remain green.
17. OpenShell denies outbound network when that backend is available.

## Phase 6 — Demo/docs

Update README, architecture, threat model, demo flow, and add `docs/openshell-verifier.md`.

Add a concise demo showing:

```text
malicious candidate -> rejected
baseline -> rejected
intermediate -> rejected
final -> accepted
final replay -> same receipt
```

Make the output visibly distinguish candidate-owned tests, trusted policy, isolated execution, exact commit/digests, and payout eligibility.

Do not add real Stripe calls in this goal. The next goal is real Stripe sandbox funding, webhook ingestion, and payout.

## Validation

Run:

```bash
python -m compileall agent_bounty tests verifiers
python -m unittest discover -s tests
nix develop --command python3 -m unittest discover -s tests
nix flake check
git diff --check
```

Run the real Motoko three-commit suite. Run OpenShell integration when available and report honestly if skipped.

Commit focused changes and push normally to `origin main`.

## Final response

Return:

- commit SHA(s) and messages;
- trust flaw reproduced before fix;
- new backend/process architecture;
- malicious/baseline/intermediate/final outputs;
- crash-recovery evidence;
- OpenShell command, policy digest, and result or exact blocker;
- full tests;
- known limitations;
- confirmation remote `main` matches local HEAD;
- next task: real Stripe sandbox settlement.
```
