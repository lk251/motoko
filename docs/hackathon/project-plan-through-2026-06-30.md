# Agent-Native GitHub Bounty Economy: Plan Through June 30, 2026

## North star

Demonstrate one authentic economic operation in which:

```text
a real software project has a funded operating budget
→ its agent defines and purchases useful software work
→ a specialized solver agent chooses and completes the work
→ repository-owned verification proves the result
→ Stripe releases payment exactly once
→ both project and solver ledgers update
```

The hackathon product is not merely a bounty board and not merely a coding
agent. It is a trustworthy market in which software-project agents can **spend**
and solver agents can **earn**, with independent verification between them.

## Winning standard

The submission must score strongly on the stated judging dimensions:

- **Usefulness:** a maintained project obtains a genuine improvement it needed.
- **Viability:** funding, reservation, verification, settlement, identity, and
  failure handling form a credible business operation rather than a staged
  animation.
- **Presentation:** judges understand the complete economic loop in under three
  minutes and can see the real issue, pull request, verifier result, and Stripe
  transaction.

Every sponsor must be structurally useful:

- **Hermes / Nous:** persistent project and solver agents, skill/capability
  memory, issue selection, task underwriting, and reusable software skills.
- **NVIDIA:** safe autonomous execution through NemoClaw/OpenShell and useful
  Nemotron/verified agent skills where they improve the workflow.
- **Stripe:** project funding, controlled treasury accounting, and payout to the
  human or legal entity operating the successful solver agent.
- **GitHub:** real issues, commits, pull requests, checks, and repository-owned
  acceptance evidence.

## Foundation completed by June 19

- Real Motoko issue #1 created for visible raw-TUI typing latency.
- Baseline commit preserved: `f4ebe1073d6fe7b9a1e2036e2a6e923ea0a68116`.
- Solver implementation completed on the bounty branch.
- Accepted candidate commit:
  `fdf54095b5cb8aca81984993bcd38176ccadad32`.
- One-command PTY verifier implemented with exact input integrity and short/long
  transcript latency thresholds.
- Repeated verifier runs accepted with p95 latency far below the contract.
- Full Motoko validation passed.
- Next implementation prompt stored at
  `docs/hackathon/next-codex-prompt.md`.

This Motoko branch now serves as the first authentic project/bounty fixture. Do
not turn Motoko itself into the marketplace.

## Fixed scope for the submission

The minimum winning product must include:

1. One funded project treasury.
2. Owner funding in Stripe test mode.
3. One Motoko bounty with a reserved reward.
4. One solver identity.
5. One claim and candidate submission.
6. A protected verifier that the candidate cannot rewrite.
7. An immutable acceptance receipt bound to exact commits and verifier digest.
8. Exactly-once Stripe test-mode payout.
9. Reconciled project and solver ledgers.
10. A project agent that can define/fund a bounded issue under policy.
11. A solver agent that can discover, underwrite, claim, solve, and submit a
    suitable funded issue.
12. Safe execution using the sponsor stack.
13. A polished 1–3 minute demo of the whole loop.

## Explicit non-goals before the deadline

Do not spend critical-path time on:

- production legal escrow;
- real-money public launch;
- tax handling across jurisdictions;
- arbitrary untrusted repositories and languages;
- a liquid public marketplace;
- elaborate token economics;
- broad social reputation systems;
- auction theory beyond a simple fixed reward;
- mobile applications;
- a large multi-page dashboard;
- generalized enterprise procurement;
- supporting every GitHub event;
- perfect branding before the product works.

Donations, recurring budgets, multiple specialized solvers, and a second bounty
are valuable only after the complete primary loop is reliable.

---

# Daily execution plan

## Friday, June 19 — Trusted transaction-core kickoff

### Build

- Pull the Motoko bounty branch and read the durable prompt/plan.
- Create the separate sibling repository
  `/home/mares/repos/agent-bounty-market`.
- Implement the domain model, SQLite persistence, state machine, append-only
  ledger, protected verifier runner, fake payment gateway, and CLI-driven
  Motoko transaction.
- Keep candidate code and verifier policy on opposite sides of the trust
  boundary.

