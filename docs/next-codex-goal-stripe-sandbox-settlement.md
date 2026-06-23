# Next Codex Goal — Real Stripe Sandbox Funding and Solver Settlement

Use this as the complete goal in a fresh Codex CLI session on Linux.

```text
Work in:
  /home/mares/repos/agent-bounty-market

Remote:
  https://github.com/lk251/agent-bounty-market.git

Motoko fixture:
  /home/mares/repos/motoko-issue-1-tui-input-latency

Motoko accepted candidate:
  4c03e0fa02a26f1cbadbe593ae687eaa9b333d2c

## Purpose

The market now has:

- an explicit bounty state machine;
- a reconcilable append-only ledger;
- a protected verifier v2;
- black-box candidate execution;
- malicious/baseline/intermediate rejection and final-candidate acceptance;
- verification restart recovery;
- exactly-once behavior against a fake payment gateway.

The next critical milestone is to replace the fake financial story in the demo
with a real Stripe **sandbox** operation:

```text
owner or donor completes Stripe Checkout
→ signed webhook credits the project treasury exactly once
→ Motoko bounty reserves those funds
→ protected verification accepts the exact candidate commit
→ Stripe Connect transfers the reward to the solver operator's test connected account
→ duplicate events and retries do not duplicate money movement
→ Stripe objects and the internal ledger reconcile
```

This goal is sandbox/test mode only. Never create live charges, transfers, or
payouts.

## Product language

Be precise:

- The project has an internal platform treasury balance.
- The solver identity represents a human or legal entity operating an agent.
- Stripe Connect creates a **transfer to a connected account**. Do not claim that
  the AI owns a bank account or that a Connect Transfer is already a bank payout.
- Do not call the platform legal escrow.
- The redirect success page is not proof of payment. Signed Stripe events and
  retrieved Stripe object state are authoritative.

## Read first

Read every current source, test, workflow, and document, especially:

- `agent_bounty/core.py`
- `agent_bounty/db.py`
- `agent_bounty/domain.py`
- `agent_bounty/ledger.py`
- `agent_bounty/payments.py`
- `agent_bounty/verification.py`
- `agent_bounty/execution.py`
- `tests/test_ledger.py`
- `tests/test_payments.py`
- `tests/test_verification_recovery.py`
- `docs/architecture.md`
- `docs/threat-model.md`
- `docs/next-stripe-step.md`
- `docs/openshell-verifier.md`

Inspect:

```bash
git status --short --branch
git log --oneline --decorate -10
git remote -v
python -m agent_bounty openshell-status
```

Preserve legitimate work. Never force-push.

## Use current official Stripe guidance

Before implementation, consult current official Stripe documentation for:

- Checkout Sessions in `payment` mode;
- webhook signature verification using the raw request body;
- API idempotency keys;
- Connect test accounts;
- separate charges and transfers;
- Transfer creation and retrieval;
- Stripe CLI local event forwarding.

If `npx` is available, inspect Stripe's official agent skills:

```bash
npx skills add https://docs.stripe.com --list
```

Install and follow the relevant Stripe best-practices skill if available. Do not
let skill installation block the implementation.

Use the official Stripe Python library for the real integration. Keep the core
usable without it by making Stripe support an explicit optional dependency.
Pin the exact version tested in this goal. Never hand-roll card handling.

# Phase 1 — Explicit sandbox configuration and status

Implement a configuration object for the Stripe sandbox integration.

Suggested environment variables:

```text
AGENT_BOUNTY_STRIPE_SANDBOX=1
STRIPE_TEST_SECRET_KEY=sk_test_... or rk_test_...
STRIPE_TEST_WEBHOOK_SECRET=whsec_...
STRIPE_TEST_CONNECTED_ACCOUNT_ID=acct_...
STRIPE_TEST_PLATFORM_ACCOUNT_ID=acct_...        # optional expected-account guard
AGENT_BOUNTY_PUBLIC_BASE_URL=http://localhost:4242
```

Requirements:

1. Refuse to initialize unless `AGENT_BOUNTY_STRIPE_SANDBOX=1`.
2. Accept only test/sandbox keys. Reject `sk_live_`, `rk_live_`, or any object/event
   with `livemode=true`.
3. Never print, persist, hash into public receipts, or expose the API key or
   webhook secret.
4. Keep Stripe credentials only in trusted orchestration. Never pass them to the
   verifier, candidate checkout, OpenShell sandbox, or Hermes solver workspace.
5. Add `.env.example` containing names and descriptions only. Confirm `.env` is
   ignored.
6. Add:

```bash
python -m agent_bounty stripe-status
```

It must report, without secrets:

- sandbox enabled/disabled;
- official Stripe Python package version;
- Stripe CLI availability/version;
- authenticated platform account ID and country when configured;
- configured connected account ID and whether retrieval succeeds;
- webhook secret configured yes/no;
- exact blockers to running the real demo.

# Phase 2 — Stripe-specific durable schema

Add a migration rather than resetting existing databases.

Model at minimum:

## Funding requests

```text
id
project_id
source_kind: owner | donation
amount
currency
status: created | checkout_pending | paid | failed | expired | refunded | review_required
checkout_session_id
payment_intent_id
charge_id
stripe_customer_id optional
request_idempotency_key
request_parameters_digest
created_at / updated_at / paid_at
```

## Stripe events

```text
event_id primary/unique
event_type
livemode
api_version
object_id
payload_sha256
received_at
processed_at
status: received | processed | ignored | failed
processing_error
```

## Stripe API operations

```text
id
operation_kind: checkout_create | payment_retrieve | account_retrieve | transfer_create | transfer_retrieve
idempotency_key unique
request_parameters_digest
status: pending | succeeded | failed | unknown_remote_result
stripe_object_type
stripe_object_id
stripe_request_id optional
error_code / error_message_safe
created_at / updated_at
```

Extend payout/solver records only as needed to bind:

- connected account ID;
- Stripe Transfer ID;
- accepted receipt ID;
- candidate SHA;
- verifier/backend/policy digests.

All amounts remain integer minor units. Existing fake-gateway data and tests must
continue working.

# Phase 3 — Stripe Checkout for owner and donor funding

Implement a `StripeSandboxPaymentGateway` or equivalently clear adapter.

Create a Stripe-hosted Checkout Session with:

- `mode=payment`;
- card-only or another deliberately synchronous sandbox method for the primary
  demo;
- exact server-owned amount and currency;
- one line item describing project treasury funding;
- `submit_type=donate` for donation funding where appropriate;
- success and cancel URLs;
- metadata binding the project ID, funding-request ID, source kind, amount, and
  currency;
- the same metadata propagated to the PaymentIntent;
- a stable Stripe API idempotency key derived from the internal funding request;
- no client-controlled amount, project ID, or metadata.

Add a command such as:

```bash
python -m agent_bounty stripe-create-funding-checkout \
  --db .demo/stripe.sqlite3 \
  --project-id project_motoko \
  --source owner \
  --amount-cents 2500 \
  --currency usd \
  --success-url http://localhost:4242/success \
  --cancel-url http://localhost:4242/cancel
