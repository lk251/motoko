# Next Codex Goal — Finish the Real Stripe Sandbox Settlement Loop

Use this as the complete goal in a fresh Codex CLI session on Linux.

```text
Work in:
  /home/mares/repos/agent-bounty-market

Remote:
  https://github.com/lk251/agent-bounty-market.git

Motoko fixture:
  /home/mares/repos/motoko-issue-1-tui-input-latency

Accepted Motoko candidate:
  4c03e0fa02a26f1cbadbe593ae687eaa9b333d2c

## Why this is a corrective goal

The previous Stripe goal produced useful foundations but did not complete the
requested real Stripe sandbox operation.

Current useful work includes:

- explicit `sk_test_` configuration guards;
- PaymentIntent and Transfer request mapping;
- raw-body Stripe signature verification;
- durable deduplication of Stripe event IDs;
- fake-transport tests for request arguments and replay behavior.

However, the repo still describes Stripe as only a test-mode boundary. The
current CLI has no Stripe funding/demo commands. Funding is credited
synchronously when a confirmed PaymentIntent is created, rather than from an
authoritative signed payment event. There is no Stripe-hosted Checkout flow,
funding-request lifecycle, outbound-operation journal, webhook server, connected
account inspection, real sandbox reconciliation command, or recorded successful
sandbox object chain.

There is also a correctness error to remove: `transfer.failed` is not a public
Stripe event type. Public Transfer events are `transfer.created`,
`transfer.reversed`, and `transfer.updated`. A Transfer creation failure is an
API error, not a later `transfer.failed` webhook.

Do not move on to GitHub agents or Hermes autonomy until this goal either
completes a real sandbox loop or produces one exact external setup blocker.

## Product truth

Use precise terminology throughout:

- Checkout payment: money paid to the platform in Stripe sandbox.
- Project treasury: internal ledger balance authorized for project work.
- Bounty reservation: internal movement from available to reserved.
- Connect Transfer: funds moved from platform Stripe balance to a connected
  account balance.
- Bank payout: not part of this milestone.
- The solver identity represents the human/legal operator of an agent.
- The AI does not own a bank account.
- This is not legal escrow.

The demo must tell one honest story:

```text
owner/donor pays real Stripe sandbox Checkout
→ signed webhook credits Motoko treasury exactly once
→ Motoko reserves a $25 bounty
→ protected verifier accepts exact commit 4c03e0f...
→ one real Stripe Connect Transfer credits the solver test connected account
→ replay creates no second credit, transfer, receipt, or ledger movement
```

## Read first

Read every source, test, workflow, and document, especially:

- `agent_bounty/core.py`
- `agent_bounty/db.py`
- `agent_bounty/domain.py`
- `agent_bounty/ledger.py`
- `agent_bounty/payments.py`
- `agent_bounty/stripe_webhooks.py`
- `agent_bounty/cli.py`
- `tests/test_payments.py`
- `tests/test_ledger.py`
- `tests/test_verification_recovery.py`
- `docs/architecture.md`
- `docs/threat-model.md`
- `docs/next-stripe-step.md`
- `docs/next-codex-goal-stripe-sandbox-settlement.md`

Inspect:

```bash
git status --short --branch
git log --oneline --decorate -12
git remote -v
python -m agent_bounty openshell-status || true
```

Preserve legitimate work. Never force-push. Never use live-mode Stripe.

# Phase 1 — Use current official Stripe contracts

Read current official Stripe documentation before coding:

- Checkout Sessions in `payment` mode;
- fulfilling Checkout payments from webhooks;
- raw request body webhook verification;
- API idempotency keys;
- Connect separate charges and transfers;
- Connect test accounts;
- Transfer creation, retrieval, and reversal events.

Use the official Stripe Python package for the real integration and webhook
construction. Pin the exact tested version in an optional integration dependency
file. Keep the fake gateway and core deterministic tests runnable without Stripe
credentials.

Do not hand-roll a second payment protocol. Existing manual HMAC/request code may
remain as low-level deterministic test support only if clearly separated, but
the real sandbox path must use the official library.

# Phase 2 — Fix current semantic errors

Before adding features, correct these issues with tests:

1. Remove all production and test handling of nonexistent `transfer.failed`.
2. Treat Transfer creation API errors as synchronous failures or unknown remote
   outcomes recoverable by idempotency key.
3. Handle `transfer.created` as an audit event, not a second settlement.
4. Handle `transfer.reversed` as a recorded reversal/manual-review state with a
   compensating ledger policy. Do not silently pretend the bounty remains fully
   settled.
5. Retrieval of a Transfer must verify exact amount, currency, destination,
   transfer group, metadata, and `livemode=false`; do not return `paid` merely
   because an ID starts with `tr_`.
6. Rename operator-facing wording from bank `payout` to connected-account
   `transfer` where appropriate, while preserving schema compatibility if needed.
7. Never credit project funds merely because a PaymentIntent object was created
   or a Checkout success URL was visited.

Keep existing fake-gateway semantics stable where they are useful for unit tests.

# Phase 3 — Durable funding and Stripe operation models

Add an additive SQLite migration. Do not reset old databases.

## Funding requests

At minimum:

```text
id
project_id
source_kind: owner | donation
amount
currency
status: created | checkout_pending | paid | failed | expired | review_required | refunded
checkout_session_id unique nullable
payment_intent_id unique nullable
charge_id nullable
stripe_customer_id nullable
request_idempotency_key unique
request_parameters_digest
created_at
updated_at
paid_at nullable
```

## Stripe operations

At minimum:

```text
id
kind: checkout_create | payment_intent_retrieve | account_retrieve | transfer_create | transfer_retrieve
idempotency_key unique
request_parameters_digest
status: pending | succeeded | failed | unknown_remote_result
stripe_object_type nullable
stripe_object_id nullable
stripe_request_id nullable
safe_error_code nullable
safe_error_message nullable
created_at
updated_at
```

## Stripe webhook events

Extend the existing table as needed with:

```text
api_version
account_id nullable
object_id nullable
processing_attempts
next_attempt_at nullable
```

Requirements:

- all money is integer minor units;
- Stripe object IDs are unique where appropriate;
- request idempotency keys are bound to a stable parameters digest;
- no secret or full unnecessary personal payload is persisted;
- migrations are tested from the current schema version.

# Phase 4 — Explicit sandbox configuration and status

Add `.env.example` with names only and ensure `.env` is ignored.

Use variables such as:

```text
AGENT_BOUNTY_STRIPE_SANDBOX=1
STRIPE_TEST_SECRET_KEY=sk_test_... or restricted rk_test_...
STRIPE_TEST_WEBHOOK_SECRET=whsec_...
STRIPE_TEST_CONNECTED_ACCOUNT_ID=acct_...
STRIPE_TEST_PLATFORM_ACCOUNT_ID=acct_...     # optional guard
AGENT_BOUNTY_PUBLIC_BASE_URL=http://127.0.0.1:4242
```

Implement:

```bash
python -m agent_bounty stripe-status
```

Output only safe fields:

- sandbox enabled;
- Stripe package version;
- Stripe CLI availability/version;
- platform account ID/country after authenticated retrieval;
- connected account ID/country and relevant transfer capability/status;
- webhook secret configured yes/no;
- exact blockers to the real demo.

Reject live keys and any Stripe object/event with `livemode=true`. Never print or
persist API/webhook secrets. Stripe credentials stay out of candidate and
OpenShell processes.

# Phase 5 — Stripe-hosted Checkout funding

Create a server-owned funding request, then a Checkout Session with:

- `mode=payment`;
- Stripe-hosted Checkout;
- card-only for the primary deterministic demo;
- exact server-owned amount/currency;
- line item describing Motoko project funding;
- `submit_type=donate` for donation mode where supported;
- success/cancel URLs;
- metadata binding funding request, project, source kind, amount, and currency;
- PaymentIntent metadata with the same bindings;
- stable Stripe idempotency key;
- `livemode=false` verification on returned objects.

Add:

```bash
python -m agent_bounty stripe-create-checkout \
  --db .demo/stripe.sqlite3 \
  --project-id project_motoko \
  --source owner \
  --amount-cents 2500 \
  --currency usd \
  --success-url http://127.0.0.1:4242/success \
  --cancel-url http://127.0.0.1:4242/cancel
