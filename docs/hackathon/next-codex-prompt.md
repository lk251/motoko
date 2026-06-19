# Next Codex Prompt: Build the Trusted Bounty Transaction Core

Use this in a **fresh Codex CLI session on Linux** after pulling the branch
`bounty/issue-1-tui-input-latency`.

---

You are implementing the first trustworthy vertical slice of an agent-native
GitHub bounty economy for the Nous Research × NVIDIA × Stripe Hermes Agent
Accelerated Business Hackathon.

## Working environment

- Linux account: `mares`
- Motoko checkout: `/home/mares/repos/motoko`
- Motoko bounty branch: `bounty/issue-1-tui-input-latency`
- Accepted solution commit: `fdf54095b5cb8aca81984993bcd38176ccadad32`
- Baseline commit: `f4ebe1073d6fe7b9a1e2036e2a6e923ea0a68116`
- GitHub issue: `lk251/motoko#1`
- Project plan: `docs/hackathon/project-plan-through-2026-06-30.md`

Read these Motoko files first:

- `AGENTS.md`
- `README.md`
- `docs/project-context.md`
- `docs/mares-motoko-handoff.md`
- `docs/draft-pr-issue-1-tui-input-latency.md`
- `tests/bounty_issue_1.py`
- the two commits between the baseline and accepted solution

Inspect `git status --short --branch`, `git log --oneline -5`, and
`git remote -v`. Do not modify, reset, merge, or deploy Motoko. Motoko is the
first participating project and read-only fixture for this task; it is not the
bounty platform.

## Create a separate sibling repository

Create a new local repository at:

```text
/home/mares/repos/agent-bounty-market
```

This is a working name, not a final product name. If that path already exists,
inspect it and preserve any legitimate work; never overwrite it blindly.

Initialize a clean Git repository with a focused first commit history. Do not
create a remote, push, use sudo, or copy credentials.

## Objective

Build the smallest complete and trustworthy transaction core for this exact
flow:

```text
owner funds project treasury
→ treasury reserves a funded bounty
→ solver claims it
→ solver submits Motoko candidate commit fdf54095...
→ a platform-owned verifier evaluates the candidate
→ an immutable verification receipt is recorded
→ the bounty becomes accepted
→ a payment gateway releases exactly one test payout
→ project and solver ledgers reconcile
```

This task is not yet the marketplace UI, autonomous issue authoring, GitHub App,
Hermes solver, donations, recurring funding, or production Stripe integration.
Build the correct economic and verification foundation first.

## Technology and craftsmanship constraints

- Python 3.12.
- Prefer the standard library for this first core: `sqlite3`, `dataclasses`,
  `enum`, `argparse`, `subprocess`, `tempfile`, `hashlib`, `json`, and `pathlib`
  are sufficient.
- Use integer minor currency units only; never use floating point for money.
- Store timestamps in UTC ISO 8601.
- Make every state transition explicit, transactional, inspectable, and
  idempotent.
- Keep secrets out of the repository and subprocess environment.
- Include a Nix development/check path if it can be done cleanly; do not make
  Nix complexity block the vertical slice.
- No web UI in this task.
- No simulated claim that an AI is a legal person or owns a bank account. A
  solver identity is operated by a human or legal entity; its internal budget
  is a platform ledger balance.

## Domain model

Implement at minimum:

- `Project`
- `Treasury`
- `FundingEvent`
- `BudgetPolicy`
- `Bounty`
- `Claim`
- `SolverIdentity`
- `Submission`
- `VerificationRun`
- `VerificationReceipt`
- `Payout`
- `LedgerEntry`

Use a strict bounty state machine:

```text
draft
→ awaiting_funding
→ funded
→ open
→ claimed
→ submitted
→ verifying
→ accepted | rejected
→ payout_pending
→ paid
```

Also model `expired`, `cancelled`, `refunded`, and `payout_failed`, even if the
demo path does not exercise all of them yet.

Invalid state transitions must fail closed with a clear error. Replaying a
command or external event must not duplicate a reserve, release, verification,
or payout.

## Ledger rules

Use a double-entry-style or equivalently reconcilable append-only ledger.
At minimum distinguish:

- available project funds;
- reserved bounty funds;
- released/refunded funds;
- platform fees, initially zero unless explicitly configured;
- solver earned funds;
- payout in transit;
- paid funds.

Every monetary transition must have:

- integer amount and currency;
- event type;
- stable idempotency key;
- related project/bounty/solver/payout IDs;
- resulting balances or enough information to recompute them.

The database must prevent a negative available treasury balance and prevent the
same bounty from being paid twice.

## Trusted verifier runner

This is the most important trust boundary.

The candidate branch is untrusted. The payout decision must **not** execute or
import `tests/bounty_issue_1.py`, `tests/motoko_tty.py`, workflow files, or any
other acceptance logic from the candidate checkout.

Create a platform-owned verifier package such as:

```text
verifiers/motoko_issue_1/
  verifier.py
  contract.json
  README.md
```

The protected verifier should contain the minimum PTY harness needed to test the
candidate Motoko executable. It may dynamically load the candidate's `motoko`
implementation and `motoko_core` modules, but all acceptance thresholds,
measurement logic, expected fixtures, and verdict logic must come from the
platform-owned verifier repository.

