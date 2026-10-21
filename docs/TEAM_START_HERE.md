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
