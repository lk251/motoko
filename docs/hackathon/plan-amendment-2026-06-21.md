# Hackathon Plan Amendment — June 21, 2026

This amendment supersedes conflicting status or dates in
`project-plan-through-2026-06-30.md`.

## Status corrections

### Motoko bounty #1 is still open

The idle TUI candidate materially improved buffered input rendering, but it did
not solve the actual user-visible defect during real background study. The
previous verifier disabled background study, so its successful result is only an
idle-path result.

The remaining defect is phase-linked:

- input may remain invisible during `study: evidence-store`;
- accumulated input can appear only after transition to `bg-light: catalog(cpu)`;
- catalog CPU work can introduce delays measured in seconds.

The corrected implementation prompt is:

```text
docs/hackathon/next-codex-prompt-background-study-latency.md
```

The bounty is accepted only after the one-command verifier includes a separate
Motoko child process running the real background worker path.

### `agent-bounty-market` is not yet reviewable on GitHub

As of June 21, GitHub reports `lk251/agent-bounty-market` as an empty repository
(size zero, default branch `main`). Codex's local commit `a30d325` may exist on
HB3, but it is not present on the GitHub remote yet. Do not treat the transaction
core as reviewed until that commit is actually visible remotely.

## Stripe/Hermes integration strategy

The product has two distinct financial layers. They should not be conflated.

### Layer A — market settlement: required

This is the core business transaction:

```text
owner/donor funds a project treasury
→ reward is reserved
→ repository-owned verification accepts work
→ Stripe releases exactly one payout to the human/legal entity operating the solver
```

Use ordinary Stripe sandbox/test-mode APIs and the appropriate marketplace payout
flow, most likely Stripe Connect, with webhook verification and idempotency. The
internal agent balance remains a platform ledger balance; the AI is not a legal
account holder.

This layer is critical path and must be real in Stripe test mode for the demo.

### Layer B — agent operating spend: valuable extension

Hermes now exposes optional payment skills that can let a solver/project agent
buy resources needed to complete work:

1. **MPP Agent** — pay HTTP-402 APIs per request.
2. **Stripe Projects** — provision supported SaaS resources and sync credentials.
3. **Stripe Link CLI** — obtain an approved one-time card or Shared Payment Token.

Use these only where the bounty itself creates a genuine need. The strongest
story is:

```text
solver underwrites bounty
→ determines a paid tool/API/service is justified
→ requests/uses a scoped payment capability
→ completes work
→ earns more than it spent
```

This gives the solver an operating budget rather than merely a payout account.

### Priority for this project

1. **Stripe test-mode market settlement** — mandatory.
2. **Hermes + MPP paid API call** — preferred optional demonstration if a real,
   inexpensive, relevant HTTP-402 service is available.
3. **Hermes + Stripe Projects provisioning** — use only if a bounty genuinely
   needs a supported service or sandbox. Do not provision Neon/Vercel/Runloop
   merely for sponsor screen time.
4. **Stripe Link CLI** — not on the critical path. Hermes documents it as
   US-only for Link authentication and every spend requires Link approval, so it
   is unreliable for Javier in Spain and is not fully autonomous.
5. **Stripe MCP** — appropriate for a trusted Hermes orchestration process to
   inspect/manage Stripe objects through OAuth or a restricted key. Keep it out
   of untrusted solver sandboxes.

### Credential boundary

- Stripe/MPP/Projects credentials stay in trusted orchestration or provider CLIs.
- Candidate repository code never receives Stripe secrets.
- `.env` writes from Stripe Projects require a verified `.gitignore` before use.
- Any billable provisioning action must have an explicit budget policy and an
  immutable ledger record.
- Link one-time card details must never enter the model transcript.

## Revised critical path: June 21–30

## Sunday, June 21

1. Push local `agent-bounty-market` commit `a30d325` to GitHub `main` and verify
   the remote SHA.
2. Start the corrected Motoko background-study responsiveness task.
3. Do not add new marketplace features before the transaction core is remotely
   reviewable.

Exit:

- market repository is non-empty and reviewable;
- background-study verifier fails on the current candidate in a separate-process
  PTY test.

## Monday, June 22

1. Finish the real Motoko responsiveness fix.
2. Run the corrected one-command verifier five times.
3. Review `a30d325` for state-machine, ledger, verifier-boundary, and idempotency
   correctness.
4. Fix only confirmed core defects.

Exit:

- Motoko bounty is genuinely accepted;
- transaction core has an explicit review verdict.

## Tuesday, June 23

1. Replace or complement the fake payment gateway with real Stripe sandbox/test
   funding and payout flow.
2. Verify webhook signatures and persist event/object IDs.
3. Demonstrate exactly-once payout and safe retry.
4. Keep the fake provider for deterministic tests.

Exit:

- one real Stripe test-mode funding event and one real test payout are attached
  to the accepted bounty.

## Wednesday, June 24

1. Add the minimum GitHub event spine for issue, claim, PR/candidate SHA, checks,
   and acceptance.
2. Bind the trusted verifier receipt to repository, base SHA, candidate SHA, and
   verifier digest.
3. Make replay harmless.

Exit:

- no manual database edits in the Motoko happy path.

## Thursday, June 25

1. Implement the project-agent buyer policy:
   budget, maximum reward, minimum reserve, allowed task classes, verifier
   requirement, and human-approval threshold.
2. Let it choose/specify/price one bounded issue from a curated set.
3. Reserve funds before publication.

Exit:

- the project agent can spend without overspending or funding unverifiable work.

## Friday, June 26

1. Implement the specialized solver-agent path in Hermes.
2. At least one unsuitable agent declines and one suitable agent claims.
3. The solver works in the NVIDIA-prescribed isolated path using
   NemoClaw/OpenShell where available.
4. Add empirical capability records rather than persona-only specialization.

Exit:

- a real solver decision and safe work execution are visible.

## Saturday, June 27

1. Run the complete authentic loop from fresh state:
   fund → define → reserve → discover → claim → submit → verify → accept → pay.
2. Replay key events to prove no duplicate payout.
3. Capture artifacts and clean video footage.

Optional only after the loop works:

- let the solver use MPP to buy one genuinely useful paid API call and show cost,
  benefit, and resulting margin.

## Sunday, June 28

Priority order:

1. reliability and removal of manual steps;
2. presentation-quality UI/CLI output;
3. a second small bounty;
4. donation funding;
5. recurring funding;
6. Stripe Projects provisioning demonstration.

Cut anything below the highest completed priority if it threatens the primary
loop.

## Monday, June 29

1. Record a 1–3 minute demo.
2. Show the real Motoko bug/fix briefly, not a benchmark lecture.
3. Show Stripe funding and payout, GitHub issue/PR, protected verification,
   buyer/solver decisions, and final reconciled balances.
4. Prepare tweet, short writeup, submission form, and backup recording.

## Tuesday, June 30

1. Run a fresh end-to-end rehearsal.
2. Verify no secrets/private data appear.
3. Submit well before organizer EOD ambiguity; target before 18:00 Europe/Madrid.

## Demo narrative

The central line remains:

> A software project can now operate as a bounded economic actor: it receives a
> budget, autonomously buys a verified improvement from a specialized agent, and
> pays exactly once when trusted evidence proves the work.

The optional operating-spend extension is:

> The solver can also spend a controlled portion of its budget on tools, APIs, or
> services needed to complete the job, making agent profit and intelligence per
> dollar measurable.