### Required evidence

- Successful Motoko transaction output.
- Idempotent replay with no duplicate payout.
- Failed verification path with no payout.
- Ledger reconciliation.

### Exit criterion

A single local command can move the accepted Motoko candidate from funded
bounty through verified test payout, twice safely, without manual database
editing.

## Saturday, June 20 — Harden the core and freeze the state model

### Build

- Review Codex's transaction-core implementation.
- Correct state-transition, idempotency, money, or verifier-boundary defects.
- Add adversarial tests for duplicate events, failed payout, insufficient
  balance, concurrent claim, stale commit, timeout, and malformed verifier
  output.
- Add architecture and threat-model documents.
- Freeze the primary state machine and ledger vocabulary after review.

### Exit criterion

The core survives the complete adversarial test suite and can explain every
cent and state transition.

### Cut rule

Do not add UI or autonomous agents until this gate passes.

## Sunday, June 21 — Real Stripe test-mode funding and payout

### Build

- Introduce the official Stripe integration in test mode.
- Implement owner funding of the project account/treasury.
- Implement the most realistic available solver-beneficiary payout flow using
  Stripe Connect or the appropriate sponsor-provided agent payment mechanism.
- Verify Stripe webhook signatures.
- Make webhook processing idempotent.
- Persist Stripe object IDs and event IDs.
- Keep the fake gateway for deterministic tests.

### Required failure paths

- repeated webhook;
- delayed webhook;
- failed payout;
- retry after failure;
- accepted bounty with missing beneficiary onboarding;
- refund/release of expired bounty reserve.

### Exit criterion

A real Stripe test-mode event funds the project and a real test-mode payout is
created exactly once after verifier acceptance.

### Cut rule

If Connect onboarding creates disproportionate delay, use one pre-onboarded test
beneficiary and document the production onboarding requirement. Do not fake a
successful Stripe event.

## Monday, June 22 — GitHub event spine

### Build

- Create the GitHub App or minimum credible repository integration.
- Import or create the Motoko bounty contract from issue #1.
- Bind bounty to repository, base SHA, verifier contract, and reward.
- Associate a solver claim with a lease/expiry.
- Associate a submission with a pull request and candidate commit.
- Consume relevant webhook events:
  - issue/bounty publication;
  - claim;
  - pull request opened/synchronized;
  - checks completed;
  - merge or explicit acceptance.
- Validate webhook signatures and installation scope.

### Exit criterion

A GitHub issue and candidate PR drive the platform state without manual state
edits, and event replay remains harmless.

### Cut rule

Support only the events required for the Motoko happy path and its obvious
failure paths. Do not build a generic GitHub automation framework.

## Tuesday, June 23 — Project agent: budgeted buyer of software work

### Build

- Give the Motoko project agent a clear budget policy:
  - total/monthly budget;
  - maximum bounty size;
  - minimum reserve;
  - allowed issue classes;
  - human-approval threshold;
  - verifier requirement.
- Let it inspect approved project signals and draft a bounded issue contract.
- Require it to explain:
  - why the issue matters;
  - why it is machine-verifiable;
  - why the proposed price is justified;
  - which policy permits the spend.
- Reserve funds before publishing.
- Reject vague, risky, or unverifiable tasks.

### Exit criterion

The project agent can autonomously turn one approved repository need into a
funded, machine-readable issue without overspending.

### Cut rule

Autonomous issue discovery may use a curated candidate list for the demo. The
important autonomy is choosing, specifying, pricing, and funding under policy;
not pretending to understand every issue in every repository.

## Wednesday, June 24 — Specialized solver agent

### Build

- Give a Hermes solver agent a capability profile grounded in evidence rather
  than persona text:
  - languages/frameworks;
  - successful task families;
  - cost/history;
  - validated skills;
  - supported versions.
- Let it scan open funded bounties.
- Require explicit underwriting:
  - fit;
  - expected effort/cost;
  - success probability;
  - reward;
  - reasons to accept or decline.
- Claim through a lease.
- Work on a dedicated branch/worktree.
- Run tests and submit a PR with evidence.

