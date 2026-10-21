# Dependency

Dependency is an agentic supply-chain recovery system.

It does not stop at "an earthquake is near a supplier."

It connects an external disruption to the company's dependency graph, finds the
products and customer commitments that are actually exposed, checks recovery
constraints, asks for missing evidence, requires approval for protected actions,
executes approved changes, invalidates stale plans, and replans.

The flagship demo is the 21 November 2022 Cianjur earthquake replay.

## Core control loop

```text
external signal
    ↓
public network exposure
    ↓
explicit private dependency graph
    ↓
BOM + inventory + POs + production + customer commitments
    ↓
deterministic recovery candidates
    ↓
reject correlated / late / unapproved / infeasible actions
    ↓
agent asks for missing supplier evidence
    ↓
confirmed business-state update
    ↓
state version increments
    ↓
old plan invalidates
    ↓
replan
    ↓
human approval for protected action
    ↓
explicit execution
    ↓
replan again
    ↓
incident / decision / outcome memory
```

The dashboard is the control surface. It is not the product logic.

## Truth model

Every important claim must preserve one of four provenance classes.

- `VERIFIED_PUBLIC` — direct authoritative public source fact.
- `PUBLIC_DERIVED` — deterministic calculation or entity match from public facts.
- `INFERRED` — hypothesis that still needs evidence.
- `SIMULATED_PRIVATE` — realistic ERP/BOM/order/capacity data created because a
  real company's private operational records are not public.

Geographic proximity is potential exposure. It is never automatic proof that a
facility is damaged, closed, or capacity-constrained.

## Data scale

The system uses two connected layers.

### Public outer network

The normalized 2026 Adidas supplier network currently contains:

- 770 geocoded public facilities.
- 836 official supplier-list relationships.
- parent-organization relationships.
- public facility identity, tier, category, address and coordinate provenance.
- Open Supply Hub coordinate enrichment where available.

### Private operational digital twin

The hand-curated flagship records are loaded first.

The loader then generates a deterministic enterprise-scale private twin from
public facility identities outside the flagship countries. This prevents scale
data from silently changing the Cianjur ground truth.

Current generated scale:

- 2,500 additional private SKUs.
- 792 realistic material/component records.
- 28,335 BOM rows.
- 7,500 SKU-to-assembly edges.
- 1,584 material-source edges.
- 170,010 exact material-source allocation edges.
- 20,000 customer commitments.
- 12,500 purchase orders.
- 5,000 production orders.
- 7,500 supplier-capacity rows.
- 900 transport lanes.
- more than 266,000 generated private-twin rows in total.

The generated CSV files are written to:

```text
data/generated/private_twin/
```

They are recreated from code. They are intentionally not hand-maintained.

Generate them without loading PostgreSQL:

```powershell
python scripts/generate_enterprise_scale_data.py
```

Normal seed loading generates and loads them automatically.

## Why the large dataset matters

The scale layer uses the same tables and graph edges as the flagship demo.

It is not a disconnected "big CSV" for screenshots.

The same SQL, graph traversal, BOM explosion, capacity checks, inventory logic,
purchase-order timing, customer allocation and agent tools query the large
operational twin.

The flagship demo remains small enough to explain in three minutes. The database
behind it is not.

## Deterministic engine

LLMs do not decide arithmetic or feasibility.

Python, SQL and PostGIS determine:

- event-to-facility distance;
- graph reachability;
- exact source-of-supply paths;
- BOM quantities;
- shared upstream dependencies;
- finished-goods and material inventory;
- protected safety stock;
- supplier capacity;
- PO timing;
- setup lead time;
- critical-component coverage;
- substitution approval;
- transport feasibility and cost;
- customer priority;
- due dates;
- revenue and gross margin;
- recovery allocation;
- state versioning and plan invalidation.

Missing data remains missing. It is not silently converted into a fabricated
supplier relationship or fake zero.

## Agents

The current agent set is intentionally small.

### Signal Investigator

Determines what happened, what public-network nodes require investigation and
what evidence is still missing.

### Impact Investigator

Traverses explicit upstream and downstream business relationships. It connects
facilities, materials, SKUs and customer commitments.

### Recovery Planner

Uses deterministic recovery tools, compares alternatives, exposes rejected
plans, requests missing supplier evidence and creates human-approval requests
when policy requires them.

Agent tool calls can be persisted in `agent_runs`.

The deterministic backend still works without an LLM key.

## Supplier evidence loop

A stale capacity value is not accepted as current truth.

The system can:

