# Next Codex goal: harden Agent Bounty Market before external integrations

## Target repository

Work only in:

```text
/home/mares/repos/agent-bounty-market
```

The Motoko repository contains this goal file only. Do not make further Motoko product changes.

## Objective

Make the current local transaction core safe to connect to GitHub and Stripe in the following goal. Preserve the working Motoko proof suite while closing recovery, idempotency, policy, and claim-lifecycle gaps found during review.

Do not add Stripe, GitHub webhooks, Hermes, NemoClaw, a UI, or marketplace discovery in this goal.

## Baseline

Before editing:

1. Read the README, architecture, threat model, demo flow, all files under `agent_bounty/`, every test, and the Motoko v2 verifier contract.
2. Record `git status --short --branch`, `git log --oneline -10`, and the starting SHA.
3. Run all existing tests and the complete Motoko demo suite.
4. Work on a dedicated branch. Do not rewrite published history or discard unrelated work.

## Required changes

### 1. Argument-bound idempotency

`Ledger.transfer()` currently returns an existing entry for a repeated idempotency key without proving that the repeated operation is identical.

On replay, compare every material field:

- event type;
- source and destination accounts;
- amount and currency;
- project, bounty, solver, and payout identifiers;
- external identifier where applicable.

Return a replay only when they match. Otherwise fail closed with a clear domain error.

Apply the same principle to immutable creation. Reusing a bounty ID with a different project, reward, currency, base commit, issue reference, verifier, or issue class must fail.

### 2. Recoverable settlement state

A process can stop after a bounty enters `payout_pending`, or after the gateway accepts a settlement but before the local success transaction commits. The current code can leave the bounty stranded.

Add a durable gateway-operation or outbox record with explicit states such as:

- prepared;
- request in flight / outcome unknown;
- succeeded;
- retryable failure;
- terminal failure.

A restart must reconcile and complete the same logical settlement without duplicate gateway action or duplicate ledger entries. Keep one stable gateway idempotency key per logical settlement.

Extend the fake gateway with deterministic fault injection for:

- failure before remote acceptance;
- remote acceptance followed by a lost response;
- interruption after local pending state;
- retry after a fresh process opens the same database.

### 3. Verification recovery

If the verifier runner raises an unexpected exception, the bounty and verification run must not remain permanently stuck in `verifying`.

Record a durable failed or retryable result, preserve a safe error classification, and provide an explicit retry path. Retrying must not duplicate receipts or state events.

### 4. Enforce budget policy

The schema stores a project budget policy but reservation currently does not enforce it. Add the minimum bounty and approval fields needed to enforce:

- maximum bounty amount;
- allowed issue classes;
- monthly autonomous budget;
- human approval threshold.

At or below the threshold, reservation may proceed automatically. Above it, reservation must fail until an explicit idempotent owner approval exists.

Record policy decisions and approvals in auditable tables. Compute monthly usage from committed economic events rather than an unaudited mutable counter.

### 5. Enforce claim leases

Validate lease timestamps when claims are created. Prevent submission after expiry. Add an idempotent expiry operation that closes the stale claim and returns an eligible funded bounty to `open` without releasing its reserved money.

A stale solver must not submit after a later solver acquires a new lease.

### 6. Rejected submission lifecycle

Add an explicit path from a rejected submission back to `open` so a different solver can claim the still-funded bounty. Close the rejected claim and prevent further submission under it.

### 7. Strong invariant reporting

Expand reconciliation so it detects at least:

- more than one successful settlement per bounty;
- paid state without an accepted receipt;
- receipt bindings inconsistent with payout, solver, commit, base, verifier, or issue;
- reserved balances inconsistent with funded/open/claimed/submitted/verifying bounties;
- pending gateway operations with no corresponding payout row;
- negative internal balances;
- idempotency replay whose stored arguments differ.

Expose a compact JSON invariant report for tests and later demo diagnostics.

## Automated tests

Preserve all current tests and add deterministic adversarial coverage for:

- every changed-argument idempotency replay;
- same bounty ID with changed immutable fields;
- interruption before gateway request;
- lost response after remote success;
- restart from `payout_pending`;
- repeated reconciliation and settlement retries;
- unexpected verifier exception and retry;
- maximum amount, issue class, monthly budget, and approval threshold enforcement;
- duplicate owner approval;
- expired-claim submission rejection;
- claim expiry followed by a different solver claim;
- rejected submission reopened and solved by a new solver;
- invariant checker detecting deliberately corrupted fixtures;
- complete Motoko baseline/intermediate/final/replay regression.

## Documentation

Update architecture and threat model with:

- durable gateway-operation lifecycle;
- exact restart/recovery semantics;
- policy decision and approval records;
- claim lease lifecycle;
- rejected-bounty reopening;
- remaining trust boundary before external integrations.

Add a short recovery drill covering interruption at each settlement boundary and the expected final state.

## Validation

Run at minimum:

```bash
python -m compileall agent_bounty tests verifiers
python -m unittest discover -s tests
nix flake check
python -m agent_bounty demo-motoko-suite \
  --motoko-repo /home/mares/repos/motoko-issue-1-tui-input-latency
```

## Exit criteria

Complete only when:

- all existing behavior remains green;
- idempotency replays are bound to original arguments;
- pending settlement always has a safe restart path;
- unexpected verifier failure is recoverable;
- budget policy is actually enforced;
- claim expiry and rejected resubmission work;
- invariant reporting catches corrupted state;
- the Motoko proof suite still rejects baseline and intermediate candidates, accepts the final candidate, and settles exactly once on replay.

Commit focused changes, push the branch, and report exact SHAs, commands, test counts, recovery scenarios, and remaining blockers. Do not merge without review.