```

Output compact JSON containing the internal funding request ID, Checkout Session
ID, PaymentIntent ID if available, amount/currency, and Checkout URL. Do not
include secrets.

Creating or visiting Checkout must **not** credit the internal treasury.

For an automated sandbox smoke path, support a separate explicit command that
uses an official Stripe test payment method such as `pm_card_visa`, only when
`AGENT_BOUNTY_STRIPE_SANDBOX=1`. The interactive Checkout path remains the
presentation path.

# Phase 4 — Signed webhook ingestion and processing

Build a small trusted webhook service using either the standard library HTTP
server or a minimal justified dependency. Prefer keeping the server small.

Suggested command:

```bash
python -m agent_bounty stripe-webhook-serve \
  --db .demo/stripe.sqlite3 \
  --host 127.0.0.1 \
  --port 4242
```

Use the raw request bytes and the official Stripe library to verify the
`Stripe-Signature` header against `STRIPE_TEST_WEBHOOK_SECRET`.

Requirements:

1. Invalid signatures return 400 and create no financial state.
2. Valid events are durably inserted by unique Stripe event ID before complex
   processing.
3. Duplicate delivery returns 200 and cannot duplicate a ledger entry.
4. Reject or safely ignore `livemode=true`.
5. Preserve raw payload digest, not secrets or unnecessary personal data.
6. Return 2xx quickly after durable ingestion. Process queued events in a bounded
   worker or explicit processor command.
7. Event processing is restart-safe.
8. Out-of-order events are harmless.
9. The canonical funding event should be `payment_intent.succeeded` after
   retrieving the PaymentIntent from Stripe and checking:

   - status is `succeeded`;
   - `amount_received` equals the internal expected amount;
   - currency matches;
   - project/funding metadata matches;
   - the PaymentIntent is in sandbox mode;
   - it is associated with the expected Checkout Session/funding request where
     applicable.

10. Handle at least:

```text
payment_intent.succeeded
payment_intent.payment_failed
checkout.session.completed
checkout.session.expired
```

Use `checkout.session.completed` for traceability, not duplicate treasury credit.
If card-only Checkout is used, document why asynchronous payment events are out
of primary demo scope.

Provide Stripe CLI instructions:

```bash
stripe listen \
  --events payment_intent.succeeded,payment_intent.payment_failed,checkout.session.completed,checkout.session.expired \
  --forward-to localhost:4242/stripe/webhook