The verifier must:

1. Resolve and record the baseline and candidate Git commit SHAs.
2. Create an isolated temporary checkout/worktree for the candidate.
3. Use temporary HOME/state/config paths.
4. Remove secrets and unrelated environment variables from the child process.
5. Require no model endpoint or network access.
6. Enforce a wall-clock timeout and bounded output.
7. Exercise the real Motoko TUI through a PTY.
8. Verify exact ASCII and Unicode input integrity.
9. Measure short- and long-transcript input-to-visible-composer latency.
10. Reject unless short p95 is at most 30 ms and long p95 at most 40 ms.
11. Reject transcript-dependent ordinary typing work.
12. Produce one compact JSON result and a nonzero process exit on rejection.
13. Compute a digest of the protected verifier files/contract.
14. Produce a receipt binding:

```json
{
  "bounty_id": "...",
  "base_commit": "f4ebe107...",
  "candidate_commit": "fdf54095...",
  "verifier_digest": "sha256:...",
  "accepted": true,
  "metrics": {},
  "stdout_sha256": "...",
  "stderr_sha256": "...",
  "started_at": "...",
  "finished_at": "..."
}
```

Do not call this a secure sandbox yet. It is a protected verifier runner with
process/time/environment isolation. NemoClaw/OpenShell hardening comes in a
later milestone.

## Payment gateway boundary

Define a small payment-gateway interface with idempotent operations:

- credit/fund a project treasury;
- create or record a connected solver beneficiary;
- release a payout;
- retrieve payout status.

For this task implement:

1. `FakePaymentGateway`, deterministic and fully tested, producing test-shaped
   external IDs and honoring idempotency keys.
2. A documented `StripePaymentGateway` boundary or skeleton that cannot be used
   accidentally without explicit configuration. Do not require Stripe
   credentials for tests or the local demo.

The fake gateway is not to be presented as the final Stripe integration. Its
purpose is to make the state machine and exactly-once settlement behavior
correct before credentials are introduced.

## CLI

Create a concise CLI that supports either individual commands or a scripted
demo. Suggested commands:

```text
project create
project fund
bounty create
bounty reserve
solver create
bounty claim
submission create
verification run
payout release
bounty show
ledger show
```

Provide one deterministic end-to-end command, for example:

```bash
python -m agent_bounty demo-motoko \
  --motoko-repo /home/mares/repos/motoko \
  --base-commit f4ebe1073d6fe7b9a1e2036e2a6e923ea0a68116 \
  --candidate-commit fdf54095b5cb8aca81984993bcd38176ccadad32 \
  --funding-cents 2500 \
  --reward-cents 2500
```

The output should make the economic loop legible and finish with compact JSON
containing project balance, reserved amount, bounty state, verifier receipt,
solver earnings, payout ID, and reconciliation status.

## Required adversarial tests

Automate at least these cases:

1. Happy path pays exactly once.
2. Re-running the same command/event produces no duplicate funding, reserve,
   verification, or payout.
3. Insufficient treasury funds cannot open/reserve a bounty.
4. A failed verifier produces no payout.
5. Candidate-supplied verifier code is ignored.
6. A stale or mismatched base/candidate commit is rejected.
7. A verifier timeout is rejected and recorded.
8. Malformed verifier JSON is rejected.
9. Two claims cannot simultaneously own an exclusive bounty.
10. A payout failure records `payout_failed` and can be retried safely with the
    same idempotency contract.
11. Ledger balances reconcile after every tested path.
12. Database constraints prevent negative balances and duplicate payouts.

Use synthetic fixtures where possible and the real Motoko commits for one
integration test.

## Repository structure

Use a clear structure resembling:

```text
agent-bounty-market/
  README.md
  AGENTS.md
  pyproject.toml
  flake.nix                    # optional but preferred if clean
  agent_bounty/
    __init__.py
    __main__.py
    cli.py
    db.py
    domain.py
    state_machine.py
    ledger.py
    verification.py
    payments.py
  verifiers/
    motoko_issue_1/
      verifier.py
      contract.json
      README.md
  tests/
    test_state_machine.py
    test_ledger.py
    test_verification.py
    test_payments.py
    test_motoko_integration.py
  docs/
    architecture.md
    threat-model.md
    demo-flow.md
```

Adjust names when a materially clearer design emerges, but keep separation
between trusted orchestration, untrusted candidate code, verification, and
payment settlement.

## Validation and deliverables

Before finishing:

- Run all unit and integration tests.
- Run the complete Motoko demo transaction twice and demonstrate exactly-once
  behavior.
- Run a deliberately failing candidate or threshold and demonstrate no payout.
- Run `git diff --check`.
- Review the diff for accidental secrets, private paths beyond the documented
  local fixture path, or misleading claims.
- Commit the work locally in focused commits.

Final response must include:

- new repository path;
- commit SHAs and messages;
- exact test command and results;
- exact demo command;
- compact successful transaction output;
- idempotent replay output;
- failed-verification/no-payout output;
- architecture summary;
- known limitations;
- the single best next task.

Do not push, deploy, create cloud resources, use real money, or modify the
Motoko repository.