### Exit criterion

At least two solver profiles inspect the bounty; an unsuitable solver declines
and the suitable solver claims and submits it.

### Cut rule

One real working solver plus one deterministic decline is sufficient. Do not
build a large agent marketplace.

## Thursday, June 25 — Hermes and NVIDIA safety integration

### Build

- Move the buyer and solver workflows onto Hermes where it provides persistent
  memory, reusable skills, and long-running agent operation.
- Use Nemotron where it materially helps task analysis or coding.
- Run untrusted repository work through NemoClaw/OpenShell or the closest
  sponsor-prescribed isolated execution path.
- Separate:
  - trusted orchestrator;
  - trusted verifier;
  - untrusted solver workspace;
  - Stripe settlement service.
- Restrict network, credentials, filesystem access, runtime, and output.
- Keep Stripe secrets entirely outside the solver workspace.

### Exit criterion

The full Motoko solver path runs through the sponsor stack with an inspectable
security boundary and no decorative integration.

### Cut rule

One well-demonstrated safe environment is better than nominal support for many
execution backends.

## Friday, June 26 — Funding extensions and operational reliability

### Priority order

1. Owner one-time funding.
2. Donation funding.
3. Recurring owner funding.
4. Solver-earned internal operating budget.

### Build

- Add donation attribution without giving donors control over acceptance.
- Add recurring funding only if Stripe supports it cleanly in the existing
  model.
- Show available, reserved, spent, earned, and paid balances clearly.
- Add expiration/refund paths.
- Add operator-visible audit history and retry controls.
- Test process restart and webhook replay.

### Exit criterion

The project can receive at least owner and donation funds, allocate only
available money, survive restart, and reconcile after failure/retry.

### Cut rule

Recurring funding is optional. Never delay the full loop for it.

## Saturday, June 27 — Full authentic Motoko loop

### Run the real story

1. Fund Motoko's project treasury in Stripe test mode.
2. Let the project agent define or publish the bounded bounty.
3. Let multiple solver profiles inspect it.
4. Let the suitable solver claim it.
5. Produce or associate the accepted Motoko PR.
6. Run protected verification.
7. Create the acceptance receipt.
8. Release the Stripe test payout.
9. Update project and solver ledgers.
10. Replay key events to prove no duplicate payout.

### Capture

- clean screenshots/video of each artifact;
- exact GitHub issue and PR;
- project policy decision;
- solver underwriting decision;
- verifier JSON;
- Stripe test event/payout;
- final balances.

### Exit criterion

The entire loop succeeds from a fresh database without hidden manual repair.

## Sunday, June 28 — Second proof point or hardening

### Preferred option

Run a second small, deterministic bounty through the platform to show that the
system is not hardcoded to Motoko issue #1.

### Only if the primary loop is already reliable

- choose another authentic issue with one-command verification;
- use a different solver capability profile;
- demonstrate repeated market use.

### Otherwise

Spend the day on:

- reliability;
- latency;
- clearer receipts;
- safer failure states;
- demo UI polish;
- eliminating manual steps.

### Exit criterion

Either a second authentic bounty works, or the primary loop is demonstrably
robust enough to run repeatedly on camera.

## Monday, June 29 — Presentation and submission assets

### Demo narrative, 1–3 minutes

Target approximately 120 seconds:

1. **0–12s:** “Software agents can write code, but projects cannot yet safely
   buy work from them.”
2. **12–25s:** Owner/donors fund Motoko's project treasury through Stripe.
3. **25–42s:** Motoko's agent chooses, specifies, prices, and funds a real bug.
4. **42–58s:** Specialized agents inspect it; one declines, one claims.
5. **58–80s:** Solver/Hermes works safely and submits the real PR.
6. **80–98s:** Protected PTY verifier proves the lag is gone and emits the
   acceptance receipt.
7. **98–110s:** Stripe pays exactly once; balances update.
8. **110–120s:** Show the smooth before/after Motoko typing and the larger vision:
   every software project can hire agents, and every specialized agent can earn.

### Produce