```

Do not commit the `whsec_` secret printed by the CLI.

# Phase 5 — Credit the internal treasury exactly once

Only a successfully processed canonical funding event may call the internal
funding/ledger operation.

Bind Stripe event ID, PaymentIntent ID, Charge ID, funding request, and ledger
entry.

Prove:

- two deliveries of one event create one funding event and one ledger transfer;
- two different Stripe events for the same PaymentIntent still credit once;
- event replay after process restart remains harmless;
- amount, currency, project, or metadata mismatch creates `review_required` and
  no credit;
- a failed or expired Checkout creates no credit;
- an API timeout after Stripe created the object can be reconciled using the same
  idempotency key and retrieved object;
- a DB failure after Stripe success can recover without creating another remote
  object.

# Phase 6 — Connect solver beneficiary

Use one pre-created Stripe **test connected account** for the primary demo.
Avoid spending the milestone on full public onboarding.

Add a command such as:

```bash
python -m agent_bounty stripe-attach-beneficiary \
  --db .demo/stripe.sqlite3 \
  --solver-id solver_codex_motoko_issue_1 \
  --account-id acct_...
```

The command must retrieve the account through the sandbox Stripe client and
store it only after validation. Show a safe summary: account ID, country,
relevant capability/status fields, and whether it is usable for a test transfer.

If creating a sandbox connected account through the current Accounts API is
straightforward, add an optional helper. Otherwise provide exact Dashboard/API
setup instructions and use `STRIPE_TEST_CONNECTED_ACCOUNT_ID`. Do not fake
onboarding success.

# Phase 7 — Real Stripe Connect transfer after accepted verification

When the bounty is accepted and has an exact accepted receipt, the real gateway
must create a Connect **Transfer** to the solver's connected account.

Use separate charges and transfers semantics. The Transfer must include:

- exact reward amount and currency;
- destination connected account;
- stable Stripe idempotency key derived from the internal payout ID;
- `transfer_group` bound to the bounty ID;
- metadata including project ID, bounty ID, solver ID, receipt ID, candidate SHA,
  verifier digest, backend digest, and policy digest, within Stripe limits.

Persist the returned `tr_...` ID and retrieve it to verify amount, currency,
destination, and metadata before marking the internal settlement paid.

If the sandbox platform balance cannot fund the transfer immediately, diagnose
honestly. Use `source_transaction` only when the funding Charge can be safely and
unambiguously associated with this one bounty and current Stripe guidance
supports it. Otherwise seed the sandbox balance through a documented Stripe test
method. Never substitute a fake transfer in the real demo path.

A Connect Transfer credits the connected account balance. Label it accurately in
CLI output and docs. Bank payout is a later connected-account operation.

# Phase 8 — External-call consistency and reconciliation

Every Stripe POST must use a stable idempotency key and a stored request digest.
Reusing a key with different arguments must fail locally before API invocation.

Implement recovery for these crash windows:

1. operation row persisted, API not called;
2. API succeeded, process died before DB update;
3. API response persisted, ledger/state transition not committed;
4. transfer succeeded, process died before payout finalization.

Add:

```bash
python -m agent_bounty stripe-reconcile --db .demo/stripe.sqlite3
```

It retrieves referenced Stripe objects and reports:

- internal versus Stripe amount/currency;
- funding request/PaymentIntent/Charge linkage;
- transfer destination and amount;
- event-processing status;
- payout/receipt linkage;
- ledger reconciliation;
- safe corrective actions, never automatic destructive mutation.

# Phase 9 — End-to-end Stripe sandbox demo

Add a command such as:

```bash
python -m agent_bounty demo-stripe-motoko \
  --db .demo/stripe.sqlite3 \
  --motoko-repo /home/mares/repos/motoko-issue-1-tui-input-latency
