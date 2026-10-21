# Dependency — team start here

## Mission
Build a working supply-chain control system. The flagship demonstration is the
real USGS Cianjur earthquake `us7000ir9t`, replayed against a clearly
labeled simulated private enterprise. The system must trace affected supplier
nodes into BOM, orders, customer promises and economic exposure; reject unsafe
recovery plans; request missing evidence; replan when confirmed facts change;
and execute protected actions only after approval.

The 2022 earthquake is historical, not a live 2026 earthquake. Public proximity
means POTENTIALLY_EXPOSED, **not** verified shutdown.

## What is already in the repository
- PostgreSQL/PostGIS schema and enterprise seed loader.
- Real public Adidas supplier identities and locations, plus a simulated
  private enterprise twin with 2,500 generated SKUs and 170,010 generated
  material allocations.
- USGS and GDACS event ingestion, exposure, explicit graph traversal, BOM,
  customer commitments and commercial impact.
- Deterministic recovery, source dependence checks and single-SKU optimization.
- Initial joint multi-SKU allocation constrained by shared backup factory
  capacity. Unconfirmed shared limits stay provisional. Shared material
  capacity is **not** yet globally optimized.
- Supplier capacity request/reply/confirmation, state versioning, stale-plan
  invalidation, transactional outbox, human approvals, action execution, memory.
- Three investigator/planner agents and a judge control dashboard.

## Get running (Windows PowerShell)
```powershell
git clone https://github.com/6aRy10/Disruptors-.git
cd Disruptors-
git switch feat/db-foundation
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Provide a PostgreSQL 16 database with PostGIS and set DATABASE_URL locally.
Never commit a real database URL or API credential. See `.env.example`.
The exact setup depends on each teammate's PostgreSQL installation.

```powershell
python scripts/validate_seed_data.py
python scripts/load_seed_data.py
python -m unittest discover -s tests -v
python scripts/rehearse_control_loop.py
uvicorn dependency.api.main:app --reload
```
Then open `http://127.0.0.1:8000/dashboard`.

**Important:** `load_seed_data.py` and the rehearsal reset/rewrite demo data.
Use a disposable development database, not a database with live operational
records. Keep external Slack messaging disabled during rehearsals.

## What six hours must deliver
1. A reliable Cianjur judge demo from event through approved action.
2. Two or more judge-controlled state edits that really change computed plans.
3. Clearly labeled verified public versus simulated private information.
4. Real tools and constraints, never a hardcoded result.
5. End-to-end tests passing on the branch used for presentation.
6. A clean deployment and rehearsed fallback if external integrations fail.

## Highest-value parallel work
**Backend/data owner:** Confirm material-source constraints and facility-wide
capacity periods; add adverse tests where two SKUs share upstream materials.
No new table is valuable until used by a solver or agent.

**Agents/integrations owner:** Confirm tool traces and supplier request/response
behavior. Enforce trust boundaries, retries, and evidence-to-action transitions.
Do not let an LLM decide deterministic feasibility or execute protected actions.

**Frontend/demo owner:** Connect the dashboard to current API responses,
especially operational state version, rejected reasons, approval status, and
economic outcomes. No prewritten Cianjur outcome cards. Rehearse live changes.

**Team lead:** Keep scope on the flagship scenario. Verify each owned branch
with tests; accept only code that improves the complete event-to-action loop.

## Hard acceptance checks
- Event moved near a different linked facility -> different affected products.
- Ocean event with no network link -> no invented business impact.
- Supplier capacity changed -> previous plan invalidated, new result computed.
- Shared backup facility -> aggregate allocation never exceeds its cap.
- Unapproved substitute or shared exposed upstream source -> rejected.
- Safety stock -> no release until human approval and explicit execution.
- Every source assertion has provenance; proximity is only potential exposure.
- Replay is deterministic and can be reset safely.

## Source of truth
Branch: `feat/db-foundation`.
CI workflow: `.github/workflows/test.yml`.
Full replay: `scripts/rehearse_control_loop.py`.
Test suite: `tests/`.
Detailed architecture: `docs/architecture.md`.
Demo: `docs/demo_contract.md`.

## Check local Python dependencies after pulling updates

If a new import fails, install the current project requirements into the
active virtual environment. This does not modify PostgreSQL:

```powershell
python -m pip install -e .
python -m pip check
```

The live ingestion runner loads AI agent modules only when the agent path is
called. The standard feed-orchestrator mode does not require AI execution.

## Run real event ingestion locally

Once the database is loaded, run this command from the repository root:

```powershell
python -m scripts.run_live_stack
```

This polls both real external feeds once, writes events to PostgreSQL, and
processes the transactional outbox. No model key or Slack integration is
required. It never resets demo records. For ongoing polling in the same
PowerShell window, run `python -m scripts.run_live_stack --watch` and stop
with Ctrl+C. A green source status means feed and ingestion ran, not that any
supplier was confirmed disrupted. Live observations do not automatically
create private operational confirmations.

## PortWatch provenance rule

PortWatch reports public observations. A decline relative to a computed
baseline is `PUBLIC_DERIVED`, not verified physical port closure. Exposure
uses explicit private transport lanes. An observed decline must not directly
close a transport lane or claim a confirmed late delivery.

## Third external signal: PortWatch

The existing IMF PortWatch adapter can be enabled in the same local runner:

```powershell
python -m scripts.run_live_stack --portwatch
python -m scripts.run_live_stack --watch --portwatch
```

Only 3 modeled ports are checked per PortWatch pass by default; batches rotate
hourly. This avoids an unbounded number of external requests during demos. Port
lookup conflicts and provider errors are reported. PortWatch is a derived
traffic-anomaly signal, never a verified port closure. Old activity records do
not create new live incidents. Cianjur remains the sole flagship demo.

## Prove that a live event reached the private business graph

After a live ingestion run, check any known event identifier:

```powershell
python -m scripts.inspect_event GDACS-WF-1032942
```

This is read-only. It shows the provider and provenance, queue consumption,
incident (if one exists), explicit dependency paths, and connected commercial
value. A missing product path is a valid outcome, not permission to invent a
factory-to-SKU assignment. Never equate proximity with verified factory damage.

## Live evidence queue (non-destructive migration)

The investigation queue is a new table. On an already loaded local development
database, run `python -m scripts.apply_migrations` after pulling this branch.
Do **not** reset your 266k-row private twin. Live events now create durable,
deduplicated tasks for missing facility, material, shipment and policy evidence.
Inspect them at `GET /investigations/tasks` or under "Missing evidence and next
actions" on `/dashboard`. These are investigation tasks, **not** outbound
supplier messages or confirmed shutdowns. A separate authorized workflow must
confirm new operational state.
