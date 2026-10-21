# Dependency: product contract and engineering gates

## Objective

Dependency controls the recovery of customer commitments when external or
internal events change supply-chain feasibility. It is not an alert dashboard.
The main buyer is a supply-chain planner or procurement operations leader at a
multi-tier manufacturer or brand.

**Product outcome:** For each event, identify exposed commitments and decision
options, request the missing operational evidence, calculate feasible
allocations, route protected actions to authorized humans, execute approved
state changes, and record the result for later use.

## One invariant system

1. Collect public or internal observations with source, timestamp, original
   payload, deduplication key and provenance class.
2. Link the observation to public facilities or transport/policy nodes.
3. Traverse **only explicit** private factory, material, BOM, production,
   shipment and customer relationships. Missing edges stay missing.
4. Produce an exposure calculation. This measures connected value, not loss.
5. Create durable investigation tasks for every relevant missing fact.
6. Confirm private operational state from an authorized source. Unconfirmed
   public exposure must never change facility availability.
7. Recompute recovery across all competing orders and shared resources.
8. Reject infeasible plans; require a human decision for protected actions.
9. Execute with idempotency and an auditable operational state change.
10. Invalidate the previous plan; recompute and record outcomes in memory.

There must be no supplier- or Cianjur-specific conditional logic in these
steps. The flagship uses fixed **data**, not fixed **reasoning**.

## Operational states, not feature names

- `OBSERVED`: external observation is stored with provenance.
- `POTENTIALLY_EXPOSED`: public graph or proximity intersects the event.
- `PRIVATE_DEPENDENCY_LINKED`: explicit ERP/graph edge reaches an SKU/order.
- `AWAITING_EVIDENCE`: recorded investigation tasks specify what is unknown.
- `OPERATIONALLY_CONFIRMED`: independent authorized evidence updates state.
- `PLANNING`: deterministic solver evaluates shared capacity, BOM, timing.
- `APPROVAL_REQUIRED`: action has explicit human gate.
- `EXECUTED`: approved action changes state with audit and idempotency.
- `REPLANNED`: new state version invalidates old output.
- `CLOSED`: outcome stored; future model suggestions remain hypotheses.

These are product-state concepts. Do not claim every transition is fully
implemented or enforced as a database state machine yet.

## Signals: different evidence, same downstream semantics

| Source | Verified observation | Derived signal | Missing private fact |
| --- | --- | --- | --- |
| USGS | earthquake location/magnitude | nearby public facilities | confirmed facility state, supply/shipments |
| GDACS | published hazard event | possible supplier intersection | whether operations actually changed |
| IMF PortWatch | port activity data | baseline departure (PUBLIC_DERIVED) | shipment status, ETAs and routing |
| Trade authorities | official effective policy text | eligible country/product paths | HS classification, exemption, landed costs |
| Supplier response | authenticated response metadata | extracted capacity/date | authorized confirmation and valid time window |
| ERP/judge edit | transactional company state | invalidated commitments | recovery feasibility / approval |

Do **not** use an LLM as the source of a fact, a risk score or a capacity cap.
Use models to choose investigative tools and draft questions. Use deterministic
code for graph reachability, arithmetic, constraint satisfaction and approvals.

## Evidence task contract

Live events without scenarios must not dead-end. Persist targeted tasks from
actual dependency paths. For example, an upstream material source yields a
material supply request. A port lane yields shipment/ETA verification. A tariff
policy yields HS classification and exemption verification. Public-only
facilities yield identity/link verification, **not** invented private SKUs.

Tasks are `INFERRED` evidence gaps, not authoritative evidence. Task creation
does not send Slack messages or set facility state. Supplier outreach and
confirmation are separate authorized operations. Repeated event delivery must
not create duplicate tasks.

## Required next engineering work (ordered)

1. **P0: Real live incident lifecycle.** Validate one live arbitrary event
   across ingestion, durable tasks, evidence updates, plan invalidation and
   recovery. Close task-resolution transitions when the right evidence arrives.
2. **P0: Physical feasibility.** Introduce dated, facility-wide capacity
   ceilings and shared materials across multiple SKUs. Joint allocation must
   not double-count scarce upstream supply.
3. **P0: Evidence-to-action.** Connect incident tasks to authorized supplier
   requests. Validate sender identity, data freshness and approval controls.
4. **P1: Deployment reliability.** Start collectors and consumers as managed
   processes; dedup retry logic, backpressure, dead-letter diagnostics,
   feed freshness, and no secret leakage.
5. **P1: Official trade intelligence.** Retrieve versioned official policy
   texts, normalize jurisdiction/HS/dates, and refuse false applicability.
6. **P1: Team demo.** Cianjur deterministic reset, judge edits, 3-minute script,
   one command for setup, failure recovery, and real trace of evidence.

## Six-hour build rules

- **One production loop** (Cianjur) must be excellent. Other arbitrary events
  must prove generalized discovery/investigation, not become equal demos.
- Judge-controlled capacity, inventory, ETA, demand and facility state must
  change computed outcomes or clearly trigger an evidence block.
- No operational action executes on an LLM text recommendation alone.
- Show three kinds of proof: source provenance, deterministic feasibility,
  and the recorded resulting state transition.
- Do not add a data feed that cannot be mapped to a private graph node and a
  meaningful next action.
- Do not equate a successful CI run with a deployed, live operating service.

## Local migration: non-destructive

After updating `feat/db-foundation` on an already seeded local database:

```powershell
python -m scripts.apply_migrations
```

This creates the investigation task table and indexes if absent. It does not
reset the 266,737 generated records. Do not run the seed loader unless a fresh
demo reset is intended.
