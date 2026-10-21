# 3-minute judge demo

This is the primary demo contract.

The product is not a risk dashboard. It is an event-to-recovery control loop.

## Before the judge arrives

Run:

```powershell
git pull
python scripts/load_seed_data.py
python -m unittest discover -s tests -v
uvicorn dependency.api.main:app --reload --port 8000
```

Open:

`http://127.0.0.1:8000/dashboard`

Optional rehearsal:

```powershell
python scripts/rehearse_control_loop.py
```

The rehearsal uses the same deterministic services as the UI. It does not send an external Slack message.

## Truth contract

Say this before any private business number appears:

> The earthquake and the supplier network are public facts. The BOM, customer commitments, margins, capacity and recovery relationships are simulated private ERP data because Adidas does not publish them. We label those separately everywhere.

Never say that USGS proves a factory was damaged.

The correct statement is:

> The event creates potential public-network exposure. Confirmed operational state comes from private evidence.

## 0:00–0:25 — show the scale and the signal

Screen: dashboard, Cianjur event selected.

Presenter:

> This is Dependency. It watches external signals and maps them onto the actual dependency graph of a company. Here we loaded 770 geocoded public Adidas supplier facilities and 836 official supplier-list relationships. This is the real USGS Cianjur earthquake from 21 November 2022, replayed against the current network.

Point to the map.

Expected deterministic value:

- 20 public supplier facilities are within 150 km.
- The label is `POTENTIALLY_EXPOSED`.
- No shutdown claim is made from distance alone.

Presenter:

> Twenty public supplier facilities are inside the investigation radius. That is not twenty damaged factories. It is twenty nodes that need investigation.

## 0:25–0:55 — show the hidden dependency graph

Click product `JI2993`.

Presenter:

> Now the system crosses from public data into the private digital twin. It follows only explicit dependency edges: supplier to material, material to assembly, assembly to SKU, SKU to customer commitment.

Show the graph.

The event reaches two products through the current demo graph:

- JI2993 Adizero SL2.
- JQ6656 Ultraboost 5.

Connected commercial exposure across those products:

- 16,000 commitment units.
- EUR 2,405,000 revenue.
- EUR 971,100 gross margin.

These are connected values, not guaranteed losses.

Then show the rejected recovery option.

Presenter:

> The obvious backup is not actually independent. It shares three explicit upstream material sources with the primary assembly path, so deterministic code rejects it.

Expected hidden shared sources:

- ADI26-0751.
- ADI26-0754.
- ADI26-0758.

Expected decision:

`REJECT_CORRELATED_BACKUP`

## 0:55–1:25 — show recovery before fresh supplier evidence

Show the JI2993 recovery panel.

Ground truth:

- demand: 9,500 units.
- normal usable finished inventory: 1,600 units.
- independent backup nominal available capacity: 7,500 units.
- total conservative supply: 9,100 units.
- conservative shortage: 400 units.
- backup capacity evidence age: 72 hours.
- status: `PROVISIONAL_SHORTAGE`.

Presenter:

> The system finds an independent backup, but the capacity evidence is stale. It refuses to convert that stale number into a promise. With protected safety stock untouched, we are 400 units short.

Show the supplier evidence request.

Presenter:

> So the Recovery Planner does work. It opens a durable supplier confirmation request instead of asking a human to manually chase the supplier.

If Slack is connected, dispatch the request.

Otherwise use the dashboard/API reply path for the rehearsal and say:

> This uses the same inbound parser and confirmation service as the Slack callback. External messaging is disabled in this rehearsal environment.

## 1:25–1:55 — supplier changes reality

Supplier reply:

> Capacity has declined to 5,500 pairs per week until 2026-11-04.

Important sequence:

1. reply arrives;
2. parser extracts 5,500 and date;
3. state does **not** change yet;
4. planner confirms the parsed operational fact;
5. supplier capacity updates from 9,500 to 5,500;
6. 2,000 units are already committed;
7. available backup capacity becomes 3,500;
8. operational state version changes from 1 to 2;
9. old plans become stale;
10. the event orchestrator replans.

