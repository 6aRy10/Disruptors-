# Dependency — single source of truth for the hackathon team

**Branch:** `feat/db-foundation`. GitHub Actions CI is the technical source of
truth; each teammate must pull the active branch and check its latest run.
**Database:** `Disruptors` on local PostgreSQL/PostGIS until a managed
instance passes the Aiven compatibility preflight. Never assume CI's temporary
Postgres updates the local database.

## The product we are demonstrating

1. Public earthquake `us7000ir9t` intersects real Adidas public supplier
   facilities: `POTENTIALLY_EXPOSED`, not confirmed damage.
2. Explicit simulated private factory/material/BOM graph connects supplier
   nodes to SKU `JI2993`, other SKUs and customer commitments.
3. Deterministic recovery rejects correlated backup paths and respects
   state-dependent capacity, timing, inventory and approvals.
4. Missing supplier evidence is requested; a human confirms changed data.
5. Old plans invalidate and a joint portfolio replan occurs; protected
   actions require explicit approval and execution.
6. The new **general live-event path** creates evidence tasks, accepts
   operator-confirmed facility state transactionally, creates a scenario
   without splitting incident memory, and queues replanning. This is
   validated by an arbitrary-event database regression test.

This is a product **loop**, not a risk dashboard. Cianjur is our only primary
demonstration. The 266,737-record twin is generated private data, not genuine
Adidas private ERP data. Fixed seed data is allowed; conditional hardcoded
decision logic is not.

## The one safe local startup

In PowerShell with `.venv` active, from the existing repo root:

```powershell
git switch feat/db-foundation
git pull --ff-only origin feat/db-foundation
python -m pip install -e .
python -m scripts.apply_migrations
python -m scripts.team_status
python -m scripts.run_live_stack
uvicorn dependency.api.main:app --reload
```

Open `http://127.0.0.1:8000/dashboard` in your browser. Run the live runner
in a separate terminal when monitoring continuously:
`python -m scripts.run_live_stack --watch`. It does not automatically send
messages or execute protected actions. The enterprise twin is already loaded
locally; **do not run the destructive seed loader again**.

Stop and report `NOT_READY` or `SCHEMA_INCOMPLETE` before testing.
`apply_migrations` is idempotent and does not reset records.
To see Aiven readiness, run `python -m scripts.aiven_preflight`; never
share passwords, certificates, access tokens or database connection strings.

## What each teammate owns

**Data and solver:** Test shared material and factory constraints across many
SKUs, avoid double-counting, verify actual inventory/PO ETA effects and
benchmark with the full enterprise graph. Explicitly document limits where
an allocation is still provisional.

**Agents and integrations:** Trace live events to linked evidence tasks.
Connect verified task evidence to authorized supplier replies, outbox events,
replanning and memory. Prove idempotency, provenance and error recovery.
Use real model tools when available; no fabricated model decisions.

**Frontend and demo:** Show source provenance, graph paths, connected revenue,
investigation tasks, state version, rejected recovery, approval and executed
results. Ensure judge edits recompute from PostgreSQL; do not hardcode
`JI2993` outcomes in UI.

**Team lead:** Keep Cianjur the flagship, check CI and the live local database
with `scripts.team_status`, assign ownership and run the timed full rehearsal.

## Finished foundation versus deployment

Code and CI have verified the seeded graph, Cianjur replay, generic event
task creation, operator-confirmed facility evidence, shared-backup joint
optimization, approvals and memory paths. This is not certification of
real supplier identity, real private transactions, production security,
production Kafka service or deploy reliability.

Still incomplete: facility-wide dated capacity plus upstream shared material
optimization; live supplier task-to-contact end-to-end automation; authenticated
user roles; actual Aiven provisioning and safe managed PostGIS migration;
official tariff intelligence; operational worker deployment and real-time
health checks.

## Engineering gates

- New unscripted event creates deduplicated evidence tasks from actual links.
- No inferred geographic proximity can change private operational state.
- Operator-confirmed evidence updates a single incident, state and outbox
  atomically; duplicate confirmations cannot double-apply.
- Replanning must cover shared-resource competing SKUs, not only the changed
  one.
- Every protected action needs authorization and an execution record.
- PostgreSQL row counts, state version and open evidence tasks are visible.
- The full Cianjur rehearsal remains passing in GitHub Actions.
- Aiven is an optional infrastructure layer; local PostGIS remains the safe
  fallback until managed PostGIS support and Kafka transport are proven.

For deep product rationale, read
`docs/PRODUCT_CONTRACT_AND_BUILD_GATES.md`. For managed data readiness,
read `docs/AIVEN_FREE_TIER_DEPLOYMENT.md`. For all regression commands,
check `.github/workflows/test.yml`.