- final demo script;
- voiceover or captions;
- one clean primary recording and one backup;
- concise architecture diagram;
- short written submission;
- credits and repository links appropriate for public release;
- secret/privacy review.

### Exit criterion

A person unfamiliar with the project can watch the video once and accurately
explain who paid whom, what work was performed, how success was proven, and why
Hermes/NVIDIA/Stripe were necessary.

### Freeze

No new product features after the demo recording begins. Only blocker fixes.

## Tuesday, June 30 — Final verification and submission

### Run

- fresh-state end-to-end transaction;
- exact verifier command;
- GitHub event replay test;
- Stripe idempotency test;
- ledger reconciliation;
- video/privacy/secret review;
- public link check.

### Submit

- tweet 1–3 minute demo tagging Nous Research;
- include the short writeup;
- submit the link in the Nous Discord submission channel;
- complete the Typeform;
- preserve confirmation evidence.

Target submission **before 18:00 Europe/Madrid**, leaving margin before the
organizer's EOD deadline.

---

# Critical-path gates

## Gate 1 — June 20

Trusted local transaction core works and pays exactly once through the fake
gateway.

If not, stop all optional work.

## Gate 2 — June 22

Real Stripe test-mode funding/payout and GitHub event integration work.

If not, reduce to one preconfigured repository and one pre-onboarded solver.

## Gate 3 — June 25

Buyer and solver agent paths operate on the sponsor stack.

If not, cut donations, recurring funding, second solver, and most UI polish.

## Gate 4 — June 27

Fresh-state complete Motoko loop works without manual database edits.

If not, do not attempt a second bounty.

## Gate 5 — June 29

Final demo is recorded and understandable.

After this, only blocker fixes are allowed.

# Quality bar

A feature is complete only when:

- its happy path works from a fresh state;
- its principal failure path is visible and safe;
- replay is idempotent;
- monetary state reconciles;
- verifier trust is not delegated to the solver;
- no secret crosses into untrusted execution;
- the user-facing wording is honest;
- the demo does not depend on an unverifiable animation;
- relevant tests are automatic;
- the diff is focused and documented.

# Risk register

## Verifier self-approval

**Risk:** solver edits its own tests or verifier.

**Control:** platform-owned verifier and contract digest; candidate supplies code,
not verdict policy.

## Duplicate payouts

**Risk:** GitHub/Stripe webhook replay or process retry.

**Control:** database uniqueness, stable idempotency keys, transactional state
transition, Stripe idempotency.

## Agent-generated spam

**Risk:** solver sprays low-quality PRs at arbitrary repositories.

**Control:** opt-in projects, funded contracts, exclusive claim leases, solver
underwriting, repository-scoped permissions.

## Malicious repository code

**Risk:** candidate build/test exfiltrates secrets or harms the host.

**Control:** secretless verifier process first; NemoClaw/OpenShell isolation,
network policy, time/output/resource limits before autonomous solving.

## Stripe onboarding friction

**Risk:** beneficiary onboarding blocks the demo.

**Control:** one pre-onboarded Connect test beneficiary; document scalable
onboarding without pretending it is instant.

## Scope explosion

**Risk:** building a broad marketplace instead of a complete transaction.

**Control:** fixed scope, daily gates, feature freeze, optional features cut
first.

## Demo fragility

**Risk:** live agent or external service fails during recording.

**Control:** fresh-state rehearsal, deterministic verifier, test-mode payment,
recorded primary and backup takes, visible authentic artifacts.

# Evidence to preserve continuously

Do not wait until June 29. Save:

- Git commit SHAs;
- issue and PR identifiers;
- state-transition logs;
- verification receipts;
- Stripe event and payout IDs;
- ledger reconciliation output;
- before/after Motoko footage;
- solver accept/decline explanations;
- architecture screenshots;
- failure-path examples;
- exact commands needed for a fresh demo.

# Final submission claim

The clearest honest formulation is:

> A funded software project can autonomously purchase a machine-verifiable fix
> from a specialized coding agent. The project controls the acceptance contract,
> the solver cannot approve itself, Stripe pays only after independent
> verification, and both agents retain budgets and capability histories for the
> next job.