```

Print funding request ID, Checkout Session ID, amount/currency, and Checkout URL.
Creating the Session must leave treasury available balance at zero.

Also add an explicit automated sandbox payment helper for repeatable smoke tests,
using an official Stripe test PaymentMethod only when both sandbox and integration
flags are set. It must be a separate command from the human Checkout path.

# Phase 6 — Real webhook HTTP endpoint

Add a small trusted HTTP service, preferably stdlib `http.server` plus official
Stripe signature construction:

```bash
python -m agent_bounty stripe-webhook-serve \
  --db .demo/stripe.sqlite3 \
  --host 127.0.0.1 \
  --port 4242
```

Requirements:

1. Verify `Stripe-Signature` against the exact raw request body.
2. Invalid/stale signatures return 400 and create no financial records.
3. Valid events are durably inserted by unique event ID before processing.
4. Return 2xx quickly after durable ingestion.
5. Process events idempotently and recover after restart.
6. Reject `livemode=true`.
7. Handle card Checkout events:

```text
checkout.session.completed
checkout.session.expired
payment_intent.succeeded
payment_intent.payment_failed
```

8. Use one documented canonical credit rule. Preferred:

- on `checkout.session.completed`, retrieve the Session with expanded
  PaymentIntent;
- require `payment_status=paid` for the card-only primary flow;
- validate amount total, currency, metadata, project, funding request,
  PaymentIntent status, and sandbox mode;
- record related PaymentIntent and Charge IDs;
- credit the internal treasury exactly once.

`payment_intent.succeeded` may safely reconcile an existing funding request, but
must not produce a second credit. Support async Checkout events only if easy;
otherwise document card-only scope.

Provide current Stripe CLI forwarding instructions. Never commit the printed
`whsec_` value.

# Phase 7 — Treasury credit exactly once

Only validated, signed, canonical payment completion may call the internal
ledger credit operation.

Prove:

- Checkout creation credits zero;
- success redirect credits zero;
- one signed paid event credits exactly once;
- duplicate event delivery is harmless;
- different event types for the same PaymentIntent cannot double-credit;
- replay after process restart is harmless;
- amount/currency/project/metadata mismatch enters `review_required`, no credit;
- failed/expired Checkout produces no credit;
- crash after remote object creation or event insert recovers without duplicate
  Stripe objects or ledger entries.

# Phase 8 — Validate the connected account

Use one pre-created Stripe test connected account for the hackathon demo.

Implement:

```bash
python -m agent_bounty stripe-attach-beneficiary \
  --db .demo/stripe.sqlite3 \
  --solver-id solver_codex_motoko_issue_1 \
  --account-id acct_...