Presenter:

> The supplier has just changed the world underneath the plan. Dependency versions operational state, invalidates the old plan and replans automatically.

Conservative result after the capacity shock:

- normal finished inventory: 1,600.
- backup available capacity: 3,500.
- total normal supply: 5,100.
- conservative shortage: 4,400.

Emergency safety-stock option:

- protected safety stock: 500.
- total emergency supply: 5,600.
- shortage after release: 3,900.
- human approval required.

## 1:55–2:30 — judge interaction: approve and execute

Show the pending safety-stock approval.

Presenter:

> The agent can propose the emergency action, but it cannot release protected stock itself. That action crosses our policy boundary.

Ask the judge:

> Approve the 500-unit safety-stock release?

Click **Approve**.

Then click **Execute approved action**.

Presenter:

> Approval and execution are separate. The execution adapter now changes the operational system, emits a business-state event and invalidates every dependent plan again.

Expected state version:

- before supplier confirmation: 1.
- after supplier confirmation: 2.
- after approved safety-stock execution: 3.

Final available supply:

- 2,100 finished units now usable.
- 3,500 backup units.
- 5,600 total.
- 3,900 units remain late.

## 2:30–2:48 — show business allocation

Show optimized customer allocation.

Policy is explicit customer priority first, then protected margin minus incremental recovery transport cost.

Expected allocation with 5,600 units:

- ORD-JI-EU: 4,000 protected, 0 late.
- ORD-JI-NA: 1,600 protected, 1,400 late.
- ORD-JI-GC: 0 protected, 2,500 late.

Expected protected economics:

- protected revenue: EUR 728,000.
- protected gross margin: EUR 300,000 before recovery transport cost.
- total late units: 3,900.

Presenter:

> We are not just calculating a risk score. We are deciding exactly which commitments get scarce supply and showing the financial consequence.

## 2:48–3:00 — show memory and close

Scroll to Operational Memory.

Presenter:

> Every event, piece of evidence, rejected plan, supplier confirmation, approval, execution and actual outcome becomes operational memory. A future incident can retrieve the lesson, but it is labelled hypothesis-only and current state must be checked again.

Closing sentence:

> Dependency turns messy external data into a versioned operational decision: what is exposed, what is actually broken, which customer promise is at risk, what recovery is feasible, who must confirm it, and what changes when reality moves.

## Judge interruption responses

### “So this is a dashboard?”

> No. The dashboard is the control surface. The product underneath ingests events, resolves exposure, traverses dependencies, requests missing evidence, runs deterministic feasibility and optimization, gates sensitive actions, executes approved changes and replans when state changes.

### “How do you know the factory is damaged?”

> We do not infer that from distance. Public proximity is labelled potential exposure. Operational unavailability is a separate private state that must be confirmed or explicitly simulated in replay mode.

### “Your data is fake.”

> The public event and public supplier network are real and sourced. Private BOM, customer, margin, capacity and route data cannot be public for a real enterprise, so those records are simulated and labelled `SIMULATED_PRIVATE`. A real customer would replace those tables with ERP/TMS/WMS integrations.

### “Why AI?”

> Deterministic code handles geometry, graph reachability, quantities, timing, constraints and optimization. Agents handle open-ended investigation: what evidence to gather, which dependency to inspect, which missing fact blocks a decision and which action to propose.

### “Why Aiven?”

> PostgreSQL/PostGIS is the operational system of record. Kafka carries state and event changes through the same idempotent topic contracts used by the local transactional-outbox worker. On Aiven, the database and event bus become managed infrastructure without changing product logic.

### “Why not SAP?”

> We are not replacing the ERP. We sit across ERP, supplier communication and external signals. The value is the cross-source dependency graph and event-to-action control loop that existing systems often leave fragmented across teams.
