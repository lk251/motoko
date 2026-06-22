# Next Codex Goal — Publish and Harden Market Core v2

Use this as the complete goal in a fresh Codex CLI session on Linux.

```text
Motoko issue #1 now has a final accepted implementation. Your next goal is to
make the local agent-bounty-market repository visible on GitHub, update it to
the corrected Motoko bounty contract, and prove its accounting and independent
verification before adding real Stripe integration.

Repositories:

- Motoko worktree: `/home/mares/repos/motoko-issue-1-tui-input-latency`
- Motoko branch: `bounty/issue-1-tui-input-latency`
- Market repo: `/home/mares/repos/agent-bounty-market`
- Intended remote: `https://github.com/lk251/agent-bounty-market.git`

Motoko commits:

- Bug baseline: `f4ebe1073d6fe7b9a1e2036e2a6e923ea0a68116`
- Incomplete idle-only candidate: `fdf54095b5cb8aca81984993bcd38176ccadad32`
- Final accepted candidate: `4c03e0fa02a26f1cbadbe593ae687eaa9b333d2c`

Reported local market starting commit:

- `a30d325 Build trusted bounty transaction core`

Read first:

- all source/tests/docs in `agent-bounty-market`;
- Motoko `docs/draft-pr-issue-1-tui-input-latency.md`;
- Motoko `tests/bounty_issue_1.py`;
- the background-study PTY code in `tests/motoko_tty.py`;
- Motoko commit `4c03e0fa...`.

Inspect status, log, and remotes in both repositories. Preserve legitimate
changes. Do not modify or merge Motoko.

## 1. Publish the market repository correctly

Confirm local `a30d325` exists. Confirm `origin` is the intended GitHub repo.
GitHub was previously empty, so push the existing history normally to `main`.
Verify with:

```bash
git ls-remote origin refs/heads/main
```

Do not overwrite unexpected remote history. Push each focused commit from this
goal normally so the work remains reviewable.

## 2. Audit the transaction core

Verify and fix the explicit state path:

```text
draft -> awaiting_funding -> funded -> open -> claimed -> submitted
-> verifying -> accepted -> payout_pending -> paid
```

Also model `rejected`, `expired`, `cancelled`, `refunded`, and
`payout_failed`. Invalid transitions must fail closed.

Audit these invariants:

- all money uses integer minor units;
- available balances never become negative;
- one reward cannot be reserved twice;
- funding, reserve, verification, and payout are idempotent;
- acceptance alone does not mark money paid;
- payout moves the reserved amount exactly once;
- payout failure can be retried safely;
- treasury, bounty, and payout currencies must match;
- database constraints protect critical exactly-once behavior;
- state and ledger updates happen in one transaction;
- only the active claimant can submit;
- submission binds repo, base SHA, candidate SHA, solver, and bounty;
- an acceptance receipt for one SHA cannot authorize another SHA.

Add focused tests for every confirmed correction.

## 3. Replace the old Motoko contract with protected verifier v2

The market repository must own the payout verifier. It must not import
candidate-owned verifier files, helper tests, workflows, thresholds, or verdict
logic.

Create or update a versioned verifier package, for example:

```text
verifiers/motoko_issue_1_v2/
  verifier.py
  contract.json
  README.md
```

Its independent contract must check:

1. Short idle PTY typing p95 <= 30 ms.
2. Long-transcript idle PTY typing p95 <= 40 ms and no transcript-dependent
   ordinary typing scan.
3. Real background-study typing in a separate Motoko child process:
   - observe `study: evidence-store`;
   - inject ASCII and Unicode while the phase is active;
   - p95 <= 50 ms;
   - max character latency <= 250 ms;
   - typed text visible before phase completion;
   - exact input integrity;
   - the synthetic evidence-store artifact completes and passes integrity
     checks.

The verifier process and Motoko candidate process must be separate so whole-
process scheduling stalls remain measurable.

Persist a receipt binding:

```text
bounty ID
project repo and issue
base SHA
candidate SHA
solver ID
verifier name/version/digest
accepted result and metrics
stdout/stderr digests
start/finish timestamps
```

A payout must reference the accepted receipt and exact verifier digest.

## 4. Prove verifier independence and evolution

Run real integration cases against the three Motoko commits:

- `f4ebe107...` -> rejected, no payout;
- `fdf54095...` -> rejected by verifier v2, no payout;
- `4c03e0fa...` -> accepted and eligible for payout.

Also prove:

- changing candidate-owned tests cannot change the platform verdict;
- timeout or malformed verifier output cannot pay;
- a receipt cannot be replayed for a different candidate SHA.

The intermediate candidate is an important demonstration: its own idle verifier
passed, but independent verifier v2 must reject it because background typing was
still blocked.

## 5. Prove exactly-once settlement with the fake gateway

Do not add real Stripe calls in this goal. Use the deterministic fake gateway.

From a fresh database demonstrate:

```text
fund project
-> reserve $25
-> claim
-> submit 4c03e0f...
-> protected verify accepted
-> accept
-> payout pending
-> paid once
-> ledgers reconcile
```

Replay funding, verification, acceptance, and payout. Require the same external
IDs where appropriate, no duplicate ledger rows, no duplicate transfer, and
unchanged balances.

Separately demonstrate the baseline and intermediate candidate rejection paths,
with zero solver earnings and no payout.

## 6. CI and documentation

Add minimal GitHub Actions CI for syntax and fast tests. Do not use secrets.

Update:

- `README.md` with the exact demo command and product thesis;
- `docs/architecture.md` with the state machine and trust boundary;
- `docs/threat-model.md` with verifier replacement, replay, stale SHA, timeout,
  and duplicate payout risks;
- `docs/demo-flow.md` with baseline reject -> intermediate reject -> final
  accept/pay;
- `docs/next-stripe-step.md` describing the next real Stripe sandbox task.

CLI/demo output must clearly show project available/reserved/spent funds, bounty
state, solver, exact candidate SHA, verifier version/digest, verdict, payout ID,
and reconciliation status.

## Required automated coverage

At minimum test:

1. valid happy path;
2. invalid transitions;
3. insufficient funds;
4. duplicate funding and reserve;
5. exclusive claim conflict;
6. wrong-solver submission;
7. unrelated/stale candidate SHA;
8. baseline rejection;
9. intermediate candidate rejection;
10. final candidate acceptance;
11. candidate-owned verifier has no authority;
12. verifier timeout/malformed output cannot pay;
13. receipt bound to exact SHA and verifier digest;
14. failed payout and safe retry;
15. paid payout replay;
16. no negative balances;
17. ledger reconciliation after all paths;
18. process restart preserves idempotency.

## Validation

Run:

```bash
python -m compileall agent_bounty tests verifiers
python -m unittest discover -s tests
nix develop --command python3 -m unittest discover -s tests
nix flake check
git diff --check
```

Run the final accepted transaction twice and the two rejection transactions.
Push focused commits normally to GitHub `main`.

## Non-goals

Do not add real Stripe API calls, Hermes agents, MPP, Stripe Projects, GitHub
webhooks, a web UI, or sandbox integration yet. First make this transaction core
remote-reviewable and correct.

## Final response

Return:

- local path and remote URL;
- remote `main` SHA;
- commit list;
- test results;
- exact successful demo command and JSON;
- idempotent replay JSON;
- intermediate rejection JSON;
- baseline rejection JSON;
- reconciliation evidence;
- known limitations;
- confirmation that remote `main` matches local HEAD.
```