1. create a durable supplier-confirmation request;
2. send it through Slack when external messaging is enabled;
3. receive a Slack thread reply;
4. verify the Slack request signature;
5. parse the reply conservatively;
6. keep operational state unchanged until explicit confirmation;
7. apply the confirmed capacity;
8. increment the operational state version;
9. invalidate dependent plans;
10. replan.

External messages are disabled by default.

## Human approval and execution

Approval and execution are separate.

An agent can request permission for a protected action, but a pending request is
not an approval.

After approval, the deterministic execution adapter can currently execute
supported actions such as:

- safety-stock release;
- substitution approval;
- purchase-order ETA change / expedite;
- setup lead-time update;
- facility-state update.

Execution creates an audit record and another business-state event.

## Operational memory

The system stores:

- incidents;
- evidence;
- plan snapshots;
- rejected actions;
- agent runs;
- approval decisions;
- executed actions;
- outcomes.

Prior incidents are retrieved as hypotheses only.

A prior lesson never becomes current evidence automatically.

## Local setup

From the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
```

Create `.env` from `.env.example`.

For local PostgreSQL/PostGIS:

```text
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/Disruptors
```

Do not commit `.env`.

Load the public network, curated flagship data and enterprise-scale private twin:

```powershell
python scripts/validate_seed_data.py
python scripts/load_seed_data.py
python scripts/check_db.py
```

Run the full test suite:

```powershell
python -m unittest discover -s tests -v
```

## Run the product

Start FastAPI:

```powershell
uvicorn dependency.api.main:app --reload --port 8000
```

Open the judge control tower:

```text
http://127.0.0.1:8000/dashboard
```

Open the API contract:

```text
http://127.0.0.1:8000/docs
```

## Live external signals

One USGS poll:

```powershell
python scripts/watch_usgs.py --min-mag 4.5 --radius-km 150
```

Continuous USGS polling:

```powershell
python scripts/watch_usgs.py --min-mag 4.5 --radius-km 150 --watch --interval 60
```

Continuous GDACS polling:

```powershell
python scripts/watch_gdacs.py --watch --interval 300
```

Collectors persist normalized events and write `external.events` to the
transactional outbox.

A live feed returning zero qualifying events is a valid result. The demo must not
invent a live disruption.

## Local orchestration

Until Aiven Kafka credentials are available:

```powershell
python scripts/run_local_orchestrator.py --watch --interval 5
```

The local worker consumes the same event contracts that the Kafka consumer will
use.

Important topics include:

- `external.events`
- `business.state.updated`
- `supplier.capacity.updated`
- `supplier.confirmation.requested`
- `supplier.confirmation.reply_received`
- `incident.detected`
- `plan.generated`
- `plan.invalidated`
- `approval.requested`
- `decision.confirmed`
- `action.executed`

## Aiven architecture

Aiven PostgreSQL/PostGIS is the operational system of record.

Aiven Kafka is the event transport.

The application uses a transactional outbox so database state and emitted events
do not drift apart.

The product logic is transport-independent. Moving from the local outbox worker
to Aiven Kafka does not require rewriting the solver or agents.

## Flagship judge rehearsal

The primary event is the real USGS Cianjur earthquake:

`us7000ir9t`

Keep its real 2022 date.

Run:

```powershell
python scripts/rehearse_control_loop.py
```

The rehearsal exercises:

- public exposure;
- private dependency traversal;
- hidden correlated-backup rejection;
- stale supplier evidence;
- supplier reply parsing and confirmation;
- state-version change;
- automatic replanning;
- human approval;
- action execution;
- customer allocation;
- incident memory.

The detailed presenter script is in:

```text
docs/demo_script.md
```

## Hardcoding policy

Fixed fixtures are allowed when they represent data.

Examples:

- the historical Cianjur event;
- simulated private customer orders;
- simulated BOMs;
- simulated supplier capacities;
- expected outputs in evaluation tests.

Business reasoning must not depend on hidden SKU/event conditionals.

The application must not contain logic such as:

```python
if sku == "JI2993":
    risk = 82

if capacity <= 5500:
    risk = 90
```

Changing demand, capacity, inventory, source allocations, PO ETA, facility state
or supplier response must change the result through data and deterministic
logic, not code edits.

## CI

GitHub Actions creates PostgreSQL/PostGIS, loads the complete dataset and tests:

- public network normalization;
- enterprise data scale;
- graph views;
- flagship ground truth;
- exposure propagation;
- de-hardcoding;
- recovery;
- component feasibility;
- optimization;
- event orchestration;
- agent contracts and tools;
- memory;
- Aiven Kafka contracts;
- supplier outreach;
- approvals;
- action execution;
- judge-editable state;
- event-type engines;
- PortWatch normalization;
- transport feasibility.

Do not merge a red branch.
