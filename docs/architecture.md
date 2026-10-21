# Dependency architecture

## Product contract

Dependency does not stop at "a disruption happened."

The system must complete this chain:

external change
-> detect
-> investigate
-> map to company dependencies
-> quantify product/order exposure
-> generate recovery choices
-> reject bad choices with deterministic rules
-> request missing evidence or approval
-> update operational state
-> invalidate stale plans
-> replan
-> save the decision and outcome

## Truth labels

Every important fact should be one of:

- VERIFIED_PUBLIC: directly disclosed by Adidas, USGS, GDACS, government, or another authoritative public source.
- PUBLIC_DERIVED: calculated or matched from public data, for example coordinates joined from Open Supply Hub.
- INFERRED: a hypothesis that still needs evidence.
- SIMULATED_PRIVATE: realistic ERP/BOM/order/capacity data created because private company data is not public.

Synthetic private data must never be shown as a public Adidas fact.

## Data layers

### 1. External signal layer

Current collectors:

- USGS: near-real-time earthquakes.
- GDACS: cyclones, floods, volcanoes, wildfires.
- IMF PortWatch: port-call activity.
- official policy sources: tariff and trade-policy scenarios.

A collector normalizes a source event, writes it to PostgreSQL, and writes the same state change to the transactional event outbox.

### 2. Public supply network

The repository contains:

- 770 geocoded Adidas network facilities from the supplied Open Supply Hub Adidas contributor export.
- 836 July 2026 official Adidas list relationships:
  - 455 primary/subcontractor rows;
  - 243 licensee rows;
  - 138 wet-process rows.
- parent-organization relationships.
- provenance for the official rows and coordinate matches.

This public graph is deliberately separate from the private operational twin.

A public facility can be near an event without having any private product/order relationship.

### 3. Private operational twin

The demo twin contains:

- products and SKUs;
- BOM;
- explicit material allocations;
- approved assembly facilities;
- finished-goods inventory;
- purchase orders;
- supplier capacity;
- production orders;
- customer commitments;
- transport lanes;
- scenario-specific operational state.

Only explicit private edges can propagate an event into a SKU or order.

### 4. PostgreSQL/PostGIS

PostgreSQL is the system of record.

PostGIS performs geospatial event-to-facility matching.

Important indexes:

- GIST on public network facility geometry;
- GIST on operational facility geometry;
- GIST on event geometry;
- relational primary/foreign keys for dependency integrity.

Local development uses local PostgreSQL.

When AIVEN_DATABASE_URL is present, the code prefers Aiven PostgreSQL. No application rewrite is required.

### 5. Event bus

All important state changes first enter event_outbox in the same PostgreSQL transaction as the business update.

Topics:

- external.events
- business.state.updated
- supplier.capacity.updated
- incident.detected
- plan.generated
- plan.invalidated
- decision.confirmed

Without Aiven credentials, these rows stay safely in the local outbox.

With Aiven Kafka configured, scripts/flush_event_bus.py --publish publishes pending rows and marks successful deliveries.

This gives the hackathon a credible path:

external source
-> collector
-> PostgreSQL transaction + outbox
-> Aiven Kafka
-> consumers
-> PostgreSQL/PostGIS state
-> agents
-> deterministic solver
-> decision
-> memory

## Agent layer

Three constrained agents are used:

1. Signal Investigator
   - asks what happened;
   - checks public network intersection;
   - separates potential exposure from confirmed disruption;
   - identifies missing evidence.

2. Impact Investigator
   - follows explicit graph edges;
   - traces material/SKU/order impact;
   - checks shared dependencies and PO timing;
   - does not invent business links.

3. Recovery Planner
   - generates actions;
   - calls deterministic planning tools;
   - surfaces rejection reasons;
   - requests supplier confirmation or planner approval.

The LLM chooses tools and frames the investigation.

Python/SQL decides arithmetic, graph reachability, feasibility, capacity, approval, and allocation.

## Deterministic recovery layer

Current controls include:

- approved SKU/facility assignments;
- explicit source-of-supply edges;
- hidden shared upstream dependency checks;
- inventory and safety stock;
- current production;
- backup capacity;
- evidence age;
- setup lead time;
- due dates;
- PO ETA;
- substitution approval;
- order priority and margin allocation;
- tariff arithmetic.

A plan can be:

- REJECTED;
- INFEASIBLE;
- CONDITIONALLY_FEASIBLE;
- FEASIBLE.

The system must explain why.

## Operational memory

Memory is stored in PostgreSQL, not a chat transcript.

Tables store:

- incident;
- evidence;
- agent tool traces;
- generated plans;
- rejected plans;
- human decisions;
- final operational outcome;
- lesson.

Past incidents can create hypotheses only.

Current inventory, capacity, approvals, and event evidence must always be rechecked.

## Demo reliability rule

Historical events keep their real historical date and a REPLAY label.

Live events keep their actual incoming timestamp.

A replay must never be presented as if the historical event happened today.
