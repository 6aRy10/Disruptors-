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

Still incomplete: confirmed facility-wide capacity in live managed operations,
upstream joint material allocation (a modeled source contention audit now flags
conflicts but does not solve a multi-material discrete optimizer), and supplier
evidence to authenticated contact delivery. Further incomplete:
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

## Dated factory ceilings — new operational contract

The joint solver now reads `confirmed_facility_capacity` from PostgreSQL
for the incident scenario date. A confirmation applies to the **entire factory
across SKUs**, not to an individual product. A dated source reference is
required; the model may not infer capacity from earthquake proximity.

`POST /facilities/{facility_id}/capacity-confirmations` accepts
`week_start`, `valid_until`, `capacity_units`, `committed_units`,
`evidence_source`, `evidence_reference` and `confirmed_by`.
The update creates transactional state/outbox records for every assigned SKU.
Repeated identical confirmations do not increment state again.

The new multi-SKU material audit detects shared source/material contention
from actual BOM and material-allocation edges. Its weekly ceilings are
**simulated private capacity**, not confirmed evidence or a complete global
multi-material optimizer. A plan with unresolved shared material evidence is
not marked executable. Do not claim otherwise in the pitch.

After `git pull --ff-only`, run `python -m scripts.apply_migrations`
(non-destructive) to create the new confirmed capacity table.

## Prevent accidental Aiven database switching

The PostgreSQL connection now refuses to silently switch when both
`DATABASE_URL` and `AIVEN_DATABASE_URL` exist. Keep
`DEPENDENCY_DATABASE_TARGET=local` until the managed PostGIS database is
populated and passes preflight. Use `DEPENDENCY_DATABASE_TARGET=aiven`
**only** after verification. The database preflight never changes the target.

## Supplier evidence draft pipeline — review required

When a live event creates tasks, the control tower now offers
`Prepare evidence request`. The server creates one durable draft per task,
links an explicit `operational_contacts` record when available and returns
`CONTACT_NOT_MODELED` otherwise. The question references the event and graph
but **does not claim supplier damage**. No email/Slack message is sent by this
action; sending needs a distinct, authorized workflow. When the operator later
confirms a facility task, its draft is marked `EVIDENCE_RECORDED` in the same
transaction as the state change. This is not automated authenticated supplier
response ingestion and must not be described as such.

## Aiven deployment: one physical topic

The always-free Aiven Kafka service has a maximum of five Kafka topics. We
use one physical topic, `dependency.events`, for all eleven distinct logical
event types, with logical topic and outbox ID retained inside the envelope.
The local data remains the authority. After Aiven service setup (outside the
repository), configure TLS privately and run:

```powershell
python -m scripts.aiven_preflight --probe-kafka
```

Only `READY_TO_STREAM` establishes broker/topic reachability. Do not enable
Kafka publishing or migrate PostgreSQL until the respective checks pass.

## Opt-in evidence investigator agent

For a new live event with a linked private graph but no confirmed operational
scenario, the deterministic worker stores prioritized investigation tasks.
With explicit `--agents` on `python -m scripts.run_live_stack`, the
Evidence Investigator may retrieve those tasks and prepare a limited set of
human-review drafts. Model tool traces are stored with the existing incident.
This uses configured paid model credits. The default without `--agents` is
free deterministic ingestion and queues only. The agent has **no tool** for
confirming disruption, sending supplier messages, modifying capacity, or
executing protected actions. Never leave paid agent mode on by accident.

## High-volume invalidation behavior

One factory change may invalidate many SKU plans. Before an expensive solver
run, the worker checks whether that incident already saved its complete
portfolio for the same operational state version. Repeated SKU messages then
skip duplicate graph work. The transport still needs one active consumer
until concurrent claim-locking is implemented; avoid two workers writing the
same incident generation in parallel.

## Local versus Kafka event counts

`python -m scripts.team_status` now reports three separate quantities:
`processed_local_outbox_messages` means the PostgreSQL orchestrator
successfully consumed the event; `pending_local_outbox_messages` means there
is no successful consumption record yet; `unpublished_outbox_messages`
means a Kafka publication timestamp has not been recorded. A locally
processed event can still be unpublished to Kafka. Do not treat the latter as
an incident-processing failure or clear the outbox just to make it zero.