```

The interactive run should:

1. create Motoko project, policy, solver, and $25 bounty;
2. create a real Stripe Checkout Session and print the URL;
3. wait for signed webhook confirmation of paid project funding;
4. reserve the $25 reward;
5. submit/verify exact candidate `4c03e0fa...`;
6. create one real Stripe Connect Transfer to the configured test account;
7. replay key events/commands;
8. print final compact JSON.

Final JSON must clearly include:

```text
checkout_session_id
payment_intent_id
charge_id
funding Stripe event ID
project available/reserved/spent balances
candidate SHA
accepted receipt ID and verifier/backend/policy digests
Stripe Transfer ID and destination account ID
replayed flags
ledger reconciled true/false
```

Also provide a fully automated sandbox smoke command for repeatable testing. It
must be explicitly gated and must never run against live mode.

# Phase 10 — Hermes/Stripe handoff documentation

Add `docs/hermes-stripe-handoff.md` explaining the next agent layer:

- Hermes project agent will invoke the trusted market CLI, not hold Stripe keys
  in its prompt or solver sandbox.
- Stripe MCP may be used by a trusted operator/orchestrator for read/audit calls
  using OAuth or a restricted key.
- MPP and Stripe Projects remain later optional solver operating-spend tools.
- Stripe Link CLI is not part of the critical path, especially because current
  Link agent-wallet availability/approval constraints may not fit a Spain-based
  autonomous demo.

Do not implement MPP, Stripe Projects, Link purchases, or Hermes autonomy in this
goal.

# Required tests

Keep all existing fake-gateway, verifier, isolation, recovery, and ledger tests.
Add deterministic tests with a fake Stripe transport/client for:

1. sandbox/live-key guard;
2. no secret leakage in status/errors/JSON;
3. Checkout request parameters and metadata;
4. Stripe API idempotency key argument binding;
5. valid webhook signature;
6. invalid signature;
7. stale signature timestamp;
8. duplicate Stripe event delivery;
9. duplicate event types for one PaymentIntent;
10. out-of-order events;
11. amount/currency/metadata mismatch;
12. `livemode=true` rejection;
13. payment failure and Checkout expiry;
14. crash after remote Checkout creation;
15. crash after successful funding event before ledger commit;
16. connected account missing/invalid;
17. transfer creation arguments and metadata;
18. transfer failure and safe retry;
19. crash after remote Transfer success;
20. transfer retrieval mismatch;
21. paid Transfer replay produces same `tr_` ID and no duplicate ledger rows;
22. real accepted receipt required before Transfer;
23. Stripe reconciliation reports all object/ledger links;
24. database restart preserves event/API idempotency.

Add optional real-sandbox tests gated by:

```text
AGENT_BOUNTY_STRIPE_SANDBOX=1
AGENT_BOUNTY_RUN_STRIPE_INTEGRATION=1
```

They must skip with an exact blocker when credentials, Stripe CLI, connected
account, or network are unavailable. Never convert a skipped real integration
into a claimed success.

# CI and dependencies

- Keep default CI runnable without Stripe credentials.
- Add the official Stripe Python package as an optional/tested integration
  dependency and pin the version used.
- Preserve the fake gateway for deterministic unit tests.
- Add a CI job for Stripe adapter unit/contract tests with no network or secrets.
- Never commit Checkout URLs containing sensitive client state, API keys,
  webhook secrets, or full webhook payloads with unnecessary personal data.

# Documentation

Update:

- `README.md`;
- `docs/architecture.md`;
- `docs/threat-model.md`;
- `docs/demo-flow.md`;
- replace `docs/next-stripe-step.md` with completed status and next steps;
- add `docs/stripe-sandbox.md`;
- add `docs/hermes-stripe-handoff.md`.

Document the exact distinction among:

- internal treasury funding;
- Stripe Checkout payment;
- Stripe platform balance;
- Connect Transfer to the solver connected account;
- eventual bank payout outside this milestone.

# Validation

Run all existing validation plus:

```bash
python -m compileall agent_bounty tests verifiers
python -m unittest discover -s tests
nix develop --command python3 -m unittest discover -s tests
nix flake check
python -m agent_bounty stripe-status
git diff --check
```

When sandbox credentials and network are available, run the real Checkout,
signed webhook, accepted Motoko verification, Connect Transfer, replay, and
reconciliation path. Preserve safe object IDs and compact outputs for the demo.

Commit in focused commits and push normally to `origin main`. Never force-push.

# Non-goals

Do not implement:

- live-mode Stripe;
- production tax/legal/escrow handling;
- public solver onboarding;
- recurring donations/subscriptions;
- disputes and post-payment clawback beyond recording/fail-closed status;
- MPP purchases;
- Stripe Projects provisioning;
- Link agent wallet;
- GitHub App/webhooks;
- Hermes buyer/solver autonomy;
- marketplace web UI.

# Exit criteria

This goal is complete only when:

1. a real Stripe sandbox Checkout or automated test payment funds the Motoko
   project;
2. a signed webhook credits the internal treasury once;
3. the accepted Motoko receipt authorizes one real Connect Transfer;
4. duplicate webhooks/API retries do not duplicate funding or settlement;
5. Stripe object retrieval and the internal ledger reconcile;
6. no live key, secret, or fake Stripe object appears in the real demo path.

If credentials or connected-account setup block the live sandbox run, complete
all code/tests/docs, print the exact minimal setup commands, and state the
blocker honestly. Do not mark the exit criteria complete.

# Final response

Return:

- commit SHA(s) and messages;
- official Stripe Python package version used;
- exact setup/environment commands without secret values;
- `stripe-status` output;
- Checkout Session, PaymentIntent, Charge, event, and Transfer IDs from sandbox,
  if completed;
- signed-webhook duplicate/replay evidence;
- successful Connect Transfer and retrieval evidence;
- reconciliation JSON;
- fake and real test results;
- skipped integration blockers, if any;
- confirmation remote `main` matches local HEAD;
- next task: GitHub event spine plus Hermes project/solver agents.
```