```

Retrieve the account and store it only after validating sandbox context and
relevant capability/status. Output a safe summary. If account creation is not
straightforward, document exact Dashboard/test setup and use the configured ID.
Do not fake onboarding.

# Phase 9 — Real Connect Transfer after acceptance

After protected verification accepts exact candidate `4c03e0fa...`, create one
Connect Transfer with:

- exact reward amount/currency;
- validated destination account;
- stable Stripe idempotency key from internal settlement ID;
- transfer group bound to the bounty;
- metadata binding project, bounty, solver, accepted receipt, candidate SHA,
  verifier digest, backend digest, and policy digest within Stripe limits.

Immediately retrieve the `tr_...` object and validate all bindings before marking
internal settlement complete.

If platform test balance is unavailable, diagnose and document the exact Stripe
sandbox step needed to fund it. Use `source_transaction` only when there is an
unambiguous associated Charge and current Stripe documentation supports the
chosen flow. Never replace the real path with `tr_test_*` placeholders.

Handle `transfer.reversed` as an explicit reversal/manual-review operation.

# Phase 10 — Reconciliation and crash windows

Implement:

```bash
python -m agent_bounty stripe-reconcile --db .demo/stripe.sqlite3
```

It must retrieve and compare:

- Checkout Session;
- PaymentIntent and Charge;
- connected account;
- Transfer;
- internal funding request;
- accepted verification receipt;
- ledger entries and balances.

Report safe corrective actions but do not perform destructive automatic repair.

Recover these windows:

1. operation row written, API not called;
2. Stripe object created, DB update lost;
3. webhook recorded, treasury credit not committed;
4. Transfer created, internal settlement not finalized.

Use Stripe idempotency keys on every POST and local parameter-digest checks.

# Phase 11 — End-to-end real sandbox demo

Add:

```bash
python -m agent_bounty demo-stripe-motoko \
  --db .demo/stripe.sqlite3 \
  --motoko-repo /home/mares/repos/motoko-issue-1-tui-input-latency
```

Interactive path:

1. initialize project, solver, policy, and $25 bounty;
2. create real Checkout Session;
3. print URL and wait for signed funding event;
4. reserve the reward;
5. submit/verify candidate `4c03e0fa...`;
6. create/retrieve one real Connect Transfer;
7. replay funding/verification/transfer commands;
8. reconcile and print compact JSON.

JSON must include safe real sandbox IDs when available:

```text
checkout_session_id
payment_intent_id
charge_id
funding_event_id
project available/reserved/spent balances
candidate_sha
receipt_id
verifier/backend/policy digests
transfer_id
destination_account_id
replay flags
ledger_reconciled
```

Add a fully automated sandbox smoke command, gated by:

```text
AGENT_BOUNTY_STRIPE_SANDBOX=1
AGENT_BOUNTY_RUN_STRIPE_INTEGRATION=1
```

# Phase 12 — Tests

Preserve every existing fake-gateway, verifier, isolation, recovery, and ledger
test. Add deterministic fake-client tests for at least:

1. live-key/live-object refusal;
2. no secret leakage;
3. Checkout request mapping;
4. Checkout creation does not credit;
5. raw-body signature verification through official Stripe library;
6. stale/invalid signature rejection;
7. duplicate and out-of-order events;
8. two event types for one PaymentIntent credit once;
9. amount/currency/metadata mismatch;
10. failed/expired Checkout;
11. durable operation argument binding;
12. crash after Checkout creation;
13. crash after webhook insert;
14. connected account validation;
15. Transfer request/retrieval binding;
16. synchronous Transfer API failure/retry;
17. no `transfer.failed` handling anywhere;
18. `transfer.created` audit is idempotent;
19. `transfer.reversed` records reversal/manual review;
20. crash after Transfer creation;
21. accepted receipt required before transfer;
22. full reconciliation;
23. database restart preserves all idempotency.

Add optional real-sandbox integration tests that skip with one exact blocker when
credentials/network/account/Stripe CLI are unavailable. A skip is not success.

# Phase 13 — CI and documentation

Keep default CI secret-free. Add a Stripe adapter unit-test job that installs the
pinned official Stripe package but makes no network calls.

Update:

- `README.md`;
- `docs/architecture.md`;
- `docs/threat-model.md`;
- `docs/demo-flow.md`;
- `docs/next-stripe-step.md`;
- add `docs/stripe-sandbox.md`;
- add/update `docs/hermes-stripe-handoff.md`;
- `.env.example` and `.gitignore`.

Document the distinctions among Checkout payment, internal treasury, Connect
Transfer, and bank payout.

# Validation

Run:

```bash
python -m compileall agent_bounty tests verifiers
python -m unittest discover -s tests
nix develop --command python3 -m unittest discover -s tests
nix flake check
python -m agent_bounty stripe-status
git diff --check
```

When sandbox credentials are available, run the complete real demo and preserve
only safe compact object IDs/results.

Commit focused changes and push normally to `origin main`. Never force-push.

## Exit criteria

Complete only when all are true:

1. real Stripe sandbox Checkout or explicit automated sandbox payment creates a
   real `cs_...`/`pi_...` object;
2. signed webhook credits Motoko treasury exactly once;
3. accepted receipt authorizes one real `tr_...` Connect Transfer;
4. replay cannot duplicate payment, credit, receipt, transfer, or ledger rows;
5. Stripe retrieval and internal reconciliation agree;
6. no live mode, secret leakage, nonexistent event type, or fake object exists in
   the real path.

If external credentials/account setup blocks the real run, finish the code/tests,
print exact setup steps and blocker, and explicitly leave the goal incomplete.

## Final response

Return:

- commit SHA(s) and messages;
- exact defects corrected from the previous Stripe implementation;
- pinned Stripe package version;
- safe `stripe-status` output;
- setup commands with placeholders only;
- real sandbox object IDs/results if achieved;
- duplicate/replay evidence;
- reconciliation JSON;
- all test results;
- exact external blocker if incomplete;
- confirmation remote `main` matches local HEAD;
- next task only after completion: GitHub event spine and Hermes buyer/solver agents.
```
